from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from keyboards import get_timezone_buttons, get_main_menu, get_back_button
from database_pg import db
from states import TimezoneStates, ReminderSetupStates, ProfileStates
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
        # Проверяем, заполнен ли профиль
        profile = await db.get_user_profile(user_id)
        if profile['age'] == 0 or profile['height'] == 0 or profile['weight'] == 0:
            await message.answer(
                "📝 Давай заполним твой профиль для более точных рекомендаций.\n\n"
                "Сколько тебе лет? (напиши число)"
            )
            await ProfileStates.age.set()
        else:
            await show_main_menu(message)

async def show_main_menu(message: types.Message):
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

# ========== ПРОФИЛЬ (возраст, рост, вес) ==========
async def profile_age(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        return
    try:
        age = int(message.text)
        if 1 <= age <= 120:
            await state.update_data(age=age)
            await message.answer("📏 Какой у тебя рост? (в см, например 175)")
            await ProfileStates.height.set()
        else:
            await message.answer("❌ Возраст должен быть от 1 до 120. Попробуй ещё раз.")
    except ValueError:
        await message.answer("❌ Введи число. Сколько тебе лет?")

async def profile_height(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        return
    try:
        height = int(message.text)
        if 50 <= height <= 250:
            await state.update_data(height=height)
            await message.answer("⚖️ Какой у тебя вес? (в кг, например 70)")
            await ProfileStates.weight.set()
        else:
            await message.answer("❌ Рост должен быть от 50 до 250 см. Попробуй ещё раз.")
    except ValueError:
        await message.answer("❌ Введи число. Какой у тебя рост в см?")

async def profile_weight(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        return
    try:
        weight = int(message.text)
        if 10 <= weight <= 300:
            data = await state.get_data()
            await db.update_user_profile(message.from_user.id, age=data['age'], height=data['height'], weight=weight)
            await state.finish()
            await message.answer("✅ Профиль сохранён!\n\nТеперь я могу давать более точные советы с учётом твоего возраста, роста и веса.")
            await show_main_menu(message)
        else:
            await message.answer("❌ Вес должен быть от 10 до 300 кг. Попробуй ещё раз.")
    except ValueError:
        await message.answer("❌ Введи число. Какой у тебя вес в кг?")

# ========== ВЫБОР ЧАСОВОГО ПОЯСА (как было) ==========
async def timezone_city(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if message.text == "Другое":
        await TimezoneStates.offset.set()
        await edit_or
