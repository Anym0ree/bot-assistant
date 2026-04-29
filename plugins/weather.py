import logging
import aiohttp
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu, get_back_button
from config import WEATHER_API_KEY
import ai_advisor

logger = logging.getLogger(__name__)

class WeatherState(StatesGroup):
    waiting_for_city = State()

async def get_weather_by_city(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return None

async def get_weather_by_coords(lat, lon):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return None

def format_weather(data):
    if not data:
        return "❌ Не удалось получить погоду."
    city = data.get('name', 'Неизвестно')
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    humidity = data['main']['humidity']
    pressure = data['main']['pressure']
    wind = data['wind']['speed']
    desc = data['weather'][0]['description']
    icon_code = data['weather'][0]['icon']
    icon_map = {
        '01d': '☀️', '01n': '🌙',
        '02d': '⛅', '02n': '☁️',
        '03d': '☁️', '03n': '☁️',
        '04d': '☁️', '04n': '☁️',
        '09d': '🌧️', '09n': '🌧️',
        '10d': '🌦️', '10n': '🌧️',
        '11d': '⛈️', '11n': '⛈️',
        '13d': '❄️', '13n': '❄️',
        '50d': '🌫️', '50n': '🌫️'
    }
    emoji = icon_map.get(icon_code, '🌡️')
    text = (
        f"{emoji} *{city}*\n"
        f"🌡️ {temp:.1f}°C (ощущается как {feels_like:.1f}°C)\n"
        f"🌬️ {desc.capitalize()}\n"
        f"💧 Влажность: {humidity}%\n"
        f"🌪️ Ветер: {wind} м/с\n"
        f"📈 Давление: {pressure} гПа\n"
    )
    return text, desc, temp

async def get_ai_recommendation(user_id, weather_desc, temp):
    prompt = f"Погода сейчас: {weather_desc}, температура {temp:.1f}°C. Дай короткий совет (до 80 символов) по одежде и аксессуарам (зонт, очки, шапка и т.п.). Не пиши лишнего."
    if ai_advisor.ai_advisor:
        advice = await ai_advisor.ai_advisor.get_advice(user_id, prompt, history=None)
        return advice[:200]
    return ""

async def show_weather_by_location(user_id, message, lat=None, lon=None, city=None):
    # Сохраняем локацию
    async with db.pool.acquire() as conn:
        if city:
            await conn.execute("INSERT INTO user_locations (user_id, city, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (user_id) DO UPDATE SET city = $2, updated_at = NOW()", user_id, city)
        elif lat and lon:
            await conn.execute("INSERT INTO user_locations (user_id, lat, lon, updated_at) VALUES ($1, $2, $3, NOW()) ON CONFLICT (user_id) DO UPDATE SET lat = $2, lon = $3, updated_at = NOW()", user_id, lat, lon)
        else:
            row = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)
            if row:
                city = row['city']
                lat = row['lat']
                lon = row['lon']
    if city:
        data = await get_weather_by_city(city)
    elif lat and lon:
        data = await get_weather_by_coords(lat, lon)
    else:
        await message.answer("📍 Я не знаю твоё местоположение. Отправь геопозицию или напиши город.")
        return
    if not data:
        await message.answer("❌ Не удалось получить погоду. Попробуй позже или укажи город заново.")
        return
    weather_text, desc, temp = format_weather(data)
    advice = await get_ai_recommendation(user_id, desc, temp)
    if advice:
        weather_text += f"\n🧥 *Совет:* {advice}"
    await message.answer(weather_text, parse_mode="Markdown", reply_markup=get_main_menu())

async def weather_cmd(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)
    if row and (row['city'] or (row['lat'] and row['lon'])):
        await show_weather_by_location(user_id, message, city=row['city'], lat=row['lat'], lon=row['lon'])
    else:
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("📍 Отправить геопозицию", request_location=True))
        kb.add(KeyboardButton("🌍 Ввести город вручную"))
        kb.add(KeyboardButton("⬅️ Назад"))
        await message.answer("📍 Чтобы узнать погоду, укажи своё местоположение:\n• Отправь геопозицию\n• Или введи название города", reply_markup=kb)
        await WeatherState.waiting_for_city.set()

async def set_city(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return
    if message.text == "🌍 Ввести город вручную":
        await message.answer("Введи название города (например, Москва):", reply_markup=get_back_button())
        return
    city = message.text.strip()
    data = await get_weather_by_city(city)
    if not data:
        await message.answer("❌ Город не найден. Попробуй ещё раз или отправь геопозицию.")
        return
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("INSERT INTO user_locations (user_id, city, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (user_id) DO UPDATE SET city = $2, updated_at = NOW()", user_id, city)
    await show_weather_by_location(user_id, message, city=city)
    await state.finish()

async def handle_location(message: types.Message, state: FSMContext):
    if not message.location:
        return
    lat = message.location.latitude
    lon = message.location.longitude
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        await conn.execute("INSERT INTO user_locations (user_id, lat, lon, updated_at) VALUES ($1, $2, $3, NOW()) ON CONFLICT (user_id) DO UPDATE SET lat = $2, lon = $3, updated_at = NOW()", user_id, lat, lon)
    await show_weather_by_location(user_id, message, lat=lat, lon=lon)
    await state.finish()

async def cancel_state(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Отменено.", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(weather_cmd, text="🌤️ Погода", state="*")
    dp.register_message_handler(set_city, state=WeatherState.waiting_for_city, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(handle_location, content_types=types.ContentTypes.LOCATION, state=WeatherState.waiting_for_city)
    dp.register_message_handler(cancel_state, text="⬅️ Назад", state=WeatherState.waiting_for_city)
