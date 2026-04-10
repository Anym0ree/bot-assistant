from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import SleepStates
from keyboards import get_time_buttons, get_morning_time_buttons, get_yes_no_buttons, get_skip_markup_text, get_main_menu, get_sleep_quality_buttons
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, is_valid_time_text

async def sleep_start(message: types.Message, state: FSMContext):
    if await db.has_sleep_today(message.from_user.id):
        await send_temp_message(message.chat.id, "🛌 Сон за сегодня уже записан.", 3)
        return
    await SleepStates.bed_time.set()
    await edit_or_send(state, message.chat.id, "🛏️ Во сколько лёг спать?", get_time_buttons(), edit=False)

async def sleep_bed_time(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if message.text == "Другое":
        await send_temp_message(message.chat.id, "✏️ Введи время в формате ЧЧ:ММ, например 23:45", 3)
        return
    if not is_valid_time_text(message.text):
        await send_temp_message(message.chat.id, "❌ Неверный формат. Нужно ЧЧ:ММ", 3)
        return
    await state.update_data(bed_time=message.text)
    await SleepStates.wake_time.set()
    await edit_or_send(state, message.chat.id, "⏰ Во сколько проснулся?", get_morning_time_buttons(), edit=True)

async def sleep_wake_time(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if message.text == "Другое":
        await send_temp_message(message.chat.id, "✏️ Введи время в формате ЧЧ:ММ, например 07:30", 3)
        return
    if not is_valid_time_text(message.text):
        await send_temp_message(message.chat.id, "❌ Неверный формат. Нужно ЧЧ:ММ", 3)
        return
    await state.update_data(wake_time=message.text)
    await SleepStates.quality.set()
    await edit_or_send(state, message.chat.id, "💤 Как оценишь качество сна?", get_sleep_quality_buttons(), edit=True)

async def sleep_quality(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    
    quality_map = {
        "😴 Плохо": 3,
        "🙂 Нормально": 6,
        "😊 Супер": 9,
    }
    if message.text in quality_map:
        quality = quality_map[message.text]
        await state.update_data(quality=quality)
        await SleepStates.woke_night.set()
        await edit_or_send(state, message.chat.id, "🌙 Просыпался ночью?", get_yes_no_buttons(), edit=True)
    elif message.text == "✍️ Свой вариант":
        await state.update_data(waiting_custom_quality=True)
        await edit_or_send(state, message.chat.id, "✏️ Напиши свою оценку (текстом, например: «очень плохо», «отлично»).\nБот сохранит твой текст.", get_back_button(), edit=True)
    else:
        await send_temp_message(message.chat.id, "❌ Выбери вариант из кнопок.", 3)

async def sleep_custom_quality(message: types.Message, state: FSMContext):
    # Обработка пользовательского текста для качества сна
    data = await state.get_data()
    if not data.get("waiting_custom_quality"):
        return
    custom_text = message.text.strip()
    if not custom_text:
        await send_temp_message(message.chat.id, "❌ Напиши что-нибудь.", 3)
        return
    # Сохраняем как качество = 0 (особое значение) и заметку сохраним отдельно
    await state.update_data(quality=0, custom_quality_text=custom_text)
    await state.update_data(waiting_custom_quality=False)
    await SleepStates.woke_night.set()
    await edit_or_send(state, message.chat.id, "🌙 Просыпался ночью?", get_yes_no_buttons(), edit=True)

async def sleep_woke_night(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if message.text not in ("✅ Да", "❌ Нет"):
        await send_temp_message(message.chat.id, "❌ Выбери ответ кнопками", 3)
        return
    await state.update_data(woke_night=(message.text == "✅ Да"))
    await SleepStates.note.set()
    await edit_or_send(state, message.chat.id, "📝 Заметка по сну? (можно пропустить)", get_skip_markup_text(), edit=True)

async def sleep_note(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    data = await state.get_data()
    note = "" if message.text == "Пропустить" else message.text
    # Если был введён свой текст качества, добавим его в заметку
    custom_quality = data.get("custom_quality_text", "")
    if custom_quality:
        note = (f"Оценка пользователя: {custom_quality}\n" + note).strip()
    saved = await db.add_sleep(
        message.from_user.id,
        data.get("bed_time"),
        data.get("wake_time"),
        data.get("quality"),
        data.get("woke_night"),
        note
    )
    await delete_dialog_message(state)
    await state.finish()
    if saved:
        await send_temp_message(message.chat.id, "✅ Сон сохранён!", 2)
    else:
        await send_temp_message(message.chat.id, "🛌 Сон за сегодня уже записан.", 3)
    await message.answer("Главное меню", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(sleep_start, text="🛌 Сон", state="*")
    dp.register_message_handler(sleep_bed_time, state=SleepStates.bed_time)
    dp.register_message_handler(sleep_wake_time, state=SleepStates.wake_time)
    dp.register_message_handler(sleep_quality, state=SleepStates.quality)
    dp.register_message_handler(sleep_custom_quality, state=SleepStates.quality, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(sleep_woke_night, state=SleepStates.woke_night)
    dp.register_message_handler(sleep_note, state=SleepStates.note)
