import re
import json
import os
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import TimezoneStates, ReminderCustomizeStates
from keyboards import get_settings_menu_no_reset, get_timezone_buttons, get_main_menu
from utils import send_temp_message, is_valid_time_text
from reminder_utils import load_reminder_settings, save_reminder_settings, get_default_reminders

REMINDER_FILE = "reminder_settings.json"

async def settings(message: types.Message):
    await message.answer(
        "⚙️ Настройки\n\nВыбери действие:",
        reply_markup=get_settings_menu_no_reset()
    )

async def change_city(message: types.Message):
    await message.answer(
        "🌍 Выбери свой город или введи смещение вручную:",
        reply_markup=get_timezone_buttons()
    )
    await TimezoneStates.city.set()

async def reminder_settings_menu(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛌 Сон", "⚡️ Чек-ины")
    kb.add("📝 Итог дня", "💧 Вода")
    kb.add("🍽 Еда", "⬅️ Назад")
    await message.answer("🔔 Выбери, для чего настроить напоминания:", reply_markup=kb)
    await ReminderCustomizeStates.waiting.set()

async def reminder_customize_choose(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await settings(message)
        return

    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()

    if message.text == "🛌 Сон":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        current_enabled = settings_data["sleep"]["enabled"]
        kb.add("✅ Включить" if not current_enabled else "❌ Выключить")
        kb.add("🕐 Изменить время")
        kb.add("⬅️ Назад")
        await message.answer(
            f"🛌 Напоминание о сне:\n"
            f"Состояние: {'✅ Включено' if current_enabled else '❌ Выключено'}\n"
            f"Время: {settings_data['sleep']['time']}\n\n"
            f"Что сделать?",
            reply_markup=kb
        )
        await state.set_state(ReminderCustomizeStates.sleep_menu)

    elif message.text == "⚡️ Чек-ины":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        current_enabled = settings_data["checkins"]["enabled"]
        kb.add("✅ Включить" if not current_enabled else "❌ Выключить")
        kb.add("🕐 Изменить время")
        kb.add("⬅️ Назад")
        times_str = ", ".join(settings_data["checkins"]["times"])
        await message.answer(
            f"⚡️ Напоминания о чек-инах:\n"
            f"Состояние: {'✅ Включено' if current_enabled else '❌ Выключено'}\n"
            f"Время: {times_str}\n\n"
            f"Что сделать?",
            reply_markup=kb
        )
        await state.set_state(ReminderCustomizeStates.checkins_menu)

    elif message.text == "📝 Итог дня":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        current_enabled = settings_data["summary"]["enabled"]
        kb.add("✅ Включить" if not current_enabled else "❌ Выключить")
        kb.add("🕐 Изменить время")
        kb.add("⬅️ Назад")
        await message.answer(
            f"📝 Напоминание об итоге дня:\n"
            f"Состояние: {'✅ Включено' if current_enabled else '❌ Выключено'}\n"
            f"Время: {settings_data['summary']['time']}\n\n"
            f"Что сделать?",
            reply_markup=kb
        )
        await state.set_state(ReminderCustomizeStates.summary_menu)

    elif message.text == "💧 Вода":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        current_enabled = settings_data.get("water", get_default_reminders()["water"])["enabled"]
        kb.add("✅ Включить" if not current_enabled else "❌ Выключить")
        kb.add("🕐 Изменить время")
        kb.add("⬅️ Назад")
        times_str = ", ".join(settings_data.get("water", get_default_reminders()["water"])["times"])
        await message.answer(
            f"💧 Напоминания о воде:\n"
            f"Состояние: {'✅ Включено' if current_enabled else '❌ Выключено'}\n"
            f"Время: {times_str}\n\n"
            f"Что сделать?",
            reply_markup=kb
        )
        await state.set_state(ReminderCustomizeStates.water_menu)

    elif message.text == "🍽 Еда":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        current_enabled = settings_data.get("meals", get_default_reminders()["meals"])["enabled"]
        kb.add("✅ Включить" if not current_enabled else "❌ Выключить")
        kb.add("🕐 Изменить время")
        kb.add("⬅️ Назад")
        times_str = ", ".join(settings_data.get("meals", get_default_reminders()["meals"])["times"])
        await message.answer(
            f"🍽 Напоминания о приёмах пищи:\n"
            f"Состояние: {'✅ Включено' if current_enabled else '❌ Выключено'}\n"
            f"Время: {times_str}\n\n"
            f"Что сделать?",
            reply_markup=kb
        )
        await state.set_state(ReminderCustomizeStates.meals_menu)

    else:
        await message.answer("Выбери из кнопок.")

# ----- НАСТРОЙКИ СНА (без изменений) -----
async def sleep_menu_action(message: types.Message, state: FSMContext):
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()

    if message.text == "✅ Включить":
        settings_data["sleep"]["enabled"] = True
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("✅ Напоминания о сне включены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "❌ Выключить":
        settings_data["sleep"]["enabled"] = False
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("❌ Напоминания о сне выключены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "🕐 Изменить время":
        await message.answer("🕐 Введи новое время для напоминания о сне в формате ЧЧ:ММ (например, 09:00):\n\nИли нажми «Назад» для отмены.")
        await state.set_state(ReminderCustomizeStates.change_sleep_time)
    elif message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
    else:
        await message.answer("Выбери действие из кнопок.")

async def change_sleep_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
        return

    if not is_valid_time_text(message.text):
        await message.answer("❌ Неверный формат. Введи время в формате ЧЧ:ММ (например, 09:00).\nИли нажми «Назад».")
        return

    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()
    settings_data["sleep"]["time"] = message.text
    save_reminder_settings(message.from_user.id, settings_data)
    await message.answer(f"✅ Время напоминания о сне изменено на {message.text}.")
    await state.finish()
    await reminder_settings_menu(message)

# ----- НАСТРОЙКИ ЧЕК-ИНОВ (без изменений) -----
async def checkins_menu_action(message: types.Message, state: FSMContext):
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()

    if message.text == "✅ Включить":
        settings_data["checkins"]["enabled"] = True
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("✅ Напоминания о чек-инах включены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "❌ Выключить":
        settings_data["checkins"]["enabled"] = False
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("❌ Напоминания о чек-инах выключены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "🕐 Изменить время":
        await message.answer("🕐 Введи время для чек-инов в формате ЧЧ:ММ через запятую или пробел.\nНапример: 12:00, 16:00, 20:00\n\nИли нажми «Назад».")
        await state.set_state(ReminderCustomizeStates.change_checkins_times)
    elif message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
    else:
        await message.answer("Выбери действие из кнопок.")

async def change_checkins_times(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
        return

    parts = re.split(r'[ ,;]+', message.text)
    times = []
    for part in parts:
        if is_valid_time_text(part.strip()):
            times.append(part.strip())
    if not times:
        await message.answer("❌ Не удалось распознать время. Введи время в формате ЧЧ:ММ через запятую или пробел (например, 12:00, 16:00, 20:00).\nИли нажми «Назад».")
        return

    times = sorted(set(times))
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()
    settings_data["checkins"]["times"] = times
    save_reminder_settings(message.from_user.id, settings_data)
    await message.answer(f"✅ Время чек-инов изменено: {', '.join(times)}.")
    await state.finish()
    await reminder_settings_menu(message)

# ----- НАСТРОЙКИ ИТОГА ДНЯ (без изменений) -----
async def summary_menu_action(message: types.Message, state: FSMContext):
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()

    if message.text == "✅ Включить":
        settings_data["summary"]["enabled"] = True
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("✅ Напоминания об итоге дня включены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "❌ Выключить":
        settings_data["summary"]["enabled"] = False
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("❌ Напоминания об итоге дня выключены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "🕐 Изменить время":
        await message.answer("🕐 Введи новое время для итога дня в формате ЧЧ:ММ (например, 22:30):\n\nИли нажми «Назад».")
        await state.set_state(ReminderCustomizeStates.change_summary_time)
    elif message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
    else:
        await message.answer("Выбери действие из кнопок.")

async def change_summary_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
        return

    if not is_valid_time_text(message.text):
        await message.answer("❌ Неверный формат. Введи время в формате ЧЧ:ММ (например, 22:30).\nИли нажми «Назад».")
        return

    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()
    settings_data["summary"]["time"] = message.text
    save_reminder_settings(message.from_user.id, settings_data)
    await message.answer(f"✅ Время итога дня изменено на {message.text}.")
    await state.finish()
    await reminder_settings_menu(message)

# ----- НАСТРОЙКИ ВОДЫ -----
async def water_menu_action(message: types.Message, state: FSMContext):
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()
    if "water" not in settings_data:
        settings_data["water"] = get_default_reminders()["water"]

    if message.text == "✅ Включить":
        settings_data["water"]["enabled"] = True
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("✅ Напоминания о воде включены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "❌ Выключить":
        settings_data["water"]["enabled"] = False
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("❌ Напоминания о воде выключены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "🕐 Изменить время":
        await message.answer("🕐 Введи время для напоминаний о воде в формате ЧЧ:ММ через запятую или пробел.\nНапример: 10:00, 14:00, 18:00, 22:00\n\nИли нажми «Назад».")
        await state.set_state(ReminderCustomizeStates.change_water_times)
    elif message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
    else:
        await message.answer("Выбери действие из кнопок.")

async def change_water_times(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
        return

    parts = re.split(r'[ ,;]+', message.text)
    times = []
    for part in parts:
        if is_valid_time_text(part.strip()):
            times.append(part.strip())
    if not times:
        await message.answer("❌ Не удалось распознать время. Введи время в формате ЧЧ:ММ через запятую или пробел.\nИли нажми «Назад».")
        return

    times = sorted(set(times))
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()
    if "water" not in settings_data:
        settings_data["water"] = get_default_reminders()["water"]
    settings_data["water"]["times"] = times
    save_reminder_settings(message.from_user.id, settings_data)
    await message.answer(f"✅ Время напоминаний о воде изменено: {', '.join(times)}.")
    await state.finish()
    await reminder_settings_menu(message)

# ----- НАСТРОЙКИ ЕДЫ (приёмы пищи) -----
async def meals_menu_action(message: types.Message, state: FSMContext):
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()
    if "meals" not in settings_data:
        settings_data["meals"] = get_default_reminders()["meals"]

    if message.text == "✅ Включить":
        settings_data["meals"]["enabled"] = True
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("✅ Напоминания о приёмах пищи включены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "❌ Выключить":
        settings_data["meals"]["enabled"] = False
        save_reminder_settings(message.from_user.id, settings_data)
        await message.answer("❌ Напоминания о приёмах пищи выключены.")
        await state.finish()
        await reminder_settings_menu(message)
    elif message.text == "🕐 Изменить время":
        await message.answer("🕐 Введи время для приёмов пищи в формате ЧЧ:ММ через запятую или пробел.\nНапример: 09:00, 13:00, 19:00\n\nИли нажми «Назад».")
        await state.set_state(ReminderCustomizeStates.change_meals_times)
    elif message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
    else:
        await message.answer("Выбери действие из кнопок.")

async def change_meals_times(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await reminder_settings_menu(message)
        return

    parts = re.split(r'[ ,;]+', message.text)
    times = []
    for part in parts:
        if is_valid_time_text(part.strip()):
            times.append(part.strip())
    if not times:
        await message.answer("❌ Не удалось распознать время. Введи время в формате ЧЧ:ММ через запятую или пробел.\nИли нажми «Назад».")
        return

    times = sorted(set(times))
    settings_data = load_reminder_settings(message.from_user.id)
    if not settings_data:
        settings_data = get_default_reminders()
    if "meals" not in settings_data:
        settings_data["meals"] = get_default_reminders()["meals"]
    settings_data["meals"]["times"] = times
    save_reminder_settings(message.from_user.id, settings_data)
    await message.answer(f"✅ Время приёмов пищи изменено: {', '.join(times)}.")
    await state.finish()
    await reminder_settings_menu(message)

# ========== РЕГИСТРАЦИЯ (добавлены новые состояния) ==========
def register(dp: Dispatcher):
    dp.register_message_handler(settings, text="⚙️ Настройки", state="*")
    dp.register_message_handler(change_city, text="🌍 Сменить город", state="*")
    dp.register_message_handler(reminder_settings_menu, text="🔔 Настройка напоминаний", state="*")
    dp.register_message_handler(reminder_customize_choose, state=ReminderCustomizeStates.waiting)
    dp.register_message_handler(sleep_menu_action, state=ReminderCustomizeStates.sleep_menu)
    dp.register_message_handler(change_sleep_time, state=ReminderCustomizeStates.change_sleep_time)
    dp.register_message_handler(checkins_menu_action, state=ReminderCustomizeStates.checkins_menu)
    dp.register_message_handler(change_checkins_times, state=ReminderCustomizeStates.change_checkins_times)
    dp.register_message_handler(summary_menu_action, state=ReminderCustomizeStates.summary_menu)
    dp.register_message_handler(change_summary_time, state=ReminderCustomizeStates.change_summary_time)
    dp.register_message_handler(water_menu_action, state=ReminderCustomizeStates.water_menu)
    dp.register_message_handler(change_water_times, state=ReminderCustomizeStates.change_water_times)
    dp.register_message_handler(meals_menu_action, state=ReminderCustomizeStates.meals_menu)
    dp.register_message_handler(change_meals_times, state=ReminderCustomizeStates.change_meals_times)
