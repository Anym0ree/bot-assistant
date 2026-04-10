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
    try:
        if not os.path.exists("reminder_settings.json"):
            return
        with open("reminder_settings.json", "r") as f:
            all_data = json.load(f)

        now_utc = datetime.utcnow()
        for user_id_str, settings in all_data.items():
            user_id = int(user_id_str)
            tz = await db.get_user_timezone(user_id)
            if tz == 0:
                tz = 3  # UTC+3 по умолчанию
            user_time = now_utc + timedelta(hours=tz)
            current_time = user_time.strftime("%H:%M")

            # Сон
            if settings.get("sleep", {}).get("enabled", False):
                if settings["sleep"].get("time") == current_time:
                    await bot.send_message(user_id, "🛌 Пора записать сон")
                    logging.info(f"Напомнили о сне {user_id} в {current_time}")

            # Чек-ины
            if settings.get("checkins", {}).get("enabled", False):
                if current_time in settings["checkins"].get("times", []):
                    await bot.send_message(user_id, "⚡️ Сделай чек-ин")
                    logging.info(f"Напомнили о чек-ине {user_id} в {current_time}")

            # Итог дня
            if settings.get("summary", {}).get("enabled", False):
                if settings["summary"].get("time") == current_time:
                    await bot.send_message(user_id, "📝 Не забудь подвести итог дня")
                    logging.info(f"Напомнили об итоге дня {user_id} в {current_time}")

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
