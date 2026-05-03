from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database import db
from keyboards import get_main_menu

def get_achievements_menu_keyboard():
    buttons = [
        [KeyboardButton("🏅 Мои достижения")],
        [KeyboardButton("📊 Таблица лидеров")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def achievements_main(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("🏆 *Достижения*\n\nВыбери, что посмотреть:", reply_markup=get_achievements_menu_keyboard(), parse_mode="Markdown")

async def my_achievements(message: types.Message):
    user_id = message.from_user.id
    xp_data = await db.get_user_xp(user_id)
    achievements = await db.get_user_achievements(user_id)
    all_achievements = await db.get_all_achievements()

    text = f"🏅 *Твой прогресс*\n\n"
    text += f"⭐ Уровень: {xp_data['level']}\n"
    text += f"✨ XP: {xp_data['xp']}\n\n"
    text += "📜 *Полученные достижения:*\n"

    if achievements:
        for a in achievements:
            text += f"{a['icon']} {a['name']} — {a['awarded_at'].strftime('%d.%m.%Y')}\n"
    else:
        text += "Пока ничего нет. Начни заполнять дневник!\n"

    text += "\n🔒 *Ещё доступно:*\n"
    earned_codes = {a['code'] for a in achievements}
    for a in all_achievements:
        if a['code'] not in earned_codes:
            text += f"⬜ {a['icon']} {a['name']} — {a['description']}\n"

    await message.answer(text, reply_markup=get_achievements_menu_keyboard(), parse_mode="Markdown")

async def leaderboard(message: types.Message):
    top = await db.get_leaderboard()
    if not top:
        await message.answer("Таблица лидеров пока пуста. Установи никнейм в настройках, чтобы участвовать!")
        return

    text = "📊 *Таблица лидеров*\n\n"
    medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    for i, user in enumerate(top[:10]):
        text += f"{medals[i]} {user['nickname']} — ур. {user['level']} ({user['xp']} XP)\n"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔄 Обновить"), KeyboardButton("⬅️ Назад"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

async def back_to_achievements(message: types.Message, state: FSMContext):
    await achievements_main(message, state)

def register(dp: Dispatcher):
    dp.register_message_handler(achievements_main, text="🏆 Достижения", state="*")
    dp.register_message_handler(my_achievements, text="🏅 Мои достижения", state="*")
    dp.register_message_handler(leaderboard, text="📊 Таблица лидеров", state="*")
    
