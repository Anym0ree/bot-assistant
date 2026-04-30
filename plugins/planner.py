import logging
from datetime import datetime, timedelta, time, date
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu, get_planner_keyboard

logger = logging.getLogger(__name__)

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

# ---------- Меню планировщика ----------
async def planner_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📅 Мой день", reply_markup=get_planner_keyboard())

# ---------- Что сегодня? ----------
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

# ---------- Добавление одноразового дела ----------
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
    if text == "сегодня":
        target_date = now.date()
    elif text == "завтра":
        target_date = (now + timedelta(days=1)).date()
    elif text == "послезавтра":
        target_date = (now + timedelta(days=2)).date()
    elif text == "⬅️ назад":
        await state.finish()
        await planner_menu(message, state)
        return
    else:
        await message.answer("Выбери из кнопок")
        return
    await state.update_data(target_date=target_date)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in range(0, 24, 2):
        row = [KeyboardButton(text=f"{h:02d}:00"), KeyboardButton(text=f"{h:02d}:30")]
        kb.add(*row)
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("Выбери время выполнения:", reply_markup=kb)
    await AddTaskStates.time.set()

async def add_task_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад":
        await AddTaskStates.date.set()
        await add_task_date(message, state)
        return
    try:
        target_time = datetime.strptime(message.text, "%H:%M").time()
    except:
        await message.answer("Неверный формат. Введи ЧЧ:ММ")
        return
    await state.update_data(target_time=target_time)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("45 минут", "1 час", "2 часа", "Другое", "⬅️ Назад")
    await message.answer("За сколько минут напомнить?", reply_markup=kb)
    await AddTaskStates.remind.set()

async def add_task_remind(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад":
        await AddTaskStates.time.set()
        await add_task_time(message, state)
        return
    remind = 45
    if message.text == "1 час":
        remind = 60
    elif message.text == "2 часа":
        remind = 120
    elif message.text == "Другое":
        await message.answer("Введи число минут (например, 30):")
        return
    else:
        try:
            remind = int(message.text)
        except:
            await message.answer("Введи число минут.")
            return
    await state.update_data(remind=remind)
    data = await state.get_data()
    user_id = message.from_user.id
    start_datetime = datetime.combine(data['target_date'], data['target_time'])
    remind_datetime = start_datetime - timedelta(minutes=remind)
    if remind_datetime < datetime.now():
        await message.answer("Время напоминания уже прошло. Выбери более позднее время.")
        return
    task_id = await db.add_task(
        user_id, data['title'], 'once',
        start_date=data['target_date'],
        start_time=data['target_time'],
        remind_before_minutes=remind,
        next_due=remind_datetime
    )
    if task_id:
        await message.answer(f"✅ Дело «{data['title']}» добавлено!\n🕒 {data['target_date']} в {data['target_time']}\n🔔 Напомню за {remind} минут.")
    else:
        await message.answer("❌ Ошибка при добавлении")
    await state.finish()
    await planner_menu(message, state)

# ---------- Список предстоящих дел ----------
async def list_tasks(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    tasks = await db.get_upcoming_tasks(user_id)
    if not tasks:
        await message.answer("У тебя нет предстоящих дел.")
    else:
        text = "🗓️ *Твои предстоящие дела:*\n"
        for t in tasks:
            text += f"• *{t['title']}* — {t['start_date']} в {t['start_time']}\n"
        await message.answer(text, parse_mode="Markdown")
    await planner_menu(message, state)

# ---------- Добавление рутины ----------
async def add_routine_start(message: types.Message, state: FSMContext):
    await message.answer("Введи название рутины:")
    await AddRoutineStates.title.set()

async def add_routine_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Каждый день", "Через день", "По будням", "По выходным", "Выбрать дни недели", "⬅️ Назад")
    await message.answer("Выбери периодичность:", reply_markup=kb)
    await AddRoutineStates.period.set()

async def add_routine_period(message: types.Message, state: FSMContext):
    period = message.text
    if period == "⬅️ назад":
        await state.finish()
        await planner_menu(message, state)
        return
    if period == "Выбрать дни недели":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс", "⬅️ Назад", "Готово")
        await message.answer("Выбери дни (нажимай на кнопки, потом «Готово»):", reply_markup=kb)
        await state.update_data(period=period, selected_days=[])
        await AddRoutineStates.days.set()
    else:
        await state.update_data(period=period, selected_days=None)
        await ask_routine_time(message, state)

async def add_routine_days(message: types.Message, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_days', [])
    if message.text == "⬅️ назад":
        await AddRoutineStates.period.set()
        await add_routine_period(message, state)
        return
    if message.text == "Готово":
        if not selected:
            await message.answer("Ты не выбрал ни одного дня. Выбери или нажми «Готово».")
            return
        await state.update_data(selected_days=selected)
        await ask_routine_time(message, state)
        return
    day_map = {"Пн":1,"Вт":2,"Ср":3,"Чт":4,"Пт":5,"Сб":6,"Вс":7}
    if message.text in day_map:
        d = day_map[message.text]
        if d not in selected:
            selected.append(d)
            await state.update_data(selected_days=selected)
            await message.answer(f"Добавлен {message.text}. Выбери ещё или отправь «Готово».")
        else:
            await message.answer(f"{message.text} уже выбран.")
    else:
        await message.answer("Выбери день из кнопок.")

async def ask_routine_time(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in range(0, 24, 2):
        row = [KeyboardButton(text=f"{h:02d}:00"), KeyboardButton(text=f"{h:02d}:30")]
        kb.add(*row)
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("В какое время напоминать?", reply_markup=kb)
    await AddRoutineStates.time.set()

async def add_routine_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад":
        await AddRoutineStates.period.set()
        await add_routine_period(message, state)
        return
    try:
        target_time = datetime.strptime(message.text, "%H:%M").time()
    except:
        await message.answer("Неверный формат. Введи ЧЧ:ММ")
        return
    await state.update_data(target_time=target_time)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("15 минут", "30 минут", "1 час", "Другое", "⬅️ Назад")
    await message.answer("За сколько минут напомнить о рутине?", reply_markup=kb)
    await AddRoutineStates.remind.set()

async def add_routine_remind(message: types.Message, state: FSMContext):
    if message.text == "⬅️ назад":
        await AddRoutineStates.time.set()
        await add_routine_time(message, state)
        return
    remind = 15
    if message.text == "30 минут":
        remind = 30
    elif message.text == "1 час":
        remind = 60
    elif message.text == "Другое":
        await message.answer("Введи число минут (например, 45):")
        return
    else:
        try:
            remind = int(message.text)
        except:
            await message.answer("Введи число минут.")
            return
    await state.update_data(remind=remind)
    data = await state.get_data()
    user_id = message.from_user.id
    recurrence_type = None
    recurrence_interval = None
    recurrence_days = None
    period = data['period']
    if period == "Каждый день":
        recurrence_type = 'daily'
    elif period == "Через день":
        recurrence_type = 'interval'
        recurrence_interval = 2
    elif period == "По будням":
        recurrence_type = 'weekdays'
    elif period == "По выходным":
        recurrence_type = 'weekends'
    elif period == "Выбрать дни недели":
        recurrence_type = 'weekly'
        recurrence_days = data['selected_days']
    task_id = await db.add_task(
        user_id, data['title'], 'recurring',
        recurrence_type=recurrence_type,
        recurrence_interval=recurrence_interval,
        recurrence_days=recurrence_days,
        start_time=data['target_time'],
        remind_before_minutes=remind
    )
    if task_id:
        await message.answer(f"✅ Рутина «{data['title']}» добавлена!")
    else:
        await message.answer("❌ Ошибка")
    await state.finish()
    await planner_menu(message, state)

# ---------- Список рутин ----------
async def list_routines(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    routines = await db.get_recurring_tasks_by_user(user_id)
    if not routines:
        await message.answer("У тебя нет добавленных рутин.")
    else:
        text = "📋 *Твои активные рутины:*\n"
        for r in routines:
            text += f"• {r['title']} — в {r['start_time']}\n"
        await message.answer(text, parse_mode="Markdown")
    await planner_menu(message, state)

async def should_run_today(routine, today_date):
    rt = routine['recurrence_type']
    if rt == 'daily':
        return True
    if rt == 'interval':
        interval = routine['recurrence_interval'] or 2
        created = routine['created_at'].date() if routine.get('created_at') else today_date
        delta = (today_date - created).days
        return delta % interval == 0
    if rt == 'weekdays':
        return today_date.weekday() < 5
    if rt == 'weekends':
        return today_date.weekday() >= 5
    if rt == 'weekly':
        return (today_date.weekday() + 1) in routine['recurrence_days']
    return False

# ========== НАПОМИНАНИЯ ==========
async def check_reminders():
    from bot import bot
    now_utc = datetime.utcnow()
    tasks = await db.get_tasks_due_now(now_utc)
    for task in tasks:
        user_id = task['user_id']
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✅ Выполнил", callback_data=f"done_task_{task['id']}"),
            InlineKeyboardButton("⏰ Отложить на час", callback_data=f"postpone_task_{task['id']}")
        )
        kb.add(InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_task_{task['id']}"))
        try:
            await bot.send_message(
                user_id,
                f"⏰ НАПОМИНАНИЕ О ДЕЛЕ:\n\n*{task['title']}*\n🕒 {task['start_date']} в {task['start_time']}",
                reply_markup=kb,
                parse_mode="Markdown"
            )
            # Деактивируем задачу, чтобы не слать повторно
            await db.deactivate_task(task['id'], user_id)
        except Exception as e:
            logging.error(f"Не удалось отправить напоминание пользователю {user_id}: {e}")

async def check_routines():
    from bot import bot
    now_utc = datetime.utcnow()
    async with db.pool.acquire() as conn:
        users = await conn.fetch("SELECT DISTINCT user_id FROM users")
    for user in users:
        user_id = user['user_id']
        tz = await db.get_user_timezone(user_id) or 3
        user_now = now_utc + timedelta(hours=tz)
        today = user_now.date()
        current_time = user_now.time().strftime("%H:%M")
        routines = await db.get_recurring_tasks_by_user(user_id)
        for r in routines:
            if await should_run_today(r, today):
                remind_minutes = r['remind_before_minutes'] or 15
                # Безопасное извлечение времени (строка или datetime.time)
                t = r['start_time']
                if isinstance(t, str):
                    start_hour, start_min = map(int, t.split(':'))
                else:
                    start_hour, start_min = t.hour, t.minute
                start_dt = datetime.combine(today, time(start_hour, start_min))
                remind_dt = start_dt - timedelta(minutes=remind_minutes)
                if remind_dt.strftime("%H:%M") == current_time:
                    kb = InlineKeyboardMarkup(row_width=2)
                    kb.add(
                        InlineKeyboardButton("✅ Выполнена", callback_data=f"done_routine_{r['id']}"),
                        InlineKeyboardButton("⏰ Напомнить позже", callback_data=f"snooze_routine_{r['id']}")
                    )
                    kb.add(InlineKeyboardButton("❌ Пропустить", callback_data=f"skip_routine_{r['id']}"))
                    await bot.send_message(
                        user_id,
                        f"🔄 НАПОМИНАНИЕ О РУТИНЕ:\n\n*{r['title']}*\n🕒 {t if isinstance(t, str) else t.strftime('%H:%M')}",
                        reply_markup=kb,
                        parse_mode="Markdown"
                    )

# ---------- Обработчики колбэков ----------
async def done_task_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    await db.complete_task(task_id, callback.from_user.id, completed=True)
    await callback.answer("✅ Дело выполнено!")
    await callback.message.delete()

async def postpone_task_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    await db.postpone_task(task_id, 60)
    await callback.answer("⏰ Напомню через час.")
    await callback.message.delete()

async def cancel_task_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    await db.complete_task(task_id, callback.from_user.id, cancelled=True)
    await callback.answer("❌ Дело отменено.")
    await callback.message.delete()

async def done_routine_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO task_logs (task_id, user_id, due_date, completed, completed_at)
            VALUES ($1, $2, CURRENT_DATE, TRUE, NOW())
        """, task_id, user_id)
    await callback.answer("✅ Рутина выполнена!")
    await callback.message.delete()

async def skip_routine_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO task_logs (task_id, user_id, due_date, skipped, completed_at)
            VALUES ($1, $2, CURRENT_DATE, TRUE, NOW())
        """, task_id, user_id)
    await callback.answer("❌ Пропущено.")
    await callback.message.delete()

async def snooze_routine_handler(callback: types.CallbackQuery):
    await callback.answer("⏰ Напомню через 30 минут.")
    await callback.message.delete()

# ---------- Регистрация ----------
def register(dp: Dispatcher):
    dp.register_message_handler(planner_menu, text="📅 Мой день", state="*")
    dp.register_message_handler(what_today, text="📋 Что сегодня?", state="*")
    dp.register_message_handler(add_task_start, text="➕ Добавить дело", state="*")
    dp.register_message_handler(list_tasks, text="🗓️ Мои дела", state="*")
    dp.register_message_handler(add_routine_start, text="🔄 Добавить рутину", state="*")
    dp.register_message_handler(list_routines, text="📋 Мои рутины", state="*")

    dp.register_message_handler(add_task_title, state=AddTaskStates.title)
    dp.register_message_handler(add_task_date, state=AddTaskStates.date)
    dp.register_message_handler(add_task_time, state=AddTaskStates.time)
    dp.register_message_handler(add_task_remind, state=AddTaskStates.remind)

    dp.register_message_handler(add_routine_title, state=AddRoutineStates.title)
    dp.register_message_handler(add_routine_period, state=AddRoutineStates.period)
    dp.register_message_handler(add_routine_days, state=AddRoutineStates.days)
    dp.register_message_handler(add_routine_time, state=AddRoutineStates.time)
    dp.register_message_handler(add_routine_remind, state=AddRoutineStates.remind)

    dp.register_callback_query_handler(done_task_handler, lambda c: c.data.startswith('done_task_'))
    dp.register_callback_query_handler(postpone_task_handler, lambda c: c.data.startswith('postpone_task_'))
    dp.register_callback_query_handler(cancel_task_handler, lambda c: c.data.startswith('cancel_task_'))
    dp.register_callback_query_handler(done_routine_handler, lambda c: c.data.startswith('done_routine_'))
    dp.register_callback_query_handler(skip_routine_handler, lambda c: c.data.startswith('skip_routine_'))
    dp.register_callback_query_handler(snooze_routine_handler, lambda c: c.data.startswith('snooze_routine_'))
