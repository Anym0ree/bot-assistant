from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from math import ceil

# ========== ГЛАВНОЕ МЕНЮ ==========
def get_main_menu():
    buttons = [
        [KeyboardButton(text="🛌 Сон")],
        [KeyboardButton(text="⚡️ Чек-ин")],
        [KeyboardButton(text="📝 Итог дня")],
        [KeyboardButton(text="🍽🥤 Еда и напитки")],
        [KeyboardButton(text="📝 Заметки и напоминания")],
        [KeyboardButton(text="📅 История")],   
        [KeyboardButton(text="🤖 AI-совет")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📤 Экспорт")],
        [KeyboardButton(text="🔄 Конвертер")],
        [KeyboardButton(text="🏆 Достижения")],
        [KeyboardButton(text="🌤️ Погода")],
        [KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== СТАТИСТИКА ==========
def get_stats_period_keyboard():
    buttons = [
        [KeyboardButton(text="📅 Неделя")],
        [KeyboardButton(text="📆 Месяц")],
        [KeyboardButton(text="📊 Вся статистика")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== НАСТРОЙКИ ==========
def get_settings_keyboard():
    buttons = [
        [KeyboardButton(text="🌍 Сменить часовой пояс")],
        [KeyboardButton(text="🔔 Настройка напоминаний")],
        [KeyboardButton(text="✏️ Редактировать профиль")],
        [KeyboardButton(text="🤖 AI-совет (вкл/выкл)")],
        [KeyboardButton(text="📊 Еженедельные отчёты (вкл/выкл)")],
        [KeyboardButton(text="🕒 Тихий час")],
        [KeyboardButton(text="🌍 Указать город")],
        [KeyboardButton(text="🌤️ Уведомления о погоде")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_reminder_settings_keyboard():
    buttons = [
        [KeyboardButton(text="🛌 Сон")],
        [KeyboardButton(text="⚡️ Чек-ины")],
        [KeyboardButton(text="📝 Итог дня")],
        [KeyboardButton(text="💧 Вода")],
        [KeyboardButton(text="🍽 Еда")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_reminder_action_keyboard():
    buttons = [
        [KeyboardButton(text="✅ Включить")],
        [KeyboardButton(text="❌ Выключить")],
        [KeyboardButton(text="🕐 Изменить время")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== КНОПКИ ДЛЯ НАПОМИНАНИЙ (старые) ==========
def get_reminder_date_buttons():
    buttons = [
        [KeyboardButton(text="📅 Сегодня")],
        [KeyboardButton(text="📆 Завтра")],
        [KeyboardButton(text="📆 Послезавтра")],
        [KeyboardButton(text="🔢 Выбрать дату")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_reminder_hour_buttons():
    row1 = [KeyboardButton(text=str(i)) for i in range(0, 6)]
    row2 = [KeyboardButton(text=str(i)) for i in range(6, 12)]
    row3 = [KeyboardButton(text=str(i)) for i in range(12, 18)]
    row4 = [KeyboardButton(text=str(i)) for i in range(18, 24)]
    buttons = [row1, row2, row3, row4, [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_reminder_minute_buttons():
    buttons = [
        [KeyboardButton(text="00"), KeyboardButton(text="15")],
        [KeyboardButton(text="30"), KeyboardButton(text="45")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_reminder_advance_buttons():
    buttons = [
        [KeyboardButton(text="⏰ За 1 день")],
        [KeyboardButton(text="⏳ За 3 часа")],
        [KeyboardButton(text="⌛ За 1 час")],
        [KeyboardButton(text="✏️ Своё время")],
        [KeyboardButton(text="🚫 Не надо")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== КНОПКИ ДЛЯ ЕДЫ, СНА, ЧЕК-ИНОВ ==========
def get_food_drink_menu():
    buttons = [
        [KeyboardButton(text="➕ Добавить еду/напитки")],
        [KeyboardButton(text="📋 Посмотреть сегодня")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_food_drink_type_buttons():
    buttons = [
        [KeyboardButton(text="🍽 Еда")],
        [KeyboardButton(text="🥤 Напитки")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_meal_type_buttons():
    buttons = [
        [KeyboardButton(text="🍳 Завтрак"), KeyboardButton(text="🍱 Обед")],
        [KeyboardButton(text="🍲 Ужин"), KeyboardButton(text="🍎 Перекус")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_drink_type_buttons():
    buttons = [
        [KeyboardButton(text="💧 Вода"), KeyboardButton(text="☕️ Кофе")],
        [KeyboardButton(text="🍵 Чай"), KeyboardButton(text="🧃 Сок")],
        [KeyboardButton(text="🍺 Алкоголь"), KeyboardButton(text="⚡️ Энергетик")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_drink_amount_buttons():
    buttons = [
        [KeyboardButton(text="1 чашка"), KeyboardButton(text="2 чашки")],
        [KeyboardButton(text="3+ чашек"), KeyboardButton(text="200 мл")],
        [KeyboardButton(text="300 мл"), KeyboardButton(text="500 мл")],
        [KeyboardButton(text="1 л"), KeyboardButton(text="Другое")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_energy_stress_buttons():
    row = [KeyboardButton(text=str(i)) for i in range(1, 6)]
    row2 = [KeyboardButton(text=str(i)) for i in range(6, 11)]
    buttons = [row, row2, [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_emotion_buttons():
    buttons = [
        [KeyboardButton(text="😊 Радость"), KeyboardButton(text="😠 Гнев")],
        [KeyboardButton(text="😰 Тревога"), KeyboardButton(text="😌 Спокойствие")],
        [KeyboardButton(text="😤 Раздражение"), KeyboardButton(text="😔 Грусть")],
        [KeyboardButton(text="😐 Апатия"), KeyboardButton(text="😨 Страх")],
        [KeyboardButton(text="😌 Облегчение"), KeyboardButton(text="😳 Стыд")],
        [KeyboardButton(text="✨ Вдохновение"), KeyboardButton(text="✍️ Своя")],
        [KeyboardButton(text="✅ Готово"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_yes_no_buttons():
    buttons = [
        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_skip_markup_text():
    buttons = [
        [KeyboardButton(text="Пропустить")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_time_buttons():
    buttons = [
        [KeyboardButton(text="22:00"), KeyboardButton(text="23:00")],
        [KeyboardButton(text="00:00"), KeyboardButton(text="01:00")],
        [KeyboardButton(text="02:00"), KeyboardButton(text="03:00")],
        [KeyboardButton(text="Другое")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_morning_time_buttons():
    buttons = [
        [KeyboardButton(text="06:00"), KeyboardButton(text="07:00")],
        [KeyboardButton(text="08:00"), KeyboardButton(text="09:00")],
        [KeyboardButton(text="10:00"), KeyboardButton(text="11:00")],
        [KeyboardButton(text="12:00"), KeyboardButton(text="Другое")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_sleep_quality_buttons():
    buttons = [
        [KeyboardButton(text="😴 Плохо"), KeyboardButton(text="🙂 Нормально")],
        [KeyboardButton(text="😊 Супер"), KeyboardButton(text="✍️ Свой вариант")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_timezone_buttons():
    buttons = [
        [KeyboardButton(text="Москва (UTC+3)"), KeyboardButton(text="Санкт-Петербург (UTC+3)")],
        [KeyboardButton(text="Екатеринбург (UTC+5)"), KeyboardButton(text="Новосибирск (UTC+7)")],
        [KeyboardButton(text="Владивосток (UTC+10)"), KeyboardButton(text="Калининград (UTC+2)")],
        [KeyboardButton(text="Другое")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_button():
    buttons = [[KeyboardButton(text="⬅️ Назад")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ЭКСПОРТ, КОНВЕРТЕР ==========
def get_export_menu():
    buttons = [
        [KeyboardButton(text="📥 Экспорт всех данных")],
        [KeyboardButton(text="🎵 SoundCloud")],
        [KeyboardButton(text="📌 Pinterest (видео)")],
        [KeyboardButton(text="🌐 Другой URL")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_download_formats_keyboard(source=None):
    if source == "🎵 SoundCloud":
        buttons = [[KeyboardButton(text="MP3 (аудио)")], [KeyboardButton(text="WAV (аудио)")], [KeyboardButton(text="⬅️ Назад")]]
    elif source == "📌 Pinterest (видео)":
        buttons = [[KeyboardButton(text="MP4 (видео)")], [KeyboardButton(text="⬅️ Назад")]]
    else:
        buttons = [[KeyboardButton(text="MP3 (аудио)")], [KeyboardButton(text="WAV (аудио)")],
                   [KeyboardButton(text="MP4 (видео)")], [KeyboardButton(text="Лучшее качество (оригинал)")],
                   [KeyboardButton(text="⬅️ Назад")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_converter_formats_keyboard():
    buttons = [[KeyboardButton(text="MP4"), KeyboardButton(text="GIF")],
               [KeyboardButton(text="MP3"), KeyboardButton(text="WEBM")],
               [KeyboardButton(text="⬅️ Назад")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ЗАМЕТКИ (Reply) ==========
def get_notes_reminders_main_menu():
    buttons = [
        [KeyboardButton(text="➕ Добавить запись")],
        [KeyboardButton(text="📋 Мои записи")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_record_type_buttons():
    buttons = [
        [KeyboardButton(text="📝 Заметка")],
        [KeyboardButton(text="⏰ Напоминание")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_view_type_buttons():
    buttons = [
        [KeyboardButton(text="📋 Заметки")],
        [KeyboardButton(text="⏰ Напоминания")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== INLINE КЛАВИАТУРЫ (для просмотра заметок/напоминаний) ==========
def get_notes_list_keyboard(notes, page=0, per_page=5):
    total_pages = ceil(len(notes) / per_page) if notes else 1
    start = page * per_page
    end = start + per_page
    page_notes = notes[start:end]
    buttons = []
    for i, note in enumerate(page_notes, start=start + 1):
        note_text = note['text'][:35] + "..." if len(note['text']) > 35 else note['text']
        buttons.append([InlineKeyboardButton(text=f"📝 {i}. {note_text}", callback_data=f"note_view_{note['id']}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"notes_page_{page-1}"))
    if page + 1 < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"notes_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("➕ Новая заметка", callback_data="note_new")])
    buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_note_action_keyboard(note_id):
    buttons = [
        [InlineKeyboardButton("📋 Копировать", callback_data=f"note_copy_{note_id}"),
         InlineKeyboardButton("✏️ Редактировать", callback_data=f"note_edit_{note_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"note_delete_{note_id}"),
         InlineKeyboardButton("⬅️ Назад к списку", callback_data="notes_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_delete_keyboard(item_type, item_id):
    buttons = [[InlineKeyboardButton("✅ Да, удалить", callback_data=f"{item_type}_confirm_del_{item_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data=f"{item_type}_cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_reminders_list_keyboard(reminders, page=0, per_page=5):
    total_pages = ceil(len(reminders) / per_page) if reminders else 1
    start = page * per_page
    end = start + per_page
    page_reminders = reminders[start:end]
    buttons = []
    for i, r in enumerate(page_reminders, start=start + 1):
        marker = "🔔" if r.get('parent_id') else "⏰"
        text = f"{marker} {r['date']} {r['time']} — {r['text'][:30]}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"reminder_view_{r['id']}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"reminders_page_{page-1}"))
    if page + 1 < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"reminders_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("➕ Новое напоминание", callback_data="reminder_new")])
    buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_reminder_action_keyboard_inline(reminder_id):
    buttons = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"reminder_edit_{reminder_id}"),
         InlineKeyboardButton("🗑 Удалить", callback_data=f"reminder_delete_{reminder_id}")],
        [InlineKeyboardButton("⬅️ К списку", callback_data="reminders_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
