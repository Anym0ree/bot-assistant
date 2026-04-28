import re
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import db
from keyboards import get_main_menu, get_settings_keyboard, get_reminder_settings_keyboard, get_reminder_action_keyboard

logger = logging.getLogger(__name__)

class SettingsStates(StatesGroup):
    waiting_for_dnd_start = State()
    waiting_for_dnd_end = State()
    waiting_for_profile_age = State()
    waiting_for_profile_height = State()
    waiting_for_profile_weight = State()
    waiting_reminder_time = State()
    waiting_for_timezone_offset = State()

async def settings_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("⚙️ *Настройки бота*", reply_markup=get_settings_keyboard(), parse_mode="Markdown")

async def change_timezone(message: types.Message, state: FSMContext):
    await message.answer("Введи смещение часового пояса от UTC (например, +3 для Москвы):")
    await SettingsStates.waiting_for_timezone_offset.set()

async def reminder_settings_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("🔔 Выбери тип напоминания:", reply_markup=get_reminder_settings_keyboard())

async def edit_profile(message: types.Message, state: FSMContext):
    await message.answer("Введи возраст (число от 1 до 120):")
    await SettingsStates.waiting_for_profile_age.set()

async def toggle_ai(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ai_enabled FROM user_settings WHERE user_id = $1", user_id)
        current = row['ai_enabled'] if row else 1
        new_val = 0 if current else 1
        await conn.execute("""
            INSERT INTO user_settings (user_id, ai_enabled) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET ai_enabled = $2
        """, user_id, new_val)
    await message.answer(f"🤖 AI-совет {'включён' if new_val else 'выключен'}")
    await settings_menu(message, state)

async def toggle_weekly_reports(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT weekly_report_enabled FROM user_settings WHERE user_id = $1", user_id)
        current = row['weekly_report_enabled'] if row else 1
        new_val = 0 if current else 1
        await conn.execute("""
            INSERT INTO user_settings (user_id, weekly_report_enabled) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET weekly_report_enabled = $2
        """, user_id, new_val)
    await message.answer(f"📊 Отчёты {'включены' if new_val else 'выключены'}")
    await settings_menu(message, state)

async def quiet_hours(message: types.Message, state: FSMContext):
    await message.answer("Введи начало тихого часа (ЧЧ:ММ):")
    await SettingsStates.waiting_for_dnd_start.set()

async def back_to_main(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Главное меню", reply_markup=get_main_menu())

async def reminder_choose_type(message: types.Message, state: FSMContext):
    text = message.text
    type_map = {
        "🛌 Сон": ("sleep", "Введи время для НАПОМИНАНИЯ о сне (ЧЧ:ММ, например 22:00):"),
        "⚡️ Чек-ины": ("checkins", "Введи время для чек-инов через запятую (12:00, 16:00, 20:00):"),
        "📝 Итог дня": ("summary", "Введи время для итога дня (ЧЧ:ММ, например 22:30):"),
        "💧 Вода": ("water", "Введи время для воды через запятую (10:00, 14:00, 18:00):"),
        "🍽 Еда": ("meals", "Введи время для приёмов пищи через запятую (09:00, 13:00, 19:00):")
    }
    if text in type_map:
        rem_type, prompt = type_map[text]
        await state.update_data(reminder_type=rem_type)
        await message.answer(prompt, reply_markup=get_reminder_action_keyboard())
        await SettingsStates.waiting_reminder_time.set()
    elif text == "⬅️ Назад":
        await settings_menu(message, state)
    else:
        await message.answer("Выбери из кнопок.")

async def reminder_action(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rem_type = data.get("reminder_type")
    if not rem_type:
        await reminder_settings_menu(message, state)
        return

    user_id = message.from_user.id
    if message.text == "✅ Включить":
        await message.answer("Введи время (в нужном формате):")
    elif message.text == "❌ Выключить":
        await db.set_reminder_setting(user_id, rem_type, False, [])
        await message.answer(f"Напоминание выключено.")
        await reminder_settings_menu(message, state)
    elif message.text == "🕐 Изменить время":
        await message.answer("Введи новое время (в нужном формате):")
    elif message.text == "⬅️ Назад":
        await reminder_settings_menu(message, state)
    else:
        await set_reminder_time(message, state)

async def set_reminder_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rem_type = data.get("reminder_type")
    if not rem_type:
        await reminder_settings_menu(message, state)
        return
    user_id = message.from_user.id
    time_str = message.text.strip()
    if rem_type in ("sleep", "summary"):
        if re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", time_str):
            await db.set_reminder_setting(user_id, rem_type, True, [time_str])
            await message.answer(f"✅ Напоминание {rem_type} установлено на {time_str}")
        else:
            await message.answer("❌ Неверный формат. Нужно ЧЧ:ММ")
    else:
        parts = re.split(r'[ ,;]+', time_str)
        times = [t for t in parts if re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", t)]
        if times:
            await db.set_reminder_setting(user_id, rem_type, True, times)
            await message.answer(f"✅ Напоминания {rem_type} установлены на {', '.join(times)}")
        else:
            await message.answer("❌ Неверный формат. Введи время через запятую (например, 12:00, 16:00)")
    await reminder_settings_menu(message, state)

async def profile_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
        if 1 <= age <= 120:
            await state.update_data(age=age)
            await message.answer("Введи рост (в см):")
            await SettingsStates.waiting_for_profile_height.set()
        else:
            await message.answer("❌ От 1 до 120.")
    except:
        await message.answer("❌ Введи число.")

async def profile_height(message: types.Message, state: FSMContext):
    try:
        height = int(message.text)
        if 50 <= height <= 250:
            await state.update_data(height=height)
            await message.answer("Введи вес (в кг):")
            await SettingsStates.waiting_for_profile_weight.set()
        else:
            await message.answer("❌ Рост 50-250 см.")
    except:
        await message.answer("❌ Введи число.")

async def profile_weight(message: types.Message, state: FSMContext):
    try:
        weight = int(message.text)
        if 10 <= weight <= 300:
            data = await state.get_data()
            await db.update_user_profile(message.from_user.id, age=data['age'], height=data['height'], weight=weight)
            await state.finish()
            await message.answer("✅ Профиль обновлён!")
            await settings_menu(message, state)
        else:
            await message.answer("❌ Вес 10-300 кг.")
    except:
        await message.answer("❌ Введи число.")

async def dnd_start(message: types.Message, state: FSMContext):
    if not re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", message.text):
        await message.answer("❌ Неверный формат. Введи ЧЧ:ММ")
        return
    await state.update_data(dnd_start=message.text)
    await message.answer("Введи конец тихого часа (ЧЧ:ММ):")
    await SettingsStates.waiting_for_dnd_end.set()

async def dnd_end(message: types.Message, state: FSMContext):
    if not re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", message.text):
        await message.answer("❌ Неверный формат.")
        return
    data = await state.get_data()
    start = data.get("dnd_start")
    end = message.text
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_settings (user_id, do_not_disturb_start, do_not_disturb_end)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET do_not_disturb_start = $2, do_not_disturb_end = $3
        """, user_id, start, end)
    await message.answer(f"✅ Тихий час установлен с {start} до {end}")
    await settings_menu(message, state)

async def set_timezone_offset(message: types.Message, state: FSMContext):
    try:
        offset = int(message.text)
        if -12 <= offset <= 14:
            await db.set_user_timezone(message.from_user.id, offset)
            await state.finish()
            await message.answer("✅ Часовой пояс обновлён.")
            await settings_menu(message, state)
        else:
            await message.answer("❌ Смещение от -12 до +14")
    except:
        await message.answer("❌ Введи целое число (например, +3)")

def register(dp: Dispatcher):
    dp.register_message_handler(settings_menu, text="⚙️ Настройки", state="*")
    dp.register_message_handler(change_timezone, text="🌍 Сменить часовой пояс", state="*")
    dp.register_message_handler(reminder_settings_menu, text="🔔 Настройка напоминаний", state="*")
    dp.register_message_handler(edit_profile, text="✏️ Редактировать профиль", state="*")
    dp.register_message_handler(toggle_ai, text="🤖 AI-совет (вкл/выкл)", state="*")
    dp.register_message_handler(toggle_weekly_reports, text="📊 Еженедельные отчёты (вкл/выкл)", state="*")
    dp.register_message_handler(quiet_hours, text="🕒 Тихий час", state="*")
    dp.register_message_handler(back_to_main, text="⬅️ Назад", state="*")
    dp.register_message_handler(reminder_choose_type, text=["🛌 Сон", "⚡️ Чек-ины", "📝 Итог дня", "💧 Вода", "🍽 Еда", "⬅️ Назад"], state="*")
    dp.register_message_handler(reminder_action, state=SettingsStates.waiting_reminder_time)
    dp.register_message_handler(set_reminder_time, state=SettingsStates.waiting_reminder_time)
    dp.register_message_handler(profile_age, state=SettingsStates.waiting_for_profile_age)
    dp.register_message_handler(profile_height, state=SettingsStates.waiting_for_profile_height)
    dp.register_message_handler(profile_weight, state=SettingsStates.waiting_for_profile_weight)
    dp.register_message_handler(dnd_start, state=SettingsStates.waiting_for_dnd_start)
    dp.register_message_handler(dnd_end, state=SettingsStates.waiting_for_dnd_end)
    dp.register_message_handler(set_timezone_offset, state=SettingsStates.waiting_for_timezone_offset)
