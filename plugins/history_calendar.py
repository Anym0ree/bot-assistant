import os
import tempfile
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu, get_history_menu, get_graph_period_menu, get_graph_type_menu

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class HistoryStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_graph_period = State()
    waiting_for_graph_type = State()
    waiting_for_custom_start = State()
    waiting_for_custom_days = State()

# ========== ОСНОВНОЕ МЕНЮ ИСТОРИИ ==========
async def history_start(message: types.Message):
    await message.answer("📅 *История*\n\nВыбери действие:", reply_markup=get_history_menu(), parse_mode="Markdown")

async def history_today(message: types.Message):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id) or 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    date_str = now_local.strftime("%Y-%m-%d")
    await show_history(message, date_str)

async def history_yesterday(message: types.Message):
    user_id = message.from_user.id
    tz = await db.get_user_timezone(user_id) or 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    yesterday = now_local - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    await show_history(message, date_str)

async def history_ask_date(message: types.Message, state: FSMContext):
    await message.answer("📅 Введи дату в формате ГГГГ-ММ-ДД (например, 2026-05-03):")
    await HistoryStates.waiting_for_date.set()

async def history_process_date(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await history_start(message)
        return
    date_str = message.text.strip()
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи дату как ГГГГ-ММ-ДД.")
        return
    await state.finish()
    await show_history(message, date_str)

async def show_history(message: types.Message, date_str: str):
    user_id = message.from_user.id
    data = await get_user_data_for_date(user_id, date_str)
    text = format_user_data(data, date_str)
    await message.answer(text, reply_markup=get_history_menu(), parse_mode="Markdown")

# ========== ГРАФИКИ ==========
async def graph_menu(message: types.Message, state: FSMContext):
    await message.answer("📈 *Графики*\n\nВыбери период:", reply_markup=get_graph_period_menu(), parse_mode="Markdown")
    await HistoryStates.waiting_for_graph_period.set()

async def graph_period_chosen(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await history_start(message)
        return

    if message.text == "Свой период":
        await message.answer("Введи начальную дату (ГГГГ-ММ-ДД):")
        await HistoryStates.waiting_for_custom_start.set()
        return

    days_map = {"7 дн": 7, "14 дн": 14, "30 дн": 30}
    days = days_map.get(message.text)
    if days is None:
        await message.answer("Выбери из кнопок.")
        return

    await state.update_data(graph_days=days)
    await message.answer("📈 *Выбери тип графика:*", reply_markup=get_graph_type_menu(), parse_mode="Markdown")
    await HistoryStates.waiting_for_graph_type.set()

async def graph_custom_start(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await graph_menu(message, state)
        return
    try:
        datetime.strptime(message.text.strip(), "%Y-%m-%d")
    except:
        await message.answer("❌ Неверный формат. ГГГГ-ММ-ДД.")
        return
    await state.update_data(custom_start=message.text.strip())
    await message.answer("Сколько дней показать? (например, 10)")
    await HistoryStates.waiting_for_custom_days.set()

async def graph_custom_days(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await graph_menu(message, state)
        return
    if not message.text.isdigit() or int(message.text) < 1 or int(message.text) > 365:
        await message.answer("Введи число от 1 до 365.")
        return
    await state.update_data(graph_days=int(message.text))
    await message.answer("📈 *Выбери тип графика:*", reply_markup=get_graph_type_menu(), parse_mode="Markdown")
    await HistoryStates.waiting_for_graph_type.set()

async def graph_type_chosen(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await graph_menu(message, state)
        return

    data = await state.get_data()
    days = data.get("graph_days", 7)
    user_id = message.from_user.id

    if message.text == "📈 Сон":
        await send_sleep_graph(message, user_id, days)
    elif message.text == "📈 Энергия":
        await send_energy_graph(message, user_id, days)
    elif message.text == "📈 Настроение":
        await send_mood_graph(message, user_id, days)
    else:
        await message.answer("Выбери из кнопок.")
        return

    await state.finish()
    await message.answer("📈 Выбери ещё или вернись назад:", reply_markup=get_graph_type_menu())
    await HistoryStates.waiting_for_graph_type.set()

# ========== ПОСТРОЕНИЕ ГРАФИКОВ ==========
async def send_sleep_graph(message, user_id, days):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT date, bed_time, wake_time, quality FROM sleep
            WHERE user_id = $1 ORDER BY date DESC LIMIT $2
        """, user_id, days)

    if not rows:
        await message.answer("Нет данных о сне за этот период.")
        return

    rows = list(reversed(rows))
    dates = [r['date'] for r in rows]
    hours = []
    qualities = []
    for r in rows:
        try:
            bh, bm = map(int, r['bed_time'].split(':'))
            wh, wm = map(int, r['wake_time'].split(':'))
            bm = bh * 60 + bm
            wm = wh * 60 + wm
            if wm <= bm:
                wm += 24 * 60
            hours.append((wm - bm) / 60)
        except:
            hours.append(0)
        qualities.append(r['quality'] or 0)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    ax1.plot(dates, hours, 'o-', color='#6C5CE7', linewidth=2, markersize=6)
    ax1.fill_between(range(len(dates)), hours, alpha=0.2, color='#6C5CE7')
    ax1.axhline(y=7, color='green', linestyle='--', alpha=0.5, label='Норма (7 ч)')
    ax1.set_title('Часы сна', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Часы')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    if len(dates) > 7:
        step = max(1, len(dates) // 7)
        ax1.set_xticks(range(0, len(dates), step))
        ax1.set_xticklabels(dates[::step], rotation=45)

    ax2.bar(range(len(dates)), qualities, color='#A29BFE', alpha=0.8)
    ax2.axhline(y=7, color='green', linestyle='--', alpha=0.5, label='Хорошо (7)')
    ax2.set_title('Качество сна', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Оценка')
    ax2.set_ylim(0, 10.5)
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    if len(dates) > 7:
        step = max(1, len(dates) // 7)
        ax2.set_xticks(range(0, len(dates), step))
        ax2.set_xticklabels(dates[::step], rotation=45)

    plt.tight_layout()
    await send_plot(message, fig)

async def send_energy_graph(message, user_id, days):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT date, energy, stress FROM checkins
            WHERE user_id = $1 ORDER BY date DESC LIMIT $2
        """, user_id, days)

    if not rows:
        await message.answer("Нет данных о чекинах за этот период.")
        return

    rows = list(reversed(rows))
    dates = [r['date'] for r in rows]
    energies = [r['energy'] for r in rows]
    stresses = [r['stress'] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, energies, 'o-', color='#00B894', linewidth=2, markersize=6, label='Энергия')
    ax.plot(dates, stresses, 's--', color='#E17055', linewidth=2, markersize=6, label='Стресс')
    ax.set_title('Энергия и стресс', fontsize=14, fontweight='bold')
    ax.set_ylabel('Уровень (1-10)')
    ax.set_ylim(0, 10.5)
    ax.legend()
    ax.grid(True, alpha=0.3)
    if len(dates) > 7:
        step = max(1, len(dates) // 7)
        ax.set_xticks(range(0, len(dates), step))
        ax.set_xticklabels(dates[::step], rotation=45)
    plt.tight_layout()
    await send_plot(message, fig)

async def send_mood_graph(message, user_id, days):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT date, score FROM day_summary
            WHERE user_id = $1 ORDER BY date DESC LIMIT $2
        """, user_id, days)

    if not rows:
        await message.answer("Нет данных об итогах дня за этот период.")
        return

    rows = list(reversed(rows))
    dates = [r['date'] for r in rows]
    scores = [r['score'] for r in rows]
    colors = ['#00B894' if s >= 8 else '#FDCB6E' if s >= 5 else '#E17055' for s in scores]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(range(len(dates)), scores, color=colors, alpha=0.8)
    ax.axhline(y=7, color='green', linestyle='--', alpha=0.5, label='Хороший день (7)')
    ax.set_title('Оценка дня', fontsize=14, fontweight='bold')
    ax.set_ylabel('Оценка (1-10)')
    ax.set_ylim(0, 10.5)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    if len(dates) > 7:
        step = max(1, len(dates) // 7)
        ax.set_xticks(range(0, len(dates), step))
        ax.set_xticklabels(dates[::step], rotation=45)
    plt.tight_layout()
    await send_plot(message, fig)

async def send_plot(message, fig):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        fig.savefig(f, dpi=100, bbox_inches='tight')
        f.flush()
        with open(f.name, 'rb') as photo:
            await message.answer_photo(photo)
    os.unlink(f.name)
    plt.close(fig)

# ========== ФОРМАТИРОВАНИЕ ДАННЫХ ДНЯ (без изменений) ==========
async def get_user_data_for_date(user_id: int, date_str: str):
    result = {}
    async with db.pool.acquire() as conn:
        sleep = await conn.fetchrow("SELECT bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1 AND date = $2", user_id, date_str)
        result['sleep'] = dict(sleep) if sleep else None
        checkin = await conn.fetchrow("SELECT time, energy, stress, emotions, note FROM checkins WHERE user_id = $1 AND date = $2 ORDER BY time LIMIT 1", user_id, date_str)
        result['checkin'] = dict(checkin) if checkin else None
        food_rows = await conn.fetch("SELECT id, time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2 ORDER BY time", user_id, date_str)
        result['food'] = [dict(r) for r in food_rows]
        drink_rows = await conn.fetch("SELECT id, time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2 ORDER BY time", user_id, date_str)
        result['drinks'] = [dict(r) for r in drink_rows]
        summary = await conn.fetchrow("SELECT score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1 AND date = $2", user_id, date_str)
        result['summary'] = dict(summary) if summary else None
        notes = await conn.fetch("SELECT text, time FROM notes WHERE user_id = $1 AND date = $2 ORDER BY time", user_id, date_str)
        result['notes'] = [dict(r) for r in notes]
    return result

def format_user_data(data: dict, date_str: str) -> str:
    text = f"📅 *{date_str}*\n\n"
    # Сон
    text += "🛌 *Сон*:\n"
    if data['sleep']:
        s = data['sleep']
        text += f"   • Лёг: {s['bed_time']}, встал: {s['wake_time']}, качество: {s['quality']}/10\n"
        text += f"   • Просыпался: {'Да' if s['woke_night'] else 'Нет'}\n"
        if s['note']: text += f"   • Заметка: {s['note']}\n"
    else:
        text += "   • Нет записи\n"
    # Чек-ин
    text += "\n⚡️ *Чек-ин*:\n"
    if data['checkin']:
        c = data['checkin']
        text += f"   • Энергия: {c['energy']}/10, стресс: {c['stress']}/10\n"
        if c['note']: text += f"   • Заметка: {c['note']}\n"
    else:
        text += "   • Нет записи\n"
    # Еда
    text += "\n🍽 *Еда*:\n"
    if data['food']:
        for idx, f in enumerate(data['food'], start=1):
            text += f"   {idx}. {f['time']} — {f['meal_type']}: {f['food_text']}\n"
    else:
        text += "   • Нет записей\n"
    # Напитки
    text += "\n🥤 *Напитки*:\n"
    if data['drinks']:
        for idx, d in enumerate(data['drinks'], start=1):
            text += f"   {idx}. {d['time']} — {d['drink_type']}: {d['amount']}\n"
    else:
        text += "   • Нет записей\n"
    # Итог дня
    text += "\n📝 *Итог дня*:\n"
    if data['summary']:
        s = data['summary']
        text += f"   • Оценка: {s['score']}/10\n"
        if s['best']: text += f"   • Лучшее: {s['best']}\n"
        if s['worst']: text += f"   • Сложное: {s['worst']}\n"
        if s['gratitude']: text += f"   • Благодарность: {s['gratitude']}\n"
    else:
        text += "   • Нет записи\n"
    return text

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(history_start, text="📅 История", state="*")
    dp.register_message_handler(history_today, text="📅 Сегодня", state="*")
    dp.register_message_handler(history_yesterday, text="📆 Вчера", state="*")
    dp.register_message_handler(history_ask_date, text="✏️ Ввести дату", state="*")
    dp.register_message_handler(history_process_date, state=HistoryStates.waiting_for_date)
    dp.register_message_handler(graph_menu, text="📈 Графики", state="*")
    dp.register_message_handler(graph_period_chosen, state=HistoryStates.waiting_for_graph_period)
    dp.register_message_handler(graph_custom_start, state=HistoryStates.waiting_for_custom_start)
    dp.register_message_handler(graph_custom_days, state=HistoryStates.waiting_for_custom_days)
    dp.register_message_handler(graph_type_chosen, state=HistoryStates.waiting_for_graph_type)
