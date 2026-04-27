import re
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import db
from keyboards import get_main_menu

logger = logging.getLogger(__name__)

class DNDStates(StatesGroup):
    waiting_start = State()
    waiting_end = State()

class ProfileEditStates(StatesGroup):
    age = State()
    height = State()
    weight = State()

async def settings_menu(message: types.Message, state: FSMContext = None):
    if state:
        await state.finish()
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT ai_enabled, reminders_enabled, daily_surveys_enabled, weekly_report_enabled, do_not_disturb_start, do_not_disturb_end FROM user_settings WHERE user_id = $1",
            user_id
        )
        if not row:
            await conn.execute("INSERT INTO user_settings (user_id) VALUES ($1)", user_id)
            ai_enabled = reminders_enabled = daily_surveys_enabled = weekly_report_enabled = 1
            dnd_start = dnd_end = None
        else:
            ai_enabled = row['ai_enabled']
            reminders_enabled = row['reminders_enabled']
            daily_surveys_enabled = row['daily_surveys_enabled']
            weekly_report_enabled = row['weekly_report_enabled']
            dnd_start = row['do_not_disturb_start']
            dnd_end = row['do_not_disturb_end']

    # Получаем профиль
    profile = await db.get_user_profile(user_id)
    if profile['age']:
        profile_text = f"👤 Профиль: {profile['age']} лет, {profile['height']} см, {profile['weight']} кг"
    else:
        profile_text = "👤 Профиль не заполнен"

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"{'✅' if ai_enabled else '❌'} AI-совет", callback_data="set_ai"),
        InlineKeyboardButton(f"{'✅' if reminders_enabled else '❌'} Напоминания", callback_data="set_reminders"),
        InlineKeyboardButton(f"{'✅' if daily_surveys_enabled else '❌'} Опросники", callback_data="set_surveys"),
        InlineKeyboardButton(f"{'✅' if weekly_report_enabled else '❌'} Отчёты", callback_data="set_reports"),
        InlineKeyboardButton("✏️ Редактировать профиль", callback_data="edit_profile"),
        InlineKeyboardButton("🕒 Тихий час", callback_data="set_dnd"),
        InlineKeyboardButton("⬅️ Назад", callback_data="settings_back")
    )
    dnd_text = f" (тихий час {dnd_start}–{dnd_end})" if dnd_start and dnd_end else ""
    await message.answer(
        f"⚙️ *Настройки бота*\n\n"
        f"{profile_text}\n\n"
        f"AI-совет: {'включён' if ai_enabled else 'выключен'}\n"
        f"Напоминания: {'включены' if reminders_enabled else 'выключены'}\n"
        f"Опросники: {'включены' if daily_surveys_enabled else 'выключены'}\n"
        f"Еженедельные отчёты: {'включены' if weekly_report_enabled else 'выключены'}{dnd_text}\n\n"
        f"Нажми на кнопку, чтобы изменить.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

async def settings_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = callback.data

    if data == "settings_back":
        await callback.message.delete()
        await callback.message.answer("Главное меню", reply_markup=get_main_menu())
        await callback.answer()
        return

    async def toggle_setting(setting_name):
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {setting_name} FROM user_settings WHERE user_id = $1", user_id)
            current = row[setting_name] if row else 1
            new_val = 0 if current else 1
            await conn.execute(f"""
                INSERT INTO user_settings (user_id, {setting_name}) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET {setting_name} = $2
            """, user_id, new_val)
        return new_val

    if data == "set_ai":
        new_val = await toggle_setting("ai_enabled")
        await callback.answer(f"AI-совет {'включён' if new_val else 'выключен'}")
        await settings_menu(callback.message, state)
        await callback.message.delete()
    elif data == "set_reminders":
        new_val = await toggle_setting("reminders_enabled")
        await callback.answer(f"Напоминания {'включены' if new_val else 'выключены'}")
        await settings_menu(callback.message, state)
        await callback.message.delete()
    elif data == "set_surveys":
        new_val = await toggle_setting("daily_surveys_enabled")
        await callback.answer(f"Опросники {'включены' if new_val else 'выключены'}")
        await settings_menu(callback.message, state)
        await callback.message.delete()
    elif data == "set_reports":
        new_val = await toggle_setting("weekly_report_enabled")
        await callback.answer(f"Отчёты {'включены' if new_val else 'выключены'}")
        await settings_menu(callback.message, state)
        await callback.message.delete()
    elif data == "edit_profile":
        await callback.message.answer("📝 Введи новый возраст (число от 1 до 120).\nОтправь /cancel для отмены.")
        await ProfileEditStates.age.set()
        await callback.answer()
    elif data == "set_dnd":
        await callback.message.answer("🕒 Введи время начала тихого часа (ЧЧ:ММ, например 23:00).\nОтправь /cancel для отмены.")
        await DNDStates.waiting_start.set()
        await callback.answer()

async def profile_age(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.finish()
        await message.answer("Отменено.", reply_markup=get_main_menu())
        return
    try:
        age = int(message.text)
        if 1 <= age <= 120:
            await state.update_data(age=age)
            await message.answer("📏 Введи рост (в см, от 50 до 250):")
            await ProfileEditStates.height.set()
        else:
            await message.answer("❌ Возраст должен быть от 1 до 120. Попробуй ещё раз.")
    except ValueError:
        await message.answer("❌ Введи число.")

async def profile_height(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.finish()
        await message.answer("Отменено.", reply_markup=get_main_menu())
        return
    try:
        height = int(message.text)
        if 50 <= height <= 250:
            await state.update_data(height=height)
            await message.answer("⚖️ Введи вес (в кг, от 10 до 300):")
            await ProfileEditStates.weight.set()
        else:
            await message.answer("❌ Рост должен быть от 50 до 250 см.")
    except ValueError:
        await message.answer("❌ Введи число.")

async def profile_weight(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.finish()
        await message.answer("Отменено.", reply_markup=get_main_menu())
        return
    try:
        weight = int(message.text)
        if 10 <= weight <= 300:
            data = await state.get_data()
            await db.update_user_profile(message.from_user.id, age=data['age'], height=data['height'], weight=weight)
            await state.finish()
            await message.answer("✅ Профиль обновлён!", reply_markup=get_main_menu())
            await settings_menu(message)
        else:
            await message.answer("❌ Вес должен быть от 10 до 300 кг.")
    except ValueError:
        await message.answer("❌ Введи число.")

async def dnd_start(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.finish()
        await message.answer("Отменено.", reply_markup=get_main_menu())
        return
    if not re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", message.text):
        await message.answer("❌ Неверный формат. Введи время как ЧЧ:ММ (например, 23:00).")
        return
    await state.update_data(dnd_start=message.text)
    await message.answer("🕒 Введи время окончания тихого часа (например, 07:00):")
    await DNDStates.waiting_end.set()

async def dnd_end(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.finish()
        await message.answer("Отменено.", reply_markup=get_main_menu())
        return
    if not re.match(r"^(2[0-3]|[01]?[0-9]):[0-5][0-9]$", message.text):
        await message.answer("❌ Неверный формат.")
        return
    data = await state.get_data()
    start = data["dnd_start"]
    end = message.text
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_settings (user_id, do_not_disturb_start, do_not_disturb_end)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET do_not_disturb_start = $2, do_not_disturb_end = $3
        """, user_id, start, end)
    await state.finish()
    await message.answer(f"✅ Тихий час установлен с {start} до {end}.")
    await settings_menu(message)

def register(dp: Dispatcher):
    dp.register_message_handler(settings_menu, text="⚙️ Настройки", state="*")
    dp.register_callback_query_handler(
        settings_callback,
        lambda c: c.data.startswith(('set_', 'edit_profile', 'settings_back')),
        state="*"
    )
    dp.register_message_handler(profile_age, state=ProfileEditStates.age, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(profile_height, state=ProfileEditStates.height, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(profile_weight, state=ProfileEditStates.weight, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(dnd_start, state=DNDStates.waiting_start, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(dnd_end, state=DNDStates.waiting_end, content_types=types.ContentTypes.TEXT)
