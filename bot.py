import asyncio
import logging
import os
from datetime import datetime, timedelta
import json

from aiogram import Bot, Dispatcher, types
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
                tz = 3
            user_time = now_utc + timedelta(hours=tz)
            current_time = user_time.strftime("%H:%M")
            today_str = user_time.strftime("%Y-%m-%d")

            # ----- СТАРЫЕ НАПОМИНАНИЯ (сон, чек-ин по расписанию, итог дня) -----
            if settings.get("sleep", {}).get("enabled", False):
                if settings["sleep"].get("time") == current_time:
                    await bot.send_message(user_id, "🛌 Пора записать сон")

            if settings.get("checkins", {}).get("enabled", False):
                if current_time in settings["checkins"].get("times", []):
                    # Проверяем, был ли чек-ин сегодня
                    checkins = await db._load_json(user_id, "checkins.json")
                    has_today = any(c.get("date") == today_str for c in checkins)
                    if not has_today:
                        await bot.send_message(user_id, "⚡️ Сделай чек-ин")

            if settings.get("summary", {}).get("enabled", False):
                if settings["summary"].get("time") == current_time:
                    target_date = await db.get_target_date_for_summary(user_id)
                    if target_date and not await db.has_day_summary_for_date(user_id, target_date):
                        await bot.send_message(user_id, "📝 Не забудь подвести итог дня")

            # ----- НОВЫЕ УМНЫЕ НАПОМИНАНИЯ -----
            # 1. Вода (каждые 4 часа)
            water_times = ["10:00", "14:00", "18:00", "22:00"]
            if current_time in water_times:
                items = await db.get_today_food_and_drinks(user_id)
                water_drunk = any("вода" in d['text'].lower() for d in items if d['type'] == "🥤 Напитки")
                if not water_drunk:
                    await bot.send_message(user_id, "💧 Не забывай пить воду! Напоминаю каждые 4 часа.")

            # 2. Еда (завтрак, обед, ужин)
            meal_times = {"09:00": "завтрак", "13:00": "обед", "19:00": "ужин"}
            if current_time in meal_times:
                items = await db.get_today_food_and_drinks(user_id)
                meal = meal_times[current_time]
                has_meal = any(meal in f['text'].lower() for f in items if f['type'] == "🍽 Еда")
                if not has_meal:
                    await bot.send_message(user_id, f"🍽 Пора {meal}! Добавь запись о еде.")

            # 3. Давно не было чек-ина (если прошло >6 часов, и сегодня не было)
            checkins = await db._load_json(user_id, "checkins.json")
            if checkins:
                last_checkin = checkins[-1]
                last_time = datetime.strptime(f"{last_checkin['date']} {last_checkin['time']}", "%Y-%m-%d %H:%M")
                # Приводим к UTC пользователя
                last_time = last_time - timedelta(hours=tz)
                hours_since = (user_time - last_time).total_seconds() / 3600
                if hours_since > 6 and not any(c.get("date") == today_str for c in checkins):
                    await bot.send_message(user_id, "⚠️ Давно не делал чек-ин. Как твоё самочувствие?")

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
# ========== ИНЛАЙН-РЕЖИМ (быстрое добавление еды/напитков) ==========
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

@dp.inline_handler()
async def inline_add_food_drink(inline_query: types.InlineQuery):
    query = inline_query.query.strip()
    if not query:
        return

    parts = query.split(maxsplit=2)
    if len(parts) < 2:
        return

    action = parts[0].lower()
    text = parts[1]

    user_id = inline_query.from_user.id

    if action == "еда":
        meal_type = "🍎 Перекус"  # можно улучшить: определять по времени
        await db.add_food(user_id, meal_type, text)
        result_text = f"✅ Добавлено: {meal_type} — {text}"
    elif action == "напиток":
        amount = parts[2] if len(parts) > 2 else "1 порция"
        await db.add_drink(user_id, text, amount)
        result_text = f"✅ Добавлено: {text} — {amount}"
    else:
        return

    article = InlineQueryResultArticle(
        id="1",
        title=f"Добавить {action}",
        description=text,
        input_message_content=InputTextMessageContent(result_text)
    )
    await inline_query.answer([article], cache_time=1)
    
if __name__ == "__main__":
    load_plugins(dp)
    executor.start_polling(dp, on_startup=on_startup_polling, on_shutdown=on_shutdown_polling, skip_updates=True)
