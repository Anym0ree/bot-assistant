from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pb import db
from states import AIState
from keyboards import get_back_button, get_main_menu
from utils import edit_or_send
import ai_advisor as ai_adv_module

def escape_markdown(text: str) -> str:
    chars = r'_*[]()~`>#+-=|{}.!'
    for ch in chars:
        text = text.replace(ch, '\\' + ch)
    return text

async def ai_advice_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    history = data.get('history', [])

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
            await AIState.waiting_question.set()
            await message.answer("🤖 *Загружаю ваши данные для анализа...*", parse_mode="Markdown")
            advice = await ai_adv_module.ai_advisor.get_advice(user_id)
            advice = escape_markdown(advice)
            await message.answer(
                f"🤖 *Совет AI:*\n\n{advice}",
                parse_mode="Markdown",
                reply_markup=get_back_button()
            )
            await message.answer(
                "✏️ *Вы можете задать уточняющий вопрос* или написать /cancel для выхода.",
                parse_mode="Markdown"
            )
            await state.update_data(history=[{"role": "assistant", "content": advice}])
        else:
            await message.answer("❌ AI-модуль не инициализирован. Проверьте настройки.")
    else:
        await AIState.waiting_question.set()
        await message.answer(
            "🤖 *AI-совет активен*. Задайте свой вопрос.\n\n"
            "Если хотите выйти, напишите /cancel.",
            parse_mode="Markdown",
            reply_markup=get_back_button()
        )

async def ai_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text == "/cancel":
        await state.finish()
        if ai_adv_module.ai_advisor:
            ai_adv_module.ai_advisor.clear_user_data(user_id)
        await message.answer("✅ Выход из AI-режима.", reply_markup=get_main_menu())
        return
    if message.text == "⬅️ Назад":
        await state.finish()
        if ai_adv_module.ai_advisor:
            ai_adv_module.ai_advisor.clear_user_data(user_id)
        await message.answer("✅ Выход из AI-режима.", reply_markup=get_main_menu())
        return

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

    data = await state.get_data()
    history = data.get('history', [])
    history.append({"role": "user", "content": message.text})
    await message.bot.send_chat_action(message.chat.id, "typing")
    if ai_adv_module.ai_advisor:
        advice = await ai_adv_module.ai_advisor.get_advice(user_id, message.text, history)
        advice = escape_markdown(advice)
        history.append({"role": "assistant", "content": advice})
        await state.update_data(history=history)
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
