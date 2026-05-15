from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from keyboards import get_main_menu

async def universal_back_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Главное меню", reply_markup=get_main_menu())

async def cmd_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Главное меню", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(universal_back_handler, text="⬅️ Назад", state=None)
    dp.register_message_handler(cmd_menu, commands=['menu'], state='*')
