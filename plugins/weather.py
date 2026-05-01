import logging
import aiohttp
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu
from config import WEATHER_API_KEY
import ai_advisor

logger = logging.getLogger(__name__)

class WeatherState(StatesGroup):
    waiting_for_city = State()

async def get_weather_by_city(city):
    if not WEATHER_API_KEY:
        return None
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Погода ошибка {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Исключение погоды: {e}")
            return None

async def get_weather_by_coords(lat, lon):
    if not WEATHER_API_KEY:
        return None
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return None
        except Exception:
            return None

def format_weather(data):
    if not data:
        return "❌ Не удалось получить погоду.", None, None
    city = data.get('name', 'Неизвестно')
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    humidity = data['main']['humidity']
    pressure = data['main']['pressure']
    wind = data['wind']['speed']
    desc = data['weather'][0]['description']
    icon_code = data['weather'][0]['icon']
    icon_map = {
        '01d': '☀️', '01n': '🌙', '02d': '⛅', '02n': '☁️',
        '03d': '☁️', '03n': '☁️', '04d': '☁️', '04n': '☁️',
        '09d': '🌧️', '09n': '🌧️', '10d': '🌦️', '10n': '🌧️',
        '11d': '⛈️', '11n': '⛈️', '13d': '❄️', '13n': '❄️',
        '50d': '🌫️', '50n': '🌫️'
    }
    emoji = icon_map.get(icon_code, '🌡️')
    text = (
        f"{emoji} *{city}*\n"
        f"🌡️ {temp:.1f}°C (ощущается {feels_like:.1f}°C)\n"
        f"🌬️ {desc.capitalize()}\n"
        f"💧 Влажность: {humidity}%\n"
        f"🌪️ Ветер: {wind} м/с\n"
        f"📈 Давление: {pressure} гПа"
    )
    return text, desc, temp

async def get_ai_recommendation(user_id, weather_desc, temp):
    if not weather_desc or not ai_advisor.ai_advisor:
        return ""
    try:
        prompt = f"Погода: {weather_desc}, температура {temp:.1f}°C. Дай короткий совет (1 предложение) по одежде/аксессуарам."
        advice = await ai_advisor.ai_advisor.get_advice(user_id, prompt, history=None)
        return advice[:200] if advice else ""
    except Exception as e:
        logger.error(f"AI-совет погоды: {e}")
        return ""

async def save_location(user_id, city=None, lat=None, lon=None):
    async with db.pool.acquire() as conn:
        if city:
            await conn.execute("INSERT INTO user_locations (user_id, city, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (user_id) DO UPDATE SET city = $2, updated_at = NOW()", user_id, city)
        elif lat and lon:
            await conn.execute("INSERT INTO user_locations (user_id, lat, lon, updated_at) VALUES ($1, $2, $3, NOW()) ON CONFLICT (user_id) DO UPDATE SET lat = $2, lon = $3, updated_at = NOW()", user_id, lat, lon)

async def show_weather_by_location(user_id, message, lat=None, lon=None, city=None):
    if not city and not lat:
        async with db.pool.acquire() as conn:
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
        await message.answer("📍 Не знаю твоё местоположение. Отправь геопозицию или введи город.", 
                           reply_markup=get_weather_location_keyboard())
        return

    if not data:
        await message.answer("❌ Не удалось получить погоду. Попробуй обновить гео в настройках.")
        return

    weather_text, desc, temp = format_weather(data)
    advice = await get_ai_recommendation(user_id, desc, temp)
    if advice:
        weather_text += f"\n\n🧥 *Совет:* {advice}"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📍 Обновить гео", "🏙️ Ввести город")
    kb.add("⬅️ Назад")
    await message.answer(weather_text, parse_mode="Markdown", reply_markup=kb)

def get_weather_location_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📍 Отправить геопозицию", request_location=True))
    kb.add(KeyboardButton("🏙️ Ввести город"))
    kb.add(KeyboardButton("⬅️ Назад"))
    return kb

async def weather_start(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)
    if row and (row['city'] or (row['lat'] and row['lon'])):
        await show_weather_by_location(user_id, message, city=row['city'], lat=row['lat'], lon=row['lon'])
    else:
        await message.answer("📍 Укажи местоположение для прогноза:", reply_markup=get_weather_location_keyboard())
        await WeatherState.waiting_for_city.set()

async def update_geo(message: types.Message, state: FSMContext):
    """Кнопка Обновить гео"""
    await state.finish()
    await message.answer("📍 Отправь новую геопозицию или введи город:", reply_markup=get_weather_location_keyboard())
    await WeatherState.waiting_for_city.set()

async def enter_city_prompt(message: types.Message, state: FSMContext):
    """Кнопка Ввести город"""
    await state.finish()
    await message.answer("🏙️ Введи название города:", reply_markup=get_weather_location_keyboard())
    await WeatherState.waiting_for_city.set()

async def process_city(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return
    if message.text == "🏙️ Ввести город":
        await message.answer("Введи название города (например, Москва):")
        return
    if message.text == "📍 Обновить гео":
        await message.answer("Отправь геопозицию:")
        return

    city = message.text.strip()
    data = await get_weather_by_city(city)
    if not data:
        await message.answer("❌ Город не найден. Попробуй ещё раз или отправь геопозицию.")
        return
    user_id = message.from_user.id
    await save_location(user_id, city=city)
    await show_weather_by_location(user_id, message, city=city)
    await state.finish()

async def handle_location(message: types.Message, state: FSMContext):
    if not message.location:
        return
    lat = message.location.latitude
    lon = message.location.longitude
    user_id = message.from_user.id
    await save_location(user_id, lat=lat, lon=lon)
    await show_weather_by_location(user_id, message, lat=lat, lon=lon)
    await state.finish()

def register(dp: Dispatcher):
    dp.register_message_handler(weather_start, text="🌤️ Погода", state="*")
    dp.register_message_handler(update_geo, text="📍 Обновить гео", state="*")
    dp.register_message_handler(enter_city_prompt, text="🏙️ Ввести город", state="*")
    dp.register_message_handler(process_city, state=WeatherState.waiting_for_city)
    dp.register_message_handler(handle_location, content_types=types.ContentTypes.LOCATION, state="*")
