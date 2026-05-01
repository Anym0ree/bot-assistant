import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db

logger = logging.getLogger(__name__)

class NoteStates(StatesGroup):
    waiting_for_text = State()
    edit_text = State()

def get_notes_menu_keyboard():
    buttons = [
        [KeyboardButton("➕ Новая заметка")],
        [KeyboardButton("📋 Мои заметки")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_cancel_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Отмена"))
    return kb

# ---------- Главное меню заметок ----------
async def notes_main(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📝 Заметки и идеи\n\nВыбери действие:", reply_markup=get_notes_menu_keyboard())

# ---------- Список заметок ----------
async def list_notes(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    notes = await db.get_notes(user_id)
    if not notes:
        await message.answer("У тебя пока нет заметок.", reply_markup=get_notes_menu_keyboard())
        return

    text = "📋 *Твои заметки:*\n\n"
    for i, note in enumerate(notes, 1):
        preview = note['text'][:60].replace('\n', ' ') + ("..." if len(note['text']) > 60 else "")
        text += f"{i}. 📅 {note['date']} {note['time']}\n   {preview}\n\n"
    text += "✏️ *Редактировать:* `редактировать заметку 1`\n"
    text += "🗑 *Удалить:* `удалить заметку 1`"
    await message.answer(text, reply_markup=get_notes_menu_keyboard(), parse_mode="Markdown")

# ---------- Создание заметки ----------
async def new_note_start(message: types.Message, state: FSMContext):
    await message.answer("📝 Напиши текст заметки. Или нажми ❌ Отмена.", reply_markup=get_cancel_keyboard())
    await NoteStates.waiting_for_text.set()

async def new_note_save(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await notes_main(message, state)
        return
    user_id = message.from_user.id
    note_id = await db.add_note(user_id, message.text)
    await state.finish()
    if note_id:
        await message.answer("✅ Заметка сохранена!", reply_markup=get_notes_menu_keyboard())
    else:
        await message.answer("❌ Не удалось сохранить.", reply_markup=get_notes_menu_keyboard())

# ---------- Редактирование заметки ----------
async def edit_note_start(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Укажи номер. Пример: `редактировать заметку 2`", parse_mode="Markdown")
        return
    try:
        num = int(parts[2])
    except ValueError:
        await message.answer("❌ Номер должен быть числом.")
        return

    user_id = message.from_user.id
    notes = await db.get_notes(user_id)
    if not notes or num < 1 or num > len(notes):
        await message.answer(f"❌ Нет заметки с номером {num}. Всего: {len(notes)}")
        return

    note = notes[num - 1]
    await state.update_data(edit_note_id=note['id'])
    await message.answer(f"✏️ Текущий текст:\n\n{note['text']}\n\nВведи новый текст (или ❌ Отмена):", reply_markup=get_cancel_keyboard())
    await NoteStates.edit_text.set()

async def edit_note_save(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await notes_main(message, state)
        return
    data = await state.get_data()
    note_id = data.get('edit_note_id')
    if note_id:
        async with db.pool.acquire() as conn:
            await conn.execute("UPDATE notes SET text = $1, timestamp = NOW() WHERE id = $2", message.text, note_id)
        await message.answer("✅ Заметка обновлена!", reply_markup=get_notes_menu_keyboard())
    else:
        await message.answer("❌ Ошибка.", reply_markup=get_notes_menu_keyboard())
    await state.finish()

# ---------- Удаление заметки ----------
async def delete_note_start(message: types.Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Укажи номер. Пример: `удалить заметку 1`", parse_mode="Markdown")
        return
    try:
        num = int(parts[2])
    except ValueError:
        await message.answer("❌ Номер должен быть числом.")
        return

    user_id = message.from_user.id
    notes = await db.get_notes(user_id)
    if not notes or num < 1 or num > len(notes):
        await message.answer(f"❌ Нет заметки с номером {num}. Всего: {len(notes)}")
        return

    note = notes[num - 1]
    success = await db.delete_note_by_id(user_id, note['id'])
    if success:
        await message.answer("🗑 Заметка удалена.", reply_markup=get_notes_menu_keyboard())
    else:
        await message.answer("❌ Не удалось удалить.", reply_markup=get_notes_menu_keyboard())

# ---------- Регистрация ----------
def register(dp: Dispatcher):
    dp.register_message_handler(notes_main, text="📝 Заметки и идеи", state="*")
    dp.register_message_handler(list_notes, text="📋 Мои заметки", state="*")
    dp.register_message_handler(new_note_start, text="➕ Новая заметка", state="*")
    dp.register_message_handler(new_note_save, state=NoteStates.waiting_for_text)
    dp.register_message_handler(edit_note_start, regexp=r'^редактировать заметку \d+$', state='*')
    dp.register_message_handler(edit_note_save, state=NoteStates.edit_text)
    dp.register_message_handler(delete_note_start, regexp=r'^удалить заметку \d+$', state='*')
