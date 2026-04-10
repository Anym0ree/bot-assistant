from datetime import datetime, timedelta
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from keyboards import get_main_menu
import json

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
            "SELECT id, time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2 ORDER BY time",
            user_id, date_str
        )
        result['food'] = [dict(r) for r in food_rows]
        drink_rows = await conn.fetch(
            "SELECT id, time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2 ORDER BY time",
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
    text += "🛌 *Сон*:\n"
    if data['sleep']:
        s = data['sleep']
        woke_night = "Да" if s['woke_night'] else "Нет"
        text += f"   • Лег: {s['bed_time']}, встал: {s['wake_time']}\n"
        text += f"   • Качество: {s['quality']}/10, просыпался ночью: {woke_night}\n"
        if s['note']:
            text += f"   • Заметка: {s['note']}\n"
    else:
        text += "   • Нет записи\n"

    text += "\n⚡️ *Чек-ин*:\n"
    if data['checkin']:
        c = data['checkin']
        emotions = c['emotions']
        if emotions:
            try:
                emotions_list = json.loads(emotions)
                emotions = ", ".join(emotions_list)
            except:
                pass
        else:
            emotions = "не указаны"
        text += f"   • Время: {c['time']}\n"
        text += f"   • Энергия: {c['energy']}/10, стресс: {c['stress']}/10\n"
        text += f"   • Эмоции: {emotions}\n"
        if c['note']:
            text += f"   • Заметка: {c['note']}\n"
    else:
        text += "   • Нет записи\n"

    text += "\n🍽 *Еда*:\n"
    if data['food']:
        for idx, f in enumerate(data['food'], start=1):
            text += f"   {idx}. 🕐 {f['time']} — {f['meal_type']}: {f['food_text']}\n"
    else:
        text += "   • Нет записей\n"

    text += "\n🥤 *Напитки*:\n"
    if data['drinks']:
        for idx, d in enumerate(data['drinks'], start=1):
            text += f"   {idx}. 🕐 {d['time']} — {d['drink_type']}: {d['amount']}\n"
    else:
        text += "   • Нет записей\n"

    text += "\n📝 *Итог дня*:\n"
    if data['summary']:
        s = data['summary']
        text += f"   • Оценка: {s['score']}/10\n"
        if s['best']:
            text += f"   • Лучшее: {s['best']}\n"
        if s['worst']:
            text += f"   • Сложное: {s['worst']}\n"
        if s['gratitude']:
            text += f"   • Благодарность: {s['gratitude']}\n"
        if s['note']:
            text += f"   • Заметка: {s['note']}\n"
    else:
        text += "   • Нет записи\n"

    text += "\n📋 *Заметки*:\n"
    if data['notes']:
        for idx, n in enumerate(data['notes'], start=1):
            text += f"   {idx}. 🕐 {n['time']}: {n['text']}\n"
    else:
        text += "   • Нет заметок\n"

    # Добавляем инструкцию по редактированию
    text += "\n━━━━━━━━━━━━━━━━━━━━\n"
    text += "✏️ *Редактирование:*\n"
    if data['food']:
        text += "   • `редактировать еду <номер>` – изменить запись о еде\n"
    if data['drinks']:
        text += "   • `редактировать напиток <номер>` – изменить запись о напитке\n"
    if data['sleep']:
        text += "   • `редактировать сон <номер>` – изменить сон (номер из списка всех снов)\n"
    if data['checkin']:
        text += "   • `редактировать чек-ин <номер>` – изменить чек-ин\n"
    if data['summary']:
        text += "   • `редактировать итог <номер>` – изменить итог дня\n"
    text += "\n📌 *Номера для сна, чек-ина, итога дня можно посмотреть командами:*\n"
    text += "   • `мои сны` – список всех записей сна\n"
    text += "   • `мои чек-ины` – список всех чек-инов\n"
    text += "   • `мои итоги` – список всех итогов дня\n"
    text += "\n*Пример:* `редактировать еду 2` или `редактировать сон 1`"

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

# ========== КОМАНДЫ ДЛЯ ПРОСМОТРА ВСЕХ ЗАПИСЕЙ ==========
async def list_all_sleep(message: types.Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, date, bed_time, wake_time, quality FROM sleep WHERE user_id = $1 ORDER BY date DESC",
            user_id
        )
    if not rows:
        await message.answer("📋 У тебя пока нет записей о сне.")
        return
    text = "📋 *Все записи сна:*\n\n"
    for idx, row in enumerate(rows, start=1):
        text += f"{idx}. {row['date']}: лёг в {row['bed_time']}, встал в {row['wake_time']}, качество {row['quality']}/10\n"
    text += "\n✏️ *Редактирование:* `редактировать сон <номер>`\nПример: `редактировать сон 2`"
    await message.answer(text, parse_mode="Markdown")

async def list_all_checkins(message: types.Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, date, time, energy, stress FROM checkins WHERE user_id = $1 ORDER BY date DESC, time DESC",
            user_id
        )
    if not rows:
        await message.answer("📋 У тебя пока нет чек-инов.")
        return
    text = "📋 *Все чек-ины:*\n\n"
    for idx, row in enumerate(rows, start=1):
        text += f"{idx}. {row['date']} {row['time']}: энергия {row['energy']}/10, стресс {row['stress']}/10\n"
    text += "\n✏️ *Редактирование:* `редактировать чек-ин <номер>`\nПример: `редактировать чек-ин 2`"
    await message.answer(text, parse_mode="Markdown")

async def list_all_summaries(message: types.Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, date, score FROM day_summary WHERE user_id = $1 ORDER BY date DESC",
            user_id
        )
    if not rows:
        await message.answer("📋 У тебя пока нет итогов дня.")
        return
    text = "📋 *Все итоги дня:*\n\n"
    for idx, row in enumerate(rows, start=1):
        text += f"{idx}. {row['date']}: оценка {row['score']}/10\n"
    text += "\n✏️ *Редактирование:* `редактировать итог <номер>`\nПример: `редактировать итог 2`"
    await message.answer(text, parse_mode="Markdown")

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(history_start, text="📅 История", state="*")
    dp.register_message_handler(history_today, text="📅 Сегодня", state="*")
    dp.register_message_handler(history_yesterday, text="📆 Вчера", state="*")
    dp.register_message_handler(history_ask_date, text="✏️ Ввести дату", state="*")
    dp.register_message_handler(history_process_date, state="waiting_for_history_date")
    dp.register_message_handler(back_to_main, text="⬅️ Назад", state="*")
    # Команды с / (работают в любом месте)
    dp.register_message_handler(list_all_sleep, commands=['мои сны'], state='*')
    dp.register_message_handler(list_all_checkins, commands=['мои чек-ины'], state='*')
    dp.register_message_handler(list_all_summaries, commands=['мои итоги'], state='*')
    # Дублируем как текстовые (без /) – на всякий случай
    dp.register_message_handler(list_all_sleep, text="мои сны", state='*')
    dp.register_message_handler(list_all_checkins, text="мои чек-ины", state='*')
    dp.register_message_handler(list_all_summaries, text="мои итоги", state='*')
