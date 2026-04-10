from datetime import datetime, timedelta
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from keyboards import get_main_menu

async def get_user_data_for_date(user_id: int, date_str: str):
    result = {}
    async with db.pool.acquire() as conn:
        sleep = await conn.fetchrow(
            "SELECT bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1 AND date = $2",
            user_id, date_str
        )
        result['sleep'] = dict(sleep) if sleep else None
        checkin = await conn.fetchrow(
            "SELECT time, energy, stress, emotions, note FROM checkins WHERE user_id = $1 AND date = $2 ORDER BY time LIMIT 1",
            user_id, date_str
        )
        result['checkin'] = dict(checkin) if checkin else None
        food_rows = await conn.fetch(
            "SELECT time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2 ORDER BY time",
            user_id, date_str
        )
        result['food'] = [dict(r) for r in food_rows]
        drink_rows = await conn.fetch(
            "SELECT time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2 ORDER BY time",
            user_id, date_str
        )
        result['drinks'] = [dict(r) for r in drink_rows]
        summary = await conn.fetchrow(
            "SELECT score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1 AND date = $2",
            user_id, date_str
        )
        result['summary'] = dict(summary) if summary else None
        notes = await conn.fetch(
            "SELECT text, time FROM notes WHERE user_id = $1 AND date = $2 ORDER BY time",
            user_id, date_str
        )
        result['notes'] = [dict(r) for r in notes]
    return result

def format_user_data(data: dict, date_str: str) -> str:
    text = f"📅 *{date_str}*\n\n"
    if data['sleep']:
        s = data['sleep']
        woke_night = "Да" if s['woke_night'] else "Нет"
        text += f"🛌 *Сон*: лёг в {s['bed_time']}, встал в {s['wake_time']}, качество {s['quality']}/10, просыпался ночью: {woke_night}\n"
        if s['note']:
            text += f"   📝 {s['note']}\n"
    else:
        text += "🛌 *Сон*: не записан\n"
    if data['checkin']:
        c = data['checkin']
        emotions = c['emotions']
        if emotions:
            try:
                import json
                emotions = json.loads(emotions)
                emotions = ", ".join(emotions)
            except:
                emotions = str(emotions)
        else:
            emotions = "не указаны"
        text += f"⚡️ *Чек-ин*: энергия {c['energy']}/10, стресс {c['stress']}/10, эмоции: {emotions}\n"
        if c['note']:
            text += f"   📝 {c['note']}\n"
    else:
        text += "⚡️ *Чек-ин*: не записан\n"
    if data['food']:
        text += "🍽 *Еда*:\n"
        for f in data['food']:
            text += f"   🕐 {f['time']} — {f['meal_type']}: {f['food_text']}\n"
    else:
        text += "🍽 *Еда*: нет записей\n"
    if data['drinks']:
        text += "🥤 *Напитки*:\n"
        for d in data['drinks']:
            text += f"   🕐 {d['time']} — {d['drink_type']}: {d['amount']}\n"
    else:
        text += "🥤 *Напитки*: нет записей\n"
    if data['summary']:
        s = data['summary']
        text += f"📝 *Итог дня*: оценка {s['score']}/10\n"
        if s['best']:
            text += f"   🌟 Лучшее: {s['best']}\n"
        if s['worst']:
            text += f"   😟 Сложное: {s['worst']}\n"
        if s['gratitude']:
            text += f"   🙏 Благодарность: {s['gratitude']}\n"
        if s['note']:
            text += f"   📝 {s['note']}\n"
    else:
        text += "📝 *Итог дня*: не подведён\n"
    if data['notes']:
        text += "📋 *Заметки*:\n"
        for n in data['notes']:
            text += f"   🕐 {n['time']}: {n['text']}\n"
    else:
        text += "📋 *Заметки*: нет\n"
    return text

async def history_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📅 Сегодня", "📆 Вчера")
    kb.add("✏️ Ввести дату", "⬅️ Назад")
    await message.answer(
        "📅 Выбери день, чтобы посмотреть историю:\n"
        "• «Сегодня» или «Вчера»\n"
        "• «Ввести дату» – в формате ГГГГ-ММ-ДД (например, 2026-04-01)",
        reply_markup=kb
    )

async def history_today(message: types.Message):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    date_str = now_local.strftime("%Y-%m-%d")
    await show_history(message, date_str)

async def history_yesterday(message: types.Message):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    yesterday = now_local - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    await show_history(message, date_str)

async def history_ask_date(message: types.Message, state: FSMContext):
    await message.answer("📅 Введи дату в формате ГГГГ-ММ-ДД (например, 2026-04-01):\n\nИли нажми «Назад» для отмены.")
    await state.set_state("waiting_for_history_date")

async def history_process_date(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await history_start(message)
        return
    date_str = message.text.strip()
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи дату как ГГГГ-ММ-ДД, например 2026-04-01.")
        return
    await state.finish()
    await show_history(message, date_str)

async def show_history(message: types.Message, date_str: str):
    user_id = message.from_user.id
    data = await get_user_data_for_date(user_id, date_str)
    text = format_user_data(data, date_str)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📅 История", "⬅️ Назад")
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def back_to_main(message: types.Message):
    await message.answer("Главное меню", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(history_start, text="📅 История", state="*")
    dp.register_message_handler(history_today, text="📅 Сегодня", state="*")
    dp.register_message_handler(history_yesterday, text="📆 Вчера", state="*")
    dp.register_message_handler(history_ask_date, text="✏️ Ввести дату", state="*")
    dp.register_message_handler(history_process_date, state="waiting_for_history_date")
    dp.register_message_handler(back_to_main, text="⬅️ Назад", state="*")
