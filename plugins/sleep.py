from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database import db
from states import SleepStates, EditSleepStates
from keyboards import get_time_buttons, get_morning_time_buttons, get_yes_no_buttons, get_skip_markup_text, get_main_menu, get_sleep_quality_buttons, get_back_button
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, is_valid_time_text

# ========== СОЗДАНИЕ ЗАПИСИ СНА ==========
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
    data = await state.get_data()
    if not data.get("waiting_custom_quality"):
        return
    custom_text = message.text.strip()
    if not custom_text:
        await send_temp_message(message.chat.id, "❌ Напиши что-нибудь.", 3)
        return
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

# ========== РЕДАКТИРОВАНИЕ СНА ==========
async def edit_sleep_start(message: types.Message):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) != 3:
        await send_temp_message(message.chat.id, "❌ Неверный формат. Пиши: `редактировать сон 1` (номер из истории)", 3)
        return
    try:
        num = int(parts[2])
    except ValueError:
        await send_temp_message(message.chat.id, "❌ Номер должен быть числом.", 3)
        return

    # Получаем все записи сна пользователя
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, date, bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1 ORDER BY date DESC, id DESC",
            user_id
        )
    if not rows or num < 1 or num > len(rows):
        await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно записей сна: {len(rows)}", 3)
        return

    target = dict(rows[num - 1])
    await message.answer(f"✏️ Редактируем сон за {target['date']}\n\nТекущие данные:\n"
                         f"Лег: {target['bed_time']}, встал: {target['wake_time']}\n"
                         f"Качество: {target['quality']}/10, просыпался ночью: {'да' if target['woke_night'] else 'нет'}\n"
                         f"Заметка: {target['note'] or 'нет'}\n\n"
                         f"Что хочешь изменить?\n"
                         f"• `время ложиться` – новое время\n"
                         f"• `время вставать` – новое время\n"
                         f"• `качество` – новая оценка\n"
                         f"• `просыпался` – да/нет\n"
                         f"• `заметка` – новый текст\n"
                         f"• `готово` – сохранить изменения\n"
                         f"• `отмена` – без сохранения")
    await EditSleepStates.waiting.set()
    await state.update_data(edit_id=target['id'], edit_data=target)

async def edit_sleep_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get('edit_id'):
        await state.finish()
        return

    text = message.text.strip().lower()
    edit_data = data['edit_data']
    edit_id = data['edit_id']

    if text == "отмена":
        await state.finish()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_main_menu())
        return
    elif text == "готово":
        # Сохраняем изменения
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE sleep SET bed_time=$1, wake_time=$2, quality=$3, woke_night=$4, note=$5 WHERE id=$6",
                edit_data['bed_time'], edit_data['wake_time'], edit_data['quality'],
                1 if edit_data['woke_night'] else 0, edit_data['note'], edit_id
            )
        await state.finish()
        await message.answer("✅ Запись сна обновлена!", reply_markup=get_main_menu())
        return
    elif text.startswith("время ложиться"):
        new_time = text.replace("время ложиться", "").strip()
        if not is_valid_time_text(new_time):
            await message.answer("❌ Неверный формат. Введи время как ЧЧ:ММ (например, 23:00)")
            return
        edit_data['bed_time'] = new_time
        await message.answer(f"✅ Время отхода ко сну изменено на {new_time}")
    elif text.startswith("время вставать"):
        new_time = text.replace("время вставать", "").strip()
        if not is_valid_time_text(new_time):
            await message.answer("❌ Неверный формат. Введи время как ЧЧ:ММ (например, 07:00)")
            return
        edit_data['wake_time'] = new_time
        await message.answer(f"✅ Время пробуждения изменено на {new_time}")
    elif text.startswith("качество"):
        new_quality = text.replace("качество", "").strip()
        try:
            q = int(new_quality)
            if 1 <= q <= 10:
                edit_data['quality'] = q
                await message.answer(f"✅ Оценка качества сна изменена на {q}/10")
            else:
                await message.answer("❌ Оценка должна быть от 1 до 10")
        except:
            await message.answer("❌ Введи число от 1 до 10")
    elif text.startswith("просыпался"):
        val = text.replace("просыпался", "").strip().lower()
        if val in ["да", "yes", "1"]:
            edit_data['woke_night'] = True
            await message.answer("✅ Просыпался ночью: да")
        elif val in ["нет", "no", "0"]:
            edit_data['woke_night'] = False
            await message.answer("✅ Просыпался ночью: нет")
        else:
            await message.answer("❌ Напиши «да» или «нет»")
    elif text.startswith("заметка"):
        new_note = text.replace("заметка", "").strip()
        edit_data['note'] = new_note
        await message.answer(f"✅ Заметка изменена: {new_note}")
    else:
        await message.answer("❌ Неизвестная команда. Доступные: время ложиться, время вставать, качество, просыпался, заметка, готово, отмена")

    await state.update_data(edit_data=edit_data)

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(sleep_start, text="🛌 Сон", state="*")
    dp.register_message_handler(sleep_bed_time, state=SleepStates.bed_time)
    dp.register_message_handler(sleep_wake_time, state=SleepStates.wake_time)
    dp.register_message_handler(sleep_quality, state=SleepStates.quality)
    dp.register_message_handler(sleep_custom_quality, state=SleepStates.quality, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(sleep_woke_night, state=SleepStates.woke_night)
    dp.register_message_handler(sleep_note, state=SleepStates.note)
    dp.register_message_handler(edit_sleep_start, regexp=r'^редактировать сон \d+$', state='*')
    dp.register_message_handler(edit_sleep_process, state=EditSleepStates.waiting)
