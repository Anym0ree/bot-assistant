import calendar
from datetime import datetime, timedelta
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database_pg import db
from keyboards import get_main_menu

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_month_calendar(year: int, month: int, user_tz_offset: int) -> InlineKeyboardMarkup:
    """Генерирует инлайн-клавиатуру календаря на месяц."""
    # Определяем первый день недели (понедельник = 0, но в calendar по умолчанию воскресенье)
    cal = calendar.monthcalendar(year, month)
    # Корректируем, чтобы первый день был понедельник: сдвигаем дни
    # В calendar.monthcalendar() дни недели: 0 - понедельник? Нет, по умолчанию 0 - понедельник? Проверим.
    # На самом деле calendar.monthcalendar возвращает недели, где понедельник — 0, воскресенье — 6.
    # Поэтому всё нормально.
    keyboard = InlineKeyboardMarkup(row_width=7)
    # Заголовок с названием месяца и года
    month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                   'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    keyboard.add(InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="ignore"))
    # Дни недели
    week_days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    keyboard.add(*[InlineKeyboardButton(day, callback_data="ignore") for day in week_days])
    # Дни месяца
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                # Формируем callback_data с датой
                date_str = f"{year}-{month:02d}-{day:02d}"
                row.append(InlineKeyboardButton(str(day), callback_data=f"hist_date_{date_str}"))
        keyboard.add(*row)
    # Кнопки навигации
    nav_buttons = []
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"hist_cal_{prev_year}_{prev_month}"))
    nav_buttons.append(InlineKeyboardButton("Сегодня", callback_data="hist_today"))
    nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"hist_cal_{next_year}_{next_month}"))
    keyboard.add(*nav_buttons)
    keyboard.add(InlineKeyboardButton("⬅️ Назад в меню", callback_data="hist_back_to_menu"))
    return keyboard

async def get_user_data_for_date(user_id: int, date_str: str):
    """Получает все записи пользователя за указанную дату."""
    result = {}
    # Сон
    async with db.pool.acquire() as conn:
        sleep = await conn.fetchrow(
            "SELECT bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1 AND date = $2",
            user_id, date_str
        )
        result['sleep'] = dict(sleep) if sleep else None
        # Чек-ин
        checkin = await conn.fetchrow(
            "SELECT time, energy, stress, emotions, note FROM checkins WHERE user_id = $1 AND date = $2 ORDER BY time LIMIT 1",
            user_id, date_str
        )
        result['checkin'] = dict(checkin) if checkin else None
        # Еда
        food_rows = await conn.fetch(
            "SELECT time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2 ORDER BY time",
            user_id, date_str
        )
        result['food'] = [dict(r) for r in food_rows]
        # Напитки
        drink_rows = await conn.fetch(
            "SELECT time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2 ORDER BY time",
            user_id, date_str
        )
        result['drinks'] = [dict(r) for r in drink_rows]
        # Итог дня
        summary = await conn.fetchrow(
            "SELECT score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1 AND date = $2",
            user_id, date_str
        )
        result['summary'] = dict(summary) if summary else None
        # Заметки
        notes = await conn.fetch(
            "SELECT text, time FROM notes WHERE user_id = $1 AND date = $2 ORDER BY time",
            user_id, date_str
        )
        result['notes'] = [dict(r) for r in notes]
    return result

def format_user_data(data: dict, date_str: str) -> str:
    """Форматирует данные за день в читаемый текст."""
    text = f"📅 *{date_str}*\n\n"
    # Сон
    if data['sleep']:
        s = data['sleep']
        woke_night = "Да" if s['woke_night'] else "Нет"
        text += f"🛌 *Сон*: лёг в {s['bed_time']}, встал в {s['wake_time']}, качество {s['quality']}/10, просыпался ночью: {woke_night}\n"
        if s['note']:
            text += f"   📝 {s['note']}\n"
    else:
        text += "🛌 *Сон*: не записан\n"
    # Чек-ин
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
    # Еда
    if data['food']:
        text += "🍽 *Еда*:\n"
        for f in data['food']:
            text += f"   🕐 {f['time']} — {f['meal_type']}: {f['food_text']}\n"
    else:
        text += "🍽 *Еда*: нет записей\n"
    # Напитки
    if data['drinks']:
        text += "🥤 *Напитки*:\n"
        for d in data['drinks']:
            text += f"   🕐 {d['time']} — {d['drink_type']}: {d['amount']}\n"
    else:
        text += "🥤 *Напитки*: нет записей\n"
    # Итог дня
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
    # Заметки
    if data['notes']:
        text += "📋 *Заметки*:\n"
        for n in data['notes']:
            text += f"   🕐 {n['time']}: {n['text']}\n"
    else:
        text += "📋 *Заметки*: нет\n"
    return text

# ========== ОБРАБОТЧИКИ ==========
async def history_start(message: types.Message):
    """Показывает календарь за текущий месяц."""
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    year, month = now_local.year, now_local.month
    keyboard = get_month_calendar(year, month, tz)
    await message.answer("📅 Выбери дату, чтобы посмотреть историю:", reply_markup=keyboard)

async def history_calendar_callback(callback_query: CallbackQuery):
    data = callback_query.data
    if data == "ignore":
        await callback_query.answer()
        return
    if data == "hist_back_to_menu":
        await callback_query.message.delete()
        await callback_query.message.answer("Главное меню", reply_markup=get_main_menu())
        await callback_query.answer()
        return
    if data == "hist_today":
        user_id = callback_query.from_user.id
        tz = await db.get_user_timezone(user_id)
        if tz == 0:
            tz = 3
        now_local = datetime.utcnow() + timedelta(hours=tz)
        date_str = now_local.strftime("%Y-%m-%d")
        await show_date_history(callback_query, date_str)
        return
    if data.startswith("hist_cal_"):
        # Навигация по календарю
        parts = data.split("_")
        year = int(parts[2])
        month = int(parts[3])
        user_id = callback_query.from_user.id
        tz = await db.get_user_timezone(user_id)
        if tz == 0:
            tz = 3
        keyboard = get_month_calendar(year, month, tz)
        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await callback_query.answer()
        return
    if data.startswith("hist_date_"):
        date_str = data.split("_")[2]
        await show_date_history(callback_query, date_str)
        return

async def show_date_history(callback_query: CallbackQuery, date_str: str):
    user_id = callback_query.from_user.id
    data = await get_user_data_for_date(user_id, date_str)
    text = format_user_data(data, date_str)
    # Кнопка для возврата к календарю
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📅 Назад к календарю", callback_data="hist_back_to_calendar"))
    await callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback_query.answer()

async def back_to_calendar(callback_query: CallbackQuery):
    # Возврат к календарю
    user_id = callback_query.from_user.id
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    year, month = now_local.year, now_local.month
    keyboard = get_month_calendar(year, month, tz)
    await callback_query.message.edit_text("📅 Выбери дату, чтобы посмотреть историю:", reply_markup=keyboard)
    await callback_query.answer()

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(history_start, text="📅 История", state="*")
    dp.register_callback_query_handler(history_calendar_callback, lambda c: c.data.startswith(('hist_', 'ignore')))
    dp.register_callback_query_handler(back_to_calendar, lambda c: c.data == "hist_back_to_calendar")
