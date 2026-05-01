import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db

logger = logging.getLogger(__name__)

class NoteStates(StatesGroup):
    new_section_name = State()
    new_note_title = State()
    new_note_content = State()
    edit_note_title = State()
    edit_note_content = State()

# ---------- Клавиатуры ----------
def get_notes_main_keyboard():
    buttons = [
        [KeyboardButton("📂 Мои разделы")],
        [KeyboardButton("➕ Новый раздел")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_section_actions_keyboard():
    buttons = [
        [KeyboardButton("➕ Новая заметка")],
        [KeyboardButton("📋 Мои заметки")],
        [KeyboardButton("🗑 Удалить раздел")],
        [KeyboardButton("⬅️ Назад к разделам")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад"))

# ---------- Главное меню заметок ----------
async def notes_main(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📝 *Заметки и идеи*", reply_markup=get_notes_main_keyboard(), parse_mode="Markdown")

# ---------- Список разделов ----------
async def list_sections(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    sections = await db.get_sections(user_id)
    if not sections:
        await db.add_section(user_id, "Мысли", "💭")
        await db.add_section(user_id, "Идеи", "💡")
        sections = await db.get_sections(user_id)

    # Сохраняем список разделов как список словарей (не asyncpg.Record)
    sections_list = [
        {"id": s['id'], "name": s['name'], "icon": s['icon']}
        for s in sections
    ]
    await state.update_data(sections=sections_list)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for s in sections_list:
        kb.add(KeyboardButton(f"{s['icon']} {s['name']}"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("📂 *Твои разделы:*\n\nВыбери раздел:", reply_markup=kb, parse_mode="Markdown")

# ---------- Выбор раздела (фильтр срабатывает на иконку + имя) ----------
async def section_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sections = data.get('sections', [])
    
    # Ищем раздел по тексту кнопки
    selected = None
    for s in sections:
        if message.text == f"{s['icon']} {s['name']}":
            selected = s
            break
    
    if not selected:
        return  # не нажали на раздел
    
    await state.update_data(current_section=selected)
    await message.answer(f"📄 *{selected['name']}*\n\nВыбери действие:", 
                        reply_markup=get_section_actions_keyboard(), parse_mode="Markdown")

# ---------- Создание раздела ----------
async def new_section_start(message: types.Message, state: FSMContext):
    await message.answer("Введи название раздела (можно с эмодзи, например «📌 Важное»):", reply_markup=get_back_keyboard())
    await NoteStates.new_section_name.set()

async def create_section(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await notes_main(message, state)
        return
    
    name = message.text.strip()
    icon = "📝"
    if name and len(name) > 0 and name[0] in "📝📌💡⭐❤️🔥✅💭📂":
        icon = name[0]
        name = name[1:].lstrip()
    
    user_id = message.from_user.id
    section_id = await db.add_section(user_id, name, icon)
    await state.finish()
    
    if section_id:
        await message.answer(f"✅ Раздел «{name}» создан!", reply_markup=get_notes_main_keyboard())
    else:
        await message.answer("❌ Ошибка (возможно, такое имя уже есть).", reply_markup=get_notes_main_keyboard())

# ---------- Удаление раздела ----------
async def delete_section(message: types.Message, state: FSMContext):
    data = await state.get_data()
    section = data.get('current_section')
    if not section:
        await message.answer("Сначала выбери раздел.")
        return
    
    async with db.pool.acquire() as conn:
        await conn.execute("DELETE FROM note_sections WHERE id = $1", section['id'])
    await state.finish()
    await message.answer(f"🗑 Раздел «{section['name']}» удалён.", reply_markup=get_notes_main_keyboard())

# ---------- Новая заметка в разделе ----------
async def new_note_start(message: types.Message, state: FSMContext):
    section = (await state.get_data()).get('current_section')
    if not section:
        await message.answer("Сначала выбери раздел.")
        return
    await message.answer("Введи заголовок (или «Пропустить»):", reply_markup=get_back_keyboard())
    await NoteStates.new_note_title.set()

async def new_note_title(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await list_sections(message, state)
        return
    title = None if message.text == "Пропустить" else message.text
    await state.update_data(note_title=title)
    await message.answer("Введи текст заметки:", reply_markup=get_back_keyboard())
    await NoteStates.new_note_content.set()

async def new_note_content(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await list_sections(message, state)
        return
    
    data = await state.get_data()
    section = data.get('current_section')
    title = data.get('note_title')
    content = message.text
    
    user_id = message.from_user.id
    note_id = await db.add_note_v2(user_id, section['id'], title, content)
    await state.finish()
    
    if note_id:
        await message.answer("✅ Заметка добавлена!", reply_markup=get_section_actions_keyboard())
    else:
        await message.answer("❌ Ошибка.", reply_markup=get_section_actions_keyboard())

# ---------- Просмотр заметок раздела ----------
async def list_notes_in_section(message: types.Message, state: FSMContext):
    data = await state.get_data()
    section = data.get('current_section')
    if not section:
        await message.answer("Сначала выбери раздел.")
        return
    
    user_id = message.from_user.id
    notes = await db.get_notes_by_section(section['id'], user_id)
    
    if not notes:
        await message.answer("В этом разделе пока нет заметок.", reply_markup=get_section_actions_keyboard())
        return
    
    text = f"📄 *{section['name']}*\n\n"
    for i, n in enumerate(notes, 1):
        preview = (n['title'] or 'Без заголовка') + ": " + (n['content'][:50] if n['content'] else "")
        text += f"{i}. {preview}\n"
    text += "\n✏️ `редактировать заметку 1`\n🗑 `удалить заметку 1`"
    await message.answer(text, reply_markup=get_section_actions_keyboard(), parse_mode="Markdown")
    
    # Сохраняем ID заметок для редактирования/удаления
    await state.update_data(current_notes_ids=[n['id'] for n in notes])

# ---------- Редактирование заметки ----------
async def edit_note_command(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Пример: `редактировать заметку 1`", parse_mode="Markdown")
        return
    try:
        num = int(parts[2]) - 1
    except:
        await message.answer("❌ Номер должен быть числом.")
        return
    
    data = await state.get_data()
    note_ids = data.get('current_notes_ids', [])
    if num < 0 or num >= len(note_ids):
        await message.answer(f"❌ Нет заметки с номером {num+1}.")
        return
    
    note_id = note_ids[num]
    note = await db.get_note_by_id(note_id, message.from_user.id)
    if not note:
        await message.answer("❌ Заметка не найдена.")
        return
    
    await state.update_data(edit_note_id=note_id)
    await message.answer(f"✏️ Текущий текст:\n\nЗаголовок: {note['title'] or 'нет'}\nСодержимое: {note['content'] or 'нет'}\n\nВведи новый заголовок (или «Пропустить»):", reply_markup=get_back_keyboard())
    await NoteStates.edit_note_title.set()

async def edit_note_title(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await list_notes_in_section(message, state)
        return
    title = None if message.text == "Пропустить" else message.text
    await state.update_data(edit_title=title)
    await message.answer("Введи новый текст (или «Пропустить»):", reply_markup=get_back_keyboard())
    await NoteStates.edit_note_content.set()

async def edit_note_content(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await list_notes_in_section(message, state)
        return
    
    data = await state.get_data()
    note_id = data.get('edit_note_id')
    title = data.get('edit_title')
    content = None if message.text == "Пропустить" else message.text
    
    await db.update_note(note_id, message.from_user.id, title, content)
    await state.finish()
    await message.answer("✅ Заметка обновлена!", reply_markup=get_section_actions_keyboard())

# ---------- Удаление заметки ----------
async def delete_note_command(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Пример: `удалить заметку 1`", parse_mode="Markdown")
        return
    try:
        num = int(parts[2]) - 1
    except:
        await message.answer("❌ Номер должен быть числом.")
        return
    
    data = await state.get_data()
    note_ids = data.get('current_notes_ids', [])
    if num < 0 or num >= len(note_ids):
        await message.answer(f"❌ Нет заметки с номером {num+1}.")
        return
    
    note_id = note_ids[num]
    await db.delete_note_v2(note_id, message.from_user.id)
    await message.answer("🗑 Заметка удалена.", reply_markup=get_section_actions_keyboard())

# ---------- Назад к разделам ----------
async def back_to_sections(message: types.Message, state: FSMContext):
    await state.finish()
    await list_sections(message, state)

# ---------- Регистрация ----------
def register(dp: Dispatcher):
    dp.register_message_handler(notes_main, text="📝 Заметки и идеи", state="*")
    dp.register_message_handler(list_sections, text="📂 Мои разделы", state="*")
    dp.register_message_handler(new_section_start, text="➕ Новый раздел", state="*")
    dp.register_message_handler(create_section, state=NoteStates.new_section_name)
    dp.register_message_handler(new_note_start, text="➕ Новая заметка", state="*")
    dp.register_message_handler(list_notes_in_section, text="📋 Мои заметки", state="*")
    dp.register_message_handler(delete_section, text="🗑 Удалить раздел", state="*")
    dp.register_message_handler(back_to_sections, text="⬅️ Назад к разделам", state="*")
    dp.register_message_handler(new_note_title, state=NoteStates.new_note_title)
    dp.register_message_handler(new_note_content, state=NoteStates.new_note_content)
    dp.register_message_handler(edit_note_command, regexp=r'^редактировать заметку \d+$', state='*')
    dp.register_message_handler(edit_note_title, state=NoteStates.edit_note_title)
    dp.register_message_handler(edit_note_content, state=NoteStates.edit_note_content)
    dp.register_message_handler(delete_note_command, regexp=r'^удалить заметку \d+$', state='*')
    
    # Выбор раздела — срабатывает на иконку + пробел + имя (любой раздел)
    dp.register_message_handler(section_selected, 
        lambda m: m.text and len(m.text) > 2 and m.text[0] in '💭💡📝📌⭐❤️🔥✅📂',
        state="*")
