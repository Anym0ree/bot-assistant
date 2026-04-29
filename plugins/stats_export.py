from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database import db
from keyboards import get_main_menu

async def stats_menu(message: types.Message, state: FSMContext):
    await state.finish()
    text = await db.get_stats(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(stats_menu, text="📊 Статистика", state="*")
