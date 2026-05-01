import re
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu, get_settings_keyboard
from reminder_utils import load_reminder_settings, save_reminder_settings, get_default_reminders

logger = logging.getLogger(__name__)

class SettingsStates(StatesGroup):
    waiting_for_dnd_start = State()
    waiting_for_dnd_end = State()
    waiting_for_profile_age = State()
    waiting_for_profile_height = State()
    waiting_for_profile_weight = State()
    waiting_reminder_time = State()
    waiting_for_timezone_offset = State()

# ---------- Главное меню настроек ----------
async def settings_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("⚙️ *Настройки бота*", reply_markup=get_settings_keyboard(), parse_mode="Markdown")

# ---------- Часовой пояс ----------
async def change_timezone(message: types.Message, state: FSMContext):
    await message.answer("Введи смещение часового пояса от UTC (например, +3 для Москвы):")
    await SettingsStates.waiting_for_timezone_offset.set()

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

# ---------- Редактирование профиля ----------
async def edit_profile(message: types.Message, state: FSMContext):
    await message.answer("Введи возраст (число от 1 до 120):")
    await SettingsStates.waiting_for_profile_age.set()

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

# ---------- AI и отчёты ----------
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

# ---------- Тихий час ----------
async def quiet_hours(message: types.Message, state: FSMContext):
    await message.answer("Введи начало тихого часа (ЧЧ:ММ):")
    await SettingsStates.waiting_for_dnd_start.set()

async def dnd_start(message: types.Message, state: FSMContext):
    if not re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", message.text):
        await message.answer("❌ Неверный формат. Введи ЧЧ:ММ")
        return
    await state.update_data(dnd_start=message.text)
    await message.answer("Введи конец тихого часа (ЧЧ:ММ):")
    await SettingsStates.waiting_for_dnd_end.set()

async def dnd_end(message: types.Message, state: FSMContext):
    if not re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", message.text):
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

# ========== НАСТРОЙКА НАПОМИНАНИЙ ==========
REMINDER_TYPES = {
    "🛌 Сон": ("sleep", "Введи время для напоминания о сне (ЧЧ:ММ, например 22:00):"),
    "⚡️ Чек-ины": ("checkins", "Введи время для чек-инов через запятую (например: 12:00, 16:00, 20:00):"),
    "📝 Итог дня": ("summary", "Введи время для напоминания об итоге дня (ЧЧ:ММ, например 22:30):"),
    "💧 Вода": ("water", "Введи время для напоминаний о воде через запятую (например: 10:00, 14:00, 18:00):"),
    "🍽 Еда": ("meals", "Введи время для приёмов пищи через запятую (например: 09:00, 13:00, 19:00):"),
}

async def reminder_settings_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await SettingsStates.waiting_reminder_time.set()
    await message.answer("🔔 Выбери тип напоминания для настройки:", reply_markup=get_reminder_settings_keyboard())

def get_reminder_settings_keyboard():
    buttons = [
        [KeyboardButton(text="🛌 Сон")],
        [KeyboardButton(text="⚡️ Чек-ины")],
        [KeyboardButton(text="📝 Итог дня")],
        [KeyboardButton(text="💧 Вода")],
        [KeyboardButton(text="🍽 Еда")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def reminder_choose_type(message: types.Message, state: FSMContext):
    text = message.text
    if text not in REMINDER_TYPES:
        return

    rem_type, prompt_text = REMINDER_TYPES[text]
    user_id = message.from_user.id
    settings = await load_reminder_settings(user_id)

    curr = settings.get(rem_type, {"enabled": False, "times": []})
    status = "✅ Включено" if curr["enabled"] else "❌ Выключено"
    times_str = ", ".join(curr["times"]) if curr["times"] else "не задано"

    info = f"🔔 *{text}*\n\nСтатус: {status}\nВремя: {times_str}\n\nЧто сделать?"
    await state.update_data(reminder_type=rem_type)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if curr["enabled"]:
        kb.add(KeyboardButton("❌ Выключить уведомления"))
        kb.add(KeyboardButton("🕐 Изменить время"))
    else:
        kb.add(KeyboardButton("✅ Включить уведомления"))
    kb.add(KeyboardButton("⬅️ К списку напоминаний"), KeyboardButton("⬅️ Назад в настройки"))
    await message.answer(info, reply_markup=kb, parse_mode="Markdown")

async def reminder_action(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rem_type = data.get("reminder_type")
    if not rem_type:
        await reminder_settings_menu(message, state)
        return

    user_id = message.from_user.id
    text = message.text

    if text == "❌ Выключить уведомления":
        await db.set_reminder_setting(user_id, rem_type, False, [])
        await message.answer(f"🔕 Уведомления выключены.")
        await reminder_choose_type(message, state)
        return
    elif text == "✅ Включить уведомления":
        _, prompt_text = REMINDER_TYPES.get(rem_type, (None, ""))
        await message.answer(f"📝 Включение уведомлений.\n{prompt_text}")
        return
    elif text == "🕐 Изменить время":
        _, prompt_text = REMINDER_TYPES.get(rem_type, (None, ""))
        await message.answer(f"✏️ Изменение времени.\n{prompt_text}")
        return
    elif text == "⬅️ К списку напоминаний":
        await reminder_settings_menu(message, state)
        return
    elif text == "⬅️ Назад в настройки":
        await settings_menu(message, state)
        return
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
        if re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", time_str):
            await db.set_reminder_setting(user_id, rem_type, True, [time_str])
            await message.answer(f"✅ Напоминание установлено на {time_str}")
        else:
            await message.answer("❌ Неверный формат. Нужно ЧЧ:ММ (например, 22:00). Попробуй ещё раз.")
            return
    else:
        parts = re.split(r'[ ,;]+', time_str)
        times = [t for t in parts if re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", t)]
        if times:
            await db.set_reminder_setting(user_id, rem_type, True, times)
            await message.answer(f"✅ Напоминания установлены на {', '.join(times)}")
        else:
            await message.answer("❌ Неверный формат. Введи время через запятую (например, 12:00, 16:00). Попробуй ещё раз.")
            return

    await reminder_choose_type(message, state)

# ---------- Регистрация ----------
def register(dp: Dispatcher):
    dp.register_message_handler(settings_menu, text="⚙️ Настройки", state="*")
    dp.register_message_handler(change_timezone, text="🌍 Сменить часовой пояс", state="*")
    dp.register_message_handler(set_timezone_offset, state=SettingsStates.waiting_for_timezone_offset)
    dp.register_message_handler(edit_profile, text="✏️ Редактировать профиль", state="*")
    dp.register_message_handler(profile_age, state=SettingsStates.waiting_for_profile_age)
    dp.register_message_handler(profile_height, state=SettingsStates.waiting_for_profile_height)
    dp.register_message_handler(profile_weight, state=SettingsStates.waiting_for_profile_weight)
    dp.register_message_handler(toggle_ai, text="🤖 AI-совет (вкл/выкл)", state="*")
    dp.register_message_handler(toggle_weekly_reports, text="📊 Еженедельные отчёты (вкл/выкл)", state="*")
    dp.register_message_handler(quiet_hours, text="🕒 Тихий час", state="*")
    dp.register_message_handler(dnd_start, state=SettingsStates.waiting_for_dnd_start)
    dp.register_message_handler(dnd_end, state=SettingsStates.waiting_for_dnd_end)

    dp.register_message_handler(reminder_settings_menu, text="🔔 Настройка напоминаний", state="*")
    dp.register_message_handler(reminder_choose_type, text=list(REMINDER_TYPES.keys()), state=SettingsStates.waiting_reminder_time)
    dp.register_message_handler(reminder_action, state=SettingsStates.waiting_reminder_time)
