# Добавь в конец ai_advice.py
async def analyze_day_command(message: types.Message):
    """Анализирует конкретный день (пример: /анализ 2026-04-10)"""
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /анализ ГГГГ-ММ-ДД\nПример: /анализ 2026-04-10")
        return
    date_str = parts[1]
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except:
        await message.answer("❌ Неверный формат даты. Используй ГГГГ-ММ-ДД")
        return
    
    user_id = message.from_user.id
    # Загружаем данные, если ещё нет
    if ai_adv_module.ai_advisor and not ai_adv_module.ai_advisor.get_user_data(user_id):
        user_data = {
            "sleep": await db._load_json(user_id, "sleep.json"),
            "checkins": await db._load_json(user_id, "checkins.json"),
            "day_summary": await db._load_json(user_id, "day_summary.json"),
        }
        ai_adv_module.ai_advisor.set_user_data(user_id, user_data)
    
    await message.answer("🔍 Анализирую день...")
    result = await ai_adv_module.ai_advisor.analyze_day(user_id, date_str)
    await message.answer(result, parse_mode="Markdown")

# В register добавь:
dp.register_message_handler(analyze_day_command, commands=['анализ'], state='*')
