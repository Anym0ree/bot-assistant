import asyncio
import logging
import os
from datetime import datetime, timedelta
import json

from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from config import BOT_TOKEN, OPENAI_API_KEY
from database import db
from keyboards import get_main_menu
from utils import set_bot_instance, safe_finish, delete_dialog_message
from reminder_utils import load_reminder_settings, get_default_reminders
import ai_advisor as ai_adv_module
from plugins.planner import check_reminders

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
set_bot_instance(bot)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Глобальный AI-советник
ai_advisor = ai_adv_module.AIAdvisor(api_key=OPENAI_API_KEY)
ai_adv_module.ai_advisor = ai_advisor

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

# ========== ЕДИНАЯ СИСТЕМА НАПОМИНАНИЙ ==========
async def check_all_reminders():
    try:
        now_utc = datetime.utcnow()
        # 1. Обычные напоминания
        reminders_due = await db.get_reminders_due_now()
        for user_id, rem in reminders_due:
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT reminders_enabled, do_not_disturb_start, do_not_disturb_end FROM user_settings WHERE user_id = $1",
                    user_id
                )
            if row:
                rem_enabled = row['reminders_enabled']
                dnd_start = row['do_not_disturb_start']
                dnd_end = row['do_not_disturb_end']
            else:
                rem_enabled = 1
                dnd_start = dnd_end = None
            if not rem_enabled:
                continue
            tz = await db.get_user_timezone(user_id) or 3
            user_time = now_utc + timedelta(hours=tz)
            current_time = user_time.strftime("%H:%M")
            if dnd_start and dnd_end:
                if dnd_start <= dnd_end:
                    if dnd_start <= current_time <= dnd_end:
                        continue
                else:
                    if current_time >= dnd_start or current_time <= dnd_end:
                        continue
            await bot.send_message(user_id, f"⏰ НАПОМИНАНИЕ!\n\n{rem['text']}")
            await db.mark_reminder_sent(user_id, rem['id'])

        # 2. Периодические напоминания
        async with db.pool.acquire() as conn:
            users = await conn.fetch("SELECT DISTINCT user_id FROM users")
        for user in users:
            user_id = user['user_id']
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT reminders_enabled, do_not_disturb_start, do_not_disturb_end FROM user_settings WHERE user_id = $1",
                    user_id
                )
            if row:
                rem_enabled = row['reminders_enabled']
                dnd_start = row['do_not_disturb_start']
                dnd_end = row['do_not_disturb_end']
            else:
                rem_enabled = 1
                dnd_start = dnd_end = None
            if not rem_enabled:
                continue
            tz = await db.get_user_timezone(user_id) or 3
            user_time = now_utc + timedelta(hours=tz)
            current_time = user_time.strftime("%H:%M")
            if dnd_start and dnd_end:
                if dnd_start <= dnd_end:
                    if dnd_start <= current_time <= dnd_end:
                        continue
                else:
                    if current_time >= dnd_start or current_time <= dnd_end:
                        continue
            today_str = user_time.strftime("%Y-%m-%d")

            sleep_set = await db.get_reminder_setting(user_id, "sleep")
            if sleep_set["enabled"] and sleep_set["times"] and sleep_set["times"][0] == current_time:
                if not await db.has_sleep_today(user_id):
                    await bot.send_message(user_id, "🛌 Пора записать сон")
            check_set = await db.get_reminder_setting(user_id, "checkins")
            if check_set["enabled"] and current_time in check_set["times"]:
                checkins = await db._load_json(user_id, "checkins.json")
                if not any(c.get("date") == today_str for c in checkins):
                    await bot.send_message(user_id, "⚡️ Сделай чек-ин")
            summary_set = await db.get_reminder_setting(user_id, "summary")
            if summary_set["enabled"] and summary_set["times"] and summary_set["times"][0] == current_time:
                target_date = await db.get_target_date_for_summary(user_id)
                if target_date and not await db.has_day_summary_for_date(user_id, target_date):
                    await bot.send_message(user_id, "📝 Не забудь подвести итог дня")
            water_set = await db.get_reminder_setting(user_id, "water")
            if water_set["enabled"] and current_time in water_set["times"]:
                items = await db.get_today_food_and_drinks(user_id)
                if not any("вода" in d['text'].lower() for d in items if d['type'] == "🥤 Напитки"):
                    await bot.send_message(user_id, "💧 Не забывай пить воду!")
            meals_set = await db.get_reminder_setting(user_id, "meals")
            if meals_set["enabled"] and current_time in meals_set["times"]:
                meal_names = {"09:00": "завтрак", "13:00": "обед", "19:00": "ужин"}
                meal_name = meal_names.get(current_time, "приём пищи")
                items = await db.get_today_food_and_drinks(user_id)
                if not any(meal_name in f['text'].lower() for f in items if f['type'] == "🍽 Еда"):
                    await bot.send_message(user_id, f"🍽 Пора {meal_name}! Добавь запись о еде.")
    except Exception as e:
        logging.error(f"Ошибка в check_all_reminders: {e}", exc_info=True)
#===============================
async def remind_update_profile():
    """Раз в месяц напоминает пользователям обновить профиль"""
    try:
        now = datetime.utcnow()
        async with db.pool.acquire() as conn:
            users = await conn.fetch("SELECT DISTINCT user_id FROM users")
        for user in users:
            user_id = user['user_id']
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT created_at FROM users WHERE user_id = $1", user_id)
            if row and row['created_at']:
                last_update = row['created_at']
                if (now - last_update).days >= 30:
                    await bot.send_message(
                        user_id,
                        "📅 Напоминание: уже прошёл месяц. Обнови свои данные (возраст, рост, вес) в настройках (кнопка ⚙️ Настройки → ✏️ Редактировать профиль)."
                    )
    except Exception as e:
        logging.error(f"Ошибка в remind_update_profile: {e}")
# ========== ЗАПУСК ==========
async def on_startup_polling(dp):
    await bot.delete_webhook()
    await db.init_pool()
    global scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(check_reminders, IntervalTrigger(minutes=1))
    scheduler.add_job(check_all_reminders, IntervalTrigger(minutes=1))
    scheduler.add_job(check_routines, IntervalTrigger(minutes=1))
    scheduler.add_job(remind_update_profile, CronTrigger(day=1, hour=12, minute=0, timezone="UTC"))  # 1-го числа каждого месяца в 12:00 UTC
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
        logging.error(f"❌ Ошибка при закрытии БД: {e}")

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
        meal_type = "🍎 Перекус"
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
