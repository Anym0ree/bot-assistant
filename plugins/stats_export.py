import os
import tempfile
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu

# Настройка русских шрифтов
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def get_stats_keyboard():
    buttons = [
        [KeyboardButton("📈 График сна")],
        [KeyboardButton("📈 График энергии")],
        [KeyboardButton("📈 График настроения")],
        [KeyboardButton("📊 Общая статистика")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def stats_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📊 *Статистика*\n\nВыбери график или общую сводку:", reply_markup=get_stats_keyboard(), parse_mode="Markdown")

async def stats_text(message: types.Message):
    text = await db.get_stats(message.from_user.id)
    await message.answer(text, reply_markup=get_stats_keyboard(), parse_mode="Markdown")

# ========== ГРАФИК СНА ==========
async def graph_sleep(message: types.Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT date, bed_time, wake_time, quality FROM sleep
            WHERE user_id = $1
            ORDER BY date DESC LIMIT 30
        """, user_id)
    
    if not rows:
        await message.answer("Недостаточно данных о сне.", reply_markup=get_stats_keyboard())
        return

    rows = list(reversed(rows))
    dates = [r['date'] for r in rows]
    
    # Считаем часы сна
    hours = []
    qualities = []
    for r in rows:
        try:
            bed_h, bed_m = map(int, r['bed_time'].split(':'))
            wake_h, wake_m = map(int, r['wake_time'].split(':'))
            bed_mins = bed_h * 60 + bed_m
            wake_mins = wake_h * 60 + wake_m
            if wake_mins <= bed_mins:
                wake_mins += 24 * 60
            h = (wake_mins - bed_mins) / 60
            hours.append(h)
        except:
            hours.append(0)
        qualities.append(r['quality'] or 0)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    
    # График 1: часы сна
    ax1.plot(dates, hours, 'o-', color='#6C5CE7', linewidth=2, markersize=6)
    ax1.fill_between(range(len(dates)), hours, alpha=0.2, color='#6C5CE7')
    ax1.axhline(y=7, color='green', linestyle='--', alpha=0.5, label='Норма (7 ч)')
    ax1.set_title('Часы сна', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Часы')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    if len(dates) > 7:
        ax1.set_xticks(range(0, len(dates), max(1, len(dates)//7)))
    ax1.set_xticklabels(dates[::max(1, len(dates)//7)], rotation=45)

    # График 2: качество сна
    ax2.bar(range(len(dates)), qualities, color='#A29BFE', alpha=0.8)
    ax2.axhline(y=7, color='green', linestyle='--', alpha=0.5, label='Хорошо (7)')
    ax2.set_title('Качество сна (1-10)', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Оценка')
    ax2.set_ylim(0, 10.5)
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    if len(dates) > 7:
        ax2.set_xticks(range(0, len(dates), max(1, len(dates)//7)))
    ax2.set_xticklabels(dates[::max(1, len(dates)//7)], rotation=45)

    plt.tight_layout()
    await send_plot(message, fig, 'sleep_graph.png')
    await message.answer("📈 График сна за последние 30 дней", reply_markup=get_stats_keyboard())

# ========== ГРАФИК ЭНЕРГИИ ==========
async def graph_energy(message: types.Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT date, energy, stress FROM checkins
            WHERE user_id = $1
            ORDER BY date DESC LIMIT 60
        """, user_id)
    
    if not rows:
        await message.answer("Недостаточно данных о чекинах.", reply_markup=get_stats_keyboard())
        return

    rows = list(reversed(rows))
    dates = [r['date'] for r in rows]
    energies = [r['energy'] for r in rows]
    stresses = [r['stress'] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, energies, 'o-', color='#00B894', linewidth=2, markersize=6, label='Энергия')
    ax.plot(dates, stresses, 's--', color='#E17055', linewidth=2, markersize=6, label='Стресс')
    ax.fill_between(range(len(dates)), energies, alpha=0.1, color='#00B894')
    ax.fill_between(range(len(dates)), stresses, alpha=0.1, color='#E17055')
    ax.set_title('Энергия и стресс', fontsize=14, fontweight='bold')
    ax.set_ylabel('Уровень (1-10)')
    ax.set_ylim(0, 10.5)
    ax.legend()
    ax.grid(True, alpha=0.3)
    if len(dates) > 10:
        ax.set_xticks(range(0, len(dates), max(1, len(dates)//10)))
    ax.set_xticklabels(dates[::max(1, len(dates)//10)], rotation=45)
    plt.tight_layout()
    await send_plot(message, fig, 'energy_graph.png')
    await message.answer("📈 Энергия и стресс за последние 60 чекинов", reply_markup=get_stats_keyboard())

# ========== ГРАФИК НАСТРОЕНИЯ ==========
async def graph_mood(message: types.Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT date, score FROM day_summary
            WHERE user_id = $1
            ORDER BY date DESC LIMIT 30
        """, user_id)
    
    if not rows:
        await message.answer("Недостаточно данных об итогах дня.", reply_markup=get_stats_keyboard())
        return

    rows = list(reversed(rows))
    dates = [r['date'] for r in rows]
    scores = [r['score'] for r in rows]

    # Цвета в зависимости от оценки
    colors = []
    for s in scores:
        if s >= 8: colors.append('#00B894')
        elif s >= 5: colors.append('#FDCB6E')
        else: colors.append('#E17055')

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(range(len(dates)), scores, color=colors, alpha=0.8)
    ax.axhline(y=7, color='green', linestyle='--', alpha=0.5, label='Хороший день (7)')
    ax.set_title('Оценка дня', fontsize=14, fontweight='bold')
    ax.set_ylabel('Оценка (1-10)')
    ax.set_ylim(0, 10.5)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    if len(dates) > 7:
        ax.set_xticks(range(0, len(dates), max(1, len(dates)//7)))
    ax.set_xticklabels(dates[::max(1, len(dates)//7)], rotation=45)
    plt.tight_layout()
    await send_plot(message, fig, 'mood_graph.png')
    await message.answer("📈 Оценки дня за последние 30 дней\n\n🟢 8+ — отлично | 🟡 5-7 — норма | 🔴 1-4 — плохо", reply_markup=get_stats_keyboard())

async def send_plot(message, fig, filename):
    """Отправляет график как фото и удаляет временный файл"""
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        fig.savefig(f, dpi=100, bbox_inches='tight')
        f.flush()
        with open(f.name, 'rb') as photo:
            await message.answer_photo(photo)
    os.unlink(f.name)
    plt.close(fig)

def register(dp: Dispatcher):
    dp.register_message_handler(stats_menu, text="📊 Статистика", state="*")
    dp.register_message_handler(graph_sleep, text="📈 График сна", state="*")
    dp.register_message_handler(graph_energy, text="📈 График энергии", state="*")
    dp.register_message_handler(graph_mood, text="📈 График настроения", state="*")
    dp.register_message_handler(stats_text, text="📊 Общая статистика", state="*")
