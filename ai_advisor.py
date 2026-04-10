import logging
import aiohttp
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import json
from database_pg import db

logger = logging.getLogger(__name__)

ai_advisor = None

class AIAdvisor:
    def __init__(self, api_key: str, model: str = "openrouter/free", base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/') + '/chat/completions'
        self.user_context = {}
        if api_key:
            logger.info(f"AIAdvisor инициализирован с OpenRouter. Модель: {self.model}")
        else:
            logger.warning("AIAdvisor: API ключ не задан!")

    def set_user_data(self, user_id: int, data: Dict):
        self.user_context[user_id] = data

    def get_user_data(self, user_id: int) -> Optional[Dict]:
        return self.user_context.get(user_id)

    def clear_user_data(self, user_id: int):
        self.user_context.pop(user_id, None)

    def _get_aggregated_stats(self, data: Dict, user_id: int) -> Dict:
        from collections import Counter
        stats = {}
        sleep_data = data.get("sleep", [])
        if sleep_data:
            sleep_hours = []
            for s in sleep_data:
                try:
                    bed = datetime.strptime(s['bed_time'], "%H:%M")
                    wake = datetime.strptime(s['wake_time'], "%H:%M")
                    hours = (wake - bed).seconds / 3600
                    if hours < 0:
                        hours += 24
                    sleep_hours.append(hours)
                except:
                    pass
            if sleep_hours:
                stats['avg_sleep_hours'] = sum(sleep_hours) / len(sleep_hours)
                stats['sleep_count'] = len(sleep_hours)
            else:
                stats['avg_sleep_hours'] = 0
                stats['sleep_count'] = 0
        else:
            stats['avg_sleep_hours'] = 0
            stats['sleep_count'] = 0

        checkins = data.get("checkins", [])
        if checkins:
            energies = [c['energy'] for c in checkins if 'energy' in c]
            stresses = [c['stress'] for c in checkins if 'stress' in c]
            stats['avg_energy'] = sum(energies) / len(energies) if energies else 0
            stats['avg_stress'] = sum(stresses) / len(stresses) if stresses else 0
            stats['checkins_count'] = len(checkins)
            all_emotions = []
            for c in checkins:
                emo = c.get('emotions', [])
                if isinstance(emo, str):
                    try:
                        emo = json.loads(emo)
                    except:
                        emo = []
                all_emotions.extend(emo)
            if all_emotions:
                stats['top_emotions'] = [e for e, _ in Counter(all_emotions).most_common(3)]
            else:
                stats['top_emotions'] = []
        else:
            stats['avg_energy'] = 0
            stats['avg_stress'] = 0
            stats['checkins_count'] = 0
            stats['top_emotions'] = []

        summaries = data.get("day_summary", [])
        if summaries:
            scores = [s['score'] for s in summaries if 'score' in s]
            stats['avg_day_score'] = sum(scores) / len(scores) if scores else 0
            stats['summaries_count'] = len(summaries)
        else:
            stats['avg_day_score'] = 0
            stats['summaries_count'] = 0

        stats['food_count'] = len(data.get("food", []))
        stats['drinks_count'] = len(data.get("drinks", []))
        water_count = 0
        for d in data.get("drinks", []):
            if "вода" in d.get('amount', '').lower() or "вода" in d.get('drink_type', '').lower():
                water_count += 1
        stats['water_entries'] = water_count

        return stats

    def _get_fixed_first_message(self, user_summary: str, agg_summary: str) -> str:
        return f"""📊 *Анализ твоих данных*

{agg_summary}

📋 *Последние записи:*
{user_summary}

💡 *Что это значит?*
На основе этих данных я могу дать персональные советы. Задай любой вопрос о своём самочувствии, привычках или просто поболтай со мной.

❓ *Примеры вопросов:*
• Как улучшить качество сна?
• Что мне делать с высоким стрессом?
• Какие у меня тенденции за последнюю неделю?
• Почему у меня низкая энергия?

Я всегда рядом, чтобы помочь. Что тебя волнует сегодня?"""

    async def get_first_advice(self, user_id: int) -> str:
        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные для анализа не найдены. Пожалуйста, сначала нажмите «🤖 AI-совет» из главного меню."

        agg_stats = self._get_aggregated_stats(user_data, user_id)
        agg_summary = (
            f"🛌 Сон: {agg_stats['avg_sleep_hours']:.1f} часов в среднем (всего записей: {agg_stats['sleep_count']})\n"
            f"⚡️ Энергия: {agg_stats['avg_energy']:.1f}/10, стресс: {agg_stats['avg_stress']:.1f}/10 (всего чек-инов: {agg_stats['checkins_count']})\n"
            f"😊 Частые эмоции: {', '.join(agg_stats['top_emotions']) if agg_stats['top_emotions'] else 'не указаны'}\n"
            f"📝 Оценка дня: {agg_stats['avg_day_score']:.1f}/10 (всего итогов: {agg_stats['summaries_count']})\n"
            f"🍽 Записей о еде: {agg_stats['food_count']}, о напитках: {agg_stats['drinks_count']} (из них водных: {agg_stats['water_entries']})"
        )
        user_summary = self._format_user_data(user_data)
        return self._get_fixed_first_message(user_summary, agg_summary)

    async def get_advice(self, user_id: int, user_question: str, history: List[Dict] = None) -> str:
        if not self.api_key:
            return ("❌ AI-модуль не настроен.\n"
                    "Добавьте API-ключ OpenRouter в config.py (переменная OPENAI_API_KEY).\n"
                    "Получить ключ можно бесплатно на https://openrouter.ai/keys")

        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные для анализа не найдены. Пожалуйста, сначала нажмите «🤖 AI-совет» из главного меню."

        agg_stats = self._get_aggregated_stats(user_data, user_id)
        agg_summary = (
            f"Средняя длительность сна: {agg_stats['avg_sleep_hours']:.1f} часов\n"
            f"Средняя энергия: {agg_stats['avg_energy']:.1f}/10, стресс: {agg_stats['avg_stress']:.1f}/10\n"
            f"Частые эмоции: {', '.join(agg_stats['top_emotions']) if agg_stats['top_emotions'] else 'не указаны'}\n"
            f"Средняя оценка дня: {agg_stats['avg_day_score']:.1f}/10"
        )

        system_prompt = (
            "Ты — дружелюбный, остроумный и вдохновляющий AI-коуч на русском языке. "
            "Твоя задача — отвечать на вопросы пользователя, основываясь на его данных.\n\n"
            "ПРАВИЛА ОТВЕТА (ОБЯЗАТЕЛЬНЫ):\n"
            "1. Пиши ТОЛЬКО на русском языке, без транслита, без английских слов.\n"
            "2. НЕ используй Markdown-разметку (звёздочки, подчёркивания, решётки). Разрешаются только переносы строк.\n"
            "3. НЕ пиши лишних символов вроде /, *, _, `, ~, #, >.\n"
            "4. Избегай грамматических ошибок и опечаток.\n"
            "5. Отвечай по существу, давай практичные советы.\n"
            "6. Будь живым, но не перегружай текст. Не используй смайлики в каждом предложении
