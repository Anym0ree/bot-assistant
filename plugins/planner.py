import logging, re, asyncio
from datetime import datetime, timedelta, time, date
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_plans_menu, get_main_menu
from reminder_utils import load_reminder_settings
import ai_advisor

logger = logging.getLogger(__name__)

undo_data = {}

class AddTaskStates(StatesGroup):
    title = State()
    datetime = State()

class AddRoutineStates(StatesGroup):
    title = State()
    time = State()
    period = State()

class QuickSleepStates(StatesGroup):
    same_as_last = State()
    bed_time = State()
    wake_time = State()

class QuickCheckinStates(StatesGroup):
    energy = State()
    stress = State()

class DailyQuestionStates(StatesGroup):
    answer = State()

# ------------------------------------------------------------
# 📋 НОВЫЙ ДАШБОРД «СЕГОДНЯ»
# ------------------------------------------------------------
async def today_view(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id) or 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    today_str = now_local.strftime("%Y-%m-%d")
    today_date = now_local.date()

    # Статус дня
    status_emoji = "🌤️"
    status_text = "Доброе утро! Пора начинать."
    try:
        checkin = await db.get_last_checkin(user_id, today_str)
        if checkin:
            energy = checkin['energy']
            stress = checkin['stress']
            if energy >= 7 and stress <= 3:
                status_emoji = "😊"
                status_text = "Отличный день для побед!"
            elif energy >= 4 and stress <= 6:
                status_emoji = "😐"
                status_text = "Нормальный день, всё под контролем."
            else:
                status_emoji = "😞"
                status_text = "День тяжёлый, но ты справляешься."
    except:
        pass

    text = f"{status_emoji} *{status_text}*\n\n"

    # Погода
    from plugins.weather import get_weather_by_city, get_weather_by_coords
    async with db.pool.acquire() as conn:
        loc = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)
    if loc and (loc['city'] or (loc['lat'] and loc['lon'])):
        try:
            if loc['city']:
                wdata = await get_weather_by_city(loc['city'])
            else:
                wdata = await get_weather_by_coords(loc['lat'], loc['lon'])
            if wdata:
                temp = wdata['main']['temp']
                desc = wdata['weather'][0]['description']
                text += f"🌤️ {temp:.0f}°C, {desc}\n"
        except:
            text += "🌤️ Погода недоступна\n"
    else:
        text += "🌤️ *Погода:* укажи город в настройках\n"

    # Быстрые действия
    quick_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
    quick_kb.add(KeyboardButton("🛌 Сон"), KeyboardButton("⚡ Чекин"), KeyboardButton("🍽 Еда"), KeyboardButton("📝 Итог"))
    await message.answer(text, reply_markup=quick_kb, parse_mode="Markdown")

    # Задачи и рутины
    tasks = await db.get_upcoming_tasks(user_id)
    routines = await db.get_recurring_tasks_by_user(user_id)
    active_items = []
    for t in tasks:
        if t['is_active']:
            active_items.append({"title": t['title'], "id": t['id'], "type": "task"})
    for r in routines:
        if await should_run_today(r, today_date):
            done = await db.was_routine_completed_today(r['id'], today_str)
            if not done:
                active_items.append({"title": r['title'], "id": r['id'], "type": "routine"})

    if active_items:
        items_text = "\n📌 *Задачи и рутины:*\n"
        items_kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for item in active_items:
            items_text += f"  • {item['title']}\n"
            items_kb.add(KeyboardButton(f"✅ {item['title'][:30]}"))
        items_text += "\nДля завершения нажми на кнопку ниже."
        await message.answer(items_text, reply_markup=items_kb, parse_mode="Markdown")
    else:
        await message.answer("📌 *На сегодня ничего не запланировано.*", parse_mode="Markdown")

# ------------------------------------------------------------
# ПОДТВЕРЖДЕНИЕ И ОТМЕНА
# ------------------------------------------------------------
async def complete_item_start(message: types.Message, state: FSMContext):
    if not message.text.startswith("✅ "):
        return
    title = message.text[2:].strip()
    user_id = message.from_user.id
    task = await db.find_task_by_title(user_id, title)
    if task:
        await state.update_data(completing_item={"id": task['id'], "type": "task", "title": title})
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("✅ Да, выполнено"), KeyboardButton("↩️ Отмена"))
        await message.answer(f"«{title}» — выполнено?", reply_markup=kb)
        return
    routine = await db.find_routine_by_title(user_id, title)
    if routine:
        await state.update_data(completing_item={"id": routine['id'], "type": "routine", "title": title})
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("✅ Да, выполнено"), KeyboardButton("↩️ Отмена"))
        await message.answer(f"«{title}» — выполнено?", reply_markup=kb)
        return
    await message.answer("❌ Не найдено.")

async def complete_item_confirm(message: types.Message, state: FSMContext):
    if message.text != "✅ Да, выполнено":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return
    data = await state.get_data()
    item = data.get("completing_item")
    if not item:
        await state.finish()
        return
    user_id = message.from_user.id
    if item['type'] == "task":
        await db.complete_task(item['id'], user_id, completed=True)
        undo_data[user_id] = {"action": "complete_task", "id": item['id'], "time": datetime.utcnow()}
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("↩️ Отменить"))
        msg = await message.answer("✅ Дело выполнено! Можно отменить.", reply_markup=kb)
        asyncio.create_task(delete_message_after(msg, 10))
    else:
        await db.complete_routine(item['id'], user_id)
        undo_data[user_id] = {"action": "complete_routine", "id": item['id'], "time": datetime.utcnow()}
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("↩️ Отменить"))
        msg = await message.answer("✅ Рутина выполнена! Можно отменить.", reply_markup=kb)
        asyncio.create_task(delete_message_after(msg, 10))
    await state.finish()

async def delete_message_after(message: types.Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

async def undo_last_action(message: types.Message):
    user_id = message.from_user.id
    if user_id not in undo_data:
        await message.answer("Нечего отменять.")
        return
    info = undo_data[user_id]
    if (datetime.utcnow() - info['time']).seconds > 10:
        await message.answer("Слишком поздно для отмены.")
        del undo_data[user_id]
        return
    if info['action'] == "complete_task":
        await db.undo_complete_task(info['id'], user_id)
        await message.answer("↩️ Дело возвращено.")
    elif info['action'] == "complete_routine":
        await db.undo_complete_routine(info['id'], user_id)
        await message.answer("↩️ Рутина возвращена.")
    del undo_data[user_id]
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ------------------------------------------------------------
# ОСТАЛЬНЫЕ ФУНКЦИИ (быстрые действия, дела, рутины, уведомления, утро, вопрос дня)
# ------------------------------------------------------------
async def quick_sleep_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        last = await conn.fetchrow("SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = $1 ORDER BY id DESC LIMIT 1", user_id)
    if last:
        await state.update_data(last_bed=last['bed_time'], last_wake=last['wake_time'], last_quality=last['quality'])
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("✅ Да, так же", "✏️ Изменить", "⬅️ Назад")
        await message.answer(f"Вчера ты лёг в {last['bed_time']}, встал в {last['wake_time']}.\nСегодня так же?", reply_markup=kb)
        await QuickSleepStates.same_as_last.set()
    else:
        await ask_bed_time(message, state)

async def quick_sleep_same(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    if message.text == "✅ Да, так же":
        data = await state.get_data()
        await db.add_sleep(message.from_user.id, data['last_bed'], data['last_wake'], data.get('last_quality',6), False)
        await state.finish()
        await message.answer("✅ Сон записан!", reply_markup=get_main_menu())
    else:
        await ask_bed_time(message, state)

async def ask_bed_time(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in ["22:00","23:00","00:00","01:00","02:00"]: kb.add(KeyboardButton(t))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("Во сколько лёг?", reply_markup=kb)
    await QuickSleepStates.bed_time.set()

async def quick_sleep_bed(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    await state.update_data(bed_time=message.text)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in ["06:00","07:00","08:00","09:00","10:00"]: kb.add(KeyboardButton(t))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("Во сколько встал?", reply_markup=kb)
    await QuickSleepStates.wake_time.set()

async def quick_sleep_wake(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    data = await state.get_data()
    await db.add_sleep(message.from_user.id, data['bed_time'], message.text, 6, False)
    await state.finish()
    await message.answer("✅ Сон записан!", reply_markup=get_main_menu())

async def quick_checkin_start(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(*[KeyboardButton(str(i)) for i in range(1,6)])
    kb.row(*[KeyboardButton(str(i)) for i in range(6,11)])
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("Энергия (1-10):", reply_markup=kb)
    await QuickCheckinStates.energy.set()

async def quick_checkin_energy(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    if message.text.isdigit() and 1 <= int(message.text) <= 10:
        await state.update_data(energy=int(message.text))
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(*[KeyboardButton(str(i)) for i in range(1,6)])
        kb.row(*[KeyboardButton(str(i)) for i in range(6,11)])
        kb.add(KeyboardButton("⬅️ Назад"))
        await message.answer("Стресс (1-10):", reply_markup=kb)
        await QuickCheckinStates.stress.set()

async def quick_checkin_stress(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    if message.text.isdigit() and 1 <= int(message.text) <= 10:
        data = await state.get_data()
        await db.add_checkin(message.from_user.id, "manual", data['energy'], int(message.text), [])
        await state.finish()
        await message.answer("✅ Чекин записан!", reply_markup=get_main_menu())

async def add_task_start(message: types.Message, state: FSMContext):
    await message.answer("Что нужно сделать?")
    await AddTaskStates.title.set()

async def add_task_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Сегодня 09:00", "Сегодня 12:00", "Сегодня 18:00")
    kb.add("Завтра 09:00", "Завтра 12:00", "Завтра 18:00")
    kb.add("📅 Своя дата", "⬅️ Назад")
    await message.answer("Когда?", reply_markup=kb)
    await AddTaskStates.datetime.set()

async def add_task_datetime(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    now = datetime.now()
    preset_map = {
        "Сегодня 09:00": (now.date(), "09:00"),
        "Сегодня 12:00": (now.date(), "12:00"),
        "Сегодня 18:00": (now.date(), "18:00"),
        "Завтра 09:00": ((now+timedelta(days=1)).date(), "09:00"),
        "Завтра 12:00": ((now+timedelta(days=1)).date(), "12:00"),
        "Завтра 18:00": ((now+timedelta(days=1)).date(), "18:00"),
    }
    if message.text == "📅 Своя дата":
        await message.answer("Формат: ГГГГ-ММ-ДД ЧЧ:ММ")
        return
    if message.text in preset_map:
        target_date, target_time = preset_map[message.text]
    else:
        try:
            dt = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
            target_date, target_time = dt.date(), dt.strftime("%H:%M")
        except:
            await message.answer("Неверный формат."); return
    data = await state.get_data()
    user_id = message.from_user.id
    target_dt = datetime.strptime(f"{target_date} {target_time}", "%Y-%m-%d %H:%M")
    next_due = target_dt - timedelta(minutes=30)
    task_id = await db.add_task(user_id, data['title'], 'once', start_date=target_date, start_time=target_time, remind_before_minutes=30, next_due=next_due)
    await state.finish()
    if task_id:
        await message.answer(f"✅ «{data['title']}» добавлено на {target_date} в {target_time}")
    await plans_menu(message, state)

async def my_tasks(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id) or 3
    today_date = (datetime.utcnow() + timedelta(hours=tz)).date()
    async with db.pool.acquire() as conn:
        tasks = await conn.fetch("""
            SELECT id, title, start_date, start_time, is_active,
                   EXISTS(SELECT 1 FROM task_logs WHERE task_id = tasks.id AND completed = TRUE) as done
            FROM tasks WHERE user_id = $1 AND task_type = 'once' AND start_date >= $2
            ORDER BY start_date, start_time LIMIT 15
        """, user_id, today_date)
    if not tasks:
        await message.answer("Нет дел."); await plans_menu(message, state); return
    text = "🗓️ *Мои дела:*\n\n"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in tasks:
        icon = "✅" if t['done'] else "⬜"
        line = f"{icon} {t['title']} — {t['start_date']} {t['start_time']}"
        if t['done']: line = f"~{line}~"
        text += line + "\n"
        if not t['done'] and t['is_active']:
            kb.add(KeyboardButton(f"✅ {t['title'][:20]}"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

async def add_routine_start(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏃 Пробежка","🧘 Медитация","📚 Чтение","💪 Тренировка","✍️ Дневник","➕ Своя","⬅️ Назад")
    await message.answer("Выбери или напиши своё:", reply_markup=kb)
    await AddRoutineStates.title.set()

async def add_routine_title(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    title = message.text if message.text != "➕ Своя" else None
    if not title: await message.answer("Введи название:"); return
    await state.update_data(title=title)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🌅 Утром (07:00)","☀️ Днём (12:00)","🌆 Вечером (19:00)","🌙 Ночью (22:00)","🕐 Своё время","⬅️ Назад")
    await message.answer("Во сколько?", reply_markup=kb)
    await AddRoutineStates.time.set()

async def add_routine_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    time_map = {"🌅 Утром (07:00)":"07:00","☀️ Днём (12:00)":"12:00","🌆 Вечером (19:00)":"19:00","🌙 Ночью (22:00)":"22:00"}
    if message.text in time_map: await state.update_data(target_time=time_map[message.text])
    elif message.text == "🕐 Своё время": await message.answer("Введи время (ЧЧ:ММ):"); return
    elif re.match(r"^\d{2}:\d{2}$", message.text): await state.update_data(target_time=message.text)
    else: await message.answer("Неверный формат."); return

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Каждый день","По будням","По выходным","⬅️ Назад")
    await message.answer("Как часто?", reply_markup=kb)
    await AddRoutineStates.period.set()

async def add_routine_period(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    period_map = {"Каждый день":"daily","По будням":"weekdays","По выходным":"weekends"}
    if message.text not in period_map: await message.answer("Выбери из кнопок."); return
    data = await state.get_data()
    user_id = message.from_user.id
    await db.add_task(user_id, data['title'], 'recurring', recurrence_type=period_map[message.text], start_time=data['target_time'], remind_before_minutes=15)
    await state.finish()
    await message.answer(f"✅ Рутина «{data['title']}» добавлена на {data['target_time']}!")
    await plans_menu(message, state)

async def my_routines(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    routines = await db.get_recurring_tasks_by_user(user_id)
    if not routines: await message.answer("Нет активных рутин.")
    else:
        text = "📋 *Мои рутины:*\n"
        for r in routines: text += f"• {r['title']} — {r['start_time']}\n"
        await message.answer(text, parse_mode="Markdown")
    await plans_menu(message, state)

async def check_reminders():
    from bot import bot
    now_utc = datetime.utcnow()
    tasks = await db.get_tasks_due_now(now_utc)
    for task in tasks:
        user_id = task['user_id']
        if not task.get('is_active'): continue
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton(f"✅ Выполнить #{task['id']}"))
        kb.add(KeyboardButton(f"⏰ Отложить #{task['id']}"))
        kb.add(KeyboardButton(f"❌ Отменить #{task['id']}"))
        try:
            await bot.send_message(user_id, f"⏰ *{task['title']}*\n🕒 {task['start_date']} в {task['start_time']}", reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка отправки напоминания: {e}")

async def check_all_reminders():
    from bot import bot
    try:
        now_utc = datetime.utcnow()
        async with db.pool.acquire() as conn:
            users = await conn.fetch("SELECT DISTINCT user_id FROM users")
        for user in users:
            user_id = user['user_id']
            tz = await db.get_user_timezone(user_id) or 3
            user_time = now_utc + timedelta(hours=tz)
            current_time = user_time.strftime("%H:%M")
            today_str = user_time.strftime("%Y-%m-%d")
            today_date = user_time.date()

            sleep_set = await db.get_reminder_setting(user_id, "sleep")
            if sleep_set["enabled"] and sleep_set["times"] and sleep_set["times"][0] == current_time:
                if not await db.has_sleep_today(user_id):
                    kb = ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(KeyboardButton("✅ Пройти сон"), KeyboardButton("⏰ Напомнить позже"))
                    await bot.send_message(user_id, "🛌 Пора записать сон", reply_markup=kb)

            check_set = await db.get_reminder_setting(user_id, "checkins")
            if check_set["enabled"] and current_time in check_set["times"]:
                checkins = await db._load_json(user_id, "checkins.json")
                if not any(c.get("date") == today_str for c in checkins):
                    kb = ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(KeyboardButton("✅ Пройти чекин"), KeyboardButton("⏰ Напомнить позже"))
                    await bot.send_message(user_id, "⚡️ Время для чек-ина", reply_markup=kb)

            summary_set = await db.get_reminder_setting(user_id, "summary")
            if summary_set["enabled"] and summary_set["times"] and summary_set["times"][0] == current_time:
                target_date = await db.get_target_date_for_summary(user_id)
                if target_date and not await db.has_day_summary_for_date(user_id, target_date):
                    kb = ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(KeyboardButton("✅ Пройти итог"), KeyboardButton("⏰ Напомнить позже"))
                    await bot.send_message(user_id, "📝 Подведи итог дня", reply_markup=kb)

            water_set = await db.get_reminder_setting(user_id, "water")
            if water_set["enabled"] and current_time in water_set["times"]:
                await bot.send_message(user_id, "💧 Не забывай пить воду!")

            meals_set = await db.get_reminder_setting(user_id, "meals")
            if meals_set["enabled"] and current_time in meals_set["times"]:
                await bot.send_message(user_id, "🍽 Пора поесть!")

            routines = await db.get_recurring_tasks_by_user(user_id)
            for r in routines:
                if await should_run_today(r, today_date):
                    remind_minutes = r.get('remind_before_minutes', 15) or 15
                    t = r['start_time']
                    if isinstance(t, str):
                        start_hour, start_minute = map(int, t.split(':'))
                    else:
                        start_hour, start_minute = t.hour, t.minute
                    start_dt = datetime.combine(today_date, time(start_hour, start_minute))
                    remind_dt = start_dt - timedelta(minutes=remind_minutes)
                    if remind_dt.strftime("%H:%M") == current_time:
                        async with db.pool.acquire() as conn:
                            done = await conn.fetchval("SELECT 1 FROM task_logs WHERE task_id = $1 AND due_date = $2 AND completed = TRUE", r['id'], today_date)
                        if not done:
                            kb = ReplyKeyboardMarkup(resize_keyboard=True)
                            kb.add(KeyboardButton(f"✅ Выполнена #{r['id']}"))
                            kb.add(KeyboardButton(f"⏰ Позже #{r['id']}"))
                            kb.add(KeyboardButton(f"❌ Пропустить #{r['id']}"))
                            await bot.send_message(user_id, f"🔄 *{r['title']}*\n🕒 {t if isinstance(t,str) else t.strftime('%H:%M')}", reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка в check_all_reminders: {e}", exc_info=True)

async def morning_greeting():
    from bot import bot
    try:
        async with db.pool.acquire() as conn:
            users = await conn.fetch("SELECT DISTINCT user_id FROM users")
        for user in users:
            user_id = user['user_id']
            tz = await db.get_user_timezone(user_id) or 3
            now_local = datetime.utcnow() + timedelta(hours=tz)
            if now_local.hour != 8: continue
            greeting = f"☀️ Доброе утро"
            from plugins.weather import get_weather_by_city, get_weather_by_coords
            async with db.pool.acquire() as conn:
                loc = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)
            weather_text = ""
            if loc and (loc['city'] or (loc['lat'] and loc['lon'])):
                try:
                    if loc['city']: wdata = await get_weather_by_city(loc['city'])
                    else: wdata = await get_weather_by_coords(loc['lat'], loc['lon'])
                    if wdata: weather_text = f"🌤️ {wdata['main']['temp']:.0f}°C, {wdata['weather'][0]['description']}"
                except: pass
            tasks = await db.get_upcoming_tasks(user_id)
            plans = "\n".join([f"  • {t['title']} в {t['start_time']}" for t in tasks[:3]]) if tasks else "  ничего не запланировано"
            advice = ""
            if ai_advisor.ai_advisor:
                try:
                    ctx = f"Погода: {weather_text}. Планы: {plans}"
                    advice = await ai_advisor.ai_advisor.get_advice(user_id, f"Дай короткое утреннее пожелание и совет на день, исходя из погоды и планов: {ctx}", history=None)
                    advice = f"💡 *Совет:* {advice[:200]}"
                except: pass
            msg = f"{greeting}!\n\n{weather_text}\n\n📌 *Сегодня:*\n{plans}\n\n{advice}\n\nХорошего дня! ❤️"
            await bot.send_message(user_id, msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"morning_greeting: {e}")

async def daily_question():
    from bot import bot
    try:
        async with db.pool.acquire() as conn:
            users = await conn.fetch("SELECT DISTINCT user_id FROM users")
        for user in users:
            user_id = user['user_id']
            tz = await db.get_user_timezone(user_id) or 3
            now_local = datetime.utcnow() + timedelta(hours=tz)
            if now_local.hour != 10: continue
            question = "Что сегодня принесло тебе радость?"
            if ai_advisor.ai_advisor:
                try:
                    question = await ai_advisor.ai_advisor.get_advice(user_id, "Придумай один глубокий, но простой вопрос для дневника, который поможет пользователю лучше понять себя. Только вопрос, без пояснений.", history=None)
                except: pass
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(KeyboardButton("📝 Ответить"), KeyboardButton("❌ Пропустить"))
            await bot.send_message(user_id, f"☕️ *Вопрос дня:*\n\n{question}", reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"daily_question: {e}")

async def answer_daily_question_start(message: types.Message, state: FSMContext):
    await message.answer("Напиши свой ответ:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await DailyQuestionStates.answer.set()

async def answer_daily_question_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await message.answer("Главное меню", reply_markup=get_main_menu()); return
    user_id = message.from_user.id
    text = f"#вопросдня\n{message.text}"
    await db.add_note(user_id, text)
    await state.finish()
    await message.answer("✅ Ответ сохранён в заметках!", reply_markup=get_main_menu())

async def skip_daily_question(message: types.Message):
    await message.answer("☕️ Хорошо, в следующий раз!", reply_markup=get_main_menu())

async def should_run_today(routine, today_date):
    rt = routine['recurrence_type']
    if rt == 'daily': return True
    if rt == 'weekdays': return today_date.weekday() < 5
    if rt == 'weekends': return today_date.weekday() >= 5
    return False

async def plans_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📅 Планы", reply_markup=get_plans_menu())

# ------------------------------------------------------------
# РЕГИСТРАЦИЯ
# ------------------------------------------------------------
def register(dp: Dispatcher):
    dp.register_message_handler(today_view, text="📋 Сегодня", state="*")
    dp.register_message_handler(plans_menu, text="📅 Планы", state="*")
    dp.register_message_handler(quick_sleep_start, text="✅ Записать сон", state="*")
    dp.register_message_handler(quick_checkin_start, text="⚡ Быстрый чекин", state="*")
    dp.register_message_handler(add_task_start, text="➕ Добавить дело", state="*")
    dp.register_message_handler(add_task_start, text="➕ Дело", state="*")
    dp.register_message_handler(my_tasks, text="🗓️ Мои дела", state="*")
    dp.register_message_handler(add_routine_start, text="🔄 Добавить рутину", state="*")
    dp.register_message_handler(add_routine_start, text="🔄 Рутина", state="*")
    dp.register_message_handler(my_routines, text="📋 Мои рутины", state="*")

    dp.register_message_handler(quick_sleep_same, state=QuickSleepStates.same_as_last)
    dp.register_message_handler(quick_sleep_bed, state=QuickSleepStates.bed_time)
    dp.register_message_handler(quick_sleep_wake, state=QuickSleepStates.wake_time)
    dp.register_message_handler(quick_checkin_energy, state=QuickCheckinStates.energy)
    dp.register_message_handler(quick_checkin_stress, state=QuickCheckinStates.stress)
    dp.register_message_handler(add_task_title, state=AddTaskStates.title)
    dp.register_message_handler(add_task_datetime, state=AddTaskStates.datetime)
    dp.register_message_handler(add_routine_title, state=AddRoutineStates.title)
    dp.register_message_handler(add_routine_time, state=AddRoutineStates.time)
    dp.register_message_handler(add_routine_period, state=AddRoutineStates.period)

    dp.register_message_handler(complete_item_start, lambda m: m.text and m.text.startswith("✅ "), state="*")
    dp.register_message_handler(complete_item_confirm, text="✅ Да, выполнено", state="*")
    dp.register_message_handler(undo_last_action, text="↩️ Отменить", state="*")

    dp.register_message_handler(answer_daily_question_start, text="📝 Ответить", state="*")
    dp.register_message_handler(skip_daily_question, text="❌ Пропустить", state="*")
    dp.register_message_handler(answer_daily_question_save, state=DailyQuestionStates.answer)
