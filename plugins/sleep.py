from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database import db
from states import SleepStates
from keyboards import get_main_menu
from utils import send_temp_message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_back_next_keyboard(back_text="↩️ Назад"):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton(back_text))
    return kb

async def sleep_start(message: types.Message, state: FSMContext):
    if await db.has_sleep_today(message.from_user.id):
        await send_temp_message(message.chat.id, "🛌 Сон за сегодня уже записан.", 3)
        return
    await state.update_data(sleep_step=1)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in ["22:00", "23:00", "00:00", "01:00", "02:00"]:
        kb.add(KeyboardButton(t))
    kb.add(KeyboardButton("✏️ Своё"), KeyboardButton("❌ Отмена"))
    await message.answer("🛏️ Во сколько лёг спать?", reply_markup=kb)
    await SleepStates.bed_time.set()

async def sleep_bed_time(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return
    if message.text == "✏️ Своё":
        await message.answer("Введи время в формате ЧЧ:ММ (например 23:45):", reply_markup=get_back_next_keyboard())
        return
    from utils import is_valid_time_text
    if not is_valid_time_text(message.text):
        await send_temp_message(message.chat.id, "❌ Неверный формат. ЧЧ:ММ", 3)
        return
    await state.update_data(bed_time=message.text)
    await SleepStates.wake_time.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in ["06:00", "07:00", "08:00", "09:00", "10:00"]:
        kb.add(KeyboardButton(t))
    kb.add(KeyboardButton("✏️ Своё"), KeyboardButton("↩️ Назад"))
    await message.answer("⏰ Во сколько проснулся?", reply_markup=kb)

async def sleep_wake_time(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await SleepStates.bed_time.set()
        await sleep_start(message, state)
        return
    if message.text == "✏️ Своё":
        await message.answer("Введи время в формате ЧЧ:ММ:", reply_markup=get_back_next_keyboard())
        return
    from utils import is_valid_time_text
    if not is_valid_time_text(message.text):
        await send_temp_message(message.chat.id, "❌ Неверный формат. ЧЧ:ММ", 3)
        return
    await state.update_data(wake_time=message.text)
    await SleepStates.quality.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("😴 Плохо"), KeyboardButton("🙂 Нормально"), KeyboardButton("😊 Отлично"))
    kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
    await message.answer("💤 Качество сна?", reply_markup=kb)

async def sleep_quality(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await SleepStates.wake_time.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for t in ["06:00", "07:00", "08:00", "09:00", "10:00"]:
            kb.add(KeyboardButton(t))
        kb.add(KeyboardButton("✏️ Своё"), KeyboardButton("↩️ Назад"))
        await message.answer("⏰ Во сколько проснулся?", reply_markup=kb)
        return
    quality_map = {"😴 Плохо": 3, "🙂 Нормально": 6, "😊 Отлично": 9}
    if message.text in quality_map:
        await state.update_data(quality=quality_map[message.text])
    elif message.text == "Пропустить":
        await state.update_data(quality=6)
    else:
        await state.update_data(quality=6, custom_quality=message.text)
    await SleepStates.woke_night.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"), KeyboardButton("↩️ Назад"))
    await message.answer("🌙 Просыпался ночью?", reply_markup=kb)

async def sleep_woke_night(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await SleepStates.quality.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("😴 Плохо"), KeyboardButton("🙂 Нормально"), KeyboardButton("😊 Отлично"))
        kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
        await message.answer("💤 Качество сна?", reply_markup=kb)
        return
    if message.text not in ("✅ Да", "❌ Нет"):
        await send_temp_message(message.chat.id, "Выбери ответ кнопкой", 3)
        return
    await state.update_data(woke_night=(message.text == "✅ Да"))
    await SleepStates.note.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
    await message.answer("📝 Заметка? (можно пропустить)", reply_markup=kb)

async def sleep_note(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await SleepStates.woke_night.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"), KeyboardButton("↩️ Назад"))
        await message.answer("🌙 Просыпался ночью?", reply_markup=kb)
        return

    data = await state.get_data()
    note = "" if message.text == "Пропустить" else message.text

    # Сводка
    quality_text = data.get("custom_quality") or {3: "Плохо", 6: "Нормально", 9: "Отлично"}.get(data.get("quality"), str(data.get("quality", "?")))
    summary = (
        f"📋 *Проверь данные:*\n\n"
        f"🛏️ Лёг: {data.get('bed_time')}\n"
        f"⏰ Встал: {data.get('wake_time')}\n"
        f"💤 Качество: {quality_text}\n"
        f"🌙 Просыпался: {'Да' if data.get('woke_night') else 'Нет'}\n"
        f"📝 Заметка: {note or 'нет'}\n\n"
        f"Всё верно?"
    )
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Сохранить"), KeyboardButton("✏️ Исправить"))
    await message.answer(summary, reply_markup=kb, parse_mode="Markdown")
    await state.update_data(note=note, _confirming=True)

async def sleep_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("_confirming"):
        return

    if message.text == "✅ Сохранить":
        await db.add_sleep(
            message.from_user.id,
            data.get("bed_time"),
            data.get("wake_time"),
            data.get("quality", 6),
            data.get("woke_night", False),
            data.get("note", "")
        )
        await state.finish()
        await message.answer("✅ Сон сохранён!", reply_markup=get_main_menu())
    elif message.text == "✏️ Исправить":
        await state.update_data(_confirming=False)
        await SleepStates.bed_time.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for t in ["22:00", "23:00", "00:00", "01:00", "02:00"]:
            kb.add(KeyboardButton(t))
        kb.add(KeyboardButton("✏️ Своё"), KeyboardButton("❌ Отмена"))
        await message.answer("🛏️ Во сколько лёг спать?", reply_markup=kb)

def register(dp: Dispatcher):
    dp.register_message_handler(sleep_start, text="🛌 Сон", state="*")
    dp.register_message_handler(sleep_bed_time, state=SleepStates.bed_time)
    dp.register_message_handler(sleep_wake_time, state=SleepStates.wake_time)
    dp.register_message_handler(sleep_quality, state=SleepStates.quality)
    dp.register_message_handler(sleep_woke_night, state=SleepStates.woke_night)
    dp.register_message_handler(sleep_note, state=SleepStates.note)
    dp.register_message_handler(sleep_confirm, lambda m: m.text in ("✅ Сохранить", "✏️ Исправить"), state="*")
