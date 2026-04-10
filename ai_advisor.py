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
            qualities = []
            for s in sleep_data:
                try:
                    bed = datetime.strptime(s['bed_time'], "%H:%M")
                    wake = datetime.strptime(s['wake_time'], "%H:%M")
                    hours = (wake - bed).seconds / 3600
                    if hours < 0:
                        hours += 24
                    sleep_hours.append(hours)
                    qualities.append(s.get('quality', 0))
                except:
                    pass
            if sleep_hours:
                stats['avg_sleep_hours'] = sum(sleep_hours) / len(sleep_hours)
                stats['avg_sleep_quality'] = sum(qualities) / len(qualities) if qualities else 0
                stats['sleep_count'] = len(sleep_hours)
                # Тенденция за последние 7 дней
                if len(sleep_hours) >= 7:
                    last_week = sum(sleep_hours[-7:]) / 7
                    prev_week = sum(sleep_hours[-14:-7]) / 7 if len(sleep_hours) >= 14 else last_week
                    stats['sleep_trend'] = "увеличилась" if last_week > prev_week else "уменьшилась" if last_week < prev_week else "осталась стабильной"
                    stats['sleep_trend_diff'] = abs(last_week - prev_week)
                else:
                    stats['sleep_trend'] = None
                # Самый длинный и короткий сон
                stats['max_sleep'] = max(sleep_hours)
                stats['min_sleep'] = min(sleep_hours)
            else:
                stats['avg_sleep_hours'] = 0
                stats['sleep_count'] = 0
                stats['sleep_trend'] = None
        else:
            stats['avg_sleep_hours'] = 0
            stats['sleep_count'] = 0
            stats['sleep_trend'] = None

        checkins = data.get("checkins", [])
        if checkins:
            energies = [c['energy'] for c in checkins if 'energy' in c]
            stresses = [c['stress'] for c in checkins if 'stress' in c]
            stats['avg_energy'] = sum(energies) / len(energies) if energies else 0
            stats['avg_stress'] = sum(stresses) / len(stresses) if stresses else 0
            stats['checkins_count'] = len(checkins)
            # Тренды энергии и стресса
            if len(energies) >= 7:
                last_week_energy = sum(energies[-7:]) / 7
                prev_week_energy = sum(energies[-14:-7]) / 7 if len(energies) >= 14 else last_week_energy
                stats['energy_trend'] = "выросла" if last_week_energy > prev_week_energy else "снизилась" if last_week_energy < prev_week_energy else "стабильна"
            else:
                stats['energy_trend'] = None
            if len(stresses) >= 7:
                last_week_stress = sum(stresses[-7:]) / 7
                prev_week_stress = sum(stresses[-14:-7]) / 7 if len(stresses) >= 14 else last_week_stress
                stats['stress_trend'] = "вырос" if last_week_stress > prev_week_stress else "снизился" if last_week_stress < prev_week_stress else "стабилен"
            else:
                stats['stress_trend'] = None
            
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
            stats['energy_trend'] = None
            stats['stress_trend'] = None

        summaries = data.get("day_summary", [])
        if summaries:
            scores = [s['score'] for s in summaries if 'score' in s]
            stats['avg_day_score'] = sum(scores) / len(scores) if scores else 0
            stats['summaries_count'] = len(summaries)
            # Лучшая и худшая оценка дня
            stats['best_day_score'] = max(scores) if scores else 0
            stats['worst_day_score'] = min(scores) if scores else 0
        else:
            stats['avg_day_score'] = 0
            stats['summaries_count'] = 0
            stats['best_day_score'] = 0
            stats['worst_day_score'] = 0

        stats['food_count'] = len(data.get("food", []))
        stats['drinks_count'] = len(data.get("drinks", []))
        water_count = 0
        for d in data.get("drinks", []):
            if "вода" in d.get('amount', '').lower() or "вода" in d.get('drink_type', '').lower():
                water_count += 1
        stats['water_entries'] = water_count
        
        stats['notes_count'] = len(data.get("notes", []))

        return stats

    async def get_first_advice(self, user_id: int) -> str:
        """AI генерирует персонализированное первое сообщение"""
        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные для анализа не найдены. Пожалуйста, сначала нажмите «🤖 AI-совет» из главного меню."

        stats = self._get_aggregated_stats(user_data, user_id)
        profile = await db.get_user_profile(user_id)
        
        # Формируем подробную статистику для AI
        stats_text = f"""
Данные пользователя:
- Возраст: {profile['age'] if profile['age'] else 'не указан'} лет
- Рост: {profile['height'] if profile['height'] else 'не указан'} см
- Вес: {profile['weight'] if profile['weight'] else 'не указан'} кг

Сон:
- Всего записей: {stats['sleep_count']}
- Средняя длительность: {stats['avg_sleep_hours']:.1f} часов
- Среднее качество: {stats.get('avg_sleep_quality', 0):.1f}/10
- Самый длинный сон: {stats.get('max_sleep', 0):.1f} ч
- Самый короткий сон: {stats.get('min_sleep', 0):.1f} ч
- Тенденция за неделю: {stats['sleep_trend'] if stats['sleep_trend'] else 'недостаточно данных'}

Чек-ины:
- Всего записей: {stats['checkins_count']}
- Средняя энергия: {stats['avg_energy']:.1f}/10
- Средний стресс: {stats['avg_stress']:.1f}/10
- Тенденция энергии: {stats['energy_trend'] if stats['energy_trend'] else 'недостаточно данных'}
- Тенденция стресса: {stats['stress_trend'] if stats['stress_trend'] else 'недостаточно данных'}
- Частые эмоции: {', '.join(stats['top_emotions']) if stats['top_emotions'] else 'не указаны'}

Итоги дня:
- Всего записей: {stats['summaries_count']}
- Средняя оценка дня: {stats['avg_day_score']:.1f}/10
- Лучшая оценка: {stats['best_day_score']}/10
- Худшая оценка: {stats['worst_day_score']}/10

Питание:
- Записей о еде: {stats['food_count']}
- Записей о напитках: {stats['drinks_count']}
- Из них водных: {stats['water_entries']}

Прочее:
- Заметок: {stats['notes_count']}
"""

        system_prompt = (
            "Ты — дружелюбный, эмпатичный и остроумный AI-коуч на русском языке. "
            "Твоя задача — проанализировать данные пользователя и написать ему тёплое, живое первое сообщение.\n\n"
            "ПРАВИЛА СООБЩЕНИЯ:\n"
            "1. Напиши приветствие и краткий обзор состояния пользователя (2-3 предложения).\n"
            "2. Добавь 1-2 интересных факта, связанных с данными пользователя (например, про сон, энергию, стресс, эмоции). Факты должны быть реальными и научно обоснованными.\n"
            "3. Если есть проблемы (мало сна, высокий стресс, низкая энергия, обезвоживание), напиши об этом и дай 1-2 конкретных совета по улучшению.\n"
            "4. Если всё хорошо — похвали пользователя и предложи поддерживать форму.\n"
            "5. Закончи вопросом или предложением задать уточняющий вопрос.\n"
            "6. Пиши ТОЛЬКО на русском языке, без транслита.\n"
            "7. НЕ используй Markdown-разметку (звёздочки, подчёркивания, решётки).\n"
            "8. НЕ пиши лишних символов вроде /, *, _, `, ~, #, >.\n"
            "9. Будь живым, человечным, не перегружай текст.\n\n"
            f"Вот данные пользователя:\n{stats_text}"
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": "Напиши моё первое сообщение с анализом состояния и советами."})

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0; +https://telegram.org)"
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 1200,
            }
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        content = content.replace('*', '').replace('_', '').replace('`', '').replace('~', '').replace('#', '').replace('>', '')
                        # Добавляем подсказку в конце
                        content += "\n\n✏️ Задай любой вопрос о своём самочувствии или привычках. Я помню наши разговоры."
                        return content
                    elif resp.status == 429:
                        return "⚠️ Превышен лимит запросов к AI-сервису. Подождите 5-10 минут и попробуйте снова."
                    else:
                        error_text = await resp.text()
                        logger.error(f"OpenRouter API error {resp.status}: {error_text}")
                        return f"⚠️ Ошибка AI-сервиса (код {resp.status}). Попробуйте позже."
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return "⚠️ Не удалось связаться с AI-сервисом. Проверьте интернет и настройки."

    async def get_advice(self, user_id: int, user_question: str, history: List[Dict] = None) -> str:
        if not self.api_key:
            return ("❌ AI-модуль не настроен.\n"
                    "Добавьте API-ключ OpenRouter в config.py (переменная OPENAI_API_KEY).\n"
                    "Получить ключ можно бесплатно на https://openrouter.ai/keys")

        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные для анализа не найдены. Пожалуйста, сначала нажмите «🤖 AI-совет» из главного меню."

        stats = self._get_aggregated_stats(user_data, user_id)
        profile = await db.get_user_profile(user_id)
        
        stats_summary = (
            f"Возраст: {profile['age']}, рост: {profile['height']} см, вес: {profile['weight']} кг. "
            f"Сон: {stats['avg_sleep_hours']:.1f} ч, качество {stats.get('avg_sleep_quality', 0):.1f}/10. "
            f"Энергия: {stats['avg_energy']:.1f}/10, стресс: {stats['avg_stress']:.1f}/10. "
            f"Оценка дня: {stats['avg_day_score']:.1f}/10. "
            f"Частые эмоции: {', '.join(stats['top_emotions']) if stats['top_emotions'] else 'не указаны'}. "
            f"Всего записей: сон {stats['sleep_count']}, чек-ины {stats['checkins_count']}, итоги {stats['summaries_count']}."
        )

        system_prompt = (
            "Ты — дружелюбный, эмпатичный AI-коуч на русском языке. "
            "Отвечай на вопрос пользователя, основываясь на его данных. "
            "Давай конкретные, практичные советы. Будь живым, но не перегружай текст. "
            "Пиши на русском, без транслита, без лишних символов.\n\n"
            f"Данные пользователя:\n{stats_summary}"
        )

        messages = [{"role": "system", "content": system_prompt}]

        if history:
            messages.extend(history[-10:])

        messages.append({"role": "user", "content": user_question})

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0; +https://telegram.org)"
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000,
            }
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        content = content.replace('*', '').replace('_', '').replace('`', '').replace('~', '').replace('#', '').replace('>', '')
                        return content
                    elif resp.status == 429:
                        return "⚠️ Превышен лимит запросов к AI-сервису. Подождите 5-10 минут и попробуйте снова."
                    else:
                        error_text = await resp.text()
                        logger.error(f"OpenRouter API error {resp.status}: {error_text}")
                        return f"⚠️ Ошибка AI-сервиса (код {resp.status}). Попробуйте позже."
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return "⚠️ Не удалось связаться с AI-сервисом. Проверьте интернет и настройки."

ai_advisor = None
