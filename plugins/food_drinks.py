from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton   # ← ОБЯЗАТЕЛЬНО
from database import db
from states import FoodDrinkStates, FoodStates, DrinkStates
from keyboards import get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish
from plugins.achievements import track_action

async def food_drink_menu(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить еду/напитки", "📋 Посмотреть сегодня")
    kb.add("👨‍🍳 Что приготовить?", "⬅️ Назад")
    await message.answer("🍽🥤 Еда и напитки", reply_markup=kb)

async def add_food_drink_start(message: types.Message, state: FSMContext):
    await FoodDrinkStates.type.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🍽 Еда", "🥤 Напитки", "⬅️ Назад")
    await edit_or_send(state, message.chat.id, "Что добавить?", kb, edit=False)

async def add_food_drink_type(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await food_drink_menu(message)
        return
    if message.text == "🍽 Еда":
        await state.finish()
        await FoodStates.meal_type.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("🍳 Завтрак", "🍱 Обед", "🍲 Ужин", "🍎 Перекус")
        kb.add("⬅️ Назад")
        await edit_or_send(state, message.chat.id, "Тип приёма?", kb, edit=False)
    elif message.text == "🥤 Напитки":
        await state.finish()
        await DrinkStates.drink_type.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("💧 Вода", "☕️ Кофе", "🍵 Чай", "🥤 Сок / газировка")
        kb.add("⬅️ Назад")
        await edit_or_send(state, message.chat.id, "Что за напиток?", kb, edit=False)

async def view_food_drink_today(message: types.Message):
    user_id = message.from_user.id
    items = await db.get_today_food_and_drinks(user_id)
    if not items:
        await message.answer("За сегодня ещё нет записей.", reply_markup=get_main_menu())
        return
    text = "🍽🥤 *Сегодня:*\n"
    for i, item in enumerate(items, 1):
        text += f"{i}. {item['time']} — {item['text']}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())

async def recipe_start(message: types.Message, state: FSMContext):
    await message.answer("Напиши, какие продукты есть (через запятую):",
                        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await FoodStates.recipe.set()

async def recipe_get(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await food_drink_menu(message)
        return
    ingredients = message.text
    user_id = message.from_user.id
    from ai_advisor import ai_advisor
    advice = await ai_advisor.get_advice(user_id,
        f"У пользователя есть: {ingredients}. Предложи 3 простых рецепта с этими продуктами. Пиши коротко: название и ингредиенты.") if ai_advisor else None
    await state.finish()
    if advice:
        await message.answer(f"👨‍🍳 *Рецепты:*\n\n{advice}", parse_mode="Markdown")
    else:
        await message.answer("AI сейчас недоступен 😔")
    await food_drink_menu(message)

async def food_meal_type(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    await state.update_data(meal_type=message.text)
    await FoodStates.next()
    await edit_or_send(state, message.chat.id, "Что съел?",
                       ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")),
                       edit=True)

async def food_text(message: types.Message, state: FSMContext):
    if message.text in ("⬅️ Назад", "❌ Отмена"):
        await safe_finish(state, message, "Добавление отменено")
        return
    data = await state.get_data()
    await db.add_food(message.from_user.id, data["meal_type"], message.text)
    await track_action(message.from_user.id, "food", bot=message.bot)
    await delete_dialog_message(state)
    await state.finish()
    await message.answer(f"✅ Добавлено: {data['meal_type']} — {message.text}", reply_markup=get_main_menu())

async def drink_type(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    await state.update_data(drink_type=message.text)
    await DrinkStates.amount.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("1 стакан", "2 стакана", "500 мл", "1 л", "Другое")
    kb.add("⬅️ Назад")
    await edit_or_send(state, message.chat.id, "Сколько?", kb, edit=True)

async def drink_amount(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if message.text == "Другое":
        await state.update_data(awaiting_custom_drink_amount=True)
        await edit_or_send(state, message.chat.id, "✏️ Введи количество:",
                           ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")),
                           edit=True)
        return
    data = await state.get_data()
    if data.get("awaiting_custom_drink_amount"):
        await state.update_data(awaiting_custom_drink_amount=False)
    amount = message.text
    await db.add_drink(message.from_user.id, data["drink_type"], amount)
    await track_action(message.from_user.id, "drink", bot=message.bot)
    await delete_dialog_message(state)
    await state.finish()
    await message.answer(f"✅ Добавлено: {data['drink_type']} — {amount}", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(food_drink_menu, text="🍽🥤 Еда и напитки", state="*")
    dp.register_message_handler(add_food_drink_start, text="➕ Добавить еду/напитки", state="*")
    dp.register_message_handler(add_food_drink_type, state=FoodDrinkStates.type)
    dp.register_message_handler(view_food_drink_today, text="📋 Посмотреть сегодня", state="*")
    dp.register_message_handler(recipe_start, text="👨‍🍳 Что приготовить?", state="*")
    dp.register_message_handler(recipe_get, state=FoodStates.recipe)
    dp.register_message_handler(food_meal_type, state=FoodStates.meal_type)
    dp.register_message_handler(food_text, state=FoodStates.food_text)
    dp.register_message_handler(drink_type, state=DrinkStates.drink_type)
    dp.register_message_handler(drink_amount, state=DrinkStates.amount)
