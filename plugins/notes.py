import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu

logger = logging.getLogger(__name__)

class NoteStates(StatesGroup):
    new_note_title = State()
    new_note_content = State()
    edit_note_select = State()
    edit_note_content = State()
    delete_note_select = State()

# ---------- Клавиатуры ----------
def get_notes_keyboard():
    buttons = [
        [KeyboardButton("➕ Новая заметка")],
        [KeyboardButton("📋 Мои заметки")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_notes_keyboard():
    buttons = [
        [KeyboardButton("⬅️ Назад к заметкам")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ---------- Главное меню заметок ----------
async def notes_main(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📝 Заметки и идеи", reply_markup=get_notes_keyboard())

# ---------- Список заметок ----------
async def list_notes(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    notes = await db.get_notes(user_id)
    if not notes:
        await message.answer("У тебя пока нет заметок.", reply_markup=get_notes_keyboard())
        return

    text = "📋 *Твои заметки:*\n\n"
    for i, n in enumerate(notes, 1):
        note_text = n['text'][:50] + "..." if len(n['text']) > 50 else n['text']
        text += f"{i}. 📅 {n['date']} {n['time']} — {note_text}\n"
    text += "\n✏️ *Редактировать:* `редактировать заметку <номер>`\n🗑 *Удалить:* `удалить заметку <номер>`"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_notes_keyboard())
    await state.update_data(current_notes=notes)

# ---------- Добавление заметки ----------
async def new_note(message: types.Message, state: FSMContext):
    await message.answer("Введи заголовок заметки (можно пропустить, отправь «Пропустить»):", reply_markup=get_back_notes_keyboard())
    await NoteStates.new_note_title.set()

async def new_note_title(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад к заметкам":
        await state.finish()
        await notes_main(message, state)
        return
    title = None if message.text == "Пропустить" else message.text
    await state.update_data(note_title=title)
    await message.answer("Введи текст заметки:", reply_markup=get_back_notes_keyboard())
    await NoteStates.new_note_content.set()

async def new_note_content(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад к заметкам":
        await state.finish()
        await notes_main(message, state)
        return
    data = await state.get_data()
    title = data.get('note_title', '')
    content = message.text
    full_text = f"{title}\n{content}" if title else content

    user_id = message.from_user.id
    note_id = await db.add_note_simple(user_id, full_text)
    if note_id:
        await message.answer("✅ Заметка добавлена!", reply_markup=get_notes_keyboard())
    else:
        await message.answer("❌ Ошибка при добавлении.", reply_markup=get_notes_keyboard())
    await state.finish()

# ---------- Редактирование заметки ----------
async def edit_note_command(message: types.Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: `редактировать заметку <номер>`", parse_mode="Markdown")
        return
    try:
        num = int(parts[2])
    except:
        await message.answer("❌ Номер должен быть числом.")
        return

    user_id = message.from_user.id
    notes = await db.get_notes(user_id)
    if not notes or num < 1 or num > len(notes):
        await message.answer(f"❌ Неверный номер. Доступно заметок: {len(notes)}")
        return

    note = notes[num - 1]
    await state.update_data(edit_note_id=note['id'])
    await message.answer(f"✏️ Редактируем заметку:\n\n{note['text']}\n\nВведи новый текст (или «Отмена»):", reply_markup=get_back_notes_keyboard())
    await NoteStates.edit_note_content.set()

async def edit_note_content(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад к заметкам":
        await state.finish()
        await notes_main(message, state)
        return
    if message.text == "Отмена":
        await state.finish()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_notes_keyboard())
        return

    data = await state.get_data()
    note_id = data.get('edit_note_id')
    new_text = message.text
    user_id = message.from_user.id

    if note_id:
        async with db.pool.acquire() as conn:
            await conn.execute("UPDATE notes SET text = $1 WHERE id = $2 AND user_id = $3", new_text, note_id, user_id)
        await message.answer("✅ Заметка обновлена!", reply_markup=get_notes_keyboard())
    else:
        await message.answer("❌ Ошибка: заметка не найдена.", reply_markup=get_notes_keyboard())
    await state.finish()

# ---------- Удаление заметки ----------
async def delete_note_command(message: types.Message):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: `удалить заметку <номер>`", parse_mode="Markdown")
        return
    try:
        num = int(parts[2])
    except:
        await message.answer("❌ Номер должен быть числом.")
        return

    user_id = message.from_user.id
    notes = await db.get_notes(user_id)
    if not notes or num < 1 or num > len(notes):
        await message.answer(f"❌ Неверный номер. Доступно заметок: {len(notes)}")
        return

    note = notes[num - 1]
    success = await db.delete_note_by_id(user_id, note['id'])
    if success:
        await message.answer("🗑 Заметка удалена.", reply_markup=get_notes_keyboard())
    else:
        await message.answer("❌ Не удалось удалить.", reply_markup=get_notes_keyboard())

# ---------- Назад ----------
async def back_to_notes_main(message: types.Message, state: FSMContext):
    await state.finish()
    await notes_main(message, state)

# ---------- Регистрация ----------
def register(dp: Dispatcher):
    dp.register_message_handler(notes_main, text="📝 Заметки и идеи", state="*")
    dp.register_message_handler(list_notes, text="📋 Мои заметки", state="*")
    dp.register_message_handler(new_note, text="➕ Новая заметка", state="*")
    dp.register_message_handler(new_note_title, state=NoteStates.new_note_title)
    dp.register_message_handler(new_note_content, state=NoteStates.new_note_content)
    dp.register_message_handler(edit_note_command, regexp=r'^редактировать заметку \d+$', state='*')
    dp.register_message_handler(edit_note_content, state=NoteStates.edit_note_content)
    dp.register_message_handler(delete_note_command, regexp=r'^удалить заметку \d+$', state='*')
    dp.register_message_handler(back_to_notes_main, text="⬅️ Назад к заметкам", state="*")
