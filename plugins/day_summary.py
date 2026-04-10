from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import DaySummaryStates, EditSummaryStates
from keyboards import get_energy_stress_buttons, get_skip_markup_text, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, is_valid_score_text

# ========== СОЗДАНИЕ ИТОГА ДНЯ ==========
async def day_summary_start(message: types.Message, state: FSMContext):
    target_date = await db.get_target_date_for_summary(message.from_user.id)
    if target_date is None:
        await send_temp_message(message.chat.id, "🕕 Итог дня доступен с 18:00 до 06:00 по твоему часовому поясу.", 4)
        return
    if await db.has_day_summary_for_date(message.from_user.id, target_date):
        await send_temp_message(message.chat.id, f"📝 Итог за {target_date} уже сохранён.", 4)
        return
    await DaySummaryStates.score.set()
    await edit_or_send(state, message.chat.id, "📊 Насколько ты доволен сегодняшним днём? (1 — ужасно, 10 — великолепно)", get_energy_stress_buttons(), edit=False)

async def summary_score(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if not is_valid_score_text(message.text):
        await send_temp_message(message.chat.id, "❌ Оценка должна быть от 1 до 10", 3)
        return
    await state.update_data(score=int(message.text))
    await DaySummaryStates.best.set()
    await edit_or_send(state, message.chat.id, "🌟 Какое событие или момент сегодня порадовали больше всего?", get_skip_markup_text(), edit=True)

async def summary_best(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    best = message.text if message.text != "Пропустить" else ""
    await state.update_data(best=best)
    await DaySummaryStates.worst.set()
    await edit_or_send(state, message.chat.id, "⚠️ С чем пришлось столкнуться? Что далось труднее всего?", get_skip_markup_text(), edit=True)

async def summary_worst(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    worst = message.text if message.text != "Пропустить" else ""
    await state.update_data(worst=worst)
    await DaySummaryStates.gratitude.set()
    await edit_or_send(state, message.chat.id, "🙏 За что ты благодарен этому дню? (даже маленькая радость)", get_skip_markup_text(), edit=True)

async def summary_gratitude(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    gratitude = message.text if message.text != "Пропустить" else ""
    await state.update_data(gratitude=gratitude)
    await DaySummaryStates.note.set()
    await edit_or_send(state, message.chat.id, "📝 Хочешь добавить что-то ещё? (любые мысли, выводы, идеи)", get_skip_markup_text(), edit=True)

async def summary_note(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    data = await state.get_data()
    note = "" if message.text == "Пропустить" else message.text
    success = await db.add_day_summary(
        message.from_user.id,
        data["score"],
        data["best"],
        data["worst"],
        data["gratitude"],
        note
    )
    await delete_dialog_message(state)
    await state.finish()
    if success:
        await send_temp_message(message.chat.id, "✅ Итог дня сохранён!", 2)
    else:
        await send_temp_message(message.chat.id, "❌ Не удалось сохранить итог дня.", 3)
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== РЕДАКТИРОВАНИЕ ИТОГА ДНЯ ==========
async def edit_summary_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) != 3:
        await send_temp_message(message.chat.id, "❌ Неверный формат. Пиши: `редактировать итог 1`", 3)
        return
    try:
        num = int(parts[2])
    except ValueError:
        await send_temp_message(message.chat.id, "❌ Номер должен быть числом.", 3)
        return

    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, date, score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1 ORDER BY date DESC",
            user_id
        )
    if not rows or num < 1 or num > len(rows):
        await send_temp_message(message.chat.id, f"❌ Неверный номер. Доступно итогов: {len(rows)}", 3)
        return

    target = dict(rows[num - 1])
    await message.answer(f"✏️ Редактируем итог дня за {target['date']}\n\n"
                         f"Оценка: {target['score']}/10\nЛучшее: {target['best'] or 'нет'}\n"
                         f"Сложное: {target['worst'] or 'нет'}\nБлагодарность: {target['gratitude'] or 'нет'}\n"
                         f"Заметка: {target['note'] or 'нет'}\n\n"
                         f"Что хочешь изменить?\n"
                         f"• `оценка` – новое значение (1-10)\n"
                         f"• `лучшее` – новый текст\n"
                         f"• `сложное` – новый текст\n"
                         f"• `благодарность` – новый текст\n"
                         f"• `заметка` – новый текст\n"
                         f"• `готово` – сохранить изменения\n"
                         f"• `отмена` – без сохранения")
    await EditSummaryStates.waiting.set()
    await state.update_data(edit_id=target['id'], edit_data=target)

async def edit_summary_process(message: types.Message, state: FSMContext):
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
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE day_summary SET score=$1, best=$2, worst=$3, gratitude=$4, note=$5 WHERE id=$6",
                edit_data['score'], edit_data.get('best', ''), edit_data.get('worst', ''),
                edit_data.get('gratitude', ''), edit_data.get('note', ''), edit_id
            )
        await state.finish()
        await message.answer("✅ Итог дня обновлён!", reply_markup=get_main_menu())
        return
    elif text.startswith("оценка"):
        val = text.replace("оценка", "").strip()
        try:
            s = int(val)
            if 1 <= s <= 10:
                edit_data['score'] = s
                await message.answer(f"✅ Оценка изменена на {s}/10")
            else:
                await message.answer("❌ Значение от 1 до 10")
        except:
            await message.answer("❌ Введи число от 1 до 10")
    elif text.startswith("лучшее"):
        new_val = text.replace("лучшее", "").strip()
        edit_data['best'] = new_val
        await message.answer(f"✅ Лучшее изменено: {new_val}")
    elif text.startswith("сложное"):
        new_val = text.replace("сложное", "").strip()
        edit_data['worst'] = new_val
        await message.answer(f"✅ Сложное изменено: {new_val}")
    elif text.startswith("благодарность"):
        new_val = text.replace("благодарность", "").strip()
        edit_data['gratitude'] = new_val
        await message.answer(f"✅ Благодарность изменена: {new_val}")
    elif text.startswith("заметка"):
        new_val = text.replace("заметка", "").strip()
        edit_data['note'] = new_val
        await message.answer(f"✅ Заметка изменена: {new_val}")
    else:
        await message.answer("❌ Неизвестная команда. Доступные: оценка, лучшее, сложное, благодарность, заметка, готово, отмена")

    await state.update_data(edit_data=edit_data)

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(day_summary_start, text="📝 Итог дня", state="*")
    dp.register_message_handler(summary_score, state=DaySummaryStates.score)
    dp.register_message_handler(summary_best, state=DaySummaryStates.best)
    dp.register_message_handler(summary_worst, state=DaySummaryStates.worst)
    dp.register_message_handler(summary_gratitude, state=DaySummaryStates.gratitude)
    dp.register_message_handler(summary_note, state=DaySummaryStates.note)
    dp.register_message_handler(edit_summary_start, regexp=r'^редактировать итог \d+$', state='*')
    dp.register_message_handler(edit_summary_process, state=EditSummaryStates.waiting)
