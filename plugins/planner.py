import logging
from datetime import datetime, timedelta, time, date
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu, get_planner_keyboard
from reminder_utils import load_reminder_settings, get_default_reminders

logger = logging.getLogger(__name__)

last_task_id = {}

class AddTaskStates(StatesGroup):
    title = State()
    date = State()
    time = State()
    remind = State()

class AddRoutineStates(StatesGroup):
    title = State()
    period = State()
    days = State()
    time = State()
    remind = State()

class ReminderEditStates(StatesGroup):
    choose_type = State()
    enter_time = State()

# ========== КЛАВИАТУРА ПЛАНИРОВЩИКА (с новой кнопкой) ==========
def get_planner_keyboard():
    buttons = [
        [KeyboardButton(text="📋 Что сегодня?")],
        [KeyboardButton(text="➕ Добавить дело")],
        [KeyboardButton(text="🔄 Добавить рутину")],
        [KeyboardButton(text="🗓️ Мои дела")],
        [KeyboardButton(text="📋 Мои рутины")],
        [KeyboardButton(text="⏰ Уведомления")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

REMINDER_LABELS = {
    "🛌 Сон": "sleep",
    "⚡️ Чек-ины": "checkins",
    "📝 Итог дня": "summary",
}

async def planner_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📅 Мой день", reply_markup=get_planner_keyboard())

# ========== НАСТРОЙКА УВЕДОМЛЕНИЙ (время) ==========
async def reminder_edit_menu(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    settings = await load_reminder_settings(user_id)
    
    text = "⏰ *Настройка времени уведомлений*\n\n"
    for label, key in REMINDER_LABELS.items():
        s = settings.get(key, {"enabled": False, "times": []})
        status = "✅" if s["enabled"] else "❌"
        times = ", ".join(s["times"]) if s.get("times") else "—"
        text += f"{status} {label}: {times}\n"
    text += "\nВыбери тип для изменения времени:"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for label in REMINDER_LABELS:
        kb.add(KeyboardButton(label))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await ReminderEditStates.choose_type.set()

async def reminder_edit_choose(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await planner_menu(message, state)
        return
    if message.text not in REMINDER_LABELS:
        return
    
    key = REMINDER_LABELS[message.text]
    await state.update_data(edit_reminder_key=key)
    
    hints = {
        "sleep": "Введи время (ЧЧ:ММ, например 09:00):",
        "checkins": "Введи время через запятую (например 12:00, 16:00, 20:00):",
        "summary": "Введи время (ЧЧ:ММ, например 22:30):",
    }
    await message.answer(hints.get(key, "Введи время:"), reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await ReminderEditStates.enter_time.set()

async def reminder_edit_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await reminder_edit_menu(message, state)
        return
    
    data = await state.get_data()
    key = data.get("edit_reminder_key")
    if not key:
        await state.finish()
        return
    
    user_id = message.from_user.id
    settings = await load_reminder_settings(user_id)
    curr = settings.get(key, {"enabled": True, "times": []})
    
    if key in ("sleep", "summary"):
        import re
        if re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", message.text.strip()):
            times = [message.text.strip()]
        else:
            await message.answer("❌ Неверный формат. ЧЧ:ММ (например 09:00).")
            return
    else:
        parts = message.text.replace(",", " ").split()
        times = [t for t in parts if re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", t)]
        if not times:
            await message.answer("❌ Неверный формат. Например: 12:00, 16:00")
            return
    
    await db.set_reminder_setting(user_id, key, curr.get("enabled", True), times)
    await message.answer(f"✅ Время для {key} обновлено: {', '.join(times)}")
    await state.finish()
    await reminder_edit_menu(message, state)

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ БЕЗ ИЗМЕНЕНИЙ ==========
async def what_today(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id) or 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    today_date = now_local.date()
    once_tasks = await db.get_upcoming_tasks(user_id)
    routines = await db.get_recurring_tasks_by_user(user_id)
    today_routines = []
    for r in routines:
        if await should_run_today(r, today_date):
            today_routines.append(r)
    if not once_tasks and not today_routines:
        await message.answer("На сегодня нет запланированных дел и рутин. Отдохни :)")
    else:
        text = f"📋 *Твой день {today_date.strftime('%d.%m.%Y')}:*\n\n"
        if today_routines:
            text += "🔄 *Рутина:*\n"
            for r in today_routines:
                text += f"• {r['title']} — в {r['start_time']}\n"
        if once_tasks:
            text += "\n📌 *Дела:*\n"
            for t in once_tasks:
                text += f"• {t['title']} — в {t['start_time']}\n"
        await message.answer(text, parse_mode="Markdown")
    await planner_menu(message, state)

async def add_task_start(message: types.Message, state: FSMContext):
    await message.answer("Введи название дела:")
    await AddTaskStates.title.set()

async def add_task_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Сегодня", "Завтра", "Послезавтра", "⬅️ Назад")
    await message.answer("Выбери дату:", reply_markup=kb)
    await AddTaskStates.date.set()

async def add_task_date(message: types.Message, state: FSMContext):
    text = message.text.lower()
    now = datetime.now()
    if text == "сегодня": target_date = now.date()
    elif text == "завтра": target_date = (now + timedelta(days=1)).date()
    elif text == "послезавтра": target_date = (now + timedelta(days=2)).date()
    elif text == "⬅️ назад": await state.finish(); await planner_menu(message, state); return
    else: await message.answer("Выбери из кнопок"); return
    await state.update_data(target_date=target_date)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in range(0, 24, 2): kb.add(KeyboardButton(f"{h:02d}:00"), KeyboardButton(f"{h:02d}:30"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("Выбери время:", reply_markup=kb)
    await AddTaskStates.time.set()

async def add_task_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад": await AddTaskStates.date.set(); await add_task_date(message, state); return
    try: target_time = datetime.strptime(message.text, "%H:%M").time()
    except: await message.answer("Неверный формат."); return
    await state.update_data(target_time=target_time)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("45 минут", "1 час", "2 часа", "Другое", "⬅️ Назад")
    await message.answer("За сколько минут напомнить?", reply_markup=kb)
    await AddTaskStates.remind.set()

async def add_task_remind(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад": await AddTaskStates.time.set(); await add_task_time(message, state); return
    remind = 45
    if message.text == "1 час": remind = 60
    elif message.text == "2 часа": remind = 120
    elif message.text == "Другое": await message.answer("Введи число минут:"); return
    else:
        try: remind = int(message.text)
        except: await message.answer("Введи число."); return
    await state.update_data(remind=remind)
    data = await state.get_data()
    user_id = message.from_user.id
    start_dt = datetime.combine(data['target_date'], data['target_time'])
    remind_dt = start_dt - timedelta(minutes=remind)
    if remind_dt < datetime.now(): await message.answer("Время уже прошло."); return
    task_id = await db.add_task(user_id, data['title'], 'once', start_date=data['target_date'], start_time=data['target_time'], remind_before_minutes=remind, next_due=remind_dt)
    if task_id: await message.answer(f"✅ Дело добавлено!\n🕒 {data['target_date']} в {data['target_time']}\n🔔 Напомню за {remind} мин.")
    else: await message.answer("❌ Ошибка")
    await state.finish(); await planner_menu(message, state)

async def list_tasks(message: types.Message, state: FSMContext):
    tasks = await db.get_upcoming_tasks(message.from_user.id)
    if not tasks: await message.answer("Нет предстоящих дел.")
    else:
        text = "🗓️ *Предстоящие дела:*\n"
        for t in tasks: text += f"• {t['title']} — {t['start_date']} в {t['start_time']}\n"
        await message.answer(text, parse_mode="Markdown")
    await planner_menu(message, state)

async def add_routine_start(message: types.Message, state: FSMContext):
    await message.answer("Введи название рутины:"); await AddRoutineStates.title.set()

async def add_routine_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Каждый день", "Через день", "По будням", "По выходным", "Выбрать дни недели", "⬅️ Назад")
    await message.answer("Выбери периодичность:", reply_markup=kb); await AddRoutineStates.period.set()

async def add_routine_period(message: types.Message, state: FSMContext):
    period = message.text
    if period == "⬅️ назад": await state.finish(); await planner_menu(message, state); return
    if period == "Выбрать дни недели":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("Пн","Вт","Ср","Чт","Пт","Сб","Вс","⬅️ Назад","Готово")
        await message.answer("Выбери дни:", reply_markup=kb)
        await state.update_data(period=period, selected_days=[]); await AddRoutineStates.days.set()
    else:
        await state.update_data(period=period, selected_days=None); await ask_routine_time(message, state)

async def add_routine_days(message: types.Message, state: FSMContext):
    data = await state.get_data(); selected = data.get('selected_days', [])
    if message.text == "⬅️ назад": await AddRoutineStates.period.set(); await add_routine_period(message, state); return
    if message.text == "Готово":
        if not selected: await message.answer("Не выбрано."); return
        await state.update_data(selected_days=selected); await ask_routine_time(message, state); return
    day_map = {"Пн":1,"Вт":2,"Ср":3,"Чт":4,"Пт":5,"Сб":6,"Вс":7}
    if message.text in day_map:
        d = day_map[message.text]
        if d not in selected: selected.append(d); await state.update_data(selected_days=selected); await message.answer(f"Добавлен {message.text}")
        else: await message.answer(f"Уже выбран.")
    else: await message.answer("Выбери из кнопок.")

async def ask_routine_time(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in range(0,24,2): kb.add(KeyboardButton(f"{h:02d}:00"), KeyboardButton(f"{h:02d}:30"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("Время напоминания:", reply_markup=kb); await AddRoutineStates.time.set()

async def add_routine_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад": await AddRoutineStates.period.set(); await add_routine_period(message, state); return
    try: target_time = datetime.strptime(message.text, "%H:%M").time()
    except: await message.answer("Неверный формат."); return
    await state.update_data(target_time=target_time)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("15 минут","30 минут","1 час","Другое","⬅️ Назад")
    await message.answer("За сколько минут напомнить?", reply_markup=kb); await AddRoutineStates.remind.set()

async def add_routine_remind(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад": await AddRoutineStates.time.set(); await add_routine_time(message, state); return
    remind = 15
    if message.text == "30 минут": remind = 30
    elif message.text == "1 час": remind = 60
    elif message.text == "Другое": await message.answer("Введи число:"); return
    else:
        try: remind = int(message.text)
        except: await message.answer("Введи число."); return
    await state.update_data(remind=remind)
    data = await state.get_data(); user_id = message.from_user.id
    recurrence_type = recurrence_interval = recurrence_days = None
    period = data['period']
    if period == "Каждый день": recurrence_type = 'daily'
    elif period == "Через день": recurrence_type = 'interval'; recurrence_interval = 2
    elif period == "По будням": recurrence_type = 'weekdays'
    elif period == "По выходным": recurrence_type = 'weekends'
    elif period == "Выбрать дни недели": recurrence_type = 'weekly'; recurrence_days = data['selected_days']
    task_id = await db.add_task(user_id, data['title'], 'recurring', recurrence_type=recurrence_type, recurrence_interval=recurrence_interval, recurrence_days=recurrence_days, start_time=data['target_time'], remind_before_minutes=remind)
    if task_id: await message.answer(f"✅ Рутина добавлена!")
    else: await message.answer("❌ Ошибка")
    await state.finish(); await planner_menu(message, state)

async def list_routines(message: types.Message, state: FSMContext):
    routines = await db.get_recurring_tasks_by_user(message.from_user.id)
    if not routines: await message.answer("Нет активных рутин.")
    else:
        text = "📋 *Активные рутины:*\n"
        for r in routines: text += f"• {r['title']} — в {r['start_time']}\n"
        await message.answer(text, parse_mode="Markdown")
    await planner_menu(message, state)

async def should_run_today(routine, today_date):
    rt = routine['recurrence_type']
    if rt == 'daily': return True
    if rt == 'interval':
        interval = routine['recurrence_interval'] or 2
        created = routine['created_at'].date() if routine.get('created_at') else today_date
        return (today_date - created).days % interval == 0
    if rt == 'weekdays': return today_date.weekday() < 5
    if rt == 'weekends': return today_date.weekday() >= 5
    if rt == 'weekly': return (today_date.weekday() + 1) in routine['recurrence_days']
    return False

# ========== НАПОМИНАНИЯ (без изменений) ==========
async def check_reminders():
    from bot import bot
    now_utc = datetime.utcnow()
    tasks = await db.get_tasks_due_now(now_utc)
    for task in tasks:
        user_id = task['user_id']; last_task_id[user_id] = task['id']
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("✅ Выполнил","⏰ Отложить на час"); kb.add("❌ Отменить")
        try:
            await bot.send_message(user_id, f"⏰ НАПОМИНАНИЕ О ДЕЛЕ:\n\n*{task['title']}*\n🕒 {task['start_date']} в {task['start_time']}", reply_markup=kb, parse_mode="Markdown")
            await db.deactivate_task(task['id'], user_id)
        except Exception as e: logging.error(f"Ошибка отправки: {e}")

async def check_routines():
    from bot import bot
    now_utc = datetime.utcnow()
    async with db.pool.acquire() as conn: users = await conn.fetch("SELECT DISTINCT user_id FROM users")
    for user in users:
        user_id = user['user_id']; tz = await db.get_user_timezone(user_id) or 3
        user_now = now_utc + timedelta(hours=tz); today = user_now.date(); current_time = user_now.time().strftime("%H:%M")
        routines = await db.get_recurring_tasks_by_user(user_id)
        for r in routines:
            if await should_run_today(r, today):
                remind_minutes = r['remind_before_minutes'] or 15
                t = r['start_time']
                if isinstance(t, str): start_hour, start_min = map(int, t.split(':'))
                else: start_hour, start_min = t.hour, t.minute
                start_dt = datetime.combine(today, time(start_hour, start_min))
                if (start_dt - timedelta(minutes=remind_minutes)).strftime("%H:%M") == current_time:
                    last_task_id[user_id] = r['id']
                    kb = ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add("✅ Выполнена","⏰ Напомнить позже"); kb.add("❌ Пропустить")
                    await bot.send_message(user_id, f"🔄 НАПОМИНАНИЕ О РУТИНЕ:\n\n*{r['title']}*\n🕒 {t if isinstance(t, str) else t.strftime('%H:%M')}", reply_markup=kb, parse_mode="Markdown")

async def complete_task_handler(message: types.Message):
    user_id = message.from_user.id; task_id = last_task_id.get(user_id)
    if task_id: await db.complete_task(task_id, user_id, completed=True); await message.answer("✅ Выполнено!", reply_markup=get_main_menu()); del last_task_id[user_id]
    else: await message.answer("Нет активных напоминаний.", reply_markup=get_main_menu())

async def postpone_task_handler(message: types.Message):
    user_id = message.from_user.id; task_id = last_task_id.get(user_id)
    if task_id: await db.postpone_task(task_id, 60); await message.answer("⏰ Напомню через час.", reply_markup=get_main_menu()); del last_task_id[user_id]
    else: await message.answer("Нет активных напоминаний.", reply_markup=get_main_menu())

async def cancel_task_handler(message: types.Message):
    user_id = message.from_user.id; task_id = last_task_id.get(user_id)
    if task_id: await db.complete_task(task_id, user_id, cancelled=True); await message.answer("❌ Отменено.", reply_markup=get_main_menu()); del last_task_id[user_id]
    else: await message.answer("Нет активных напоминаний.", reply_markup=get_main_menu())

async def routine_done_handler(message: types.Message):
    user_id = message.from_user.id; task_id = last_task_id.get(user_id)
    if task_id:
        async with db.pool.acquire() as conn: await conn.execute("INSERT INTO task_logs (task_id, user_id, due_date, completed, completed_at) VALUES ($1, $2, CURRENT_DATE, TRUE, NOW())", task_id, user_id)
        await message.answer("✅ Рутина выполнена!", reply_markup=get_main_menu()); del last_task_id[user_id]
    else: await message.answer("Нет активных напоминаний.", reply_markup=get_main_menu())

async def routine_skip_handler(message: types.Message):
    user_id = message.from_user.id; task_id = last_task_id.get(user_id)
    if task_id:
        async with db.pool.acquire() as conn: await conn.execute("INSERT INTO task_logs (task_id, user_id, due_date, skipped, completed_at) VALUES ($1, $2, CURRENT_DATE, TRUE, NOW())", task_id, user_id)
        await message.answer("❌ Пропущено.", reply_markup=get_main_menu()); del last_task_id[user_id]
    else: await message.answer("Нет активных напоминаний.", reply_markup=get_main_menu())

async def routine_snooze_handler(message: types.Message):
    await message.answer("⏰ Напомню позже.", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(planner_menu, text="📅 Мой день", state="*")
    dp.register_message_handler(what_today, text="📋 Что сегодня?", state="*")
    dp.register_message_handler(add_task_start, text="➕ Добавить дело", state="*")
    dp.register_message_handler(list_tasks, text="🗓️ Мои дела", state="*")
    dp.register_message_handler(add_routine_start, text="🔄 Добавить рутину", state="*")
    dp.register_message_handler(list_routines, text="📋 Мои рутины", state="*")
    dp.register_message_handler(reminder_edit_menu, text="⏰ Уведомления", state="*")
    dp.register_message_handler(reminder_edit_choose, state=ReminderEditStates.choose_type)
    dp.register_message_handler(reminder_edit_save, state=ReminderEditStates.enter_time)
    dp.register_message_handler(add_task_title, state=AddTaskStates.title)
    dp.register_message_handler(add_task_date, state=AddTaskStates.date)
    dp.register_message_handler(add_task_time, state=AddTaskStates.time)
    dp.register_message_handler(add_task_remind, state=AddTaskStates.remind)
    dp.register_message_handler(add_routine_title, state=AddRoutineStates.title)
    dp.register_message_handler(add_routine_period, state=AddRoutineStates.period)
    dp.register_message_handler(add_routine_days, state=AddRoutineStates.days)
    dp.register_message_handler(add_routine_time, state=AddRoutineStates.time)
    dp.register_message_handler(add_routine_remind, state=AddRoutineStates.remind)
    dp.register_message_handler(complete_task_handler, text="✅ Выполнил", state="*")
    dp.register_message_handler(postpone_task_handler, text="⏰ Отложить на час", state="*")
    dp.register_message_handler(cancel_task_handler, text="❌ Отменить", state="*")
    dp.register_message_handler(routine_done_handler, text="✅ Выполнена", state="*")
    dp.register_message_handler(routine_snooze_handler, text="⏰ Напомнить позже", state="*")
    dp.register_message_handler(routine_skip_handler, text="❌ Пропустить", state="*")
