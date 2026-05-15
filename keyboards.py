from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu():
    buttons = [
        [KeyboardButton("📋 Сегодня")],
        [KeyboardButton("📝 Записать")],
        [KeyboardButton("📅 Планы")],
        [KeyboardButton("📂 Заметки")],
        [KeyboardButton("📅 История")],
        [KeyboardButton("🌤️ Погода")],
        [KeyboardButton("☕️ Вопрос дня")],
        [KeyboardButton("🎤 Конвертер")],
        [KeyboardButton("🤖 AI-совет")],
        [KeyboardButton("🏆 Достижения")],
        [KeyboardButton("🆘 Срыв")],
        [KeyboardButton("📤 Экспорт")],
        [KeyboardButton("⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_record_menu():
    buttons = [
        [KeyboardButton("🛌 Сон"), KeyboardButton("⚡️ Чек-ин")],
        [KeyboardButton("📝 Итог дня"), KeyboardButton("😊 Настроение")],
        [KeyboardButton("🍽🥤 Еда и напитки")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_plans_menu():
    buttons = [
        [KeyboardButton("📋 Сегодня")],
        [KeyboardButton("➕ Добавить дело")],
        [KeyboardButton("🔄 Добавить рутину")],
        [KeyboardButton("🗓️ Мои дела")],
        [KeyboardButton("📋 Мои рутины")],
        [KeyboardButton("⏰ Уведомления")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_notes_main_keyboard():
    buttons = [
        [KeyboardButton("📂 Мои разделы")],
        [KeyboardButton("➕ Новый раздел")],
        [KeyboardButton("🗣️ Правда дня")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_history_menu():
    buttons = [
        [KeyboardButton("📅 Сегодня")],
        [KeyboardButton("📆 Вчера")],
        [KeyboardButton("✏️ Ввести дату")],
        [KeyboardButton("📈 Графики")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_graph_period_menu():
    buttons = [
        [KeyboardButton("7 дн"), KeyboardButton("14 дн")],
        [KeyboardButton("30 дн"), KeyboardButton("Свой период")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_graph_type_menu():
    buttons = [
        [KeyboardButton("📈 Сон")],
        [KeyboardButton("📈 Энергия")],
        [KeyboardButton("📈 Настроение")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_converter_menu():
    buttons = [
        [KeyboardButton("🎤 Голос в текст")],
        [KeyboardButton("🎥 Кружок в GIF")],
        [KeyboardButton("📥 YouTube / SoundCloud")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_settings_keyboard():
    buttons = [
        [KeyboardButton("🌍 Сменить часовой пояс")],
        [KeyboardButton("🏙️ Указать город")],
        [KeyboardButton("🔔 Настройка напоминаний")],
        [KeyboardButton("✏️ Редактировать профиль")],
        [KeyboardButton("🤖 AI-совет (вкл/выкл)")],
        [KeyboardButton("📊 Еженедельные отчёты (вкл/выкл)")],
        [KeyboardButton("🕒 Тихий час")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_planner_keyboard():
    return get_plans_menu()

def get_export_menu():
    buttons = [
        [KeyboardButton("📥 Экспорт всех данных")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
