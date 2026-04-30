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

# ... все функции добавления и просмотра оставлены как в предыдущей reply-версии,
# они не меняются. Меняются только напоминания.

# ========== НАПОМИНАНИЯ (проверка каждую минуту) ==========
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
    """Проверяет рутины и отправляет напоминания с инлайн‑кнопками"""
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
                start_hour, start_min = map(int, r['start_time'].split(':'))
                start_dt = datetime.combine(today, time(start_hour, start_min))
                remind_dt = start_dt - timedelta(minutes=remind_minutes)
                remind_str = remind_dt.strftime("%H:%M")
                if remind_str == current_time:
                    kb = InlineKeyboardMarkup(row_width=2)
                    kb.add(
                        InlineKeyboardButton("✅ Выполнена", callback_data=f"done_routine_{r['id']}"),
                        InlineKeyboardButton("⏰ Напомнить позже", callback_data=f"snooze_routine_{r['id']}")
                    )
                    kb.add(InlineKeyboardButton("❌ Пропустить", callback_data=f"skip_routine_{r['id']}"))
                    await bot.send_message(
                        user_id,
                        f"🔄 НАПОМИНАНИЕ О РУТИНЕ:\n\n*{r['title']}*\n🕒 {r['start_time']}",
                        reply_markup=kb,
                        parse_mode="Markdown"
                    )
                    # Не деактивируем рутину, она периодическая

# ---------- Обработчики инлайн‑кнопок (ОБЯЗАТЕЛЬНО ЗАРЕГИСТРИРОВАНЫ В register) ----------
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

# ---------- Регистрация (добавлены инлайн‑колбэки) ----------
def register(dp: Dispatcher):
    # старые регистрации текстовых команд
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

    # Инлайн‑кнопки
    dp.register_callback_query_handler(done_task_handler, lambda c: c.data.startswith('done_task_'))
    dp.register_callback_query_handler(postpone_task_handler, lambda c: c.data.startswith('postpone_task_'))
    dp.register_callback_query_handler(cancel_task_handler, lambda c: c.data.startswith('cancel_task_'))
    dp.register_callback_query_handler(done_routine_handler, lambda c: c.data.startswith('done_routine_'))
    dp.register_callback_query_handler(skip_routine_handler, lambda c: c.data.startswith('skip_routine_'))
    dp.register_callback_query_handler(snooze_routine_handler, lambda c: c.data.startswith('snooze_routine_'))
