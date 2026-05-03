import asyncio
import logging
import os
import tempfile
import speech_recognition as sr
from pydub import AudioSegment
import yt_dlp
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from keyboards import get_converter_menu, get_main_menu
from utils import safe_remove_file

logger = logging.getLogger(__name__)

class ConverterStates(StatesGroup):
    waiting_for_voice = State()
    waiting_for_video_note = State()
    waiting_for_url = State()
    waiting_for_format = State()

# ========== Главное меню конвертера ==========
async def converter_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("🎤 *Конвертер*\n\nВыбери действие:", reply_markup=get_converter_menu(), parse_mode="Markdown")

# ========== ГОЛОС → ТЕКСТ ==========
async def voice_to_text_start(message: types.Message, state: FSMContext):
    await message.answer("🎤 Отправь голосовое сообщение, и я распознаю текст.", 
                        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await ConverterStates.waiting_for_voice.set()

async def voice_to_text_process(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await converter_menu(message, state)
        return

    if not message.voice:
        await message.answer("❌ Это не голосовое сообщение. Отправь голосовое.")
        return

    await state.finish()
    status_msg = await message.answer("🎧 Скачиваю голосовое...")

    try:
        # Скачиваем файл
        file = await message.voice.get_file()
        ogg_path = os.path.join(tempfile.gettempdir(), f"voice_{message.from_user.id}.ogg")
        await message.bot.download_file(file.file_path, ogg_path)

        await status_msg.edit_text("🔄 Конвертирую в WAV...")
        wav_path = ogg_path.replace(".ogg", ".wav")
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")

        await status_msg.edit_text("🧠 Распознаю речь...")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            await status_msg.edit_text(f"📝 *Распознанный текст:*\n\n{text}", parse_mode="Markdown")
        except sr.UnknownValueError:
            await status_msg.edit_text("❌ Не удалось распознать речь.")
        except sr.RequestError as e:
            await status_msg.edit_text(f"❌ Ошибка сервиса распознавания: {e}")

    except Exception as e:
        logger.error(f"Ошибка распознавания голоса: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при обработке голосового.")
    finally:
        safe_remove_file(ogg_path)
        if 'wav_path' in locals():
            safe_remove_file(wav_path)

    await message.answer("Выбери действие:", reply_markup=get_converter_menu())

# ========== ВИДЕОКРУЖОК → GIF / ТЕКСТ ==========
async def video_note_start(message: types.Message, state: FSMContext):
    await message.answer("🎥 Отправь видеокружок. Я определю, есть ли там речь, и либо распознаю текст, либо сделаю GIF.",
                        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await ConverterStates.waiting_for_video_note.set()

async def video_note_process(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await converter_menu(message, state)
        return

    if not message.video_note:
        await message.answer("❌ Это не видеокружок. Отправь кружок.")
        return

    await state.finish()
    status_msg = await message.answer("📥 Скачиваю кружок...")

    try:
        file = await message.video_note.get_file()
        video_path = os.path.join(tempfile.gettempdir(), f"circle_{message.from_user.id}.mp4")
        await message.bot.download_file(file.file_path, video_path)

        # Пытаемся извлечь аудио и распознать речь
        text = None
        try:
            await status_msg.edit_text("🔊 Извлекаю аудио...")
            wav_path = video_path.replace(".mp4", ".wav")
            import subprocess
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path, "-y"],
                capture_output=True, check=True
            )
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            safe_remove_file(wav_path)
        except Exception:
            pass  # речи нет или не удалось распознать

        if text:
            await status_msg.edit_text(f"📝 *Распознанный текст:*\n\n{text}", parse_mode="Markdown")
        else:
            await status_msg.edit_text("🎞 Конвертирую в GIF...")
            gif_path = video_path.replace(".mp4", ".gif")
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-vf", "fps=15,scale=320:-1:flags=lanczos", "-loop", "0", gif_path, "-y"],
                capture_output=True, check=True
            )
            with open(gif_path, 'rb') as gif:
                await message.answer_document(gif, caption="🎥 Твой GIF")
            await status_msg.delete()
            safe_remove_file(gif_path)

    except Exception as e:
        logger.error(f"Ошибка обработки кружка: {e}")
        await status_msg.edit_text("❌ Не удалось обработать видеокружок.")
    finally:
        safe_remove_file(video_path)

    await message.answer("Выбери действие:", reply_markup=get_converter_menu())

# ========== YouTube / SoundCloud ==========
async def url_download_start(message: types.Message, state: FSMContext):
    await message.answer("🔗 Отправь ссылку на YouTube или SoundCloud:",
                        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await ConverterStates.waiting_for_url.set()

async def url_download_process(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await converter_menu(message, state)
        return

    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("❌ Это не ссылка.")
        return

    await state.update_data(url=url)
    source = "🎵 SoundCloud" if "soundcloud" in url else "🌐 Другое"
    if "youtube" in url or "youtu.be" in url:
        source = "📺 YouTube"

    buttons = []
    if source == "📺 YouTube":
        buttons.append([KeyboardButton("MP4 (видео)")])
        buttons.append([KeyboardButton("MP3 (аудио)")])
    elif source == "🎵 SoundCloud":
        buttons.append([KeyboardButton("MP3 (аудио)")])
    else:
        buttons.append([KeyboardButton("MP3 (аудио)")])
        buttons.append([KeyboardButton("MP4 (видео)")])
    buttons.append([KeyboardButton("⬅️ Назад")])
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer(f"Выбери формат для {source}:", reply_markup=kb)
    await ConverterStates.waiting_for_format.set()

async def url_format_chosen(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.finish()
        await converter_menu(message, state)
        return

    fmt = message.text
    data = await state.get_data()
    url = data.get("url")
    if not url:
        await state.finish()
        await converter_menu(message, state)
        return

    await state.finish()
    progress_msg = await message.answer("⏳ Начинаю скачивание...")

    loop = asyncio.get_running_loop()
    try:
        def sync_download():
            tmp_dir = tempfile.gettempdir()
            outtmpl = os.path.join(tmp_dir, '%(title).100s-%(id)s.%(ext)s')
            opts = {
                "outtmpl": outtmpl,
                "noplaylist": True,
                "quiet": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            if "youtube" in url or "youtu.be" in url:
                opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]"
                if fmt == "MP3 (аудио)":
                    opts["format"] = "bestaudio/best"
                    opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                elif fmt == "MP4 (видео)":
                    opts["merge_output_format"] = "mp4"
            else:
                if fmt == "MP3 (аудио)":
                    opts["format"] = "bestaudio/best"
                    opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                elif fmt == "MP4 (видео)":
                    opts["format"] = "best"
                    opts["merge_output_format"] = "mp4"

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if fmt == "MP3 (аудио)":
                    filename = filename.rsplit(".", 1)[0] + ".mp3"
                return filename

        file_path = await asyncio.to_thread(sync_download)
        await progress_msg.edit_text("✅ Скачивание завершено! Отправляю файл...")
        with open(file_path, 'rb') as f:
            if file_path.endswith(".mp3"):
                await message.answer_audio(f, title=os.path.basename(file_path))
            else:
                await message.answer_document(f)
        safe_remove_file(file_path)
        await progress_msg.delete()

    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        await progress_msg.edit_text(f"❌ Не удалось скачать: {str(e)[:200]}")
        await asyncio.sleep(5)
        await progress_msg.delete()

    await message.answer("Выбери действие:", reply_markup=get_converter_menu())

# ========== Регистрация ==========
def register(dp: Dispatcher):
    dp.register_message_handler(converter_menu, text="🎤 Конвертер", state="*")
    dp.register_message_handler(voice_to_text_start, text="🎤 Голос в текст", state="*")
    dp.register_message_handler(voice_to_text_process, state=ConverterStates.waiting_for_voice, content_types=types.ContentTypes.ANY)
    dp.register_message_handler(video_note_start, text="🎥 Кружок в GIF", state="*")
    dp.register_message_handler(video_note_process, state=ConverterStates.waiting_for_video_note, content_types=types.ContentTypes.ANY)
    dp.register_message_handler(url_download_start, text="📥 YouTube / SoundCloud", state="*")
    dp.register_message_handler(url_download_process, state=ConverterStates.waiting_for_url)
    dp.register_message_handler(url_format_chosen, state=ConverterStates.waiting_for_format)
