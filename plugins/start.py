from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from keyboards import get_timezone_buttons, get_main_menu, get_back_button
from database_pg import db
from states import TimezoneStates, ReminderSetupStates
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish
from reminder_utils import save_reminder_settings, get_default_reminders
import re

CITY_TO_OFFSET = {
    "Москва (UTC+3)": 3, "Санкт-Петербург (UTC+3)": 3,
    "Екатеринбург (UTC+5)": 5, "Новосибирск (UTC+7)": 7,
    "Владивосток (UTC+10)": 10, "Калининград (UTC+2)": 2,
}

async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if await db.get_user_timezone(user_id) == 0:
        await message.answer(
            "👋 Привет! Я твой личный дневник-трекер.\n\n"
            "Для корректной работы мне нужно знать твой часовой пояс.\n"
            "Выбери свой город или нажми 'Другое' и введи смещение:",
            reply_markup=get_timezone_buttons()
        )
        await TimezoneStates.city.set()
    else:
        await message.answer(
            "👋 Привет! Я твой личный дневник-трекер.\n\n"
            "Что я умею:\n"
            "• 🛌 Записывать сон (один раз в день)\n"
            "• ⚡️ Делать чек-ины (энергия, стресс, эмоции)\n"
            "• 🍽🥤 Еда и напитки (добавление и просмотр)\n"
            "• 📝 Заметки и напоминания\n"
            "• 📝 Итог дня (с 18:00 до 6:00 утра)\n"
            "• 📊 Статистика\n"
            "• 📤 Экспорт (данные / скачивание с YouTube, SoundCloud, VK, Spotify и др.)\n"
            "• 🔄 Конвертер файлов (gif, mp4 и др.)\n"
            "• 🤖 AI-совет\n"
            "• ⚙️ Настройки\n\n"
            "Главное меню — /menu",
            reply_markup=get_main_menu()
        )

async def cmd_menu(message: types.Message, state: FSMContext):
    import ai_advisor as ai_adv_module
    if ai_adv_module.ai_advisor:
        ai_adv_module.ai_advisor.clear_user_data(message.from_user.id)
    await state.finish()
    await message.answer("Главное меню", reply_markup=get_main_menu())

async def timezone_city(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if message.text == "Другое":
        await TimezoneStates.offset.set()
        await edit_or_send(state, message.chat.id, "Введи смещение от UTC (например: -5, 0, +3):", get_back_button(), edit=False)
        return
    if message.text in CITY_TO_OFFSET:
        await db.set_user_timezone(message.from_user.id, CITY_TO_OFFSET[message.text])
        await delete_dialog_message(state)
        await state.finish()
        await message.answer(
            "✅ Часовой пояс сохранён.\n\n🔔 Хочешь включить напоминания?",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Да", "❌ Нет")
        )
        await ReminderSetupStates.ask.set()
        return
    await message.answer("Выбери город из кнопок или нажми «Другое».", reply_markup=get_timezone_buttons())

async def timezone_offset(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await TimezoneStates.city.set()
        await edit_or_send(state, message.chat.id, "Выбери свой город или нажми «Другое»:", get_timezone_buttons(), edit=True)
        return
    if message.text == "❌ Отмена":
        await safe_finish(state, message)
        return
    raw_value = message.text.strip().replace("UTC", "").replace("utc", "")
    if not re.fullmatch(r"[+-]?\d{1,2}", raw_value):
        await send_temp_message(message.chat.id, "❌ Введи число от -12 до +14 (например: -5, 0, +3).", 3)
        return
    offset = int(raw_value)
    if offset < -12 or offset > 14:
        await send_temp_message(message.chat.id, "❌ Смещение должно быть в диапазоне от -12 до +14.", 3)
        return
    await db.set_user_timezone(message.from_user.id, offset)
    await delete_dialog_message(state)
    await state.finish()
    await message.answer(
        "✅ Часовой пояс сохранён.\n\n🔔 Хочешь включить напоминания?",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Да", "❌ Нет")
    )
    await ReminderSetupStates.ask.set()

async def reminder_setup_ask(message: types.Message, state: FSMContext):
    if message.text == "❌ Нет":
        settings = get_default_reminders()
        settings["sleep"]["enabled"] = False
        settings["checkins"]["enabled"] = False
        settings["summary"]["enabled"] = False
        save_reminder_settings(message.from_user.id, settings)
        await state.finish()
        await message.answer("❌ Напоминания выключены", reply_markup=get_main_menu())
        return
    await message.answer(
        "Использовать стандартные настройки?\n\n"
        "🛌 Сон — 09:00\n⚡️ Чек-ины — 12:00, 16:00, 20:00\n📝 Итог дня — 22:30",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Да", "✏️ Настроить вручную")
    )
    await ReminderSetupStates.choose_mode.set()

async def reminder_setup_mode(message: types.Message, state: FSMContext):
    if message.text == "✅ Да":
        save_reminder_settings(message.from_user.id, get_default_reminders())
        await state.finish()
        await message.answer("✅ Напоминания включены со стандартными настройками!", reply_markup=get_main_menu())
    elif message.text == "✏️ Настроить вручную":
        await state.finish()
        from plugins.settings import reminder_settings_menu
        await reminder_settings_menu(message)
    else:
        await message.answer("Выбери вариант из кнопок.")

def register(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=['start'], state='*')
    dp.register_message_handler(cmd_menu, commands=['menu'], state='*')
    dp.register_message_handler(timezone_city, state=TimezoneStates.city)
    dp.register_message_handler(timezone_offset, state=TimezoneStates.offset)
    dp.register_message_handler(reminder_setup_ask, state=ReminderSetupStates.ask)
    dp.register_message_handler(reminder_setup_mode, state=ReminderSetupStates.choose_mode)
