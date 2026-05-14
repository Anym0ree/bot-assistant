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

# Импорты для запуска опросов из уведомлений
from plugins.sleep import sleep_start
from plugins.checkin import checkin_start
from plugins.day_summary import day_summary_start

logger = logging.getLogger(__name__)

# ========== FSM ==========
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

# ========== КЛАВИАТУРЫ ==========
def get_today_actions_keyboard():
    buttons = [
        [KeyboardButton("✅ Записать сон"), KeyboardButton("⚡ Быстрый чекин")],
        [KeyboardButton("📝 Итог дня")],
        [KeyboardButton("➕ Дело"), KeyboardButton("🔄 Рутина")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== 📋 СЕГОДНЯ (дашборд) ==========
async def today_view(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id) or 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    today_str = now_local.strftime("%Y-%m-%d")
    today_date = now_local.date()

    text = f"📋 *{today_str}, {['пн','вт','ср','чт','пт','сб','вс'][now_local.weekday()]}*\n\n"

    # Погода
    from plugins.weather import get_weather_by_city, get_weather_by_coords
    async with db.pool.acquire() as conn:
        loc = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)
    if loc and (loc['city'] or (loc['lat'] and loc['lon'])):
        try:
            if loc['city']:
                data = await get_weather_by_city(loc['city'])
            else:
                data = await get_weather_by_coords(loc['lat'], loc['lon'])
            if data:
                temp = data['main']['temp']
                desc = data['weather'][0]['description']
                text += f"🌤️ {temp:.0f}°C, {desc}\n"
        except:
            text += "🌤️ Погода недоступна\n"
    else:
        text += "🌤️ *Погода:* укажи город в настройках\n"

    # Сон
    async with db.pool.acquire() as conn:
        sleep_row = await conn.fetchrow("SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = $1 AND date = $2", user_id, today_str)
    text += "🛌 *Сон:* " + (f"✅ {sleep_row['bed_time']}–{sleep_row['wake_time']}, кач-во {sleep_row['quality']}/10" if sleep_row else "❌ не записан") + "\n"

    # Чек-ин
    async with db.pool.acquire() as conn:
        checkin_row = await conn.fetchrow("SELECT energy, stress FROM checkins WHERE user_id = $1 AND date = $2", user_id, today_str)
    text += "⚡️ *Чек-ин:* " + (f"✅ энергия {checkin_row['energy']}/10, стресс {checkin_row['stress']}/10" if checkin_row else "❌ не сделан") + "\n"

    # Итог дня
    local_hour = now_local.hour
    summary_available = local_hour >= 18 or local_hour < 6
    async with db.pool.acquire() as conn:
        summary_row = await conn.fetchrow("SELECT score FROM day_summary WHERE user_id = $1 AND date = $2", user_id, today_str)
    if summary_row:
        text += f"📝 *Итог дня:* ✅ {summary_row['score']}/10\n"
    elif summary_available:
        text += "📝 *Итог дня:* ⬜ можно записать\n"
    else:
        text += "📝 *Итог дня:* 🔒 будет доступен после 18:00\n"

    # Дела
    async with db.pool.acquire() as conn:
        tasks = await conn.fetch("""
            SELECT id, title, is_active,
                   EXISTS(SELECT 1 FROM task_logs WHERE task_id = tasks.id AND due_date = $2 AND completed = TRUE) as done
            FROM tasks WHERE user_id = $1 AND task_type = 'once' AND start_date = $2 ORDER BY start_time
        """, user_id, today_date)
    active_tasks = [t for t in tasks if t['is_active'] and not t['done']]
    done_tasks = [t for t in tasks if t['done']]
    if active_tasks or done_tasks:
        text += "\n📌 *Дела:*\n"
        for t in active_tasks:
            text += f"  ⬜ {t['title']}\n"
        for t in done_tasks:
            text += f"  ✅ ~{t['title']}~\n"

    # Рутины
    routines = await db.get_recurring_tasks_by_user(user_id)
    today_routines = []
    for r in routines:
        if await should_run_today(r, today_date):
            async with db.pool.acquire() as conn:
                done = await conn.fetchval("SELECT 1 FROM task_logs WHERE task_id = $1 AND due_date = $2 AND completed = TRUE", r['id'], today_date)
            today_routines.append({"title": r['title'], "done": done is not None})
    if today_routines:
        text += "\n🔄 *Рутины:*\n"
        for r in today_routines:
            icon = "✅" if r['done'] else "⬜"
            name = f"~{r['title']}~" if r['done'] else r['title']
            text += f"  {icon} {name}\n"

    # Вода и еда
    items = await db.get_today_food_and_drinks(user_id)
    water_count = sum(1 for i in items if i['type'] == "🥤 Напитки" and "вода" in i['text'].lower())
    food_count = sum(1 for i in items if i['type'] == "🍽 Еда")
    text += f"\n💧 Вода: {water_count} записей | 🍽 Еда: {food_count} записей"

    await message.answer(text, reply_markup=get_today_actions_keyboard(), parse_mode="Markdown")

# ========== БЫСТРЫЕ ДЕЙСТВИЯ ==========
# (быстрый сон и чекин — без изменений)

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
    for t in ["22:00","23:00","00:00","01:00","02:00"]:
        kb.add(KeyboardButton(t))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("Во сколько лёг?", reply_markup=kb)
    await QuickSleepStates.bed_time.set()

async def quick_sleep_bed(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад": await state.finish(); await plans_menu(message, state); return
    await state.update_data(bed_time=message.text)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in ["06:00","07:00","08:00","09:00","10:00"]:
        kb.add(KeyboardButton(t))
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

# ========== ДЕЛА ==========
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
            kb.add(KeyboardButton(f"✅ Выполнить #{t['id']}"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

async def handle_complete(message: types.Message):
    if "✅ Выполнить #" in message.text:
        task_id = int(message.text.split("#")[1])
        task = await db.get_task_by_id(task_id)
        if task and task['user_id'] == message.from_user.id:
            await db.complete_task(task_id, message.from_user.id, completed=True)
            await message.answer("✅ Выполнено!", reply_markup=get_main_menu())
        else:
            await message.answer("❌ Задача не найдена.")

async def handle_postpone(message: types.Message):
    if "⏰ Отложить #" in message.text:
        task_id = int(message.text.split("#")[1])
        task = await db.get_task_by_id(task_id)
        if task and task['user_id'] == message.from_user.id:
            await db.postpone_task(task_id, 60)
            await message.answer("⏰ Напомню через час.", reply_markup=get_main_menu())

async def handle_cancel(message: types.Message):
    if "❌ Отменить #" in message.text:
        task_id = int(message.text.split("#")[1])
        task = await db.get_task_by_id(task_id)
        if task and task['user_id'] == message.from_user.id:
            await db.complete_task(task_id, message.from_user.id, cancelled=True)
            await message.answer("❌ Отменено.", reply_markup=get_main_menu())

# ========== РУТИНЫ ==========
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

# ========== НАПОМИНАНИЯ (дела + опросы с кнопками) ==========
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
    """Расширенная версия: опросы с кнопками, рутины с кнопками"""
    try:
        from bot import bot
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

            # Сон с кнопками
            sleep_set = await db.get_reminder_setting(user_id, "sleep")
            if sleep_set["enabled"] and sleep_set["times"] and sleep_set["times"][0] == current_time:
                if not await db.has_sleep_today(user_id):
                    kb = ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(KeyboardButton("✅ Пройти сон"), KeyboardButton("⏰ Напомнить позже"))
                    await bot.send_message(user_id, "🛌 Пора записать сон", reply_markup=kb)

            # Чекин с кнопками
            check_set = await db.get_reminder_setting(user_id, "checkins")
            if check_set["enabled"] and current_time in check_set["times"]:
                checkins = await db._load_json(user_id, "checkins.json")
                if not any(c.get("date") == today_str for c in checkins):
                    kb = ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(KeyboardButton("✅ Пройти чекин"), KeyboardButton("⏰ Напомнить позже"))
                    await bot.send_message(user_id, "⚡️ Время для чек-ина", reply_markup=kb)

            # Итог дня с кнопками
            summary_set = await db.get_reminder_setting(user_id, "summary")
            if summary_set["enabled"] and summary_set["times"] and summary_set["times"][0] == current_time:
                target_date = await db.get_target_date_for_summary(user_id)
                if target_date and not await db.has_day_summary_for_date(user_id, target_date):
                    kb = ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(KeyboardButton("✅ Пройти итог"), KeyboardButton("⏰ Напомнить позже"))
                    await bot.send_message(user_id, "📝 Подведи итог дня", reply_markup=kb)

            # Вода и еда (без кнопок)
            water_set = await db.get_reminder_setting(user_id, "water")
            if water_set["enabled"] and current_time in water_set["times"]:
                await bot.send_message(user_id, "💧 Не забывай пить воду!")

            meals_set = await db.get_reminder_setting(user_id, "meals")
            if meals_set["enabled"] and current_time in meals_set["times"]:
                await bot.send_message(user_id, "🍽 Пора поесть!")

            # Рутины (с кнопками)
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

# Обработчики кнопок опросов
async def start_sleep_from_reminder(message: types.Message, state: FSMContext):
    await sleep_start(message, state)

async def start_checkin_from_reminder(message: types.Message, state: FSMContext):
    await checkin_start(message, state)

async def start_summary_from_reminder(message: types.Message, state: FSMContext):
    await day_summary_start(message, state)

async def postpone_reminder(message: types.Message):
    await message.answer("⏰ Напомню позже.", reply_markup=get_main_menu())

# Обработчики кнопок рутин
async def handle_routine_done(message: types.Message):
    if "✅ Выполнена #" in message.text:
        task_id = int(message.text.split("#")[1])
        task = await db.get_task_by_id(task_id)
        if task and task['user_id'] == message.from_user.id:
            async with db.pool.acquire() as conn:
                await conn.execute("INSERT INTO task_logs (task_id, user_id, due_date, completed, completed_at) VALUES ($1,$2,CURRENT_DATE,TRUE,NOW())", task_id, message.from_user.id)
            await message.answer("✅ Рутина выполнена!", reply_markup=get_main_menu())

async def handle_routine_snooze(message: types.Message):
    if "⏰ Позже #" in message.text:
        await message.answer("⏰ Напомню позже.", reply_markup=get_main_menu())

async def handle_routine_skip(message: types.Message):
    if "❌ Пропустить #" in message.text:
        task_id = int(message.text.split("#")[1])
        task = await db.get_task_by_id(task_id)
        if task and task['user_id'] == message.from_user.id:
            async with db.pool.acquire() as conn:
                await conn.execute("INSERT INTO task_logs (task_id, user_id, due_date, skipped, completed_at) VALUES ($1,$2,CURRENT_DATE,TRUE,NOW())", task_id, message.from_user.id)
            await message.answer("❌ Рутина пропущена.", reply_markup=get_main_menu())

# ========== УТРЕННЕЕ ПРИВЕТСТВИЕ ==========
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

# ========== ВОПРОС ДНЯ ==========
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

# ========== ВСПОМОГАТЕЛЬНЫЕ ==========
async def should_run_today(routine, today_date):
    rt = routine['recurrence_type']
    if rt == 'daily': return True
    if rt == 'weekdays': return today_date.weekday() < 5
    if rt == 'weekends': return today_date.weekday() >= 5
    return False

async def plans_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📅 Планы", reply_markup=get_plans_menu())

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(plans_menu, text="📅 Планы", state="*")
    dp.register_message_handler(today_view, text="📋 Сегодня", state="*")
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

    dp.register_message_handler(handle_complete, lambda m: m.text and "✅ Выполнить #" in m.text, state="*")
    dp.register_message_handler(handle_postpone, lambda m: m.text and "⏰ Отложить #" in m.text, state="*")
    dp.register_message_handler(handle_cancel, lambda m: m.text and "❌ Отменить #" in m.text, state="*")

    # Обработчики опросов с кнопками
    dp.register_message_handler(start_sleep_from_reminder, text="✅ Пройти сон", state="*")
    dp.register_message_handler(start_checkin_from_reminder, text="✅ Пройти чекин", state="*")
    dp.register_message_handler(start_summary_from_reminder, text="✅ Пройти итог", state="*")
    dp.register_message_handler(postpone_reminder, text="⏰ Напомнить позже", state="*")

    # Рутины
    dp.register_message_handler(handle_routine_done, lambda m: m.text and "✅ Выполнена #" in m.text, state="*")
    dp.register_message_handler(handle_routine_snooze, lambda m: m.text and "⏰ Позже #" in m.text, state="*")
    dp.register_message_handler(handle_routine_skip, lambda m: m.text and "❌ Пропустить #" in m.text, state="*")

    dp.register_message_handler(answer_daily_question_start, text="📝 Ответить", state="*")
    dp.register_message_handler(skip_daily_question, text="❌ Пропустить", state="*")
    dp.register_message_handler(answer_daily_question_save, state=DailyQuestionStates.answer)
