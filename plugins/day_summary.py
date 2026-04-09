from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import DaySummaryStates
from keyboards import get_energy_stress_buttons, get_skip_markup_text, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, is_valid_score_text

async def day_summary_start(message: types.Message, state: FSMContext):
    target_date = await db.get_target_date_for_summary(message.from_user.id)
    if target_date is None:
        await send_temp_message(message.chat.id, "🕕 Итог дня доступен с 18:00 до 06:00 по твоему часовому поясу.", 4)
        return
    if await db.has_day_summary_for_date(message.from_user.id, target_date):
        await send_temp_message(message.chat.id, f"📝 Итог за {target_date} уже сохранён.", 4)
        return
    await DaySummaryStates.score.set()
    await edit_or_send(state, message.chat.id, "Как прошёл день? Оценка от 1 до 10:", get_energy_stress_buttons(), edit=False)

async def summary_score(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    if not is_valid_score_text(message.text):
        await send_temp_message(message.chat.id, "❌ Оценка должна быть от 1 до 10", 3)
        return
    await state.update_data(score=int(message.text))
    await DaySummaryStates.best.set()
    await edit_or_send(state, message.chat.id, "Что было лучшим за день?", get_skip_markup_text(), edit=True)

async def summary_best(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    best = message.text if message.text != "Пропустить" else ""
    await state.update_data(best=best)
    await DaySummaryStates.worst.set()
    await edit_or_send(state, message.chat.id, "Что было самым сложным?", get_skip_markup_text(), edit=True)

async def summary_worst(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    worst = message.text if message.text != "Пропустить" else ""
    await state.update_data(worst=worst)
    await DaySummaryStates.gratitude.set()
    await edit_or_send(state, message.chat.id, "За что благодарен?", get_skip_markup_text(), edit=True)

async def summary_gratitude(message: types.Message, state: FSMContext):
    if message.text in ("❌ Отмена", "⬅️ Назад"):
        await safe_finish(state, message)
        return
    gratitude = message.text if message.text != "Пропустить" else ""
    await state.update_data(gratitude=gratitude)
    await DaySummaryStates.note.set()
    await edit_or_send(state, message.chat.id, "Заметка? (можно пропустить)", get_skip_markup_text(), edit=True)

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

def register(dp: Dispatcher):
    dp.register_message_handler(day_summary_start, text="📝 Итог дня", state="*")
    dp.register_message_handler(summary_score, state=DaySummaryStates.score)
    dp.register_message_handler(summary_best, state=DaySummaryStates.best)
    dp.register_message_handler(summary_worst, state=DaySummaryStates.worst)
    dp.register_message_handler(summary_gratitude, state=DaySummaryStates.gratitude)
    dp.register_message_handler(summary_note, state=DaySummaryStates.note)
