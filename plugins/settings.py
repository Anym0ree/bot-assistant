import re
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu, get_settings_keyboard
from reminder_utils import load_reminder_settings, get_default_reminders

logger = logging.getLogger(__name__)

class SettingsStates(StatesGroup):
    waiting_for_dnd_start = State()
    waiting_for_dnd_end = State()
    waiting_for_profile_age = State()
    waiting_for_profile_height = State()
    waiting_for_profile_weight = State()
    waiting_reminder_time = State()
    waiting_reminder_value = State()
    waiting_for_timezone_offset = State()
    waiting_for_city = State()

# ========== ГЛАВНОЕ МЕНЮ НАСТРОЕК ==========
async def settings_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("⚙️ *Настройки бота*", reply_markup=get_settings_keyboard(), parse_mode="Markdown")

# ========== ЧАСОВОЙ ПОЯС ==========
async def change_timezone(message: types.Message, state: FSMContext):
    await message.answer("Введи смещение от UTC (например: +3 для Москвы, -5 для Нью-Йорка):")
    await SettingsStates.waiting_for_timezone_offset.set()

async def set_timezone_offset(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await settings_menu(message, state)
        return
    try:
        offset = int(message.text)
        if -12 <= offset <= 14:
            await db.set_user_timezone(message.from_user.id, offset)
            await state.finish()
            await message.answer(f"✅ Часовой пояс установлен: UTC{'+' if offset >= 0 else ''}{offset}")
            await settings_menu(message, state)
        else:
            await message.answer("❌ Смещение должно быть от -12 до +14.")
    except:
        await message.answer("❌ Введи целое число (например, +3).")

# ========== ГОРОД (для погоды) ==========
async def set_city_start(message: types.Message, state: FSMContext):
    await message.answer("🏙️ Введи название города для прогноза погоды:")
    await SettingsStates.waiting_for_city.set()

async def set_city_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await settings_menu(message, state)
        return
    city = message.text.strip()
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_locations (user_id, city, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (user_id) DO UPDATE SET city = $2, updated_at = NOW()",
            user_id, city
        )
    await state.finish()
    await message.answer(f"✅ Город установлен: {city}")
    await settings_menu(message, state)

# ========== ПРОФИЛЬ ==========
async def edit_profile(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    profile = await db.get_user_profile(user_id)
    await message.answer(
        f"📝 *Твой профиль*\n\n"
        f"Возраст: {profile['age'] or 'не указан'}\n"
        f"Рост: {profile['height'] or 'не указан'} см\n"
        f"Вес: {profile['weight'] or 'не указан'} кг\n\n"
        f"Что хочешь изменить?\n"
        f"[🔄 Возраст] [🔄 Рост] [🔄 Вес] [⬅️ Назад]",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(
            KeyboardButton("🔄 Возраст"), KeyboardButton("🔄 Рост"), KeyboardButton("🔄 Вес"), KeyboardButton("⬅️ Назад")
        )
    )

async def profile_age_start(message: types.Message, state: FSMContext):
    await message.answer("Введи возраст (1-120):")
    await SettingsStates.waiting_for_profile_age.set()

async def profile_age_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await edit_profile(message, state)
        return
    try:
        age = int(message.text)
        if 1 <= age <= 120:
            await db.update_user_profile(message.from_user.id, age=age)
            await state.finish()
            await message.answer(f"✅ Возраст: {age}")
            await edit_profile(message, state)
        else:
            await message.answer("❌ От 1 до 120.")
    except:
        await message.answer("❌ Введи число.")

async def profile_height_start(message: types.Message, state: FSMContext):
    await message.answer("Введи рост в см (50-250):")
    await SettingsStates.waiting_for_profile_height.set()

async def profile_height_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await edit_profile(message, state)
        return
    try:
        height = int(message.text)
        if 50 <= height <= 250:
            await db.update_user_profile(message.from_user.id, height=height)
            await state.finish()
            await message.answer(f"✅ Рост: {height} см")
            await edit_profile(message, state)
        else:
            await message.answer("❌ От 50 до 250 см.")
    except:
        await message.answer("❌ Введи число.")

async def profile_weight_start(message: types.Message, state: FSMContext):
    await message.answer("Введи вес в кг (10-300):")
    await SettingsStates.waiting_for_profile_weight.set()

async def profile_weight_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await edit_profile(message, state)
        return
    try:
        weight = int(message.text)
        if 10 <= weight <= 300:
            await db.update_user_profile(message.from_user.id, weight=weight)
            await state.finish()
            await message.answer(f"✅ Вес: {weight} кг")
            await edit_profile(message, state)
        else:
            await message.answer("❌ От 10 до 300 кг.")
    except:
        await message.answer("❌ Введи число.")

# ========== AI И ОТЧЁТЫ ==========
async def toggle_ai(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ai_enabled FROM user_settings WHERE user_id = $1", user_id)
        current = row['ai_enabled'] if row else 1
        new_val = 0 if current else 1
        await conn.execute("INSERT INTO user_settings (user_id, ai_enabled) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET ai_enabled = $2", user_id, new_val)
    await message.answer(f"🤖 AI-совет: {'✅ Вкл' if new_val else '❌ Выкл'}")
    await settings_menu(message, state)

async def toggle_weekly_reports(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT weekly_report_enabled FROM user_settings WHERE user_id = $1", user_id)
        current = row['weekly_report_enabled'] if row else 1
        new_val = 0 if current else 1
        await conn.execute("INSERT INTO user_settings (user_id, weekly_report_enabled) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET weekly_report_enabled = $2", user_id, new_val)
    await message.answer(f"📊 Еженедельные отчёты: {'✅ Вкл' if new_val else '❌ Выкл'}")
    await settings_menu(message, state)

# ========== ТИХИЙ ЧАС ==========
async def quiet_hours_start(message: types.Message, state: FSMContext):
    await message.answer("Введи начало тихого часа (ЧЧ:ММ):")
    await SettingsStates.waiting_for_dnd_start.set()

async def dnd_start(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await settings_menu(message, state)
        return
    if not re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", message.text):
        await message.answer("❌ Неверный формат. ЧЧ:ММ (например, 23:00).")
        return
    await state.update_data(dnd_start=message.text)
    await message.answer("Введи конец тихого часа (ЧЧ:ММ):")
    await SettingsStates.waiting_for_dnd_end.set()

async def dnd_end(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await settings_menu(message, state)
        return
    if not re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", message.text):
        await message.answer("❌ Неверный формат.")
        return
    data = await state.get_data()
    start = data.get("dnd_start")
    end = message.text
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("INSERT INTO user_settings (user_id, do_not_disturb_start, do_not_disturb_end) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET do_not_disturb_start = $2, do_not_disturb_end = $3", user_id, start, end)
    await state.finish()
    await message.answer(f"✅ Тихий час: {start} – {end}")
    await settings_menu(message, state)

# ========== НАСТРОЙКА УВЕДОМЛЕНИЙ (Reply-кнопки) ==========
REMINDER_TYPES = {
    "🛌 Сон": "sleep",
    "⚡️ Чек-ины": "checkins",
    "📝 Итог дня": "summary",
    "💧 Вода": "water",
    "🍽 Еда": "meals",
}

REMINDER_HINTS = {
    "sleep": "Введи время для сна (ЧЧ:ММ):",
    "checkins": "Введи времена через запятую (12:00, 16:00, 20:00):",
    "summary": "Введи время для итога дня (ЧЧ:ММ):",
    "water": "Введи времена через запятую (10:00, 14:00, 18:00):",
    "meals": "Введи времена через запятую (09:00, 13:00, 19:00):",
}

async def reminder_settings_menu(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    settings = await load_reminder_settings(user_id)

    text = "⏰ *Уведомления об опросах*\n\n"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for label, key in REMINDER_TYPES.items():
        s = settings.get(key, {"enabled": False, "times": []})
        status = "✅" if s["enabled"] else "❌"
        times_str = ", ".join(s.get("times", [])) if s.get("times") else "—"
        text += f"{status} {label}: {times_str}\n"
        kb.add(KeyboardButton(f"{'❌' if s['enabled'] else '✅'} {label}"))
    text += "\n🕐 *Изменить время:* нажми кнопку с типом"
    kb.add(KeyboardButton("⚙️ Сбросить на стандартные"), KeyboardButton("⬅️ Назад"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await SettingsStates.waiting_reminder_time.set()

async def reminder_toggle(message: types.Message, state: FSMContext):
    text = message.text
    # Проверяем, это кнопка «✅ Тип» или «❌ Тип»
    for label, key in REMINDER_TYPES.items():
        if text in [f"✅ {label}", f"❌ {label}"]:
            user_id = message.from_user.id
            settings = await load_reminder_settings(user_id)
            curr = settings.get(key, {"enabled": False, "times": []})
            new_enabled = text.startswith("❌")  # если нажали "❌ Сон" — значит хотим выключить
            # Инвертируем: если сейчас включено (стоит ❌), выключаем; если выключено (✅), включаем
            if text.startswith("❌"):
                new_enabled = False
            else:
                new_enabled = True
                if not curr.get("times"):
                    defaults = get_default_reminders()
                    curr["times"] = defaults.get(key, {}).get("times", [])
            await db.set_reminder_setting(user_id, key, new_enabled, curr.get("times", []))
            await reminder_settings_menu(message, state)
            return

    # Проверяем, это запрос на изменение времени
    for label, key in REMINDER_TYPES.items():
        if text == f"🕐 {label}":
            await state.update_data(edit_reminder_key=key)
            await message.answer(f"✏️ {REMINDER_HINTS[key]}")
            return

    if text == "⚙️ Сбросить на стандартные":
        user_id = message.from_user.id
        defaults = get_default_reminders()
        for key, val in defaults.items():
            await db.set_reminder_setting(user_id, key, val["enabled"], val.get("times", []))
        await message.answer("✅ Сброшено на стандартные настройки.")
        await reminder_settings_menu(message, state)
        return

    if text == "⬅️ Назад":
        await state.finish()
        await settings_menu(message, state)
        return

    # Иначе — пользователь ввёл время
    await set_reminder_time(message, state)

async def set_reminder_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("edit_reminder_key")
    if not key:
        await reminder_settings_menu(message, state)
        return

    user_id = message.from_user.id
    time_str = message.text.strip()

    if key in ("sleep", "summary"):
        if re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", time_str):
            await db.set_reminder_setting(user_id, key, True, [time_str])
            await message.answer(f"✅ Время для {key} обновлено: {time_str}")
        else:
            await message.answer("❌ Неверный формат. ЧЧ:ММ (например, 22:00).")
            return
    else:
        parts = re.split(r'[ ,;]+', time_str)
        times = [t for t in parts if re.match(r"^(2[0-3]|[01]?\d):[0-5]\d$", t)]
        if times:
            await db.set_reminder_setting(user_id, key, True, times)
            await message.answer(f"✅ Время для {key} обновлено: {', '.join(times)}")
        else:
            await message.answer("❌ Неверный формат. Например: 12:00, 16:00")
            return

    await state.update_data(edit_reminder_key=None)
    await reminder_settings_menu(message, state)

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(settings_menu, text="⚙️ Настройки", state="*")
    dp.register_message_handler(change_timezone, text="🌍 Сменить часовой пояс", state="*")
    dp.register_message_handler(set_timezone_offset, state=SettingsStates.waiting_for_timezone_offset)
    dp.register_message_handler(set_city_start, text="🏙️ Указать город", state="*")
    dp.register_message_handler(set_city_save, state=SettingsStates.waiting_for_city)
    dp.register_message_handler(edit_profile, text="✏️ Редактировать профиль", state="*")
    dp.register_message_handler(profile_age_start, text="🔄 Возраст", state="*")
    dp.register_message_handler(profile_age_save, state=SettingsStates.waiting_for_profile_age)
    dp.register_message_handler(profile_height_start, text="🔄 Рост", state="*")
    dp.register_message_handler(profile_height_save, state=SettingsStates.waiting_for_profile_height)
    dp.register_message_handler(profile_weight_start, text="🔄 Вес", state="*")
    dp.register_message_handler(profile_weight_save, state=SettingsStates.waiting_for_profile_weight)
    dp.register_message_handler(toggle_ai, text="🤖 AI-совет (вкл/выкл)", state="*")
    dp.register_message_handler(toggle_weekly_reports, text="📊 Еженедельные отчёты (вкл/выкл)", state="*")
    dp.register_message_handler(quiet_hours_start, text="🕒 Тихий час", state="*")
    dp.register_message_handler(dnd_start, state=SettingsStates.waiting_for_dnd_start)
    dp.register_message_handler(dnd_end, state=SettingsStates.waiting_for_dnd_end)
    dp.register_message_handler(reminder_settings_menu, text="🔔 Настройка напоминаний", state="*")
    dp.register_message_handler(reminder_toggle, state=SettingsStates.waiting_reminder_time)
