import asyncio
import logging
import os
from datetime import datetime, timedelta
import json

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import BOT_TOKEN, OPENAI_API_KEY
from database_pg import db
from keyboards import get_main_menu
from utils import set_bot_instance, safe_finish, delete_dialog_message
from reminder_utils import load_reminder_settings, get_default_reminders
import ai_advisor as ai_adv_module

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
set_bot_instance(bot)  # чтобы utils.bot был доступен
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Глобальный AI-советник
ai_advisor = ai_adv_module.AIAdvisor(api_key=OPENAI_API_KEY)
ai_adv_module.ai_advisor = ai_advisor  # делаем доступным глобально

scheduler = None

# ========== ЗАГРУЗКА ПЛАГИНОВ ==========
def load_plugins(dispatcher, plugins_dir="plugins"):
    import importlib
    if not os.path.isdir(plugins_dir):
        os.makedirs(plugins_dir, exist_ok=True)
        return
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"{plugins_dir}.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "register"):
                    module.register(dispatcher)
                    logging.info(f"✅ Плагин {filename} загружен")
                else:
                    logging.warning(f"⚠️ В {filename} нет функции register(dp)")
            except Exception as e:
                logging.error(f"❌ Ошибка загрузки плагина {filename}: {e}", exc_info=True)

# ========== ШЕДУЛЕР ==========
async def check_custom_reminders():
    """Проверка напоминаний (сон, чек-ины, итог дня)"""
    try:
        reminder_file = "reminder_settings.json"
        if not os.path.exists(reminder_file):
            logging.warning("Файл reminder_settings.json не найден")
            return
        
        with open(reminder_file, "r") as f:
            all_data = json.load(f)
        
        now_utc = datetime.utcnow()
        for user_id_str, settings_data in all_data.items():
            user_id = int(user_id_str)
            
            # Получаем часовой пояс пользователя
            tz = await db.get_user_timezone(user_id)
            if tz == 0:
                tz = 3  # по умолчанию Москва
                logging.warning(f"У пользователя {user_id} часовой пояс 0, ставим UTC+3")
            
            user_time = now_utc + timedelta(hours=tz)
            current_time = user_time.strftime("%H:%M")
            today_str = user_time.strftime("%Y-%m-%d")
            
            # 1. НАПОМИНАНИЕ О СНЕ
            if settings_data.get("sleep", {}).get("enabled", False):
                sleep_time = settings_data["sleep"].get("time", "09:00")
                if sleep_time == current_time:
                    # Проверяем, записан ли уже сон сегодня
                    has_sleep = await db.has_sleep_today(user_id)
                    if not has_sleep:
                        await bot.send_message(user_id, "🛌 Пора записать сон")
                        logging.info(f"Напоминание о сне отправлено {user_id} в {current_time}")
                    else:
                        logging.info(f"У {user_id} сон уже записан, напоминание не отправлено")
            
            # 2. НАПОМИНАНИЕ О ЧЕК-ИНАХ
            if settings_data.get("checkins", {}).get("enabled", False):
                check_times = settings_data["checkins"].get("times", [])
                if current_time in check_times:
                    # Проверяем, был ли уже чек-ин сегодня
                    checkins = await db._load_json(user_id, "checkins.json")
                    has_today_checkin = any(c.get("date") == today_str for c in checkins)
                    if not has_today_checkin:
                        await bot.send_message(user_id, "⚡️ Сделай чек-ин")
                        logging.info(f"Напоминание о чек-ине отправлено {user_id} в {current_time}")
                    else:
                        logging.info(f"У {user_id} чек-ин уже есть, напоминание не отправлено")
            
            # 3. НАПОМИНАНИЕ ОБ ИТОГЕ ДНЯ
            if settings_data.get("summary", {}).get("enabled", False):
                summary_time = settings_data["summary"].get("time", "22:30")
                if summary_time == current_time:
                    target_date = await db.get_target_date_for_summary(user_id)
                    if target_date and not await db.has_day_summary_for_date(user_id, target_date):
                        await bot.send_message(user_id, "📝 Не забудь подвести итог дня")
                        logging.info(f"Напоминание об итоге дня отправлено {user_id} в {current_time}")
                    else:
                        logging.info(f"Итог дня уже есть или не нужно, напоминание не отправлено")
                        
    except Exception as e:
        logging.error(f"Ошибка в check_custom_reminders: {e}", exc_info=True)

async def check_reminders():
    """Проверка обычных напоминаний (созданных пользователем)"""
    try:
        due_reminders = await db.get_reminders_due_now()
        for user_id, reminder in due_reminders:
            try:
                await bot.send_message(user_id, f"⏰ НАПОМИНАНИЕ!\n\n{reminder['text']}")
                await db.mark_reminder_sent(user_id, reminder["id"])
                logging.info(f"Отправлено напоминание {reminder['id']} пользователю {user_id}")
            except Exception as e:
                logging.error(f"Ошибка отправки напоминания {reminder['id']}: {e}")
    except Exception as e:
        logging.error(f"Ошибка в check_reminders: {e}", exc_info=True)
        
async def check_reminders():
    due_reminders = await db.get_reminders_due_now()
    for user_id, reminder in due_reminders:
        try:
            await bot.send_message(user_id, f"⏰ НАПОМИНАНИЕ!\n\n{reminder['text']}")
            await db.mark_reminder_sent(user_id, reminder["id"])
        except Exception as e:
            logging.error(f"Ошибка отправки напоминания {reminder['id']}: {e}")

# ========== ЗАПУСК ==========
async def on_startup_polling(dp):
    await bot.delete_webhook()
    await db.init_pool()
    global scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(check_reminders, IntervalTrigger(minutes=1))
    scheduler.add_job(check_custom_reminders, IntervalTrigger(minutes=1))
    scheduler.start()
    logging.info("✅ Бот запущен в polling режиме!")

async def on_shutdown_polling(dp):
    if scheduler and scheduler.running:
        scheduler.shutdown()
    try:
        if hasattr(db, 'close_pool'):
            await db.close_pool()
        elif hasattr(db, 'close'):
            await db.close()
    except Exception as e:
        logging.error(f"Ошибка при закрытии БД: {e}")

if __name__ == "__main__":
    load_plugins(dp)
    executor.start_polling(dp, on_startup=on_startup_polling, on_shutdown=on_shutdown_polling, skip_updates=True)
