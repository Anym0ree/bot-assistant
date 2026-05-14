import json
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db

logger = logging.getLogger(__name__)

TRUTH_SECTION_NAME = "🗣️ Правда дня"

class NoteStates(StatesGroup):
    new_section_name = State()
    new_note_title = State()
    new_note_content = State()
    edit_note_title = State()
    edit_note_content = State()
    # состояния для списков
    new_list_title = State()
    new_list_items = State()
    list_view = State()             # просмотр и работа со списком
    list_add_item = State()        # ввод нового пункта
    list_edit_title = State()      # смена названия списка

# ---------- Клавиатуры ----------
def get_notes_main_keyboard():
    buttons = [
        [KeyboardButton("📂 Мои разделы")],
        [KeyboardButton("➕ Новый раздел")],
        [KeyboardButton("🗣️ Правда дня")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_section_actions_keyboard():
    buttons = [
        [KeyboardButton("➕ Новая заметка"), KeyboardButton("📋 Создать список")],
        [KeyboardButton("📋 Мои заметки")],
        [KeyboardButton("🗑 Удалить раздел")],
        [KeyboardButton("⬅️ Назад к разделам")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("↩️ Назад"))
    return kb

# ---------- Главное меню заметок ----------
async def notes_main(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("📝 *Заметки и идеи*", reply_markup=get_notes_main_keyboard(), parse_mode="Markdown")

# ---------- Список разделов ----------
async def list_sections(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    sections = await db.get_sections(user_id)
    sections_list = [{"id": s['id'], "name": s['name'], "icon": s['icon']} for s in sections]
    await state.update_data(sections=sections_list)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for s in sections_list:
        kb.add(KeyboardButton(f"{s['icon']} {s['name']}"))
    kb.add(KeyboardButton("⬅️ Назад"))
    await message.answer("📂 *Твои разделы:*\n\nВыбери раздел:", reply_markup=kb, parse_mode="Markdown")

# ---------- Выбор раздела ----------
async def section_selected(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sections = data.get('sections', [])
    selected = None
    for s in sections:
        if message.text == f"{s['icon']} {s['name']}":
            selected = s
            break
    if not selected:
        return

    await state.update_data(current_section=selected)
    await message.answer(f"📄 *{selected['name']}*\n\nВыбери действие:",
                        reply_markup=get_section_actions_keyboard(), parse_mode="Markdown")

# ---------- Правда дня ----------
async def truth_of_the_day(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    sections = await db.get_sections(user_id)
    truth_section = None
    for s in sections:
        if s['name'] == TRUTH_SECTION_NAME:
            truth_section = s
            break
    if not truth_section:
        section_id = await db.add_section(user_id, TRUTH_SECTION_NAME, "🗣️")
        if section_id:
            sections = await db.get_sections(user_id)
            for s in sections:
                if s['id'] == section_id:
                    truth_section = s
                    break
    if not truth_section:
        await message.answer("❌ Не удалось создать раздел «Правда дня».")
        return

    selected = {"id": truth_section['id'], "name": truth_section['name'], "icon": truth_section['icon']}
    await state.update_data(current_section=selected)
    await message.answer(
        "🗣️ *Правда дня*\n\n"
        "Что ты сегодня скрыл от других? Что побоялся сказать?\n"
        "Напиши честно — это только твоё пространство.",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    await NoteStates.new_note_title.set()

# ---------- Новый раздел ----------
async def new_section_start(message: types.Message, state: FSMContext):
    await message.answer("Введи название раздела (можно с эмодзи, например «📌 Важное»):", reply_markup=get_back_keyboard())
    await NoteStates.new_section_name.set()

async def create_section(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
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

# ---------- Обычная заметка ----------
async def new_note_start(message: types.Message, state: FSMContext):
    section = (await state.get_data()).get('current_section')
    if not section:
        await message.answer("Сначала выбери раздел.")
        return
    if section.get('name') == TRUTH_SECTION_NAME:
        await message.answer("Напиши свою правду дня — честно, как есть:", reply_markup=get_back_keyboard())
        await NoteStates.new_note_content.set()
        return
    await message.answer("Введи заголовок (или «Пропустить»):", reply_markup=get_back_keyboard())
    await NoteStates.new_note_title.set()

async def new_note_title(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await state.finish()
        await list_sections(message, state)
        return
    title = None if message.text == "Пропустить" else message.text
    await state.update_data(note_title=title)
    await message.answer("Введи текст заметки:", reply_markup=get_back_keyboard())
    await NoteStates.new_note_content.set()

async def new_note_content(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await state.finish()
        await list_sections(message, state)
        return
    data = await state.get_data()
    section = data.get('current_section')
    title = data.get('note_title')
    content = message.text
    if section and section.get('name') == TRUTH_SECTION_NAME:
        if not content.startswith("#правда"):
            content = f"#правда {content}"
    user_id = message.from_user.id
    note_id = await db.add_note_v2(user_id, section['id'], title, content)
    await state.finish()
    if note_id:
        await message.answer("✅ Заметка добавлена!", reply_markup=get_section_actions_keyboard())
    else:
        await message.answer("❌ Ошибка.", reply_markup=get_section_actions_keyboard())

# ---------- Создание списка ----------
async def new_list_start(message: types.Message, state: FSMContext):
    section = (await state.get_data()).get('current_section')
    if not section:
        await message.answer("Сначала выбери раздел.")
        return
    await message.answer("Введи название списка:", reply_markup=get_back_keyboard())
    await NoteStates.new_list_title.set()

async def new_list_title(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await state.finish()
        await list_sections(message, state)
        return
    await state.update_data(list_title=message.text)
    await message.answer(
        "Теперь напиши пункты списка.\n"
        "Каждый пункт с новой строки, например:\n"
        "Хлеб\nМолоко\nЯйца",
        reply_markup=get_back_keyboard()
    )
    await NoteStates.new_list_items.set()

async def new_list_items(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await state.finish()
        await list_sections(message, state)
        return
    lines = [line.strip() for line in message.text.split('\n') if line.strip()]
    if not lines:
        await message.answer("Напиши хотя бы один пункт.")
        return

    data = await state.get_data()
    section = data.get('current_section')
    title = data.get('list_title', 'Список')
    items = [{"text": line, "done": False} for line in lines]
    content = json.dumps(items, ensure_ascii=False)

    user_id = message.from_user.id
    note_id = await db.add_note_v2(user_id, section['id'], f"📋 {title}", content)
    await state.finish()
    if note_id:
        # сразу показываем список в режиме просмотра
        fake_note = {"id": note_id, "title": f"📋 {title}", "content": content}
        await state.update_data(current_list=fake_note)
        await show_list_view(message, state, fake_note)
    else:
        await message.answer("❌ Ошибка при создании списка.", reply_markup=get_section_actions_keyboard())

# ---------- Просмотр всех записей раздела (включая списки) ----------
async def list_notes_in_section(message: types.Message, state: FSMContext):
    data = await state.get_data()
    section = data.get('current_section')
    if not section:
        await message.answer("Сначала выбери раздел.")
        return
    user_id = message.from_user.id
    notes = await db.get_notes_by_section(section['id'], user_id)
    if not notes:
        await message.answer("В этом разделе пока нет записей.", reply_markup=get_section_actions_keyboard())
        return

    # Сохраняем ID всех записей (и заметок, и списков) для редактирования/удаления
    ids = [n['id'] for n in notes]
    await state.update_data(current_notes_ids=ids)

    text = f"📄 *{section['name']}*\n\n"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for i, n in enumerate(notes, 1):
        title = n['title'] or 'Без заголовка'
        if title.startswith("📋 "):
            # это список, делаем кнопку для открытия
            text += f"{i}. {title}\n"
            kb.add(KeyboardButton(f"📋 Открыть #{n['id']}"))
        else:
            preview = (n['content'][:50] if n['content'] else "")
            text += f"{i}. {title}: {preview}\n"
    text += "\n✏️ `редактировать заметку 1`\n🗑 `удалить заметку 1`"
    kb.add(KeyboardButton("⬅️ Назад к разделу"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# ---------- Открыть список по кнопке из общего списка ----------
async def open_list_by_button(message: types.Message, state: FSMContext):
    if not message.text.startswith("📋 Открыть #"):
        return
    list_id = int(message.text.split("#")[1])
    user_id = message.from_user.id
    note = await db.get_note_by_id(list_id, user_id)
    if not note:
        await message.answer("Список не найден.")
        return
    await state.update_data(current_list=note)
    await NoteStates.list_view.set()
    await show_list_view(message, state, note)

# ---------- Отображение списка и кнопок управления ----------
async def show_list_view(message: types.Message, state: FSMContext, note):
    try:
        items = json.loads(note['content'])
    except:
        items = []
    text = f"📋 *{note['title']}*\n\n"
    for i, item in enumerate(items, 1):
        done = item.get('done', False)
        line = f"{'~' if done else ''}{item['text']}{'~' if done else ''}"
        text += f"{i}. {line}\n"

    # клавиатура управления (Reply)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    # кнопки для отметки пунктов (максимум 9, чтобы не забивать)
    for i, item in enumerate(items[:9], 1):
        if not item.get('done'):
            kb.add(KeyboardButton(f"✅ Отм. {i}"))
    kb.add(KeyboardButton("➕ Добавить пункт"))
    kb.add(KeyboardButton("✏️ Название"), KeyboardButton("🗑 Удалить список"))
    kb.add(KeyboardButton("⬅️ Назад к разделу"))
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# ---------- Отметка пункта ----------
async def list_toggle_item(message: types.Message, state: FSMContext):
    if not message.text.startswith("✅ Отм. "):
        return
    idx = int(message.text.split(".")[1]) - 1
    data = await state.get_data()
    note = data.get('current_list')
    if not note:
        await message.answer("Список не найден.")
        return
    items = json.loads(note['content'])
    if 0 <= idx < len(items):
        items[idx]['done'] = not items[idx].get('done', False)
        new_content = json.dumps(items, ensure_ascii=False)
        await db.update_note(note['id'], message.from_user.id, content=new_content)
        note['content'] = new_content
        await state.update_data(current_list=note)
    # перерисовываем список
    await show_list_view(message, state, note)

# ---------- Добавление пункта ----------
async def list_add_item_start(message: types.Message, state: FSMContext):
    await message.answer("Введи новый пункт:", reply_markup=get_back_keyboard())
    await NoteStates.list_add_item.set()

async def list_add_item_save(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await NoteStates.list_view.set()
        data = await state.get_data()
        note = data.get('current_list')
        if note:
            await show_list_view(message, state, note)
        return
    text = message.text.strip()
    if not text:
        await message.answer("Введи текст пункта.")
        return
    data = await state.get_data()
    note = data.get('current_list')
    if not note:
        await message.answer("Список не найден.")
        return
    items = json.loads(note['content'])
    items.append({"text": text, "done": False})
    new_content = json.dumps(items, ensure_ascii=False)
    await db.update_note(note['id'], message.from_user.id, content=new_content)
    note['content'] = new_content
    await state.update_data(current_list=note)
    await NoteStates.list_view.set()
    await show_list_view(message, state, note)

# ---------- Изменение названия ----------
async def list_edit_title_start(message: types.Message, state: FSMContext):
    await message.answer("Введи новое название списка:", reply_markup=get_back_keyboard())
    await NoteStates.list_edit_title.set()

async def list_edit_title_save(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await NoteStates.list_view.set()
        data = await state.get_data()
        note = data.get('current_list')
        if note:
            await show_list_view(message, state, note)
        return
    new_title = message.text.strip()
    if not new_title:
        await message.answer("Название не может быть пустым.")
        return
    data = await state.get_data()
    note = data.get('current_list')
    if not note:
        return
    if not new_title.startswith("📋 "):
        new_title = "📋 " + new_title
    await db.update_note(note['id'], message.from_user.id, title=new_title)
    note['title'] = new_title
    await state.update_data(current_list=note)
    await NoteStates.list_view.set()
    await show_list_view(message, state, note)

# ---------- Удаление списка ----------
async def list_delete(message: types.Message, state: FSMContext):
    data = await state.get_data()
    note = data.get('current_list')
    if not note:
        return
    await db.delete_note_v2(note['id'], message.from_user.id)
    await state.finish()
    await message.answer("🗑 Список удалён.", reply_markup=get_section_actions_keyboard())

# ---------- Обратно из списка в раздел ----------
async def list_back_to_section(message: types.Message, state: FSMContext):
    await state.finish()
    # имитируем вызов section_selected, чтобы вернуться в меню раздела
    data = await state.get_data()
    section = data.get('current_section')
    if section:
        await state.update_data(current_section=section)
        await message.answer(f"📄 *{section['name']}*\n\nВыбери действие:",
                            reply_markup=get_section_actions_keyboard(), parse_mode="Markdown")
    else:
        await list_sections(message, state)

# ---------- Общие обработчики редактирования/удаления (оставлены без изменений) ----------
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
    await message.answer(
        f"✏️ Текущий текст:\n\nЗаголовок: {note['title'] or 'нет'}\nСодержимое: {note['content'] or 'нет'}\n\n"
        "Введи новый заголовок (или «Пропустить»):",
        reply_markup=get_back_keyboard()
    )
    await NoteStates.edit_note_title.set()

async def edit_note_title(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await state.finish()
        await list_notes_in_section(message, state)
        return
    title = None if message.text == "Пропустить" else message.text
    await state.update_data(edit_title=title)
    await message.answer("Введи новый текст (или «Пропустить»):", reply_markup=get_back_keyboard())
    await NoteStates.edit_note_content.set()

async def edit_note_content(message: types.Message, state: FSMContext):
    if message.text == "↩️ Назад":
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

async def back_to_sections(message: types.Message, state: FSMContext):
    await state.finish()
    await list_sections(message, state)

# ---------- Регистрация ----------
def register(dp: Dispatcher):
    dp.register_message_handler(notes_main, text="📂 Заметки", state="*")
    dp.register_message_handler(list_sections, text="📂 Мои разделы", state="*")
    dp.register_message_handler(new_section_start, text="➕ Новый раздел", state="*")
    dp.register_message_handler(create_section, state=NoteStates.new_section_name)
    dp.register_message_handler(truth_of_the_day, text="🗣️ Правда дня", state="*")
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

    # Списки
    dp.register_message_handler(new_list_start, text="📋 Создать список", state="*")
    dp.register_message_handler(new_list_title, state=NoteStates.new_list_title)
    dp.register_message_handler(new_list_items, state=NoteStates.new_list_items)
    dp.register_message_handler(open_list_by_button, lambda m: m.text and m.text.startswith("📋 Открыть #"), state="*")
    dp.register_message_handler(list_toggle_item, lambda m: m.text and m.text.startswith("✅ Отм. "), state=NoteStates.list_view)
    dp.register_message_handler(list_add_item_start, text="➕ Добавить пункт", state=NoteStates.list_view)
    dp.register_message_handler(list_add_item_save, state=NoteStates.list_add_item)
    dp.register_message_handler(list_edit_title_start, text="✏️ Название", state=NoteStates.list_view)
    dp.register_message_handler(list_edit_title_save, state=NoteStates.list_edit_title)
    dp.register_message_handler(list_delete, text="🗑 Удалить список", state=NoteStates.list_view)
    dp.register_message_handler(list_back_to_section, text="⬅️ Назад к разделу", state=NoteStates.list_view)

    dp.register_message_handler(section_selected,
        lambda m: m.text and len(m.text) > 2 and m.text[0] in '💭💡📝📌⭐❤️🔥✅📂',
        state="*")
