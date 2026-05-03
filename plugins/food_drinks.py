# В функцию food_drink_menu добавить кнопку:
[KeyboardButton(text="👨‍🍳 Что приготовить?")]

# И новый хэндлер:
async def recipe_suggestion_start(message: types.Message, state: FSMContext):
    await message.answer("Напиши, какие продукты есть (через запятую), и AI предложит рецепты:",
                        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await FoodStates.recipe.set()  # нужно добавить стейт recipe в FoodStates

async def recipe_suggestion_get(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await food_drink_menu(message)
        return
    ingredients = message.text
    user_id = message.from_user.id
    prompt = f"У пользователя есть продукты: {ingredients}. Предложи 3 простых рецепта с этими продуктами. Пиши коротко: название и основные ингредиенты."
    advice = await ai_advisor.ai_advisor.get_advice(user_id, prompt) if ai_advisor.ai_advisor else None
    if advice:
        await message.answer(f"👨‍🍳 *Рецепты:*\n\n{advice}", parse_mode="Markdown")
    else:
        await message.answer("AI сейчас недоступен 😔")
    await state.finish()
    await food_drink_menu(message)
