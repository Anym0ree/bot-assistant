import logging
import aiohttp
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import db
from keyboards import get_main_menu, get_back_button

logger = logging.getLogger(__name__)

class WeatherStates(StatesGroup):
    waiting_for_city = State()

async def get_weather(city):
    try:
        url = f"https://wttr.in/{city}?format=%C+%t+%w+%h+%P"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.text()
                    parts = data.strip().split()
                    condition = parts[0]
                    temp = parts[1]
                    wind = parts[2] if len(parts) > 2 else ""
                    humidity = parts[3] if len(parts) > 3 else ""
                    pressure = parts[4] if len(parts) > 4 else ""
                    advice = ""
                    if "rain" in condition.lower() or "drizzle" in condition.lower():
                        advice += "🌂 Не забудь зонтик! "
                    if "snow" in condition.lower():
                        advice += "🧣 Одевайся теплее, идёт снег. "
                    if "thunder" in condition.lower():
                        advice += "⚡️ Гроза, лучше оставайся дома. "
                    try:
                        temp_val = int(temp.replace("+", "").replace("-", "").replace("°C", ""))
                        if temp_val < 0:
                            advice += "🥶 Очень холодно, надень пуховик и шапку. "
                        elif temp_val < 10:
                            advice += "🧥 Прохладно, куртка не помешает. "
                        elif temp_val > 25:
                            advice += "🕶️ Жарко, пей воду и носи головной убор. "
                    except:
                        pass
                    forecast = f"🌍 *{city}*\n{condition} {temp}\nВетер: {wind}\nВлажность: {humidity}\nДавление: {pressure}\n\n{advice}"
                    return forecast
    except Exception as e:
        logger.error(f"Ошибка погоды: {e}")
    return "Не удалось получить погоду. Проверь название города."

async def show_weather(message: types.Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT city FROM users WHERE user_id = $1", user_id)
    if not row or not row['city']:
        await message.answer("Сначала укажи свой город в настройках (⚙️ Настройки → 🌍 Указать город).")
        return
    city = row['city']
    await message.answer("🌤️ Запрашиваю погоду...")
    forecast = await get_weather(city)
    await message.answer(forecast, parse_mode="Markdown", reply_markup=get_main_menu())

async def set_city_start(message: types.Message, state: FSMContext):
    await message.answer("Введи название своего города (например, Москва):", reply_markup=get_back_button())
    await WeatherStates.waiting_for_city.set()

async def set_city(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await message.answer("Отменено.", reply_markup=get_main_menu())
        return
    city = message.text.strip()
    test = await get_weather(city)
    if "Не удалось" in test:
        await message.answer("Не удалось определить город. Попробуй другое название или напиши на русском.")
        return
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE users SET city = $1 WHERE user_id = $2", city, user_id)
    await state.finish()
    await message.answer(f"✅ Город {city} сохранён. Теперь можешь узнавать погоду по кнопке 🌤️ Погода.")
    from plugins.settings import settings_menu
    await settings_menu(message, state)

async def toggle_weather_notify(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT weather_notify FROM user_settings WHERE user_id = $1", user_id)
        current = row['weather_notify'] if row else 0
        new_val = 0 if current else 1
        await conn.execute("""
            INSERT INTO user_settings (user_id, weather_notify) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET weather_notify = $2
        """, user_id, new_val)
    await message.answer(f"🌤️ Утренние уведомления о погоде {'включены' if new_val else 'выключены'}")
    from plugins.settings import settings_menu
    await settings_menu(message, state)

def register(dp: Dispatcher):
    dp.register_message_handler(show_weather, text="🌤️ Погода", state="*")
    dp.register_message_handler(set_city_start, text="🌍 Указать город", state="*")
    dp.register_message_handler(set_city, state=WeatherStates.waiting_for_city)
    dp.register_message_handler(toggle_weather_notify, text="🌤️ Уведомления о погоде", state="*")
