from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu():
    """Главное меню бота — минималистичное, без дубликатов"""
    buttons = [
        [KeyboardButton(text="📋 Сегодня")],
        [KeyboardButton(text="📝 Записать")],
        [KeyboardButton(text="📅 Планы")],
        [KeyboardButton(text="📂 Заметки")],
        [KeyboardButton(text="📅 История")],
        [KeyboardButton(text="🌤️ Погода")],
        [KeyboardButton(text="☕️ Вопрос дня")],
        [KeyboardButton(text="🎤 Конвертер")],
        [KeyboardButton(text="🤖 AI-совет")],
        [KeyboardButton(text="🏆 Достижения")],
        [KeyboardButton(text="📤 Экспорт")],
        [KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_record_menu():
    """Меню «Записать» — быстрый доступ к опросам"""
    buttons = [
        [KeyboardButton(text="🛌 Сон"), KeyboardButton(text="⚡️ Чек-ин")],
        [KeyboardButton(text="📝 Итог дня"), KeyboardButton(text="😊 Настроение")],
        [KeyboardButton(text="🍽🥤 Еда и напитки")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_plans_menu():
    """Меню «Планы» — дела, рутины, уведомления, цели"""
    buttons = [
        [KeyboardButton(text="📋 Сегодня")],
        [KeyboardButton(text="➕ Добавить дело")],
        [KeyboardButton(text="🔄 Добавить рутину")],
        [KeyboardButton(text="🗓️ Мои дела")],
        [KeyboardButton(text="📋 Мои рутины")],
        [KeyboardButton(text="⏰ Уведомления")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_notes_menu():
    """Меню «Заметки»"""
    buttons = [
        [KeyboardButton(text="📂 Мои разделы")],
        [KeyboardButton(text="➕ Новый раздел")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_history_menu():
    """Меню «История»"""
    buttons = [
        [KeyboardButton(text="📅 Сегодня")],
        [KeyboardButton(text="📆 Вчера")],
        [KeyboardButton(text="✏️ Ввести дату")],
        [KeyboardButton(text="📈 Графики")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_graph_period_menu():
    """Меню выбора периода для графиков"""
    buttons = [
        [KeyboardButton(text="7 дн"), KeyboardButton(text="14 дн")],
        [KeyboardButton(text="30 дн"), KeyboardButton(text="Свой период")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_graph_type_menu():
    """Меню выбора типа графика"""
    buttons = [
        [KeyboardButton(text="📈 Сон")],
        [KeyboardButton(text="📈 Энергия")],
        [KeyboardButton(text="📈 Настроение")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_converter_menu():
    """Меню конвертера"""
    buttons = [
        [KeyboardButton(text="🎤 Голос в текст")],
        [KeyboardButton(text="🎥 Кружок в GIF")],
        [KeyboardButton(text="📥 YouTube / SoundCloud")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_settings_keyboard():
    buttons = [
        [KeyboardButton(text="🌍 Сменить часовой пояс")],
        [KeyboardButton(text="🏙️ Указать город")],
        [KeyboardButton(text="🔔 Настройка напоминаний")],
        [KeyboardButton(text="✏️ Редактировать профиль")],
        [KeyboardButton(text="🤖 AI-совет (вкл/выкл)")],
        [KeyboardButton(text="📊 Еженедельные отчёты (вкл/выкл)")],
        [KeyboardButton(text="🕒 Тихий час")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Остальные старые клавиатуры (для совместимости с другими модулями)
def get_planner_keyboard():
    return get_plans_menu()

def get_notes_main_keyboard():
    return get_notes_menu()

def get_export_menu():
    buttons = [
        [KeyboardButton(text="📥 Экспорт всех данных")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
