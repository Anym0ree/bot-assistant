import os
import json
import logging

REMINDER_FILE = "reminder_settings.json"

def load_reminder_settings(user_id):
    try:
        if not os.path.exists(REMINDER_FILE):
            return None
        with open(REMINDER_FILE, "r") as f:
            data = json.load(f)
        return data.get(str(user_id))
    except Exception as e:
        logging.error(f"Ошибка загрузки настроек напоминаний: {e}")
        return None

def save_reminder_settings(user_id, settings):
    data = {}
    if os.path.exists(REMINDER_FILE):
        try:
            with open(REMINDER_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            pass
    data[str(user_id)] = settings
    with open(REMINDER_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_default_reminders():
    return {
        "sleep": {"enabled": True, "time": "09:00"},
        "checkins": {"enabled": True, "times": ["12:00", "16:00", "20:00"]},
        "summary": {"enabled": True, "time": "22:30"}
    }
