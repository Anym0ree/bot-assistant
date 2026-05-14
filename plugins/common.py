from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from keyboards import get_main_menu

# Хранилище истории навигации для каждого пользователя
navigation_stack = {}

async def go_back(message: types.Message, state: FSMContext):
    """Умная кнопка «Назад»: возвращает на предыдущий уровень или в главное меню"""
    user_id = message.from_user.id
    current_state = await state.get_state()
    
    # Если пользователь в процессе какого-то опроса (FSM активно), 
    # даём самому опросу обработать «Назад» через их собственные хендлеры
    if current_state:
        # Не перехватываем, пусть опрос сам решит
        return
    
    # Если нет активного опроса, работаем как навигация между разделами
    stack = navigation_stack.get(user_id, [])
    
    if stack:
        # Возвращаемся на предыдущий экран
        previous = stack.pop()
        navigation_stack[user_id] = stack
        
        # Вызываем соответствующую функцию меню
        if previous == "main":
            await message.answer("Главное меню", reply_markup=get_main_menu())
        elif previous == "plans":
            from plugins.planner import plans_menu
            await plans_menu(message, state)
        elif previous == "notes":
            from plugins.notes import notes_main
            await notes_main(message, state)
        elif previous == "history":
            from plugins.history_calendar import history_start
            await history_start(message)
        elif previous == "settings":
            from plugins.settings import settings_menu
            await settings_menu(message, state)
        elif previous == "achievements":
            from plugins.leaderboard import achievements_main
            await achievements_main(message, state)
        else:
            await message.answer("Главное меню", reply_markup=get_main_menu())
    else:
        # Стек пуст, возвращаем в главное меню
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())

def push_navigation(user_id: int, screen: str):
    """Добавляет экран в историю навигации"""
    if user_id not in navigation_stack:
        navigation_stack[user_id] = []
    navigation_stack[user_id].append(screen)

def clear_navigation(user_id: int):
    """Очищает историю (при входе в главное меню)"""
    navigation_stack.pop(user_id, None)

def register(dp: Dispatcher):
    # Универсальный обработчик «Назад», только когда нет активного FSM
    dp.register_message_handler(go_back, text="⬅️ Назад", state=None)
    # Дублируем для состояния "*", но с низким приоритетом — 
    # специфичные хендлеры опросов должны быть зарегистрированы раньше и иметь приоритет
