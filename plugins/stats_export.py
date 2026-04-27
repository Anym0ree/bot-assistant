import logging
from datetime import datetime, timedelta
from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from keyboards import get_main_menu

logger = logging.getLogger(__name__)

# ФОРСИРОВАННЫЙ ЛОГ ПРИ ЗАГРУЗКЕ МОДУЛЯ
logging.error("!!! STATS_EXPORT MODULE LOADED !!!")

async def get_stats_data(user_id, days):
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    start_date = (now_local - timedelta(days=days)).strftime("%Y-%m-%d")

    async with db.pool.acquire() as conn:
        sleep_rows = await conn.fetch(
            "SELECT date, bed_time, wake_time, quality FROM sleep WHERE user_id = $1 AND date >= $2",
            user_id, start_date
        )
        checkin_rows = await conn.fetch(
            "SELECT date, energy, stress FROM checkins WHERE user_id = $1 AND date >= $2",
            user_id, start_date
        )
        summary_rows = await conn.fetch(
            "SELECT date, score FROM day_summary WHERE user_id = $1 AND date >= $2",
            user_id, start_date
        )
        water_rows = await conn.fetch(
            "SELECT amount FROM drinks WHERE user_id = $1 AND date >= $2 AND (drink_type = '💧 Вода' OR amount LIKE '%вода%')",
            user_id, start_date
        )
        ach_rows = await conn.fetch(
            "SELECT COUNT(*) FROM user_achievements WHERE user_id = $1 AND awarded_at >= $2",
            user_id, start_date
        )
        stats_row = await conn.fetchrow(
            "SELECT sleep_streak, checkin_streak FROM user_stats WHERE user_id = $1",
            user_id
        )

    sleep_hours = []
    sleep_qualities = []
    for row in sleep_rows:
        try:
            bed = datetime.strptime(row['bed_time'], "%H:%M")
            wake = datetime.strptime(row['wake_time'], "%H:%M")
            hours = (wake - bed).seconds / 3600
            if hours < 0:
                hours += 24
            sleep_hours.append(hours)
            sleep_qualities.append(row['quality'])
        except:
            pass

    energies = [r['energy'] for r in checkin_rows]
    stresses = [r['stress'] for r in checkin_rows]
    scores = [r['score'] for r in summary_rows]
    water_liters = len(water_rows) * 0.5
    new_achievements = ach_rows[0][0] if ach_rows else 0
    sleep_streak = stats_row['sleep_streak'] if stats_row else 0
    checkin_streak = stats_row['checkin_streak'] if stats_row else 0

    avg_sleep = sum(sleep_hours)/len(sleep_hours) if sleep_hours else 0
    max_sleep = max(sleep_hours) if sleep_hours else 0
    min_sleep = min(sleep_hours) if sleep_hours else 0
    avg_quality = sum(sleep_qualities)/len(sleep_qualities) if sleep_qualities else 0
    avg_energy = sum(energies)/len(energies) if energies else 0
    avg_stress = sum(stresses)/len(stresses) if stresses else 0
    avg_score = sum(scores)/len(scores) if scores else 0

    return {
        "days": days,
        "start_date": start_date,
        "sleep_count": len(sleep_hours),
        "avg_sleep": avg_sleep,
        "max_sleep": max_sleep,
        "min_sleep": min_sleep,
        "avg_quality": avg_quality,
        "avg_energy": avg_energy,
        "avg_stress": avg_stress,
        "avg_score": avg_score,
        "water_liters": water_liters,
        "new_achievements": new_achievements,
        "sleep_streak": sleep_streak,
        "checkin_streak": checkin_streak,
    }

async def format_stats_text(stats):
    days = stats["days"]
    period = "неделю" if days == 7 else "месяц"
    text = f"📊 *Ваша статистика за {period}*\n"
    text += f"📅 {stats['start_date']} – {datetime.now().strftime('%Y-%m-%d')}\n\n"

    text += "🛌 *Сон*\n"
    if stats["sleep_count"] == 0:
        text += "   • Нет записей\n"
    else:
        text += f"   • Средняя длительность: {stats['avg_sleep']:.1f} ч "
        if stats['avg_sleep'] < 7:
            text += "😴 (маловато)\n"
        elif stats['avg_sleep'] > 9:
            text += "😴 (многовато)\n"
        else:
            text += "✅\n"
        text += f"   • Самая долгая ночь: {stats['max_sleep']:.1f} ч\n"
        text += f"   • Самая короткая: {stats['min_sleep']:.1f} ч\n"
        text += f"   • Качество сна: {stats['avg_quality']:.1f}/10\n"
        if stats['sleep_streak'] >= 3:
            text += f"   • 🔥 Серия: {stats['sleep_streak']} дней\n"

    text += "\n⚡️ *Энергия и стресс*\n"
    if stats.get("checkin_count", 0) == 0 and stats["sleep_count"] > 0:
        text += "   • Нет чек-инов\n"
    else:
        energy_text = "🔋 (низкая)\n" if stats['avg_energy'] < 5 else "✅\n"
        text += f"   • Энергия: {stats['avg_energy']:.1f}/10 {energy_text}"
        stress_text = "😰 (высокий)\n" if stats['avg_stress'] > 6 else "✅\n"
        text += f"   • Стресс: {stats['avg_stress']:.1f}/10 {stress_text}"
        if stats['checkin_streak'] >= 7:
            text += f"   • 🔥 Серия чек-инов: {stats['checkin_streak']} дней\n"

    text += "\n📝 *Оценка дня*\n"
    if stats.get("summary_count", 0) == 0 and stats["sleep_count"] > 0:
        text += "   • Нет итогов\n"
    else:
        text += f"   • Средняя оценка: {stats['avg_score']:.1f}/10\n"

    text += "\n💧 *Вода*\n"
    text += f"   • Выпито за период: {stats['water_liters']:.1f} л (~{stats['water_liters']/stats['days']:.1f} л/день)\n"
    if stats['water_liters']/stats['days'] < 2:
        text += "   ⚠️ Пей больше воды (2-2.5 л/день)\n"

    if stats['new_achievements'] > 0:
        text += f"\n🏆 *Новые достижения*: {stats['new_achievements']} 🎉\n"

    text += "\n📌 *Рекомендации*\n"
    rec = 0
    if stats['avg_sleep'] < 7 and stats['sleep_count'] > 0:
        text += "• Ложись спать на 30 минут раньше\n"
        rec += 1
    if stats['avg_energy'] < 5 and stats.get('checkin_count', 0) > 0:
        text += "• Добавь фрукты и овощи, пей воду\n"
        rec += 1
    if stats['avg_stress'] > 6 and stats.get('checkin_count', 0) > 0:
        text += "• Попробуй медитацию или дыхательные упражнения\n"
        rec += 1
    if stats['water_liters']/stats['days'] < 2:
        text += "• Поставь бутылку воды на видное место\n"
        rec += 1
    if rec == 0:
        text += "• Отличная работа! Продолжай в том же духе 💪\n"
    return text

async def stats_menu(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📅 Неделя", callback_data="stats_week"),
        InlineKeyboardButton("📆 Месяц", callback_data="stats_month"),
        InlineKeyboardButton("📄 Полная статистика", callback_data="stats_text"),
        InlineKeyboardButton("⬅️ Назад", callback_data="stats_back")
    )
    await message.answer("📊 Выбери период:", reply_markup=kb)

async def stats_callback_handler(callback_query: types.CallbackQuery):
    logging.error(f"🔥🔥🔥 STATS CALLBACK RECEIVED: {callback_query.data} from {callback_query.from_user.id}")
    user_id = callback_query.from_user.id
    data = callback_query.data
    await callback_query.answer()
    if data == "stats_back":
        await callback_query.message.delete()
        await callback_query.message.answer("Главное меню", reply_markup=get_main_menu())
        return
    if data == "stats_text":
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
    msg = await callback_query.message.answer("⏳ Собираю данные...")
    stats = await get_stats_data(user_id, days)
    text = await format_stats_text(stats)
    await msg.delete()
    await callback_query.message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())
    await callback_query.message.delete()

async def stats(message: types.Message):
    await stats_menu(message)

def register(dp: Dispatcher):
    logging.error("!!! REGISTERING STATS HANDLERS !!!")
    dp.register_message_handler(stats, text="📊 Статистика", state="*")
    dp.register_callback_query_handler(stats_callback_handler, lambda c: c.data.startswith('stats_'))
