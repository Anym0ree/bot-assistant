import logging
from datetime import datetime, timedelta
from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext

from database import db
from keyboards import get_main_menu, get_back_button
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def get_stats_data(user_id, days):
    """
    Возвращает словарь со статистикой за указанное количество дней.
    Без pandas и matplotlib, только SQLite и Python.
    """
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    start_date = (now_local - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = now_local.strftime("%Y-%m-%d")
    
    # Сон
    sleep_rows = await db.conn.execute_fetchall(
        "SELECT date, bed_time, wake_time, quality FROM sleep WHERE user_id = ? AND date >= ? ORDER BY date",
        (user_id, start_date)
    )
    sleep_hours = []
    sleep_qualities = []
    sleep_dates = []
    for row in sleep_rows:
        try:
            bed = datetime.strptime(row[1], "%H:%M")
            wake = datetime.strptime(row[2], "%H:%M")
            hours = (wake - bed).seconds / 3600
            if hours < 0:
                hours += 24
            sleep_hours.append(hours)
            sleep_qualities.append(row[3])
            sleep_dates.append(row[0])
        except:
            pass
    
    # Чек-ины
    checkin_rows = await db.conn.execute_fetchall(
        "SELECT date, energy, stress FROM checkins WHERE user_id = ? AND date >= ? ORDER BY date",
        (user_id, start_date)
    )
    energies = [r[1] for r in checkin_rows]
    stresses = [r[2] for r in checkin_rows]
    
    # Итоги дня
    summary_rows = await db.conn.execute_fetchall(
        "SELECT date, score FROM day_summary WHERE user_id = ? AND date >= ? ORDER BY date",
        (user_id, start_date)
    )
    scores = [r[1] for r in summary_rows]
    
    # Вода (записи напитков с типом "💧 Вода" или содержанием "вода" в amount)
    water_rows = await db.conn.execute_fetchall(
        "SELECT amount FROM drinks WHERE user_id = ? AND date >= ? AND (drink_type = '💧 Вода' OR amount LIKE '%вода%')",
        (user_id, start_date)
    )
    # Грубая оценка: каждая запись ≈ 0.5 л (можно улучшить)
    water_liters = len(water_rows) * 0.5
    
    # Достижения за период (количество новых)
    achievements_rows = await db.conn.execute_fetchall(
        "SELECT COUNT(*) FROM user_achievements WHERE user_id = ? AND awarded_at >= ?",
        (user_id, start_date)
    )
    new_achievements = achievements_rows[0][0] if achievements_rows else 0
    
    # Серии
    stats_row = await db.conn.execute_fetchone(
        "SELECT sleep_streak, checkin_streak FROM user_stats WHERE user_id = ?",
        (user_id,)
    )
    sleep_streak = stats_row[0] if stats_row else 0
    checkin_streak = stats_row[1] if stats_row else 0
    
    # Подсчёт средних
    avg_sleep = sum(sleep_hours) / len(sleep_hours) if sleep_hours else 0
    max_sleep = max(sleep_hours) if sleep_hours else 0
    min_sleep = min(sleep_hours) if sleep_hours else 0
    avg_quality = sum(sleep_qualities) / len(sleep_qualities) if sleep_qualities else 0
    
    avg_energy = sum(energies) / len(energies) if energies else 0
    avg_stress = sum(stresses) / len(stresses) if stresses else 0
    
    avg_score = sum(scores) / len(scores) if scores else 0
    
    return {
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "sleep_count": len(sleep_hours),
        "avg_sleep": avg_sleep,
        "max_sleep": max_sleep,
        "min_sleep": min_sleep,
        "avg_quality": avg_quality,
        "checkin_count": len(checkin_rows),
        "avg_energy": avg_energy,
        "avg_stress": avg_stress,
        "summary_count": len(summary_rows),
        "avg_score": avg_score,
        "water_liters": water_liters,
        "new_achievements": new_achievements,
        "sleep_streak": sleep_streak,
        "checkin_streak": checkin_streak,
    }

async def format_stats_text(stats):
    """Форматирует статистику в красивый текст с эмодзи и рекомендациями"""
    days = stats["days"]
    period = "неделю" if days == 7 else "месяц"
    text = f"📊 *Ваша статистика за {period}*\n"
    text += f"📅 {stats['start_date']} – {stats['end_date']}\n\n"
    
    # Сон
    text += "🛌 *Сон*\n"
    if stats["sleep_count"] == 0:
        text += "   • Нет записей\n"
    else:
        text += f"   • Средняя длительность: {stats['avg_sleep']:.1f} ч "
        if stats['avg_sleep'] < 7:
            text += "😴 (маловато, норма 7-8 ч)\n"
        elif stats['avg_sleep'] > 9:
            text += "😴 (многовато, возможно пересып)\n"
        else:
            text += "✅ (в норме)\n"
        text += f"   • Самая долгая ночь: {stats['max_sleep']:.1f} ч\n"
        text += f"   • Самая короткая ночь: {stats['min_sleep']:.1f} ч\n"
        text += f"   • Качество сна: {stats['avg_quality']:.1f}/10\n"
        if stats['sleep_streak'] >= 3:
            text += f"   • 🔥 Серия: {stats['sleep_streak']} дней подряд\n"
    
    # Энергия и стресс
    text += "\n⚡️ *Энергия и стресс*\n"
    if stats["checkin_count"] == 0:
        text += "   • Нет чек-инов\n"
    else:
        text += f"   • Энергия: {stats['avg_energy']:.1f}/10 "
        if stats['avg_energy'] < 5:
            text += "🔋 (низкая, нужен отдых)\n"
        else:
            text += "✅\n"
        text += f"   • Стресс: {stats['avg_stress']:.1f}/10 "
        if stats['avg_stress'] > 6:
            text += "😰 (высокий, попробуй релаксацию)\n"
        else:
            text += "✅\n"
        if stats['checkin_streak'] >= 7:
            text += f"   • 🔥 Серия чек-инов: {stats['checkin_streak']} дней\n"
    
    # Оценка дня
    text += "\n📝 *Оценка дня*\n"
    if stats["summary_count"] == 0:
        text += "   • Нет итогов\n"
    else:
        text += f"   • Средняя оценка: {stats['avg_score']:.1f}/10\n"
    
    # Вода
    text += "\n💧 *Вода*\n"
    text += f"   • Выпито за период: {stats['water_liters']:.1f} л (≈{stats['water_liters']/days:.1f} л/день)\n"
    if stats['water_liters']/days < 2:
        text += "   ⚠️ Рекомендуется 2-2.5 л в день\n"
    
    # Достижения
    if stats['new_achievements'] > 0:
        text += f"\n🏆 *Новые достижения*: {stats['new_achievements']} 🎉\n"
    
    # Общие рекомендации
    text += "\n📌 *Рекомендации*\n"
    rec_cnt = 0
    if stats['avg_sleep'] < 7 and stats['sleep_count'] > 0:
        text += "• Постарайся ложиться спать на 30-60 минут раньше\n"
        rec_cnt += 1
    if stats['avg_energy'] < 5 and stats['checkin_count'] > 0:
        text += "• Добавь в рацион больше фруктов и овощей, пей воду\n"
        rec_cnt += 1
    if stats['avg_stress'] > 6 and stats['checkin_count'] > 0:
        text += "• Попробуй медитацию или дыхательные упражнения\n"
        rec_cnt += 1
    if stats['water_liters']/days < 2 and days > 0:
        text += "• Пей больше воды – поставь бутылку на видное место\n"
        rec_cnt += 1
    if rec_cnt == 0:
        text += "• Отличная работа! Продолжай в том же духе 💪\n"
    
    return text

# ========== ХЕНДЛЕРЫ МЕНЮ ==========
async def stats_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📅 Неделя", callback_data="stats_week"),
        InlineKeyboardButton("📆 Месяц", callback_data="stats_month"),
        InlineKeyboardButton("📄 Полная статистика", callback_data="stats_text"),
        InlineKeyboardButton("⬅️ Назад", callback_data="stats_back")
    )
    await message.answer("📊 Выбери период для аналитики:", reply_markup=keyboard)

async def stats_callback_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    await callback_query.answer()  # убираем часики
    
    if data == "stats_back":
        await callback_query.message.delete()
        await callback_query.message.answer("Главное меню", reply_markup=get_main_menu())
        return
    
    if data == "stats_text":
        # Полная статистика (за всё время) – можно просто вызвать db.get_stats
        text = await db.get_stats(user_id)
        await callback_query.message.answer(text, reply_markup=get_main_menu())
        await callback_query.message.delete()
        return
    
    if data == "stats_week":
        days = 7
    elif data == "stats_month":
        days = 30
    else:
        await callback_query.message.answer("Неизвестный выбор")
        return
    
    # Показываем прогресс
    msg = await callback_query.message.answer("⏳ Собираю данные...")
    stats = await get_stats_data(user_id, days)
    text = await format_stats_text(stats)
    await msg.delete()
    await callback_query.message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())
    await callback_query.message.delete()

async def stats(message: types.Message):
    await stats_menu(message)

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(stats, text="📊 Статистика", state="*")
    dp.register_callback_query_handler(stats_callback_handler, lambda c: c.data.startswith('stats_'))