from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import AIState, ProfileStates
from keyboards import get_back_button, get_main_menu
import ai_advisor as ai_adv_module

def escape_markdown(text: str) -> str:
    chars = r'_*[]()~`>#+-=|{}.!'
    for ch in chars:
        text = text.replace(ch, '\\' + ch)
    return text

async def check_profile_and_continue(message: types.Message, state: FSMContext, user_id: int):
    """Проверяет профиль и продолжает AI-режим"""
    profile = await db.get_user_profile(user_id)
    missing = []
    if profile['age'] == 0:
        missing.append("возраст")
    if profile['height'] == 0:
        missing.append("рост")
    if profile['weight'] == 0:
        missing.append("вес")
    
    if missing:
        await state.update_data(return_to_ai=True)
        await message.answer(
            f"📝 Для более точных рекомендаций мне нужно знать твои данные.\n\n"
            f"Укажи, пожалуйста, свой {', '.join(missing)}.\n\n"
            f"Начнём с возраста: сколько тебе лет?"
        )
        await ProfileStates.age.set()
        return False
    return True

async def ai_advice_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем профиль
    profile = await db.get_user_profile(user_id)
    if profile['age'] == 0 or profile['height'] == 0 or profile['weight'] == 0:
        await state.update_data(return_to_ai=True)
        await message.answer(
            "📝 Для более точных рекомендаций AI нужно знать твои данные.\n\n"
            "Сколько тебе лет? (напиши число)"
        )
        await ProfileStates.age.set()
        return

    # Профиль заполнен – запускаем AI
    await start_ai(message, state, user_id)

async def start_ai(message: types.Message, state: FSMContext, user_id: int):
    history = await db.get_ai_history(user_id, limit=10)
    if not history:
        user_data = {
            "sleep": await db._load_json(user_id, "sleep.json"),
            "checkins": await db._load_json(user_id, "checkins.json"),
            "day_summary": await db._load_json(user_id, "day_summary.json"),
            "notes": await db._load_json(user_id, "notes.json"),
            "reminders": await db._load_json(user_id, "reminders.json"),
            "food": await db._load_json(user_id, "food.json"),
            "drinks": await db._load_json(user_id, "drinks.json")
        }
        if ai_adv_module.ai_advisor:
            ai_adv_module.ai_advisor.set_user_data(user_id, user_data)
            first_message = await ai_adv_module.ai_advisor.get_first_advice(user_id)
            await message.answer(first_message, parse_mode="Markdown", reply_markup=get_back_button())
            await db.save_ai_message(user_id, "assistant", first_message)
        else:
            await message.answer("❌ AI-модуль не инициализирован. Проверьте настройки.")
            return

    await AIState.waiting_question.set()
    await message.answer(
        "✏️ *Задай свой вопрос* или напиши /cancel для выхода.\n\n"
        "Я помню предыдущие вопросы и могу дать совет на основе всей истории.",
        parse_mode="Markdown",
        reply_markup=get_back_button()
    )

# ========== ЗАПОЛНЕНИЕ ПРОФИЛЯ ==========
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
            
            # Проверяем, нужно ли вернуться в AI
            return_to_ai = data.get('return_to_ai', False)
            await state.finish()
            
            await message.answer("✅ Профиль сохранён! Теперь я могу давать более точные советы.")
            
            if return_to_ai:
                await start_ai(message, state, message.from_user.id)
            else:
                await message.answer("Главное меню", reply_markup=get_main_menu())
        else:
            await message.answer("❌ Вес должен быть от 10 до 300 кг. Попробуй ещё раз.")
    except ValueError:
        await message.answer("❌ Введи число. Какой у тебя вес в кг?")

async def safe_finish(state: FSMContext, message: types.Message):
    await state.finish()
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== ОСНОВНОЙ AI ДИАЛОГ ==========
async def ai_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "/cancel":
        await state.finish()
        await db.clear_ai_history(user_id)
        if ai_adv_module.ai_advisor:
            ai_adv_module.ai_advisor.clear_user_data(user_id)
        await message.answer("✅ История диалога очищена. Выход из AI-режима.", reply_markup=get_main_menu())
        return

    if message.text == "⬅️ Назад":
        await state.finish()
        await db.clear_ai_history(user_id)
        if ai_adv_module.ai_advisor:
            ai_adv_module.ai_advisor.clear_user_data(user_id)
        await message.answer("✅ Выход из AI-режима.", reply_markup=get_main_menu())
        return

    history = await db.get_ai_history(user_id, limit=10)
    await db.save_ai_message(user_id, "user", message.text)

    if ai_adv_module.ai_advisor and not ai_adv_module.ai_advisor.get_user_data(user_id):
        user_data = {
            "sleep": await db._load_json(user_id, "sleep.json"),
            "checkins": await db._load_json(user_id, "checkins.json"),
            "day_summary": await db._load_json(user_id, "day_summary.json"),
            "notes": await db._load_json(user_id, "notes.json"),
            "reminders": await db._load_json(user_id, "reminders.json"),
            "food": await db._load_json(user_id, "food.json"),
            "drinks": await db._load_json(user_id, "drinks.json"),
        }
        ai_adv_module.ai_advisor.set_user_data(user_id, user_data)

    await message.bot.send_chat_action(message.chat.id, "typing")
    if ai_adv_module.ai_advisor:
        advice = await ai_adv_module.ai_advisor.get_advice(user_id, message.text, history)
        advice = escape_markdown(advice)
        await db.save_ai_message(user_id, "assistant", advice)
        await message.answer(
            f"🤖 *Ответ:*\n\n{advice}",
            parse_mode="Markdown",
            reply_markup=get_back_button()
        )
    else:
        await message.answer("❌ AI-модуль недоступен.")

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(ai_advice_start, text="🤖 AI-совет", state="*")
    dp.register_message_handler(ai_question, state=AIState.waiting_question)
    dp.register_message_handler(profile_age, state=ProfileStates.age)
    dp.register_message_handler(profile_height, state=ProfileStates.height)
    dp.register_message_handler(profile_weight, state=ProfileStates.weight)
