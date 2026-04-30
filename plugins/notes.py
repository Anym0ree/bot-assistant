import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_notes_main_keyboard, get_main_menu

logger = logging.getLogger(__name__)

class NoteStates(StatesGroup):
    new_section_name = State()
    new_note_title = State()
    new_note_content = State()
    edit_note_select = State()
    edit_note_title = State()
    edit_note_content = State()
    delete_note_select = State()

# ... функции notes_main, list_sections, new_section, new_note, etc. (без изменений)

# ---------- Редактирование заметки (инлайн‑выбор) ----------
async def edit_note(message: types.Message, state: FSMContext):
    notes = (await state.get_data()).get('current_notes', [])
    if not notes:
        await message.answer("Нет заметок для редактирования.")
        return
    kb = InlineKeyboardMarkup(row_width=2)
    for i, n in enumerate(notes, 1):
        kb.insert(InlineKeyboardButton(str(i), callback_data=f"editnote_{n['id']}"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="editnote_cancel"))
    await message.answer("Выбери номер заметки для редактирования:", reply_markup=kb)
    await NoteStates.edit_note_select.set()

async def edit_note_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    if callback.data == "editnote_cancel":
        await state.finish()
        await section_callback(callback.message, state)
        return
    note_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    note = await db.get_note_by_id(note_id, user_id)
    if not note:
        await callback.message.answer("Заметка не найдена.")
        await state.finish()
        return
    await state.update_data(edit_note=note)
    await callback.message.answer("Введи новый заголовок (или «Пропустить»):")
    await NoteStates.edit_note_title.set()

# ---------- Удаление заметки (инлайн‑выбор) ----------
async def delete_note(message: types.Message, state: FSMContext):
    notes = (await state.get_data()).get('current_notes', [])
    if not notes:
        await message.answer("Нет заметок для удаления.")
        return
    kb = InlineKeyboardMarkup(row_width=2)
    for i, n in enumerate(notes, 1):
        kb.insert(InlineKeyboardButton(str(i), callback_data=f"delnote_{n['id']}"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="delnote_cancel"))
    await message.answer("Выбери номер заметки для удаления:", reply_markup=kb)
    await NoteStates.delete_note_select.set()

async def delete_note_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    if callback.data == "delnote_cancel":
        await state.finish()
        await section_callback(callback.message, state)
        return
    note_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    await db.delete_note(note_id, user_id)
    await callback.message.answer("🗑 Заметка удалена.")
    await state.finish()
    await section_callback(callback.message, state)

# ---------- Регистрация (добавлены инлайн‑колбэки) ----------
def register(dp: Dispatcher):
    dp.register_message_handler(notes_main, text="📝 Заметки и идеи", state="*")
    dp.register_message_handler(list_sections, text="📂 Мои разделы", state="*")
    dp.register_message_handler(new_section, text="➕ Новый раздел", state="*")
    dp.register_message_handler(create_section, state=NoteStates.new_section_name)
    dp.register_message_handler(new_note, text="➕ Новая заметка", state="*")
    dp.register_message_handler(edit_note, text="✏️ Редактировать", state="*")
    dp.register_message_handler(delete_note, text="🗑 Удалить заметку", state="*")
    dp.register_message_handler(new_note_title, state=NoteStates.new_note_title)
    dp.register_message_handler(new_note_content, state=NoteStates.new_note_content)
    dp.register_message_handler(edit_note_title, state=NoteStates.edit_note_title)
    dp.register_message_handler(edit_note_content, state=NoteStates.edit_note_content)
    dp.register_message_handler(section_callback, lambda m: m.text and len(m.text) > 2 and m.text[0] in '📝📌💡⭐❤️🔥✅', state="*")

    # Инлайн‑колбэки
    dp.register_callback_query_handler(edit_note_callback, lambda c: c.data.startswith('editnote_'), state=NoteStates.edit_note_select)
    dp.register_callback_query_handler(delete_note_callback, lambda c: c.data.startswith('delnote_'), state=NoteStates.delete_note_select)
