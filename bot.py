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
from database import db
from keyboards import get_main_menu
from utils import set_bot_instance, safe_finish, delete_dialog_message
from reminder_utils import load_reminder_settings, get_default_reminders
import ai_advisor as ai_adv_module

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
    """Проверяет все напоминания (и обычные из БД, и кастомные из JSON)"""
    try:
        now_utc = datetime.utcnow()
        
        # 1. Обычные напоминания из БД (с remind_utc)
        async with db.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, user_id, text FROM reminders
                WHERE is_active = 1 AND remind_utc <= $1
            ''', now_utc)
            
            for row in rows:
                reminder_id, user_id, text = row
                try:
                    await bot.send_message(user_id, f"⏰ НАПОМИНАНИЕ!\n\n{text}")
                    await conn.execute("UPDATE reminders SET is_active = 0 WHERE id = $1", reminder_id)
                    logging.info(f"✅ Отправлено напоминание {reminder_id} пользователю {user_id}")
                except Exception as e:
                    logging.error(f"❌ Ошибка отправки {reminder_id}: {e}")
        
        # 2. Кастомные напоминания (сон, чек-ины, итог дня, вода, еда)
        if not os.path.exists("reminder_settings.json"):
            return
            
        with open("reminder_settings.json", "r") as f:
            all_data = json.load(f)
        
        for user_id_str, settings in all_data.items():
            user_id = int(user_id_str)
            tz = await db.get_user_timezone(user_id)
            if tz == 0:
                tz = 3
            user_time = now_utc + timedelta(hours=tz)
            current_time = user_time.strftime("%H:%M")
            today_str = user_time.strftime("%Y-%m-%d")
            
            # Сон
            if settings.get("sleep", {}).get("enabled", False):
                if settings["sleep"].get("time") == current_time:
                    if not await db.has_sleep_today(user_id):
                        await bot.send_message(user_id, "🛌 Пора записать сон")
                        logging.info(f"📢 Напоминание о сне {user_id} в {current_time}")
            
            # Чек-ины по расписанию
            if settings.get("checkins", {}).get("enabled", False):
                if current_time in settings["checkins"].get("times", []):
                    checkins = await db._load_json(user_id, "checkins.json")
                    has_today = any(c.get("date") == today_str for c in checkins)
                    if not has_today:
                        await bot.send_message(user_id, "⚡️ Сделай чек-ин")
                        logging.info(f"📢 Напоминание о чек-ине {user_id} в {current_time}")
            
            # Итог дня
            if settings.get("summary", {}).get("enabled", False):
                if settings["summary"].get("time") == current_time:
                    target_date = await db.get_target_date_for_summary(user_id)
                    if target_date and not await db.has_day_summary_for_date(user_id, target_date):
                        await bot.send_message(user_id, "📝 Не забудь подвести итог дня")
                        logging.info(f"📢 Напоминание об итоге дня {user_id} в {current_time}")
            
            # Вода
            water_settings = settings.get("water", {})
            if water_settings.get("enabled", False):
                if current_time in water_settings.get("times", []):
                    items = await db.get_today_food_and_drinks(user_id)
                    water_drunk = any("вода" in d['text'].lower() for d in items if d['type'] == "🥤 Напитки")
                    if not water_drunk:
                        await bot.send_message(user_id, "💧 Не забывай пить воду!")
                        logging.info(f"📢 Напоминание о воде {user_id} в {current_time}")
            
            # Еда (завтрак, обед, ужин)
            meals_settings = settings.get("meals", {})
            if meals_settings.get("enabled", False):
                meal_times = meals_settings.get("times", [])
                if current_time in meal_times:
                    meal_names = {"09:00": "завтрак", "13:00": "обед", "19:00": "ужин"}
                    meal_name = meal_names.get(current_time, "приём пищи")
                    items = await db.get_today_food_and_drinks(user_id)
                    has_meal = any(meal_name in f['text'].lower() for f in items if f['type'] == "🍽 Еда")
                    if not has_meal:
                        await bot.send_message(user_id, f"🍽 Пора {meal_name}! Добавь запись о еде.")
                        logging.info(f"📢 Напоминание о еде {user_id} в {current_time}")
            
            # Давно не было чек-ина (>6 часов)
            checkins = await db._load_json(user_id, "checkins.json")
            if checkins:
                last_checkin = checkins[-1]
                try:
                    last_time = datetime.strptime(f"{last_checkin['date']} {last_checkin['time']}", "%Y-%m-%d %H:%M")
                    last_time = last_time - timedelta(hours=tz)
                    hours_since = (user_time - last_time).total_seconds() / 3600
                    if hours_since > 6 and not any(c.get("date") == today_str for c in checkins):
                        await bot.send_message(user_id, "⚠️ Давно не делал чек-ин. Как твоё самочувствие?")
                        logging.info(f"📢 Напоминание о давнем чек-ине {user_id}")
                except:
                    pass
                    
    except Exception as e:
        logging.error(f"❌ Ошибка в check_all_reminders: {e}", exc_info=True)

# ========== ЗАПУСК ==========
async def on_startup_polling(dp):
    await bot.delete_webhook()
    await db.init_pool()
    global scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(check_all_reminders, IntervalTrigger(minutes=1))
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
