from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from keyboards import get_main_menu

async def universal_back_handler(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Главное меню", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(universal_back_handler, text="⬅️ Назад", state="*")
