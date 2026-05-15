import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional
from database import db
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

ai_advisor = None

class AIAdvisor:
    def __init__(self, api_key: str, model: str = "openrouter/auto"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        if api_key:
            logger.info(f"AIAdvisor инициализирован. Модель: {self.model}")

    async def _ask_ai(self, messages: list, max_tokens: int = 400, temperature: float = 0.7) -> Optional[str]:
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
        ctx = {}
        try:
            profile = await db.get_user_profile(user_id)
            ctx['profile'] = profile

            tz = await db.get_user_timezone(user_id) or 3
            now_local = datetime.utcnow() + timedelta(hours=tz)
            today_str = now_local.strftime("%Y-%m-%d")
            today_date = now_local.date()  # <-- объект date

            async with db.pool.acquire() as conn:
                sleep = await conn.fetchrow("SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = $1 AND date = $2", user_id, today_str)
                ctx['sleep'] = dict(sleep) if sleep else None

                checkin = await conn.fetchrow("SELECT energy, stress, emotions FROM checkins WHERE user_id = $1 AND date = $2 ORDER BY time DESC LIMIT 1", user_id, today_str)
                ctx['checkin'] = dict(checkin) if checkin else None

                summary = await conn.fetchrow("SELECT score, best, worst, gratitude FROM day_summary WHERE user_id = $1 AND date = $2", user_id, today_str)
                ctx['summary'] = dict(summary) if summary else None

                sleep_rows = await conn.fetch("SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = $1 ORDER BY date DESC LIMIT 3", user_id)
                ctx['sleep_rows'] = [dict(r) for r in sleep_rows]

                checkin_rows = await conn.fetch("SELECT energy, stress, emotions FROM checkins WHERE user_id = $1 ORDER BY date DESC LIMIT 3", user_id)
                ctx['checkin_rows'] = [dict(r) for r in checkin_rows]

                # ИСПРАВЛЕНИЕ: используем today_date (объект date) вместо строки
                tasks = await conn.fetch("""
                    SELECT title FROM tasks WHERE user_id = $1 AND task_type = 'once' AND start_date = $2
                """, user_id, today_date)
                ctx['tasks'] = [r['title'] for r in tasks]

                routines = await db.get_recurring_tasks_by_user(user_id)
                ctx['routines'] = [dict(r) for r in routines]

                loc = await conn.fetchrow("SELECT city FROM user_locations WHERE user_id = $1", user_id)
                ctx['city'] = loc['city'] if loc else None

            return ctx
        except Exception as e:
            logger.error(f"Ошибка сбора контекста: {e}")
            return ctx

    async def get_smart_advice(self, user_id: int, context_type: str = "general", extra_context: str = "") -> Optional[str]:
        if not self.api_key:
            return None
        ctx = await self.collect_user_context(user_id)
        if context_type == "morning":
            prompt = self._build_morning_prompt(ctx, extra_context)
        elif context_type == "weather":
            prompt = self._build_weather_prompt(ctx, extra_context)
        elif context_type == "summary":
            prompt = self._build_summary_prompt(ctx, extra_context)
        elif context_type == "question":
            prompt = self._build_question_prompt(ctx, extra_context)
        else:
            prompt = extra_context
        messages = [
            {"role": "system", "content": "Ты — заботливый помощник для ведения дневника. Отвечай кратко, дружелюбно, на русском."},
            {"role": "user", "content": prompt}
        ]
        return await self._ask_ai(messages)

    def _build_morning_prompt(self, ctx, extra):
        weather = extra or "Погода неизвестна"
        tasks = ', '.join(ctx.get('tasks', [])) or "ничего не запланировано"
        return f"Пользователь просыпается. На улице {weather}. На сегодня запланировано: {tasks}. Напиши короткое утреннее пожелание и один конкретный совет (15-25 слов)."

    def _build_weather_prompt(self, ctx, extra):
        return f"Погода: {extra}. Дай ОДИН короткий совет по одежде (зонт, куртка). Только совет, без лишних слов."

    def _build_summary_prompt(self, ctx, extra):
        summary = ctx.get('summary', {})
        sleep = ctx.get('sleep', {})
        checkin = ctx.get('checkin', {})
        return f"Итог дня: оценка {summary.get('score','нет')}/10, лучшее: {summary.get('best','нет')}. Сон: {sleep.get('bed_time','?')}-{sleep.get('wake_time','?')}. Энергия {checkin.get('energy','?')}/10, стресс {checkin.get('stress','?')}/10. Дай короткий комментарий и поддержку (1-2 предложения)."

    def _build_question_prompt(self, ctx, extra):
        return "Придумай один глубокий, но простой вопрос для вечернего дневника, который поможет пользователю лучше понять своё самочувствие. Только вопрос, без пояснений."

    async def get_advice(self, user_id: int, user_question: str, history=None) -> str:
        return await self.get_smart_advice(user_id, "general", user_question) or "AI сейчас недоступен."

    async def get_first_advice(self, user_id: int) -> str:
        return await self.get_smart_advice(user_id, "morning") or "Доброе утро! Хорошего дня!"

    async def analyze_day(self, user_id: int, date_str: str) -> str:
        return await self.get_smart_advice(user_id, "summary", f"Дата: {date_str}") or "Не удалось проанализировать день."
