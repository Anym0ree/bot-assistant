from aiogram.dispatcher.filters.state import State, StatesGroup

class SleepStates(StatesGroup):
    bed_time = State()
    wake_time = State()
    quality = State()
    woke_night = State()
    note = State()

class CheckinStates(StatesGroup):
    energy = State()
    stress = State()
    emotions = State()
    note = State()

class DaySummaryStates(StatesGroup):
    score = State()
    best = State()
    worst = State()
    gratitude = State()
    note = State()

class FoodStates(StatesGroup):
    meal_type = State()
    food_text = State()

class DrinkStates(StatesGroup):
    drink_type = State()
    amount = State()

class FoodDrinkStates(StatesGroup):
    type = State()

class TimezoneStates(StatesGroup):
    city = State()
    offset = State()

class NoteStates(StatesGroup):
    text = State()
    edit_text = State()

class ReminderStates(StatesGroup):
    text = State()
    date = State()
    hour = State()
    minute = State()
    advance = State()
    custom_time = State()
    edit_text = State()
    edit_date = State()
    edit_hour = State()
    edit_minute = State()
    edit_reminder_id = State()

class LastSectionState(StatesGroup):
    section = State()   # 'notes' или 'reminders'

class ExportStates(StatesGroup):
    url = State()
    format = State()

class ConverterStates(StatesGroup):
    file = State()
    format = State()

class AIState(StatesGroup):
    waiting_question = State()

class ReminderSetupStates(StatesGroup):
    ask = State()
    choose_mode = State()

# ========== ДОБАВЛЕННЫЙ КЛАСС ДЛЯ НАСТРОЕК НАПОМИНАНИЙ ==========
class ReminderCustomizeStates(StatesGroup):
    waiting = State()
    sleep_menu = State()
    checkins_menu = State()
    summary_menu = State()
    change_sleep_time = State()
    change_checkins_times = State()
    change_summary_time = State()
    water_menu = State()
    change_water_times = State()
    meals_menu = State()
    change_meals_times = State()

class EditSleepStates(StatesGroup):
    waiting = State()

class EditCheckinStates(StatesGroup):
    waiting = State()

class EditSummaryStates(StatesGroup):
    waiting = State()

class EditFoodStates(StatesGroup):
    waiting = State()

class EditDrinkStates(StatesGroup):
    waiting = State()
