from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from keyboards import get_main_menu

async def universal_back_handler(message: types.Message, state: FSMContext):
    """
    Сработает, только если пользователь завис вне FSM (в главном меню).
    Внутри опросов этот обработчик не перехватит «Назад», потому что там state не None.
    """
    current_state = await state.get_state()
    if current_state is None:
        # Пользователь в главном меню, просто обновляем его
        await message.answer("Главное меню", reply_markup=get_main_menu())

async def cmd_menu(message: types.Message, state: FSMContext):
    """Экстренный сброс в главное меню"""
    await state.finish()
    await message.answer("Главное меню", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    # Этот обработчик ловит «⬅️ Назад» только когда нет активного FSM
    dp.register_message_handler(universal_back_handler, text="⬅️ Назад", state=None)
    # Команда /menu работает всегда
    dp.register_message_handler(cmd_menu, commands=['menu'], state='*')
