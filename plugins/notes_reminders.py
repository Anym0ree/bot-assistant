import re
import logging
from datetime import datetime, timedelta
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import NoteStates, ReminderStates, LastSectionState
from keyboards import get_notes_reminders_main_menu, get_record_type_buttons, get_view_type_buttons, get_back_button, get_reminder_date_buttons, get_reminder_hour_buttons, get_reminder_minute_buttons, get_reminder_advance_buttons, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish

MIN_DELTA = timedelta(minutes=2)

# ========== ОСНОВНОЕ МЕНЮ ==========
async def notes_reminders_main(message: types.Message):
    await message.answer("📝 Заметки и напоминания\n\nВыбери действие:", reply_markup=get_notes_reminders_main_menu())

async def add_record_type(message: types.Message):
    await message.answer("Что хочешь добавить?", reply_markup=get_record_type_buttons())

# ========== ЗАМЕТКИ ==========
async def create_note_start(message: types.Message, state: FSMContext):
    await NoteStates.text.set()
    await edit_or_send(state, message.chat.id, "📝 Введи текст заметки:", get_back_button(), edit=False)

async def create_note_text(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await notes_reminders_main(message)
        return
    await db.add_note(message.from_user.id, message.text)
    await delete_dialog_message(state)
    await state.finish()
    await send_temp_message(message.chat.id, "✅ Заметка сохранена!", 2)
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== НАПОМИНАНИЯ ==========
async def create_reminder_start(message: types.Message, state: FSMContext):
    await ReminderStates.text.set()
    await edit_or_send(state, message.chat.id, "📝 Введи название напоминания:", get_back_button(), edit=False)

async def reminder_text(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await notes_reminders_main(message)
        return
    await state.update_data(text=message.text)
    await ReminderStates.date.set()
    await edit_or_send(state, message.chat.id, "📅 Выбери дату:", get_reminder_date_buttons(), edit=True)

async def reminder_date(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await safe_finish(state, message)
        await notes_reminders_main(message)
        return
    if message.text == "⬅️ Назад":
        await ReminderStates.text.set()
        await edit_or_send(state, message.chat.id, "📝 Введи название напоминания:", get_back_button(), edit=True)
        return

    today = datetime.now().date()
    if message.text == "📅 Сегодня":
        target_date = today
    elif message.text == "📆 Завтра":
        target_date = today + timedelta(days=1)
    elif message.text == "📆 Послезавтра":
        target_date = today + timedelta(days=2)
    elif message.text == "🔢 Выбрать дату":
        await edit_or_send(state, message.chat.id, "📅 Введи дату в формате: число месяц\n\nПримеры: 25 декабря, 1 января", get_back_button(), edit=True)
        return
    else:
        try:
            day_month = message.text.split()
            day = int(day_month[0])
            month_name = day_month[1]
            month_map = {
                "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
                "мая": 5, "июня": 6, "июля": 7, "августа": 8,
                "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
            }
            month = month_map.get(month_name.lower())
            if not month:
                raise ValueError
            year = today.year
            target_date = datetime(year, month, day).date()
            if target_date < today:
                target_date = datetime(year + 1, month, day).date()
        except:
            await edit_or_send(state, message.chat.id, "❌ Неверный формат. Введи дату как '25 декабря'", get_reminder_date_buttons(), edit=True)
            return

    await state.update_data(date=target_date.strftime("%Y-%m-%d"))
    await ReminderStates.hour.set()
    await edit_or_send(state, message.chat.id, "🕐 Выбери час:", get_reminder_hour_buttons(), edit=True)

async def reminder_hour(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await safe_finish(state, message)
        await notes_reminders_main(message)
        return
    if message.text == "⬅️ Назад":
        await ReminderStates.date.set()
        await edit_or_send(state, message.chat.id, "📅 Выбери дату:", get_reminder_date_buttons(), edit=True)
        return
    try:
        hour = int(message.text)
        if 0 <= hour <= 23:
            await state.update_data(hour=hour)
            await ReminderStates.minute.set()
            await edit_or_send(state, message.chat.id, "🕐 Выбери минуты:", get_reminder_minute_buttons(), edit=True)
        else:
            raise ValueError
    except:
        await edit_or_send(state, message.chat.id, "❌ Выбери час из кнопок (0-23)", get_reminder_hour_buttons(), edit=True)

async def reminder_minute(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await safe_finish(state, message)
        await notes_reminders_main(message)
        return
    if message.text == "⬅️ Назад":
        await ReminderStates.hour.set()
        await edit_or_send(state, message.chat.id, "🕐 Выбери час:", get_reminder_hour_buttons(), edit=True)
        return
    if message.text not in ["00", "15", "30", "45"]:
        await edit_or_send(state, message.chat.id, "❌ Выбери минуты из кнопок: 00, 15, 30, 45", get_reminder_minute_buttons(), edit=True)
        return

    data = await state.get_data()
    text = data["text"]
    target_date = data["date"]
    time_str = f"{data['hour']:02d}:{message.text}"

    user_tz_offset = await db.get_user_timezone(message.from_user.id)
    if user_tz_offset == 0:
        user_tz_offset = 3

    try:
        target_local = datetime.strptime(f"{target_date} {time_str}", "%Y-%m-%d %H:%M")
        target_utc = target_local - timedelta(hours=user_tz_offset)
        now_utc = datetime.utcnow()
        if target_utc < now_utc:
            await edit_or_send(state, message.chat.id, "❌ Нельзя создать напоминание на прошедшее время.", get_reminder_minute_buttons(), edit=True)
            return
        if target_utc < now_utc + MIN_DELTA:
            await edit_or_send(state, message.chat.id, f"❌ Нельзя установить напоминание раньше, чем через {int(MIN_DELTA.total_seconds()//60)} минут.", get_reminder_minute_buttons(), edit=True)
            return
    except Exception as e:
        await edit_or_send(state, message.chat.id, "❌ Ошибка в дате/времени. Попробуй снова.", get_notes_reminders_main_menu(), edit=False)
        await state.finish()
        return

    await state.update_data(minute=message.text)
    await ReminderStates.advance.set()
    await edit_or_send(state, message.chat.id, "⏰ Нужно ли напомнить заранее?", get_reminder_advance_buttons(), edit=True)

async def reminder_advance(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await safe_finish(state, message)
        await notes_reminders_main(message)
        return
    if message.text == "⬅️ Назад":
        await ReminderStates.minute.set()
        await edit_or_send(state, message.chat.id, "🕐 Выбери минуты:", get_reminder_minute_buttons(), edit=True)
        return

    advance_map = {
        "⏰ За 1 день": "day",
        "⏳ За 3 часа": "3h",
        "⌛ За 1 час": "1h",
        "🚫 Не надо": None,
        "✏️ Своё время": "custom"
    }
    if message.text not in advance_map:
        await edit_or_send(state, message.chat.id, "❌ Выбери вариант из кнопок.", get_reminder_advance_buttons(), edit=True)
        return
    advance_type = advance_map.get(message.text)

    if advance_type == "custom":
        await ReminderStates.custom_time.set()
        await edit_or_send(state, message.chat.id, "✏️ Введи время в формате ЧЧ:ММ (например, 10:30).\n\nДоп. напоминание сработает в этот час в день основного.", get_back_button(), edit=True)
        return

    data = await state.get_data()
    text = data["text"]
    target_date = data["date"]
    time_str = f"{data['hour']:02d}:{data['minute']}"
    user_tz_offset = await db.get_user_timezone(message.from_user.id)
    if user_tz_offset == 0:
        user_tz_offset = 3

    try:
        target_local = datetime.strptime(f"{target_date} {time_str}", "%Y-%m-%d %H:%M")
        target_utc = target_local - timedelta(hours=user_tz_offset)
        now_utc = datetime.utcnow()
        if target_utc < now_utc + MIN_DELTA:
            await delete_dialog_message(state)
            await state.finish()
            await send_temp_message(message.chat.id, "❌ Нельзя создать напоминание на прошедшее или слишком близкое время.", 3)
            await message.answer("Главное меню", reply_markup=get_main_menu())
            return

        # Создаём основное напоминание
        main_id = await db.add_reminder(message.from_user.id, text, target_date, time_str, advance_type=None, remind_utc=target_utc)
        if not main_id:
            await send_temp_message(message.chat.id, "❌ Не удалось создать напоминание.", 3)
            await safe_finish(state, message)
            return

        # Создаём дополнительное, если нужно
        if advance_type:
            if advance_type == "day":
                adv_utc = target_utc - timedelta(days=1)
            elif advance_type == "3h":
                adv_utc = target_utc - timedelta(hours=3)
            elif advance_type == "1h":
                adv_utc = target_utc - timedelta(hours=1)
            else:
                adv_utc = None
            if adv_utc and adv_utc < now_utc + MIN_DELTA:
                await db.delete_reminder(message.from_user.id, main_id)
                await edit_or_send(state, message.chat.id, "❌ Выбранное доп.напоминание попадает в прошлое или слишком близко — выбери другой вариант.", get_reminder_advance_buttons(), edit=True)
                return
            adv_text = f"🔔 Напоминание: {text}"
            await db.add_reminder(message.from_user.id, adv_text, target_date, time_str, advance_type=advance_type, parent_id=main_id, is_custom=False, remind_utc=adv_utc)

        await delete_dialog_message(state)
        await state.finish()
        await send_temp_message(message.chat.id, f"✅ Напоминание добавлено!\n\n📝 {text}\n🕐 {target_date} {time_str}", 4)
        await message.answer("Главное меню", reply_markup=get_main_menu())
    except Exception as e:
        logging.error(f"Ошибка создания напоминания: {e}")
        await edit_or_send(state, message.chat.id, "❌ Ошибка в дате/времени. Попробуй снова.", get_notes_reminders_main_menu(), edit=False)
        await state.finish()

async def reminder_custom_time(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await ReminderStates.advance.set()
        await edit_or_send(state, message.chat.id, "⏰ Выбери вариант доп. напоминания:", get_reminder_advance_buttons(), edit=True)
        return
    if message.text == "❌ Отмена":
        await safe_finish(state, message)
        await notes_reminders_main(message)
        return

    time_pattern = r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$'
    if not re.match(time_pattern, message.text):
        await send_temp_message(message.chat.id, "❌ Неверный формат. Введи время в формате ЧЧ:ММ (например, 10:30).", 3)
        await edit_or_send(state, message.chat.id, "✏️ Введи время в формате ЧЧ:ММ:", get_back_button(), edit=True)
        return

    data = await state.get_data()
    target_date = data['date']
    custom_time = message.text
    user_tz_offset = await db.get_user_timezone(message.from_user.id)
    if user_tz_offset == 0:
        user_tz_offset = 3

    try:
        custom_local = datetime.strptime(f"{target_date} {custom_time}", "%Y-%m-%d %H:%M")
        custom_utc = custom_local - timedelta(hours=user_tz_offset)
        now_utc = datetime.utcnow()
        if custom_utc < now_utc + MIN_DELTA:
            await send_temp_message(message.chat.id, f"❌ Доп. напоминание не может быть раньше, чем через {int(MIN_DELTA.total_seconds()//60)} минут от текущего момента.", 3)
            await edit_or_send(state, message.chat.id, "✏️ Введи другое время:", get_back_button(), edit=True)
            return
    except Exception as e:
        await send_temp_message(message.chat.id, "❌ Ошибка даты/времени.", 3)
        await ReminderStates.advance.set()
        await edit_or_send(state, message.chat.id, "⏰ Выбери вариант доп. напоминания:", get_reminder_advance_buttons(), edit=True)
        return

    await state.update_data(custom_time=custom_time)

    text = data['text']
    target_date_str = data['date']
    time_str = f"{data['hour']:02d}:{data['minute']}"
    user_tz_offset = await db.get_user_timezone(message.from_user.id)
    if user_tz_offset == 0:
        user_tz_offset = 3
    target_local = datetime.strptime(f"{target_date_str} {time_str}", "%Y-%m-%d %H:%M")
    target_utc = target_local - timedelta(hours=user_tz_offset)

    main_id = await db.add_reminder(message.from_user.id, text, target_date_str, time_str, advance_type=None, remind_utc=target_utc)
    if not main_id:
        await send_temp_message(message.chat.id, "❌ Не удалось создать напоминание.", 3)
        await safe_finish(state, message)
        return

    adv_text = f"🔔 Напоминание: {text}"
    await db.add_reminder(message.from_user.id, adv_text, target_date_str, custom_time, advance_type="custom", parent_id=main_id, is_custom=True, remind_utc=custom_utc)

    await delete_dialog_message(state)
    await state.finish()
    await send_temp_message(message.chat.id, f"✅ Напоминание добавлено!\n\n📝 {text}\n🕐 {target_date_str} {time_str}\n🔔 Доп. напоминание: {target_date_str} {custom_time}", 4)
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== ПРОСМОТР ЗАПИСЕЙ ==========
async def view_records(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Что хочешь посмотреть?", reply_markup=get_view_type_buttons())

async def list_notes(message: types.Message, state: FSMContext):
    await state.finish()
    notes = await db.get_notes(message.from_user.id)
    if not notes:
        await message.answer("📋 У тебя пока нет заметок.", reply_markup=get_notes_reminders_main_menu())
        return
    await state.update_data(last_section='notes')
    visible = list(reversed(notes))
    text = "📋 *Твои заметки:*\n\n"
    for i, note in enumerate(visible, 1):
        note_text = note['text'][:60] + "..." if len(note['text']) > 60 else note['text']
        text += f"{i}. {note_text}\n   📅 {note.get('date','-')} {note.get('time','')}\n\n"
    text += "\n✏️ *Команды:*\n`копировать <номер>` — скопировать текст заметки\n`редактировать <номер>` — изменить заметку\n`удалить <номер>` — удалить заметку\n\n*Пример:* `удалить 2`"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_notes_reminders_main_menu())

async def list_reminders(message: types.Message, state: FSMContext):
    await state.finish()
    reminders = await db.get_active_reminders(message.from_user.id)
    if not reminders:
        await message.answer("📋 У тебя пока нет активных напоминаний.", reply_markup=get_notes_reminders_main_menu())
        return
    await state.update_data(last_section='reminders')
    main_reminders = [r for r in reminders if not r.get('parent_id')]
    text = "📋 *Твои основные напоминания:*\n\n"
    for i, r in enumerate(main_reminders, 1):
        text += f"{i}. ⏰ {r['date']} {r['time']} — {r['text'][:50]}\n"
    text += "\n🗑 *Команды:*\n`редактировать <номер>` — изменить напоминание\n`удалить <номер>` — удалить напоминание (вместе с доп.)\n\n*Пример:* `удалить 2`"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_notes_reminders_main_menu())

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def copy_note(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_section = data.get('last_section')
    if last_section != 'notes':
        await send_temp_message(message.chat.id, "❌ Сначала открой список заметок.", 3)
        return
    match = re.match(r'^копировать (\d+)$', message.text)
    if not match:
        return
    index = int(match.group(1))
    notes = await db.get_notes(message.from_user.id)
    if not notes:
        await send_temp_message(message.chat.id, "❌ Заметок нет.", 3)
        return
    visible = list(reversed(notes))
    if index < 1 or index > len(visible):
        await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно заметок: {len(visible)}", 3)
        return
    note = visible[index-1]
    await message.bot.send_message(message.from_user.id, f"📋 *Скопированная заметка:*\n\n{note['text']}", parse_mode="Markdown")
    await send_temp_message(message.chat.id, "✅ Заметка скопирована и отправлена тебе в чат!", 3)

async def edit_note_or_reminder(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_section = data.get('last_section')
    if not last_section:
        await send_temp_message(message.chat.id, "❌ Сначала открой список заметок или напоминаний.", 3)
        return
    match = re.match(r'^редактировать (\d+)$', message.text)
    if not match:
        return
    index = int(match.group(1))

    if last_section == 'notes':
        notes = await db.get_notes(message.from_user.id)
        if not notes:
            await send_temp_message(message.chat.id, "❌ Заметок нет.", 3)
            return
        visible = list(reversed(notes))
        if index < 1 or index > len(visible):
            await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно заметок: {len(visible)}", 3)
            return
        note = visible[index-1]
        await db.delete_note_by_id(message.from_user.id, note['id'])
        await NoteStates.text.set()
        await state.update_data(edit_note_text=note['text'])
        await edit_or_send(state, message.chat.id, f"✏️ *Редактирование заметки*\n\nТекущий текст:\n{note['text']}\n\nВведи новый текст заметки (или оставь как есть):", get_back_button(), edit=False)

    elif last_section == 'reminders':
        reminders = await db.get_active_reminders(message.from_user.id)
        if not reminders:
            await send_temp_message(message.chat.id, "❌ Напоминаний нет.", 3)
            return
        main_reminders = [r for r in reminders if not r.get('parent_id')]
        if index < 1 or index > len(main_reminders):
            await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно основных напоминаний: {len(main_reminders)}", 3)
            return
        reminder = main_reminders[index-1]
        await state.update_data(edit_reminder_data=reminder)
        await db.delete_reminder(message.from_user.id, reminder['id'])
        await ReminderStates.text.set()
        await state.update_data(edit_reminder_text=reminder['text'])
        await edit_or_send(state, message.chat.id, f"✏️ *Редактирование напоминания*\n\nТекущий текст:\n{reminder['text']}\n\nВведи новый текст (или оставь как есть):", get_back_button(), edit=False)
    else:
        await send_temp_message(message.chat.id, "❌ Неизвестный раздел.", 3)

async def delete_item(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_section = data.get('last_section')
    if not last_section:
        await send_temp_message(message.chat.id, "❌ Сначала открой список заметок или напоминаний.", 3)
        return
    match = re.match(r'^удалить (\d+)$', message.text)
    if not match:
        return
    index = int(match.group(1))

    if last_section == 'notes':
        notes = await db.get_notes(message.from_user.id)
        if not notes:
            await send_temp_message(message.chat.id, "❌ Заметок нет.", 3)
            return
        visible = list(reversed(notes))
        if index < 1 or index > len(visible):
            await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно заметок: {len(visible)}", 3)
            return
        note = visible[index-1]
        await db.delete_note_by_id(message.from_user.id, note['id'])
        await send_temp_message(message.chat.id, f"✅ Заметка {index} удалена.", 3)

    elif last_section == 'reminders':
        reminders = await db.get_active_reminders(message.from_user.id)
        if not reminders:
            await send_temp_message(message.chat.id, "❌ Напоминаний нет.", 3)
            return
        main_reminders = [r for r in reminders if not r.get('parent_id')]
        if index < 1 or index > len(main_reminders):
            await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно основных напоминаний: {len(main_reminders)}", 3)
            return
        reminder = main_reminders[index-1]
        await db.delete_reminder(message.from_user.id, reminder['id'])
        await send_temp_message(message.chat.id, f"✅ Напоминание {index} и связанные с ним удалены.", 3)
    else:
        await send_temp_message(message.chat.id, "❌ Неизвестный раздел.", 3)

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(notes_reminders_main, text="📝 Заметки и напоминания", state="*")
    dp.register_message_handler(add_record_type, text="➕ Добавить запись", state="*")
    dp.register_message_handler(create_note_start, text="📝 Заметка", state="*")
    dp.register_message_handler(create_note_text, state=NoteStates.text)
    dp.register_message_handler(create_reminder_start, text="⏰ Напоминание", state="*")
    dp.register_message_handler(reminder_text, state=ReminderStates.text)
    dp.register_message_handler(reminder_date, state=ReminderStates.date)
    dp.register_message_handler(reminder_hour, state=ReminderStates.hour)
    dp.register_message_handler(reminder_minute, state=ReminderStates.minute)
    dp.register_message_handler(reminder_advance, state=ReminderStates.advance)
    dp.register_message_handler(reminder_custom_time, state=ReminderStates.custom_time)
    dp.register_message_handler(view_records, text="📋 Мои записи", state="*")
    dp.register_message_handler(list_notes, text="📋 Заметки", state="*")
    dp.register_message_handler(list_reminders, text="⏰ Напоминания", state="*")
    dp.register_message_handler(copy_note, regexp=r'^копировать (\d+)$', state='*')
    dp.register_message_handler(edit_note_or_reminder, regexp=r'^редактировать (\d+)$', state='*')
    dp.register_message_handler(delete_item, regexp=r'^удалить (\d+)$', state='*')
