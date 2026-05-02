from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database import db
from states import DaySummaryStates
from keyboards import get_main_menu
from utils import send_temp_message, is_valid_score_text
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

async def day_summary_start(message: types.Message, state: FSMContext):
    target_date = await db.get_target_date_for_summary(message.from_user.id)
    if target_date is None:
        await send_temp_message(message.chat.id, "🕕 Итог дня доступен с 18:00 до 06:00.", 4)
        return
    if await db.has_day_summary_for_date(message.from_user.id, target_date):
        await send_temp_message(message.chat.id, f"📝 Итог за {target_date} уже сохранён.", 4)
        return
    await DaySummaryStates.score.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
    kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
    kb.add(KeyboardButton("❌ Отмена"))
    await message.answer("📊 Оценка дня (1–10):", reply_markup=kb)

async def summary_score(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return
    if not is_valid_score_text(message.text):
        await send_temp_message(message.chat.id, "❌ Оценка от 1 до 10", 3)
        return
    await state.update_data(score=int(message.text))
    await DaySummaryStates.best.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
    await message.answer("🌟 Лучшее событие дня?", reply_markup=kb)

async def summary_best(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await DaySummaryStates.score.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
        kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
        kb.add(KeyboardButton("❌ Отмена"))
        await message.answer("📊 Оценка дня (1–10):", reply_markup=kb)
        return
    best = "" if message.text == "Пропустить" else message.text
    await state.update_data(best=best)
    await DaySummaryStates.worst.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
    await message.answer("⚠️ Что было труднее всего?", reply_markup=kb)

async def summary_worst(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await DaySummaryStates.best.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
        await message.answer("🌟 Лучшее событие дня?", reply_markup=kb)
        return
    worst = "" if message.text == "Пропустить" else message.text
    await state.update_data(worst=worst)
    await DaySummaryStates.gratitude.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
    await message.answer("🙏 За что благодарен этому дню?", reply_markup=kb)

async def summary_gratitude(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await DaySummaryStates.worst.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
        await message.answer("⚠️ Что было труднее всего?", reply_markup=kb)
        return
    gratitude = "" if message.text == "Пропустить" else message.text
    await state.update_data(gratitude=gratitude)
    await DaySummaryStates.note.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
    await message.answer("📝 Заметка? (можно пропустить)", reply_markup=kb)

async def summary_note(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await DaySummaryStates.gratitude.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Пропустить"), KeyboardButton("↩️ Назад"))
        await message.answer("🙏 За что благодарен этому дню?", reply_markup=kb)
        return

    data = await state.get_data()
    note = "" if message.text == "Пропустить" else message.text

    summary = (
        f"📋 *Проверь данные:*\n\n"
        f"📊 Оценка: {data.get('score')}/10\n"
        f"🌟 Лучшее: {data.get('best') or 'нет'}\n"
        f"⚠️ Трудное: {data.get('worst') or 'нет'}\n"
        f"🙏 Благодарность: {data.get('gratitude') or 'нет'}\n"
        f"📝 Заметка: {note or 'нет'}\n\n"
        f"Всё верно?"
    )
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Сохранить"), KeyboardButton("✏️ Исправить"))
    await message.answer(summary, reply_markup=kb, parse_mode="Markdown")
    await state.update_data(note=note, _confirming=True)

async def summary_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("_confirming"):
        return

    if message.text == "✅ Сохранить":
        await db.add_day_summary(message.from_user.id, data['score'], data.get('best', ''), data.get('worst', ''), data.get('gratitude', ''), data.get('note', ''))
        await state.finish()
        await message.answer("✅ Итог дня сохранён!", reply_markup=get_main_menu())
    elif message.text == "✏️ Исправить":
        await state.update_data(_confirming=False)
        await DaySummaryStates.score.set()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(*[KeyboardButton(str(i)) for i in range(1, 6)])
        kb.row(*[KeyboardButton(str(i)) for i in range(6, 11)])
        kb.add(KeyboardButton("❌ Отмена"))
        await message.answer("📊 Оценка дня (1–10):", reply_markup=kb)

def register(dp: Dispatcher):
    dp.register_message_handler(day_summary_start, text="📝 Итог дня", state="*")
    dp.register_message_handler(summary_score, state=DaySummaryStates.score)
    dp.register_message_handler(summary_best, state=DaySummaryStates.best)
    dp.register_message_handler(summary_worst, state=DaySummaryStates.worst)
    dp.register_message_handler(summary_gratitude, state=DaySummaryStates.gratitude)
    dp.register_message_handler(summary_note, state=DaySummaryStates.note)
    dp.register_message_handler(summary_confirm, lambda m: m.text in ("✅ Сохранить", "✏️ Исправить"), state="*")
