import asyncio
import os
import logging
import re
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from database_pg import db
from states import ExportStates
from keyboards import get_export_menu, get_download_formats_keyboard, get_back_button, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, is_valid_url, download_media_with_ytdlp, safe_remove_file, safe_delete_message_obj

# ========== СТАТИСТИКА ==========
async def stats(message: types.Message):
    text = await db.get_stats(message.from_user.id)
    await message.answer(text, reply_markup=get_main_menu())

# ========== ЭКСПОРТ ДАННЫХ ==========
async def export_menu(message: types.Message):
    await message.answer("Выбери, что хочешь экспортировать:", reply_markup=get_export_menu())

async def export_all_data(message: types.Message):
    file_path = await db.export_all(message.from_user.id)
    with open(file_path, 'rb') as f:
        await message.answer_document(f, caption="📁 Вот все твои данные")
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== СКАЧИВАНИЕ МЕДИА ПО ССЫЛКЕ ==========
async def export_any_start(message: types.Message, state: FSMContext):
    await ExportStates.url.set()
    if message.text == "🌐 Другой URL":
        await edit_or_send(state, message.chat.id, "📎 Отправь ссылку на трек, видео или плейлист (YouTube, SoundCloud, VK, Spotify и др.):\n\n_Поддерживаются любые ссылки, включая короткие._", get_back_button(), edit=False, parse_mode="Markdown")
    else:
        await edit_or_send(state, message.chat.id, f"📎 Отправь ссылку на трек или плейлист {message.text}:\n\n_Поддерживаются любые ссылки._", get_back_button(), edit=False, parse_mode="Markdown")

async def export_any_url(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await export_menu(message)
        return
    url = message.text.strip()
    # Проверяем, что это похоже на URL
    if not is_valid_url(url) and not re.match(r'^https?://', url):
        await send_temp_message(message.chat.id, "❌ Это не похоже на ссылку. Отправь корректный URL (начинается с http:// или https://).", 4)
        await edit_or_send(state, message.chat.id, "📎 Отправь ссылку на трек или плейлист:", get_back_button(), edit=True)
        return
    await state.update_data(url=url)
    await ExportStates.format.set()
    await edit_or_send(state, message.chat.id, "Выбери формат:", reply_markup=get_download_formats_keyboard(source="unknown"), edit=True)

async def export_any_format(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await export_menu(message)
        return
    fmt = message.text
    allowed_formats = {"MP3 (аудио)", "WAV (аудио)", "MP4 (видео)", "Лучшее качество (оригинал)"}
    if fmt not in allowed_formats:
        await send_temp_message(message.chat.id, "❌ Выбери формат только кнопками.", 3)
        await edit_or_send(state, message.chat.id, "Выбери формат:", get_download_formats_keyboard(), edit=True)
        return
    data = await state.get_data()
    url = data.get('url')
    if not url:
        await safe_finish(state, message, "Ошибка: ссылка не найдена. Начни заново.")
        return
    await delete_dialog_message(state)
    await state.finish()

    progress_msg = await message.answer("⏳ Начинаю обработку ссылки...")
    filename = None
    try:
        filename, title = await download_media_with_ytdlp(url, fmt, progress_msg)
        if not filename or not os.path.exists(filename):
            raise Exception("Скачанный файл не найден после завершения загрузки.")
        await message.bot.edit_message_text("✅ Скачивание завершено! Отправляю файл...", chat_id=progress_msg.chat.id, message_id=progress_msg.message_id)
        file_size = os.path.getsize(filename)
        if file_size > 50 * 1024 * 1024:
            raise Exception("Файл слишком большой для отправки в Telegram (более 50 MB).")
        with open(filename, 'rb') as f:
            await message.answer_document(f, caption=f"🎵 {title}")
    except Exception as e:
        logging.error(f"Ошибка загрузки: {e}")
        error_msg = str(e)
        # Пользовательские сообщения для частых ошибок
        if "Sign in to confirm you’re not a bot" in error_msg:
            await message.bot.edit_message_text(
                "❌ YouTube временно блокирует запросы. Попробуйте:\n"
                "• Подождать 10–15 минут\n"
                "• Использовать другой источник (SoundCloud, VK)\n"
                "• Скачать позже, когда нагрузка снизится",
                chat_id=progress_msg.chat.id, message_id=progress_msg.message_id
            )
        elif "ffmpeg" in error_msg.lower():
            await message.bot.edit_message_text(
                "❌ Для конвертации в MP3/WAV требуется ffmpeg, который не установлен на сервере.\n"
                "Пожалуйста, попробуйте формат «Лучшее качество (оригинал)» или обратитесь к администратору.",
                chat_id=progress_msg.chat.id, message_id=progress_msg.message_id
            )
        else:
            await message.bot.edit_message_text(f"❌ Ошибка: {error_msg[:200]}\nПроверь ссылку и попробуй снова.", chat_id=progress_msg.chat.id, message_id=progress_msg.message_id)
        await asyncio.sleep(3)
        await safe_delete_message_obj(progress_msg)
    finally:
        safe_remove_file(filename)
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(stats, text="📊 Статистика", state="*")
    dp.register_message_handler(export_menu, text="📤 Экспорт", state="*")
    dp.register_message_handler(export_all_data, text="📥 Экспорт всех данных", state="*")
    dp.register_message_handler(export_any_start, text=["🎵 SoundCloud", "📌 Pinterest (видео)", "🌐 Другой URL"], state="*")
    dp.register_message_handler(export_any_url, state=ExportStates.url)
    dp.register_message_handler(export_any_format, state=ExportStates.format)
