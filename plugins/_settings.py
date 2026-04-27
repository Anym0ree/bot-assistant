import re
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import db
from keyboards import (
    get_main_menu, get_settings_keyboard, get_reminder_settings_keyboard,
    get_reminder_action_keyboard, get_hour_buttons, get_minute_buttons
)

logger = logging.getLogger(__name__)

# Состояния для FSM (тихий час, редактирование профиля, настройка времени напоминаний)
class SettingsStates(StatesGroup):
    waiting_for_dnd_start = State()
    waiting_for_dnd_end = State()
    waiting_for_profile_age = State()
    waiting_for_profile_height = State()
    waiting_for_profile_weight = State()
    waiting_for_sleep_time = State()
    waiting_for_checkins_times = State()
    waiting_for_summary_time = State()
    waiting_for_water_times = State()
    waiting_for_meals_times = State()
    waiting_for_reminder_type = State()  # какой тип напоминания настраиваем

async def settings_menu(message: types.Message, state: FSMContext):
    """Главное меню настроек"""
    await state.finish()
    await message.answer("⚙️ *Настройки бота*\nВыберите действие:", reply_markup=get_settings_keyboard(), parse_mode="Markdown")

# ========== ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ НАСТРОЕК ==========
async def change_timezone(message: types.Message, state: FSMContext):
    # Здесь можно вызвать старый выбор города (уже есть в start.py)
    # Для простоты вызовем команду смены города из другого модуля.
    # Но можно и просто попросить ввести смещение.
    await message.answer("Введи смещение часового пояса от UTC (например, +3 для Москвы, -5 для Нью-Йорка):")
    state = await state
    await state.set_state("waiting_for_timezone_offset")

async def reminder_settings(message: types.Message, state: FSMContext):
    """Меню настройки конкретных напоминаний"""
    await state.finish()
    await message.answer("🔔 Выбери тип напоминания для настройки:", reply_markup=get_reminder_settings_keyboard())

async def edit_profile(message: types.Message, state: FSMContext):
    await message.answer("Введите ваш возраст (число от 1 до 120):")
    await SettingsStates.waiting_for_profile_age.set()

async def toggle_ai(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    # Получить текущее состояние
    cur = await db.conn.execute("SELECT ai_enabled FROM user_settings WHERE user_id = $1", user_id)
    row = await cur.fetchone()
    current = row[0] if row else 1
    new_val = 0 if current else 1
    await db.conn.execute("""
        INSERT INTO user_settings (user_id, ai_enabled) VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET ai_enabled = $2
    """, user_id, new_val)
    await message.answer(f"🤖 AI-совет {'включён' if new_val else 'выключен'}")
    await settings_menu(message, state)

async def toggle_weekly_reports(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cur = await db.conn.execute("SELECT weekly_report_enabled FROM user_settings WHERE user_id = $1", user_id)
    row = await cur.fetchone()
    current = row[0] if row else 1
    new_val = 0 if current else 1
    await db.conn.execute("""
        INSERT INTO user_settings (user_id, weekly_report_enabled) VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET weekly_report_enabled = $2
    """, user_id, new_val)
    await message.answer(f"📊 Еженедельные отчёты {'включены' if new_val else 'выключены'}")
    await settings_menu(message, state)

async def quiet_hours(message: types.Message, state: FSMContext):
    await message.answer("Введи время начала тихого часа в формате ЧЧ:ММ (например, 23:00):")
    await SettingsStates.waiting_for_dnd_start.set()

async def back_to_main(message: types.Message, state: FSMContext):
    await state.finish()
    from keyboards import get_main_menu
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== НАСТРОЙКА НАПОМИНАНИЙ (выбор типа) ==========
async def reminder_choose_type(message: types.Message, state: FSMContext):
    text = message.text
    if text == "🛌 Сон":
        rem_type = "sleep"
        prompt = "Введи время для напоминания о сне (ЧЧ:ММ, например 09:00):"
    elif text == "⚡️ Чек-ины":
        rem_type = "checkins"
        prompt = "Введи время для чек-инов через запятую или пробел (например, 12:00, 16:00, 20:00):"
    elif text == "📝 Итог дня":
        rem_type = "summary"
        prompt = "Введи время для итога дня (ЧЧ:ММ, например 22:30):"
    elif text == "💧 Вода":
        rem_type = "water"
        prompt = "Введи время для напоминаний о воде через запятую (например, 10:00, 14:00, 18:00, 22:00):"
    elif text == "🍽 Еда":
        rem_type = "meals"
        prompt = "Введи время для приёмов пищи через запятую (например, 09:00, 13:00, 19:00):"
    elif text == "⬅️ Назад":
        await settings_menu(message, state)
        return
    else:
        await message.answer("Выбери из кнопок.")
        return
    await state.update_data(reminder_type=rem_type)
    await message.answer(prompt, reply_markup=get_reminder_action_keyboard())
    await SettingsStates.waiting_for_reminder_type.set()

async def reminder_action(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rem_type = data.get("reminder_type")
    if not rem_type:
        await reminder_settings(message, state)
        return

    user_id = message.from_user.id
    if message.text == "✅ Включить":
        await db.set_reminder_setting(user_id, rem_type, True, [])
        # Для получения текущего времени нужно сначала прочитать старое, но лучше попросить ввести время
        await message.answer("Введите время (в формате, который ожидается для этого типа):")
        # Здесь лучше перейти к вводу времени, а не просто включить без времени
        # Упростим: запросим ввод времени отдельно.
        return
    elif message.text == "❌ Выключить":
        await db.set_reminder_setting(user_id, rem_type, False, [])
        await message.answer(f"Напоминание выключено.")
        await reminder_settings(message, state)
    elif message.text == "🕐 Изменить время":
        # Переходим к вводу времени
        if rem_type == "sleep" or rem_type == "summary":
            await message.answer("Введите новое время в формате ЧЧ:ММ:")
            await SettingsStates.waiting_for_sleep_time.set() if rem_type == "sleep" else SettingsStates.waiting_for_summary_time.set()
        else:
            await message.answer("Введите новое время (одно или несколько через запятую):")
            if rem_type == "checkins":
                await SettingsStates.waiting_for_checkins_times.set()
            elif rem_type == "water":
                await SettingsStates.waiting_for_water_times.set()
            elif rem_type == "meals":
                await SettingsStates.waiting_for_meals_times.set()
    elif message.text == "⬅️ Назад":
        await reminder_settings(message, state)

# Обработчики ввода времени для каждого типа (пишем кратко)
async def set_sleep_time(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    if not re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", time_str):
        await message.answer("Неверный формат. Введи ЧЧ:ММ")
        return
    data = await state.get_data()
    rem_type = data.get("reminder_type")
    user_id = message.from_user.id
    # Включаем напоминание и устанавливаем время
    await db.set_reminder_setting(user_id, rem_type, True, [time_str])
    await message.answer(f"✅ Напоминание '{rem_type}' установлено на {time_str}")
    await reminder_settings(message, state)

async def set_checkins_times(message: types.Message, state: FSMContext):
    times_raw = message.text.strip()
    parts = re.split(r'[ ,;]+', times_raw)
    times = [t for t in parts if re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", t)]
    if not times:
        await message.answer("Неверный формат. Введи время через запятую, например 12:00, 16:00, 20:00")
        return
    data = await state.get_data()
    rem_type = data.get("reminder_type")
    user_id = message.from_user.id
    await db.set_reminder_setting(user_id, rem_type, True, times)
    await message.answer(f"✅ Напоминания '{rem_type}' установлены на {', '.join(times)}")
    await reminder_settings(message, state)

# Аналогично для water, meals (можно использовать одну функцию)
async def set_multiple_times(message: types.Message, state: FSMContext):
    # Универсальная функция для checkins, water, meals
    times_raw = message.text.strip()
    parts = re.split(r'[ ,;]+', times_raw)
    times = [t for t in parts if re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", t)]
    if not times:
        await message.answer("Неверный формат. Введи время через запятую.")
        return
    data = await state.get_data()
    rem_type = data.get("reminder_type")
    user_id = message.from_user.id
    await db.set_reminder_setting(user_id, rem_type, True, times)
    await message.answer(f"✅ Напоминания '{rem_type}' установлены на {', '.join(times)}")
    await reminder_settings(message, state)

# Обработчики для профиля (возраст, рост, вес)
async def profile_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
        if 1 <= age <= 120:
            await state.update_data(age=age)
            await message.answer("Введите рост (в см, от 50 до 250):")
            await SettingsStates.waiting_for_profile_height.set()
        else:
            await message.answer("Возраст должен быть от 1 до 120.")
    except:
        await message.answer("Введите число.")

async def profile_height(message: types.Message, state: FSMContext):
    try:
        height = int(message.text)
        if 50 <= height <= 250:
            await state.update_data(height=height)
            await message.answer("Введите вес (в кг, от 10 до 300):")
            await SettingsStates.waiting_for_profile_weight.set()
        else:
            await message.answer("Рост должен быть от 50 до 250.")
    except:
        await message.answer("Введите число.")

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
            await message.answer("Вес должен быть от 10 до 300.")
    except:
        await message.answer("Введите число.")

# Обработчики тихого часа
async def dnd_start(message: types.Message, state: FSMContext):
    if not re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", message.text):
        await message.answer("Неверный формат. Введи ЧЧ:ММ")
        return
    await state.update_data(dnd_start=message.text)
    await message.answer("Введите время окончания тихого часа (ЧЧ:ММ):")
    await SettingsStates.waiting_for_dnd_end.set()

async def dnd_end(message: types.Message, state: FSMContext):
    if not re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", message.text):
        await message.answer("Неверный формат.")
        return
    data = await state.get_data()
    start = data.get("dnd_start")
    end = message.text
    user_id = message.from_user.id
    await db.conn.execute("""
        INSERT INTO user_settings (user_id, do_not_disturb_start, do_not_disturb_end)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE SET do_not_disturb_start = $2, do_not_disturb_end = $3
    """, user_id, start, end)
    await db.conn.commit()
    await message.answer(f"✅ Тихий час установлен с {start} до {end}")
    await settings_menu(message, state)

# Обработчик для смены часового пояса (упрощённо)
async def set_timezone_offset(message: types.Message, state: FSMContext):
    try:
        offset = int(message.text)
        if -12 <= offset <= 14:
            await db.set_user_timezone(message.from_user.id, offset)
            await state.finish()
            await message.answer("✅ Часовой пояс обновлён.")
            await settings_menu(message, state)
        else:
            await message.answer("Смещение должно быть от -12 до +14")
    except:
        await message.answer("Введите целое число (например, +3)")

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(settings_menu, text="⚙️ Настройки", state="*")
    dp.register_message_handler(change_timezone, text="🌍 Сменить часовой пояс", state="*")
    dp.register_message_handler(reminder_settings, text="🔔 Настройка напоминаний", state="*")
    dp.register_message_handler(edit_profile, text="✏️ Редактировать профиль", state="*")
    dp.register_message_handler(toggle_ai, text="🤖 AI-совет (вкл/выкл)", state="*")
    dp.register_message_handler(toggle_weekly_reports, text="📊 Еженедельные отчёты (вкл/выкл)", state="*")
    dp.register_message_handler(quiet_hours, text="🕒 Тихий час", state="*")
    dp.register_message_handler(back_to_main, text="⬅️ Назад", state="*")

    dp.register_message_handler(reminder_choose_type, state="*", text=["🛌 Сон", "⚡️ Чек-ины", "📝 Итог дня", "💧 Вода", "🍽 Еда", "⬅️ Назад"])
    dp.register_message_handler(reminder_action, state=SettingsStates.waiting_for_reminder_type)

    dp.register_message_handler(set_sleep_time, state=SettingsStates.waiting_for_sleep_time)
    dp.register_message_handler(set_checkins_times, state=SettingsStates.waiting_for_checkins_times)
    dp.register_message_handler(set_multiple_times, state=SettingsStates.waiting_for_summary_time) # для итога дня одно время
    dp.register_message_handler(set_multiple_times, state=SettingsStates.waiting_for_water_times)
    dp.register_message_handler(set_multiple_times, state=SettingsStates.waiting_for_meals_times)

    dp.register_message_handler(profile_age, state=SettingsStates.waiting_for_profile_age)
    dp.register_message_handler(profile_height, state=SettingsStates.waiting_for_profile_height)
    dp.register_message_handler(profile_weight, state=SettingsStates.waiting_for_profile_weight)

    dp.register_message_handler(dnd_start, state=SettingsStates.waiting_for_dnd_start)
    dp.register_message_handler(dnd_end, state=SettingsStates.waiting_for_dnd_end)

    dp.register_message_handler(set_timezone_offset, state="waiting_for_timezone_offset")
