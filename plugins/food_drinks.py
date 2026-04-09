from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database_pg import db
from states import FoodDrinkStates, FoodStates, DrinkStates
from keyboards import get_food_drink_menu, get_food_drink_type_buttons, get_meal_type_buttons, get_drink_type_buttons, get_drink_amount_buttons, get_back_button, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def ask_add_another(message: types.Message, state: FSMContext):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить ещё", "🏠 Главное меню")
    await message.answer("✅ Добавлено! Что дальше?", reply_markup=kb)
    await state.set_state("waiting_add_another")

async def handle_add_another(message: types.Message, state: FSMContext):
    if message.text == "➕ Добавить ещё":
        await state.finish()
        await add_food_drink_start(message, state)
    else:
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def food_drink_menu(message: types.Message):
    await message.answer("🍽🥤 Еда и напитки\n\nВыбери действие:", reply_markup=get_food_drink_menu())

async def add_food_drink_start(message: types.Message, state: FSMContext):
    await FoodDrinkStates.type.set()
    await edit_or_send(state, message.chat.id, "Что хочешь добавить?", get_food_drink_type_buttons(), edit=False)

async def add_food_drink_type(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await food_drink_menu(message)
        return
    if message.text == "🍽 Еда":
        await state.finish()
        await FoodStates.meal_type.set()
        await edit_or_send(state, message.chat.id, "Что это за прием?", get_meal_type_buttons(), edit=False)
    elif message.text == "🥤 Напитки":
        await state.finish()
        await DrinkStates.drink_type.set()
        await edit_or_send(state, message.chat.id, "Что выпил?", get_drink_type_buttons(), edit=False)
    else:
        await edit_or_send(state, message.chat.id, "Выбери из предложенных вариантов.", get_food_drink_type_buttons(), edit=True)

# НОВАЯ ФУНКЦИЯ ПРОСМОТРА С УДАЛЕНИЕМ
async def view_food_drink_today(message: types.Message):
    user_id = message.from_user.id
    items = await db.get_today_food_and_drinks_with_ids(user_id)  # используем новый метод из database_pg
    if not items:
        await message.answer("🍽🥤 За сегодня ещё нет записей о еде и напитках.", reply_markup=get_food_drink_menu())
        return

    text = "🍽🥤 *Еда и напитки сегодня:*\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    for item in items:
        # item = {"id": int, "type": "food"/"drink", "time": str, "text": str}
        text += f"🕐 {item['time']} — {item['type'].capitalize()}: {item['text']}\n"
        callback_data = f"delete_food_{item['id']}" if item['type'] == 'food' else f"delete_drink_{item['id']}"
        keyboard.insert(InlineKeyboardButton(f"🗑 Удалить", callback_data=callback_data))
    text += "\n_Нажмите на кнопку удаления рядом с записью._"
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

# ОБРАБОТЧИК КНОПОК УДАЛЕНИЯ
async def delete_food_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data.startswith("delete_food_"):
        food_id = int(data.split("_")[2])
        success = await db.delete_food_by_id(user_id, food_id)
        if success:
            await callback_query.answer("✅ Запись о еде удалена", show_alert=False)
        else:
            await callback_query.answer("❌ Не найдено или уже удалено", show_alert=True)
    elif data.startswith("delete_drink_"):
        drink_id = int(data.split("_")[2])
        success = await db.delete_drink_by_id(user_id, drink_id)
        if success:
            await callback_query.answer("✅ Запись о напитке удалена", show_alert=False)
        else:
            await callback_query.answer("❌ Не найдено или уже удалено", show_alert=True)
    else:
        return

    # Обновляем сообщение – показываем актуальный список
    await view_food_drink_today(callback_query.message)

# ========== ДОБАВЛЕНИЕ ЕДЫ ==========
async def food_meal_type(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    await state.update_data(meal_type=message.text)
    await FoodStates.next()
    await edit_or_send(state, message.chat.id, "Что съел?", get_back_button(), edit=True)

async def food_text(message: types.Message, state: FSMContext):
    if message.text in ("⬅️ Назад", "❌ Отмена"):
        await safe_finish(state, message, "Добавление отменено")
        return
    data = await state.get_data()
    await db.add_food(message.from_user.id, data["meal_type"], message.text)
    await delete_dialog_message(state)
    await state.finish()
    await send_temp_message(message.chat.id, f"✅ Добавлено: {data['meal_type']} — {message.text}", 2)
    await ask_add_another(message, state)

# ========== ДОБАВЛЕНИЕ НАПИТКОВ ==========
async def drink_type(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    await state.update_data(drink_type=message.text)
    await DrinkStates.amount.set()
    await edit_or_send(state, message.chat.id, "Сколько?", get_drink_amount_buttons(), edit=True)

async def drink_amount(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if message.text == "Другое":
        await state.update_data(awaiting_custom_drink_amount=True)
        await edit_or_send(state, message.chat.id, "Введи количество (например: 0.5 л, 2 стакана):", get_back_button(), edit=True)
        return
    data = await state.get_data()
    if data.get("awaiting_custom_drink_amount"):
        if not message.text.strip():
            await edit_or_send(state, message.chat.id, "❌ Введи количество напитка текстом.", get_back_button(), edit=True)
            return
        await state.update_data(awaiting_custom_drink_amount=False)
    drink_type = data["drink_type"]
    amount = message.text
    await db.add_drink(message.from_user.id, drink_type, amount)
    await delete_dialog_message(state)
    await state.finish()
    await send_temp_message(message.chat.id, f"✅ Добавлено: {drink_type} — {amount}", 2)
    await ask_add_another(message, state)

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(food_drink_menu, text="🍽🥤 Еда и напитки", state="*")
    dp.register_message_handler(add_food_drink_start, text="➕ Добавить еду/напитки", state="*")
    dp.register_message_handler(add_food_drink_type, state=FoodDrinkStates.type)
    dp.register_message_handler(view_food_drink_today, text="📋 Посмотреть сегодня", state="*")
    dp.register_message_handler(food_meal_type, state=FoodStates.meal_type)
    dp.register_message_handler(food_text, state=FoodStates.food_text)
    dp.register_message_handler(drink_type, state=DrinkStates.drink_type)
    dp.register_message_handler(drink_amount, state=DrinkStates.amount)
    dp.register_message_handler(handle_add_another, state="waiting_add_another")
    dp.register_callback_query_handler(delete_food_callback, lambda c: c.data.startswith(("delete_food_", "delete_drink_")))
