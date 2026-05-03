import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional
from database import db
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Глобальный экземпляр (инициализируется в bot.py)
ai_advisor = None

class AIAdvisor:
    def __init__(self, api_key: str, model: str = "openrouter/auto"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        if api_key:
            logger.info(f"AIAdvisor инициализирован. Модель: {self.model}")

    async def _ask_ai(self, messages: list, max_tokens: int = 400, temperature: float = 0.7) -> Optional[str]:
        """Отправляет запрос в OpenRouter с таймаутом 7 секунд"""
        if not self.api_key:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=payload, timeout=7) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        if content:
                            return content.strip()
                    else:
                        logger.error(f"AI ошибка {resp.status}: {await resp.text()}")
        except asyncio.TimeoutError:
            logger.warning("AI запрос превысил таймаут 7 секунд")
        except Exception as e:
            logger.error(f"AI запрос исключение: {e}")
        return None

    async def collect_user_context(self, user_id: int) -> dict:
        """Собирает всю доступную информацию о пользователе"""
        ctx = {}
        try:
            profile = await db.get_user_profile(user_id)
            ctx['profile'] = profile

            tz = await db.get_user_timezone(user_id) or 3
            now_local = datetime.utcnow() + timedelta(hours=tz)
            today_str = now_local.strftime("%Y-%m-%d")

            # Сон
            async with db.pool.acquire() as conn:
                sleep = await conn.fetchrow("SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = $1 AND date = $2", user_id, today_str)
                ctx['sleep'] = dict(sleep) if sleep else None

                # Чек-ин
                checkin = await conn.fetchrow("SELECT energy, stress, emotions FROM checkins WHERE user_id = $1 AND date = $2 ORDER BY time DESC LIMIT 1", user_id, today_str)
                ctx['checkin'] = dict(checkin) if checkin else None

                # Итог дня
                summary = await conn.fetchrow("SELECT score, best, worst, gratitude FROM day_summary WHERE user_id = $1 AND date = $2", user_id, today_str)
                ctx['summary'] = dict(summary) if summary else None

                # Последние 3 записи сна и чекинов для тренда
                sleep_rows = await conn.fetch("SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = $1 ORDER BY date DESC LIMIT 3", user_id)
                ctx['sleep_rows'] = [dict(r) for r in sleep_rows]

                checkin_rows = await conn.fetch("SELECT energy, stress, emotions FROM checkins WHERE user_id = $1 ORDER BY date DESC LIMIT 3", user_id)
                ctx['checkin_rows'] = [dict(r) for r in checkin_rows]

                # Дела
                tasks = await conn.fetch("""
                    SELECT title FROM tasks WHERE user_id = $1 AND task_type = 'once' AND start_date = $2
                """, user_id, today_str)
                ctx['tasks'] = [r['title'] for r in tasks]

                # Рутины
                routines = await db.get_recurring_tasks_by_user(user_id)
                ctx['routines'] = [dict(r) for r in routines]

                # Погода (город)
                loc = await conn.fetchrow("SELECT city FROM user_locations WHERE user_id = $1", user_id)
                ctx['city'] = loc['city'] if loc else None

            return ctx
        except Exception as e:
            logger.error(f"Ошибка сбора контекста: {e}")
            return ctx

    async def get_smart_advice(self, user_id: int, context_type: str = "general", extra_context: str = "") -> Optional[str]:
        """
        Единый метод для получения AI‑совета в зависимости от контекста.
        Возвращает строку с ответом или None, если AI недоступен.
        """
        if not self.api_key:
            return None

        ctx = await self.collect_user_context(user_id)

        # Формируем промпт в зависимости от ситуации
        if context_type == "morning":
            prompt = self._build_morning_prompt(ctx, extra_context)
        elif context_type == "weather":
            prompt = self._build_weather_prompt(ctx, extra_context)
        elif context_type == "summary":
            prompt = self._build_summary_prompt(ctx, extra_context)
        elif context_type == "question":
            prompt = self._build_question_prompt(ctx, extra_context)
        else:  # general
            prompt = extra_context

        messages = [
            {"role": "system", "content": "Ты — заботливый помощник для ведения дневника и отслеживания самочувствия. Отвечай кратко, дружелюбно, на русском языке."},
            {"role": "user", "content": prompt}
        ]

        return await self._ask_ai(messages)

    def _build_morning_prompt(self, ctx: dict, extra: str) -> str:
        weather = extra or "Погода неизвестна"
        tasks = ', '.join(ctx.get('tasks', [])) or "ничего не запланировано"
        return f"Пользователь просыпается. На улице {weather}. На сегодня запланировано: {tasks}. Напиши короткое утреннее пожелание и один конкретный совет на день (15-25 слов)."

    def _build_weather_prompt(self, ctx: dict, extra: str) -> str:
        return f"Погода: {extra}. Дай ОДИН короткий совет по одежде (зонт, шапка, куртка) для этой погоды. Только совет, без лишних слов."

    def _build_summary_prompt(self, ctx: dict, extra: str) -> str:
        summary = ctx.get('summary', {})
        sleep = ctx.get('sleep', {})
        checkin = ctx.get('checkin', {})
        return f"Итог дня: оценка {summary.get('score', 'нет')}/10, лучшее: {summary.get('best', 'нет')}. Сон: лёг {sleep.get('bed_time', '?')}, встал {sleep.get('wake_time', '?')}. Энергия {checkin.get('energy', '?')}/10, стресс {checkin.get('stress', '?')}/10. Дай короткий комментарий и поддержку (1-2 предложения)."

    def _build_question_prompt(self, ctx: dict, extra: str) -> str:
        return "Придумай один глубокий, но простой вопрос для вечернего дневника, который поможет пользователю лучше понять своё самочувствие. Только вопрос, без пояснений."

    # -- Старые методы для совместимости --
    async def get_advice(self, user_id: int, user_question: str, history=None) -> str:
        return await self.get_smart_advice(user_id, "general", user_question) or "AI сейчас недоступен."

    async def get_first_advice(self, user_id: int) -> str:
        return await self.get_smart_advice(user_id, "morning") or "Доброе утро! Хорошего дня!"

    async def analyze_day(self, user_id: int, date_str: str) -> str:
        return await self.get_smart_advice(user_id, "summary", f"Дата: {date_str}") or "Не удалось проанализировать день."
