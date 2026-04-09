from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
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

# ПРОСМОТР СПИСКА С НОМЕРАМИ
async def view_food_drink_today(message: types.Message):
    user_id = message.from_user.id
    items = await db.get_today_food_and_drinks_with_ids(user_id)
    if not items:
        await message.answer("🍽🥤 За сегодня ещё нет записей о еде и напитках.", reply_markup=get_food_drink_menu())
        return

    text = "🍽🥤 *Еда и напитки сегодня:*\n\n"
    for idx, item in enumerate(items, start=1):
        text += f"{idx}. 🕐 {item['time']} — {item['type'].capitalize()}: {item['text']}\n"
    text += "\n✏️ *Команды:*\n`удалить еду <номер>` — удалить запись о еде\n`удалить напиток <номер>` — удалить запись о напитке\n\n*Пример:* `удалить еду 2`"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_food_drink_menu())

# ОБРАБОТЧИК КОМАНДЫ УДАЛЕНИЯ
async def delete_food_by_number(message: types.Message):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) != 3:
        await send_temp_message(message.chat.id, "❌ Неверный формат. Пиши: `удалить еду 2` или `удалить напиток 3`", 3)
        return
    action, what, num_str = parts[0], parts[1], parts[2]
    if action.lower() != "удалить":
        return
    try:
        num = int(num_str)
    except ValueError:
        await send_temp_message(message.chat.id, "❌ Номер должен быть числом.", 3)
        return

    items = await db.get_today_food_and_drinks_with_ids(user_id)
    if not items or num < 1 or num > len(items):
        await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно записей: {len(items)}", 3)
        return

    target = items[num - 1]
    if what.lower() == "еду" and target['type'] == 'food':
        success = await db.delete_food_by_id(user_id, target['id'])
        if success:
            await send_temp_message(message.chat.id, f"✅ Запись о еде удалена.", 2)
        else:
            await send_temp_message(message.chat.id, f"❌ Не удалось удалить.", 3)
    elif what.lower() == "напиток" and target['type'] == 'drink':
        success = await db.delete_drink_by_id(user_id, target['id'])
        if success:
            await send_temp_message(message.chat.id, f"✅ Запись о напитке удалена.", 2)
        else:
            await send_temp_message(message.chat.id, f"❌ Не удалось удалить.", 3)
    else:
        await send_temp_message(message.chat.id, f"❌ Несоответствие типа. Запись #{num} — это {target['type']}, а вы пытаетесь удалить {what}.", 3)

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
    dp.register_message_handler(delete_food_by_number, regexp=r'^удалить (еду|напиток) \d+$', state='*')
