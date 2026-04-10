from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import CheckinStates
from keyboards import get_energy_stress_buttons, get_emotion_buttons, get_skip_markup_text, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, is_valid_score_text

async def checkin_start(message: types.Message, state: FSMContext):
    await CheckinStates.energy.set()
    await edit_or_send(state, message.chat.id, "Оцени уровень энергии (1–10):", get_energy_stress_buttons(), edit=False)

async def checkin_energy(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if not is_valid_score_text(message.text):
        await send_temp_message(message.chat.id, "❌ Оценка должна быть от 1 до 10", 3)
        return
    await state.update_data(energy=int(message.text))
    await CheckinStates.stress.set()
    await edit_or_send(state, message.chat.id, "Оцени уровень стресса (1–10):", get_energy_stress_buttons(), edit=True)

async def checkin_stress(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if not is_valid_score_text(message.text):
        await send_temp_message(message.chat.id, "❌ Оценка должна быть от 1 до 10", 3)
        return
    await state.update_data(stress=int(message.text), emotions=[])
    await CheckinStates.emotions.set()
    await edit_or_send(state, message.chat.id, "Выбери эмоции (можно несколько), затем нажми «✅ Готово»", get_emotion_buttons(), edit=True)

async def checkin_emotions(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await safe_finish(state, message)
        return
    data = await state.get_data()
    emotions = data.get("emotions", [])
    if message.text == "⬅️ Назад":
        await CheckinStates.stress.set()
        await edit_or_send(state, message.chat.id, "Оцени уровень стресса (1–10):", get_energy_stress_buttons(), edit=True)
        return
    if message.text == "✍️ Своя":
        await send_temp_message(message.chat.id, "Напиши свою эмоцию текстом, затем нажми «✅ Готово».", 4)
        return
    if message.text == "✅ Готово":
        await CheckinStates.note.set()
        await edit_or_send(state, message.chat.id, "Короткая заметка? (можно пропустить)", get_skip_markup_text(), edit=True)
        return
    if message.text not in emotions:
        emotions.append(message.text)
        await state.update_data(emotions=emotions)
    await send_temp_message(message.chat.id, f"Добавлено эмоций: {len(emotions)}", 2)

async def checkin_note(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    data = await state.get_data()
    note = "" if message.text == "Пропустить" else message.text
    await db.add_checkin(
        message.from_user.id,
        "manual",
        data.get("energy"),
        data.get("stress"),
        data.get("emotions", []),
        note
    )
    await delete_dialog_message(state)
    await state.finish()
    await send_temp_message(message.chat.id, "✅ Чек-ин сохранён!", 2)
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== РЕДАКТИРОВАНИЕ ЧЕК-ИНА ==========
async def edit_checkin_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) != 3:
        await send_temp_message(message.chat.id, "❌ Неверный формат. Пиши: `редактировать чек-ин 1`", 3)
        return
    try:
        num = int(parts[2])
    except ValueError:
        await send_temp_message(message.chat.id, "❌ Номер должен быть числом.", 3)
        return

    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, date, time, energy, stress, emotions, note FROM checkins WHERE user_id = $1 ORDER BY date DESC, time DESC",
            user_id
        )
    if not rows or num < 1 or num > len(rows):
        await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно чек-инов: {len(rows)}", 3)
        return

    target = dict(rows[num - 1])
    emotions = target['emotions']
    if emotions:
        try:
            import json
            emotions = json.loads(emotions)
            emotions = ", ".join(emotions)
        except:
            pass
    else:
        emotions = "не указаны"

    await message.answer(f"✏️ Редактируем чек-ин за {target['date']} {target['time']}\n\n"
                         f"Энергия: {target['energy']}/10\nСтресс: {target['stress']}/10\nЭмоции: {emotions}\n"
                         f"Заметка: {target['note'] or 'нет'}\n\n"
                         f"Что хочешь изменить?\n"
                         f"• `энергия` – новое значение (1-10)\n"
                         f"• `стресс` – новое значение (1-10)\n"
                         f"• `эмоции` – список через запятую\n"
                         f"• `заметка` – новый текст\n"
                         f"• `готово` – сохранить изменения\n"
                         f"• `отмена` – без сохранения")
    await EditCheckinStates.waiting.set()
    await state.update_data(edit_id=target['id'], edit_data=target)

async def edit_checkin_process(message: types.Message, state: FSMContext):
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
        import json
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE checkins SET energy=$1, stress=$2, emotions=$3, note=$4 WHERE id=$5",
                edit_data['energy'], edit_data['stress'],
                json.dumps(edit_data.get('emotions', []), ensure_ascii=False),
                edit_data.get('note', ''), edit_id
            )
        await state.finish()
        await message.answer("✅ Чек-ин обновлён!", reply_markup=get_main_menu())
        return
    elif text.startswith("энергия"):
        val = text.replace("энергия", "").strip()
        try:
            e = int(val)
            if 1 <= e <= 10:
                edit_data['energy'] = e
                await message.answer(f"✅ Энергия изменена на {e}/10")
            else:
                await message.answer("❌ Значение от 1 до 10")
        except:
            await message.answer("❌ Введи число от 1 до 10")
    elif text.startswith("стресс"):
        val = text.replace("стресс", "").strip()
        try:
            s = int(val)
            if 1 <= s <= 10:
                edit_data['stress'] = s
                await message.answer(f"✅ Стресс изменён на {s}/10")
            else:
                await message.answer("❌ Значение от 1 до 10")
        except:
            await message.answer("❌ Введи число от 1 до 10")
    elif text.startswith("эмоции"):
        new_emotions = text.replace("эмоции", "").strip()
        if new_emotions:
            emotions_list = [e.strip() for e in new_emotions.split(",") if e.strip()]
            edit_data['emotions'] = emotions_list
            await message.answer(f"✅ Эмоции изменены: {', '.join(emotions_list)}")
        else:
            edit_data['emotions'] = []
            await message.answer("✅ Эмоции очищены")
    elif text.startswith("заметка"):
        new_note = text.replace("заметка", "").strip()
        edit_data['note'] = new_note
        await message.answer(f"✅ Заметка изменена: {new_note}")
    else:
        await message.answer("❌ Неизвестная команда. Доступные: энергия, стресс, эмоции, заметка, готово, отмена")

    await state.update_data(edit_data=edit_data)
    
def register(dp: Dispatcher):
    dp.register_message_handler(checkin_start, text="⚡️ Чек-ин", state="*")
    dp.register_message_handler(checkin_energy, state=CheckinStates.energy)
    dp.register_message_handler(checkin_stress, state=CheckinStates.stress)
    dp.register_message_handler(checkin_emotions, state=CheckinStates.emotions)
    dp.register_message_handler(checkin_note, state=CheckinStates.note)
    dp.register_message_handler(edit_checkin_start, regexp=r'^редактировать чек-ин \d+$', state='*')
    dp.register_message_handler(edit_checkin_process, state=EditCheckinStates.waiting)
