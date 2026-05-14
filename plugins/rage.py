from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database import db
from keyboards import get_main_menu
import ai_advisor

class RageStates(StatesGroup):
    ready = State()
    reason = State()

async def rage_start(message: types.Message, state: FSMContext):
    """Кнопка 🆘 Срыв в главном меню"""
    await state.finish()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Готов"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer(
        "🆘 *Срыв*\n\n"
        "Сделай 10 отжиманий или просто глубоко вдохни.\n"
        "Как будешь готов — жми кнопку.",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await RageStates.ready.set()

async def rage_ready(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return

    if message.text == "✅ Готов":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("📝 Рассказать"), KeyboardButton("▶️ Продолжить"))
        await message.answer(
            "Если хочешь выговориться — расскажи, что именно взбесило.\n"
            "Я просто выслушаю. Если нет — нажми «Продолжить».",
            reply_markup=kb
        )
        await RageStates.reason.set()

async def rage_reason(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "▶️ Продолжить":
        await state.finish()
        await message.answer("Это пройдёт. Ты справляешься 💪", reply_markup=get_main_menu())
        return

    # Пользователь написал причину – даём осмысленный ответ через AI
    reason = message.text
    await state.finish()

    # Пробуем получить AI‑совет с учётом контекста
    advice = None
    if ai_advisor.ai_advisor:
        try:
            # Собираем контекст: последние чекины, цели, стиль
            ctx = await ai_advisor.ai_advisor.collect_user_context(user_id)
            prompt = (
                f"Пользователь в состоянии срыва. Его причина: '{reason}'. "
                f"Данные: стресс {ctx.get('checkin', {}).get('stress', '?')}/10, "
                f"энергия {ctx.get('checkin', {}).get('energy', '?')}/10. "
                f"Цели: {ctx.get('goals', 'нет')}. "
                f"Ответь коротко (1-2 предложения) с поддержкой и конкретным советом, "
                f"учитывая его состояние и цели. Без общих фраз."
            )
            advice = await ai_advisor.ai_advisor.get_advice(user_id, prompt)
        except:
            pass

    if advice:
        text = f"🧠 *Совет:*\n{advice}"
    else:
        text = "Это пройдёт. Ты справляешься 💪"

    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")

def register(dp: Dispatcher):
    dp.register_message_handler(rage_start, text="🆘 Срыв", state="*")
    dp.register_message_handler(rage_ready, state=RageStates.ready)
    dp.register_message_handler(rage_reason, state=RageStates.reason)
