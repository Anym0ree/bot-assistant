import logging
import aiohttp
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import json
from database import db

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
                stats['max_sleep'] = max(sleep_hours)
                stats['min_sleep'] = min(sleep_hours)
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
            stats['best_day_score'] = max(scores) if scores else 0
            stats['worst_day_score'] = min(scores) if scores else 0
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
        stats['notes_count'] = len(data.get("notes", []))

        return stats

    async def get_first_advice(self, user_id: int) -> str:
        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные для анализа не найдены. Нажмите «🤖 AI-совет» снова."

        stats = self._get_aggregated_stats(user_data, user_id)
        profile = await db.get_user_profile(user_id)
        
        stats_text = f"""
ВОТ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ (используй только их, не выдумывай):

Возраст: {profile['age'] if profile['age'] else 'не указан'} лет
Рост: {profile['height'] if profile['height'] else 'не указан'} см
Вес: {profile['weight'] if profile['weight'] else 'не указан'} кг

СОН:
- Всего записей: {stats['sleep_count']}
- Средняя длительность: {stats['avg_sleep_hours']:.1f} часов
- Среднее качество: {stats.get('avg_sleep_quality', 0):.1f}/10
- Самый долгий сон: {stats.get('max_sleep', 0):.1f} ч
- Самый короткий сон: {stats.get('min_sleep', 0):.1f} ч

ЧЕК-ИНЫ:
- Всего записей: {stats['checkins_count']}
- Средняя энергия: {stats['avg_energy']:.1f}/10
- Средний стресс: {stats['avg_stress']:.1f}/10
- Частые эмоции: {', '.join(stats['top_emotions']) if stats['top_emotions'] else 'не указаны'}

ИТОГИ ДНЯ:
- Всего записей: {stats['summaries_count']}
- Средняя оценка: {stats['avg_day_score']:.1f}/10
- Лучшая оценка: {stats['best_day_score']}/10
- Худшая оценка: {stats['worst_day_score']}/10

ПИТАНИЕ:
- Записей о еде: {stats['food_count']}
- Записей о напитках: {stats['drinks_count']}
- Из них с водой: {stats['water_entries']}
"""

        system_prompt = f"""Ты — дружелюбный, эмпатичный AI-коуч. Напиши пользователю первое сообщение по строгой структуре.

СТРУКТУРА:
1. Приветствие.
2. Анализ состояния (сон, энергия, стресс, эмоции, оценка дня).
3. Советы по улучшению (если есть проблемы). Если проблем нет — похвали.
4. Завершение: "Задай любой вопрос о своём самочувствии или привычках. Я помню наши разговоры."

ПРАВИЛА:
- Пиши только на русском языке, грамотно.
- Не используй звёздочки, подчёркивания, решётки.
- Не выдумывай то, чего нет в данных.
- Будь человечным, но не перегружай текст.

Вот данные пользователя:
{stats_text}"""

        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": "Напиши моё первое сообщение по структуре выше."})

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": 800,
            }
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        content = content.replace('*', '').replace('_', '').replace('`', '').replace('~', '').replace('#', '').replace('>', '')
                        return content
                    else:
                        return "⚠️ Ошибка AI-сервиса. Попробуйте позже."
            except Exception as e:
                logger.error(f"AI request failed: {e}")
                return "⚠️ Не удалось связаться с AI-сервисом."

    async def analyze_day(self, user_id: int, date_str: str) -> str:
        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные не найдены."

        day_data = {}
        for s in user_data.get("sleep", []):
            if s.get('date') == date_str:
                day_data['sleep'] = s
                break
        for c in user_data.get("checkins", []):
            if c.get('date') == date_str:
                day_data['checkin'] = c
                break
        for d in user_data.get("day_summary", []):
            if d.get('date') == date_str:
                day_data['summary'] = d
                break
        
        if not day_data:
            return f"📅 За {date_str} нет данных. Заполни их, чтобы я мог проанализировать."

        day_text = f"Данные за {date_str}:\n"
        if 'sleep' in day_data:
            s = day_data['sleep']
            day_text += f"- Сон: лёг в {s['bed_time']}, встал в {s['wake_time']}, качество {s['quality']}/10\n"
        if 'checkin' in day_data:
            c = day_data['checkin']
            day_text += f"- Чек-ин: энергия {c['energy']}/10, стресс {c['stress']}/10\n"
        if 'summary' in day_data:
            d = day_data['summary']
            day_text += f"- Итог дня: оценка {d['score']}/10, лучшее: {d['best']}, сложное: {d['worst']}\n"

        system_prompt = f"""Ты — AI-коуч. Проанализируй один день пользователя.

Данные за день:
{day_text}

Напиши короткий анализ (3-5 предложений):
- Хороший ли был день? Почему?
- Что можно было улучшить?
- Один конкретный совет.

Пиши на русском, без звёздочек и лишних символов."""

        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": f"Проанализируй мой день за {date_str}."})

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {"model": self.model, "messages": messages, "temperature": 0.5, "max_tokens": 400}
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        content = content.replace('*', '').replace('_', '').replace('`', '')
                        return f"📅 *Анализ дня {date_str}*\n\n{content}"
                    else:
                        return "⚠️ Ошибка анализа. Попробуй позже."
            except Exception as e:
                logger.error(f"Day analysis failed: {e}")
                return "⚠️ Ошибка связи с AI."

    async def get_advice(self, user_id: int, user_question: str, history: List[Dict] = None) -> str:
        if not self.api_key:
            return "❌ AI-модуль не настроен."

        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные не найдены."

        stats = self._get_aggregated_stats(user_data, user_id)
        profile = await db.get_user_profile(user_id)
        
        stats_summary = f"Сон: {stats['avg_sleep_hours']:.1f} ч, энергия: {stats['avg_energy']:.1f}/10, стресс: {stats['avg_stress']:.1f}/10, оценка дня: {stats['avg_day_score']:.1f}/10."

        system_prompt = f"""Ты — дружелюбный AI-коуч. Отвечай на вопрос пользователя, используя его данные.

Данные: {stats_summary}
Возраст: {profile['age']}, рост: {profile['height']}, вес: {profile['weight']}

Правила:
- Пиши на русском, грамотно
- Без звёздочек и лишних символов
- Давай конкретные советы
- Будь человечным"""

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history[-10:])
        messages.append({"role": "user", "content": user_question})

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {"model": self.model, "messages": messages, "temperature": 0.7, "max_tokens": 800}
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        content = content.replace('*', '').replace('_', '').replace('`', '')
                        return content
                    else:
                        return "⚠️ Ошибка AI. Попробуй позже."
            except Exception as e:
                return "⚠️ Ошибка связи с AI."

ai_advisor = None
