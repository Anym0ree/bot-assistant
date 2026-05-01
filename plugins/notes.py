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

# ---------- Главное меню заметок ----------
async def notes_main(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    sections = await db.get_sections(user_id)
    if not sections:
        await db.add_section(user_id, "Мысли", "💭")
        await db.add_section(user_id, "Заметки", "📂")
        await db.add_section(user_id, "Идеи", "💡")
    await message.answer("📝 Заметки и идеи", reply_markup=get_notes_main_keyboard())

# ---------- Список разделов ----------
async def list_sections(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    sections = await db.get_sections(user_id)
    if not sections:
        await message.answer("У тебя нет разделов. Создай новый кнопкой «➕ Новый раздел».")
        return
    await state.update_data(sections=sections, section_page=0)
    await show_sections_page(message, state, sections, 0)

async def show_sections_page(message: types.Message, state: FSMContext, sections, page):
    per_page = 5
    start = page * per_page
    end = start + per_page
    page_sections = sections[start:end]
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for s in page_sections:
        kb.insert(KeyboardButton(text=f"{s['icon']} {s['name']}"))
    if len(sections) > per_page:
        if page > 0:
            kb.add(KeyboardButton("◀️ Предыдущая страница разделов"))
        if end < len(sections):
            kb.add(KeyboardButton("Следующая страница разделов ▶️"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer(f"📂 Твои разделы (страница {page+1}):", reply_markup=kb)
    await state.update_data(section_page=page)

async def change_section_page(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sections = data.get('sections', [])
    page = data.get('section_page', 0)
    if "предыдущая" in message.text.lower():
        page = max(0, page - 1)
    elif "следующая" in message.text.lower():
        page = min(page + 1, (len(sections)-1)//5)
    else:
        return
    await state.update_data(section_page=page)
    await show_sections_page(message, state, sections, page)

# ---------- Выбор раздела ----------
async def section_callback(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sections = data.get('sections', [])
    selected = None
    for s in sections:
        if message.text.startswith(s['icon']) and message.text[len(s['icon'])+1:] == s['name']:
            selected = s
            break
    if not selected:
        await message.answer("Раздел не найден.")
        return
    await state.update_data(current_section=selected)
    notes = await db.get_notes_by_section(selected['id'], message.from_user.id)
    if not notes:
        await message.answer(f"В разделе «{selected['name']}» пока нет заметок.", reply_markup=get_note_actions_keyboard())
    else:
        text = f"📄 *{selected['name']}*\n"
        for i, n in enumerate(notes, 1):
            text += f"{i}. {n['title'] or 'Без заголовка'}\n"
        await message.answer(text, parse_mode="Markdown", reply_markup=get_note_actions_keyboard())
        await state.update_data(current_notes=notes)

def get_note_actions_keyboard():
    buttons = [
        [KeyboardButton("➕ Новая заметка")],
        [KeyboardButton("✏️ Редактировать")],
        [KeyboardButton("🗑 Удалить заметку")],
        [KeyboardButton("⬅️ Назад в раздел")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ---------- Создание раздела ----------
async def new_section(message: types.Message, state: FSMContext):
    await message.answer("Введи название нового раздела (можно с эмодзи в начале, например «📌 Важное»):")
    await NoteStates.new_section_name.set()

async def create_section(message: types.Message, state: FSMContext):
    name = message.text.strip()
    icon = "📂"
    if name and name[0] in "📂📌💡⭐❤️🔥✅":
        icon = name[0]
        name = name[1:].lstrip()
    user_id = message.from_user.id
    section_id = await db.add_section(user_id, name, icon)
    if section_id:
        await message.answer(f"✅ Раздел «{name}» создан.")
    else:
        await message.answer("❌ Не удалось создать раздел (возможно, такое имя уже есть).")
    await state.finish()
    await notes_main(message, state)

# ---------- Добавление заметки ----------
async def new_note(message: types.Message, state: FSMContext):
    current_section = (await state.get_data()).get('current_section')
    if not current_section:
        await message.answer("Сначала выбери раздел через «📂 Мои разделы».")
        return
    await message.answer("Введи заголовок заметки (можно пропустить, отправь «Пропустить»):")
    await NoteStates.new_note_title.set()

async def new_note_title(message: types.Message, state: FSMContext):
    title = None if message.text == "Пропустить" else message.text
    await state.update_data(new_note_title=title)
    await message.answer("Введи текст заметки (можно несколько строк, отправь «Готово» для завершения):")
    await NoteStates.new_note_content.set()

async def new_note_content(message: types.Message, state: FSMContext):
    content = message.text
    if content == "Готово":
        content = ""
    data = await state.get_data()
    title = data.get('new_note_title')
    section = data.get('current_section')
    user_id = message.from_user.id
    note_id = await db.add_note(user_id, section['id'], title, content)
    if note_id:
        await message.answer("✅ Заметка добавлена.")
    else:
        await message.answer("❌ Ошибка.")
    await state.finish()
    await section_callback(message, state)

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

async def edit_note_title(message: types.Message, state: FSMContext):
    title = None if message.text == "Пропустить" else message.text
    await state.update_data(edit_title=title)
    await message.answer("Введи новый текст заметки (или «Пропустить»):")
    await NoteStates.edit_note_content.set()

async def edit_note_content(message: types.Message, state: FSMContext):
    content = None if message.text == "Пропустить" else message.text
    data = await state.get_data()
    note = data['edit_note']
    user_id = message.from_user.id
    await db.update_note(note['id'], user_id, data.get('edit_title'), content)
    await message.answer("✅ Заметка обновлена.")
    await state.finish()
    await section_callback(message, state)

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

# ---------- Регистрация ----------
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
    
    # ИСПРАВЛЕНО: не перехватываем "📝 Итог дня" и "📝 Заметки и идеи"
    dp.register_message_handler(section_callback,
        lambda m: m.text and m.text[0] in '📝📂📌💡⭐❤️🔥✅' 
                  and m.text not in ('📝 Итог дня', '📝 Заметки и идеи'),
        state="*")
    
    dp.register_message_handler(change_section_page,
        lambda m: m.text and "страница разделов" in m.text,
        state="*")

    dp.register_callback_query_handler(edit_note_callback,
        lambda c: c.data.startswith('editnote_'),
        state=NoteStates.edit_note_select)
    dp.register_callback_query_handler(delete_note_callback,
        lambda c: c.data.startswith('delnote_'),
        state=NoteStates.delete_note_select)
