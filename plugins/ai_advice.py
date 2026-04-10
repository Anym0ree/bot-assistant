from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import AIState
from keyboards import get_back_button, get_main_menu
import ai_advisor as ai_adv_module

def escape_markdown(text: str) -> str:
    chars = r'_*[]()~`>#+-=|{}.!'
    for ch in chars:
        text = text.replace(ch, '\\' + ch)
    return text

async def ai_advice_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

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

def register(dp: Dispatcher):
    dp.register_message_handler(ai_advice_start, text="🤖 AI-совет", state="*")
    dp.register_message_handler(ai_question, state=AIState.waiting_question)
