import re
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from plugins.weather import update_geo

from database import db
from keyboards import get_main_menu, get_settings_keyboard

logger = logging.getLogger(__name__)

class SettingsStates(StatesGroup):
    waiting_for_dnd_start = State()
    waiting_for_dnd_end = State()
    waiting_for_profile_age = State()
    waiting_for_profile_height = State()
    waiting_for_profile_weight = State()
    waiting_for_timezone_offset = State()

async def settings_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("⚙️ *Настройки бота*", reply_markup=get_settings_keyboard(), parse_mode="Markdown")

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

async def toggle_ai(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ai_enabled FROM user_settings WHERE user_id = $1", user_id)
        current = row['ai_enabled'] if row else 1
        new_val = 0 if current else 1
        await conn.execute("INSERT INTO user_settings (user_id, ai_enabled) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET ai_enabled = $2", user_id, new_val)
    await message.answer(f"🤖 AI-совет {'включён' if new_val else 'выключен'}")
    await settings_menu(message, state)

async def toggle_weekly_reports(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT weekly_report_enabled FROM user_settings WHERE user_id = $1", user_id)
        current = row['weekly_report_enabled'] if row else 1
        new_val = 0 if current else 1
        await conn.execute("INSERT INTO user_settings (user_id, weekly_report_enabled) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET weekly_report_enabled = $2", user_id, new_val)
    await message.answer(f"📊 Отчёты {'включены' if new_val else 'выключены'}")
    await settings_menu(message, state)

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
        await conn.execute("INSERT INTO user_settings (user_id, do_not_disturb_start, do_not_disturb_end) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET do_not_disturb_start = $2, do_not_disturb_end = $3", user_id, start, end)
    await message.answer(f"✅ Тихий час установлен с {start} до {end}")
    await settings_menu(message, state)

# ========== ВКЛ/ВЫКЛ УВЕДОМЛЕНИЙ ОБ ОПРОСАХ ==========
REMINDER_TOGGLE_MAP = {
    "🛌 Уведомления о сне": ("sleep", "сне"),
    "⚡️ Уведомления о чек-инах": ("checkins", "чек-инах"),
    "📝 Уведомления об итогах": ("summary", "итогах дня"),
}

async def reminder_toggle_menu(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    settings = await load_reminder_settings(user_id)
    
    text = "🔔 *Уведомления об опросах*\n\n"
    text += "Нажми на кнопку чтобы включить/выключить:\n"
    for label, (key, name) in REMINDER_TOGGLE_MAP.items():
        status = "✅" if settings.get(key, {}).get("enabled", False) else "❌"
        text += f"{status} {label}\n"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for label in REMINDER_TOGGLE_MAP:
        kb.add(KeyboardButton(label))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

async def reminder_toggle_handler(message: types.Message, state: FSMContext):
    text = message.text
    if text not in REMINDER_TOGGLE_MAP:
        if text == "⬅️ Назад":
            await settings_menu(message, state)
        return
    
    key, name = REMINDER_TOGGLE_MAP[text]
    user_id = message.from_user.id
    settings = await load_reminder_settings(user_id)
    curr = settings.get(key, {"enabled": False, "times": []})
    new_enabled = not curr["enabled"]
    
    # сохраняем время по умолчанию если включили впервые
    if new_enabled and not curr["times"]:
        defaults = get_default_reminders()
        curr["times"] = defaults.get(key, {}).get("times", [])
    
    await db.set_reminder_setting(user_id, key, new_enabled, curr.get("times", []))
    
    status_text = "включены" if new_enabled else "выключены"
    await message.answer(f"🔔 Уведомления о {name} {status_text}.")
    await reminder_toggle_menu(message, state)

def register(dp: Dispatcher):
    dp.register_message_handler(update_geo, text="📍 Обновить гео", state="*")
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
    dp.register_message_handler(reminder_toggle_menu, text="🔔 Настройка напоминаний", state="*")
    dp.register_message_handler(reminder_toggle_handler, text=list(REMINDER_TOGGLE_MAP.keys()), state="*")
