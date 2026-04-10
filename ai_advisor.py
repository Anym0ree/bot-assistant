import logging
import aiohttp
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import json

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
        """Вычисляет средние значения за последние 7 и 30 дней."""
        from database_pg import db
        import asyncio
        # Получаем временную зону пользователя (если нужно для дат, но даты уже в UTC)
        # Проще считать по датам из записей
        stats = {}
        now = datetime.utcnow()
        # Сон: вычисляем длительность из bed_time и wake_time
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

        # Чек-ины
        checkins = data.get("checkins", [])
        if checkins:
            energies = [c['energy'] for c in checkins if 'energy' in c]
            stresses = [c['stress'] for c in checkins if 'stress' in c]
            stats['avg_energy'] = sum(energies) / len(energies) if energies else 0
            stats['avg_stress'] = sum(stresses) / len(stresses) if stresses else 0
            stats['checkins_count'] = len(checkins)
            # Собираем все эмоции
            all_emotions = []
            for c in checkins:
                emo = c.get('emotions', [])
                if isinstance(emo, str):
                    try:
                        emo = json.loads(emo)
                    except:
                        emo = []
                all_emotions.extend(emo)
            from collections import Counter
            if all_emotions:
                stats['top_emotions'] = [e for e, _ in Counter(all_emotions).most_common(3)]
            else:
                stats['top_emotions'] = []
        else:
            stats['avg_energy'] = 0
            stats['avg_stress'] = 0
            stats['checkins_count'] = 0
            stats['top_emotions'] = []

        # Итоги дня
        summaries = data.get("day_summary", [])
        if summaries:
            scores = [s['score'] for s in summaries if 'score' in s]
            stats['avg_day_score'] = sum(scores) / len(scores) if scores else 0
            stats['summaries_count'] = len(summaries)
        else:
            stats['avg_day_score'] = 0
            stats['summaries_count'] = 0

        # Еда и напитки (просто количество записей)
        stats['food_count'] = len(data.get("food", []))
        stats['drinks_count'] = len(data.get("drinks", []))
        # Вода (упрощённо: ищем слово "вода" в напитках)
        water_count = 0
        for d in data.get("drinks", []):
            if "вода" in d.get('amount', '').lower() or "вода" in d.get('drink_type', '').lower():
                water_count += 1
        stats['water_entries'] = water_count

        return stats

    async def get_advice(self, user_id: int, user_question: Optional[str] = None, history: Optional[List[Dict]] = None) -> str:
        if not self.api_key:
            return ("❌ AI-модуль не настроен.\n"
                    "Добавьте API-ключ OpenRouter в config.py (переменная OPENAI_API_KEY).\n"
                    "Получить ключ можно бесплатно на https://openrouter.ai/keys")

        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные для анализа не найдены. Пожалуйста, сначала нажмите «🤖 AI-совет» из главного меню."

        # Получаем агрегированную статистику
        agg_stats = self._get_aggregated_stats(user_data, user_id)

        # Формируем сводку для AI
        user_summary = self._format_user_data(user_data)  # подробные последние записи
        agg_summary = (
            f"📊 *Агрегированная статистика (за всё время):*\n"
            f"🛌 Сон: {agg_stats['avg_sleep_hours']:.1f} часов в среднем (всего записей: {agg_stats['sleep_count']})\n"
            f"⚡️ Энергия: {agg_stats['avg_energy']:.1f}/10, стресс: {agg_stats['avg_stress']:.1f}/10 (всего чек-инов: {agg_stats['checkins_count']})\n"
            f"😊 Частые эмоции: {', '.join(agg_stats['top_emotions']) if agg_stats['top_emotions'] else 'не указаны'}\n"
            f"📝 Оценка дня: {agg_stats['avg_day_score']:.1f}/10 (всего итогов: {agg_stats['summaries_count']})\n"
            f"🍽 Записей о еде: {agg_stats['food_count']}, о напитках: {agg_stats['drinks_count']} (из них водных: {agg_stats['water_entries']})\n"
        )

        system_prompt = (
            "Ты — дружелюбный, остроумный и вдохновляющий AI-коуч на русском языке. "
            "Твоя задача — анализировать данные пользователя и давать полезные, конкретные советы.\n\n"
            "ПРАВИЛА ОТВЕТА (ОБЯЗАТЕЛЬНЫ):\n"
            "1. Пиши ТОЛЬКО на русском языке, без транслита, без английских слов (кроме имён собственных).\n"
            "2. НЕ используй Markdown-разметку (звёздочки, подчёркивания, решётки, обратные кавычки). "
            "Разрешаются только обычные переносы строк.\n"
            "3. НЕ пиши лишних символов вроде /, *, _, `, ~, #, >.\n"
            "4. Избегай грамматических ошибок и опечаток. Пиши грамотно.\n"
            "5. Структура ответа:\n"
            "   - Начни с короткого тёплого приветствия (без восклицательных знаков).\n"
            "   - Затем блок «Сон» (средняя длительность, качество, если есть тенденция).\n"
            "   - Блок «Энергия и стресс» (средние значения, частые эмоции).\n"
            "   - Блок «Питание и вода» (хватает ли воды, регулярность еды).\n"
            "   - Блок «Итоги дня» (средняя оценка, что обычно радует или огорчает).\n"
            "   - Блок «Заметки и напоминания» (если есть).\n"
            "   - 1–2 практичных совета, основанных на данных.\n"
            "   - Закончи фразой: «Я всегда рядом, чтобы поговорить. Задай любой вопрос о твоём самочувствии, привычках или просто поболтать.»\n"
            "6. Будь живым, но не перегружай текст. Не используй смайлики в каждом предложении.\n"
            "7. Если данных мало, скажи об этом и дай общие рекомендации.\n\n"
            "Вот данные пользователя:\n"
            f"{agg_summary}\n"
            "А вот последние подробные записи:\n"
            f"{user_summary}"
        )

        messages = [
            {"role": "system", "content": system_prompt}
        ]

        if history:
            # Если есть история диалога, добавляем её после системного промпта
            messages.extend(history)
            if user_question:
                messages.append({"role": "user", "content": user_question})
        else:
            # Первое сообщение: просим дать полный анализ
            messages.append({"role": "user", "content": "Проанализируй все мои данные и дай развёрнутый итог с советами."})

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
                "max_tokens": 1500,
                "stop": ["```"]  # дополнительная защита от markdown
            }
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        # Финальная очистка от случайных символов
                        content = content.replace('*', '').replace('_', '').replace('`', '').replace('~', '').replace('#', '').replace('>', '')
                        return content
                    else:
                        error_text = await resp.text()
                        logger.error(f"OpenRouter API error {resp.status}: {error_text}")
                        return f"⚠️ Ошибка AI-сервиса (код {resp.status}). Попробуйте позже."
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return "⚠️ Не удалось связаться с AI-сервисом. Проверьте интернет и настройки."

    def _format_user_data(self, data: Dict) -> str:
        # Оставляем как есть (твоя старая функция), но можно чуть сократить, чтобы не перегружать
        lines = []
        sleep = data.get("sleep", [])
        if sleep:
            lines.append("🛌 СОН (последние 10 записей):")
            for s in sleep[-10:]:
                woke = "да" if s.get('woke_night') else "нет"
                lines.append(f"  • {s.get('date')}: лёг в {s.get('bed_time')}, встал в {s.get('wake_time')}, качество {s.get('quality')}/10, просыпался ночью: {woke}")
                if s.get('note'):
                    lines.append(f"       заметка: {s['note'][:100]}")
        else:
            lines.append("🛌 Данные о сне отсутствуют.")
        checkins = data.get("checkins", [])
        if checkins:
            lines.append("\n⚡️ ЧЕК-ИНЫ (последние 10):")
            for c in checkins[-10:]:
                emotions = ', '.join(c.get('emotions', [])) or 'не указаны'
                lines.append(f"  • {c.get('date')} {c.get('time')}: энергия {c.get('energy')}/10, стресс {c.get('stress')}/10, эмоции: {emotions}")
                if c.get('note'):
                    lines.append(f"       заметка: {c['note'][:100]}")
        else:
            lines.append("\n⚡️ Чек-ины отсутствуют.")
        summaries = data.get("day_summary", [])
        if summaries:
            lines.append("\n📝 ИТОГИ ДНЯ (последние 10):")
            for s in summaries[-10:]:
                lines.append(f"  • {s.get('date')}: оценка {s.get('score')}/10, лучшее: {s.get('best') or '—'}, сложное: {s.get('worst') or '—'}")
                if s.get('gratitude'):
                    lines.append(f"       благодарность: {s['gratitude'][:80]}")
                if s.get('note'):
                    lines.append(f"       заметка: {s['note'][:100]}")
        else:
            lines.append("\n📝 Итоги дня отсутствуют.")
        notes = data.get("notes", [])
        if notes:
            lines.append("\n📋 ЗАМЕТКИ (последние 10):")
            for n in notes[-10:]:
                lines.append(f"  • {n.get('date')}: {n.get('text')[:120]}{'...' if len(n.get('text', '')) > 120 else ''}")
        else:
            lines.append("\n📋 Заметки отсутствуют.")
        food = data.get("food", [])
        if food:
            lines.append("\n🍽 ЕДА (последние 10):")
            for f in food[-10:]:
                lines.append(f"  • {f.get('date')} {f.get('time')}: {f.get('meal_type')} — {f.get('food_text')[:100]}")
        else:
            lines.append("\n🍽 Данные о еде отсутствуют.")
        drinks = data.get("drinks", [])
        if drinks:
            lines.append("\n🥤 НАПИТКИ (последние 10):")
            for d in drinks[-10:]:
                lines.append(f"  • {d.get('date')} {d.get('time')}: {d.get('drink_type')} — {d.get('amount')}")
        else:
            lines.append("\n🥤 Данные о напитках отсутствуют.")
        reminders = data.get("reminders", [])
        active_reminders = [r for r in reminders if r.get('is_active')]
        if active_reminders:
            lines.append("\n⏰ АКТИВНЫЕ НАПОМИНАНИЯ (до 5):")
            for r in active_reminders[:5]:
                lines.append(f"  • {r.get('date')} {r.get('time')}: {r.get('text')[:100]}")
        else:
            lines.append("\n⏰ Активных напоминаний нет.")
        return "\n".join(lines)

ai_advisor = None
