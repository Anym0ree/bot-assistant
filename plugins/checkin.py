from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database import db
from states import CheckinStates
from keyboards import get_main_menu
from utils import send_temp_message, is_valid_score_text
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

async def checkin_start(message: types.Message, state: FSMContext):
    await state.update_data(emotions=[], _step=1)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
    kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
    kb.add(KeyboardButton("❌ Отмена"))
    await message.answer("⚡ Оцени энергию (1–10):", reply_markup=kb)
    await CheckinStates.energy.set()

async def checkin_energy(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return
    if not is_valid_score_text(message.text):
        await send_temp_message(message.chat.id, "❌ Оценка от 1 до 10", 3)
        return
    await state.update_data(energy=int(message.text))
    await CheckinStates.stress.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
    kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
    kb.add(KeyboardButton("↩️ Назад"))
    await message.answer("😤 Оцени стресс (1–10):", reply_markup=kb)

async def checkin_stress(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await CheckinStates.energy.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
        kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
        kb.add(KeyboardButton("❌ Отмена"))
        await message.answer("⚡ Оцени энергию (1–10):", reply_markup=kb)
        return
    if not is_valid_score_text(message.text):
        await send_temp_message(message.chat.id, "❌ Оценка от 1 до 10", 3)
        return
    await state.update_data(stress=int(message.text))
    await CheckinStates.emotions.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("😊 Радость"), KeyboardButton("😌 Спокойствие"))
    kb.add(KeyboardButton("😰 Тревога"), KeyboardButton("😔 Грусть"))
    kb.add(KeyboardButton("😤 Раздражение"), KeyboardButton("✨ Вдохновение"))
    kb.add(KeyboardButton("➕ Своя"), KeyboardButton("✅ Готово"), KeyboardButton("↩️ Назад"))
    await message.answer("😊 Выбери эмоции (можно несколько), затем «✅ Готово».\n\nВыбрано: 0", reply_markup=kb)

async def checkin_emotions(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await CheckinStates.stress.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
        kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
        kb.add(KeyboardButton("↩️ Назад"))
        await message.answer("😤 Оцени стресс (1–10):", reply_markup=kb)
        return

    data = await state.get_data()
    emotions = data.get("emotions", [])

    if message.text == "✅ Готово":
        await CheckinStates.note.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
        await message.answer("📝 Заметка? (можно пропустить)", reply_markup=kb)
        return

    if message.text == "➕ Своя":
        await send_temp_message(message.chat.id, "Напиши свою эмоцию, затем нажми «✅ Готово».", 4)
        return

    if message.text not in emotions:
        emotions.append(message.text)
        await state.update_data(emotions=emotions)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("😊 Радость"), KeyboardButton("😌 Спокойствие"))
    kb.add(KeyboardButton("😰 Тревога"), KeyboardButton("😔 Грусть"))
    kb.add(KeyboardButton("😤 Раздражение"), KeyboardButton("✨ Вдохновение"))
    kb.add(KeyboardButton("➕ Своя"), KeyboardButton("✅ Готово"), KeyboardButton("↩️ Назад"))
    await message.answer(f"😊 Выбери эмоции, затем «✅ Готово».\n\nВыбрано: {len(emotions)}", reply_markup=kb)

async def checkin_note(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await CheckinStates.emotions.set()
        data = await state.get_data()
        emotions = data.get("emotions", [])
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("😊 Радость"), KeyboardButton("😌 Спокойствие"))
        kb.add(KeyboardButton("😰 Тревога"), KeyboardButton("😔 Грусть"))
        kb.add(KeyboardButton("😤 Раздражение"), KeyboardButton("✨ Вдохновение"))
        kb.add(KeyboardButton("➕ Своя"), KeyboardButton("✅ Готово"), KeyboardButton("↩️ Назад"))
        await message.answer(f"😊 Выбери эмоции, затем «✅ Готово».\n\nВыбрано: {len(emotions)}", reply_markup=kb)
        return

    data = await state.get_data()
    note = "" if message.text == "Пропустить" else message.text

    summary = (
        f"📋 *Проверь данные:*\n\n"
        f"⚡ Энергия: {data.get('energy')}/10\n"
        f"😤 Стресс: {data.get('stress')}/10\n"
        f"😊 Эмоции: {', '.join(data.get('emotions', [])) or 'нет'}\n"
        f"📝 Заметка: {note or 'нет'}\n\n"
        f"Всё верно?"
    )
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Сохранить"), KeyboardButton("✏️ Исправить"))
    await message.answer(summary, reply_markup=kb, parse_mode="Markdown")
    await state.update_data(note=note, _confirming=True)

async def checkin_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("_confirming"):
        return

    if message.text == "✅ Сохранить":
        await db.add_checkin(message.from_user.id, "manual", data['energy'], data['stress'], data.get('emotions', []), data.get('note', ''))
        await state.finish()
        await message.answer("✅ Чекин сохранён!", reply_markup=get_main_menu())
    elif message.text == "✏️ Исправить":
        await state.update_data(_confirming=False)
        await CheckinStates.energy.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
        kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
        kb.add(KeyboardButton("❌ Отмена"))
        await message.answer("⚡ Оцени энергию (1–10):", reply_markup=kb)

def register(dp: Dispatcher):
    dp.register_message_handler(checkin_start, text="⚡️ Чек-ин", state="*")
    dp.register_message_handler(checkin_energy, state=CheckinStates.energy)
    dp.register_message_handler(checkin_stress, state=CheckinStates.stress)
    dp.register_message_handler(checkin_emotions, state=CheckinStates.emotions)
    dp.register_message_handler(checkin_note, state=CheckinStates.note)
    dp.register_message_handler(checkin_confirm, lambda m: m.text in ("✅ Сохранить", "✏️ Исправить"), state="*")
