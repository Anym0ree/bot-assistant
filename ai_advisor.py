import logging
import aiohttp
from typing import Dict, Optional, List

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

    async def get_advice(self, user_id: int, user_question: Optional[str] = None, history: Optional[List[Dict]] = None) -> str:
        if not self.api_key:
            return ("❌ AI-модуль не настроен.\n"
                    "Добавьте API-ключ OpenRouter в config.py (переменная OPENAI_API_KEY).\n"
                    "Получить ключ можно бесплатно на https://openrouter.ai/keys")

        user_data = self.get_user_data(user_id)
        if not user_data:
            return "⚠️ Данные для анализа не найдены. Пожалуйста, сначала нажмите «🤖 AI-совет» из главного меню."

        user_summary = self._format_user_data(user_data)

        system_prompt = (
            "Ты — дружелюбный, остроумный и вдохновляющий AI-коуч на русском языке. "
            "Твоя задача — анализировать данные пользователя (сон, чек-ины, итоги дня, заметки, еда, напитки, напоминания). "
            "Отвечай ТОЛЬКО на русском языке, без ошибок, без транслита, без случайных латинских букв и символов. "
            "Не используй Markdown-разметку (звёздочки, подчёркивания, решётки), кроме базовых переносов строк. "
            "Не пиши лишних символов вроде /, *, _, `, ~. Пиши обычным текстом.\n\n"
            "Структура ответа:\n"
            "1. Начни с приветствия в стиле пользователя(основываясь на его записях) \n"
            "2. Затем выдели 2-3 ключевых наблюдения из данных (например, качество сна, уровень энергии, эмоции).\n"
            "3. Добавь несколько интересных фактов и позитивных замечаниий.\n"
            "4. Дай 3-4 практичных, но лёгких совета.\n"
            "5. Закончи тёплым напоминанием: «Я всегда рядом, чтобы поговорить. Можешь спросить меня о чём угодно — о привычках, питании, стрессе или просто поболтать. Что тебя волнует сегодня?»\n\n"
            "Будь живым, немного игривым, но не перегружай текст. Пиши короткими абзацами. "
            "Ни в коем случае не используй английские слова, если нет прямой необходимости. "
            "Избегай грамматических ошибок и опечаток."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Привет! Вот мои данные за последнее время:\n{user_summary}"}
        ]

        if history:
            new_messages = [messages[0]]
            new_messages.extend(history)
            if user_question:
                new_messages.append({"role": "user", "content": user_question})
            messages = new_messages
        else:
            if user_question:
                messages.append({"role": "user", "content": user_question})
            else:
                messages.append({"role": "user", "content": "Расскажи, что интересного ты видишь в моих данных? Дай общий анализ и пару советов."})

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
                "max_tokens": 1200
            }
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result["choices"][0]["message"]["content"]
                        # Дополнительная очистка от случайных символов
                        content = content.replace('*', '').replace('_', '').replace('`', '').replace('~', '')
                        return content
                    else:
                        error_text = await resp.text()
                        logger.error(f"OpenRouter API error {resp.status}: {error_text}")
                        return f"⚠️ Ошибка AI-сервиса (код {resp.status}). Попробуйте позже."
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return "⚠️ Не удалось связаться с AI-сервисом. Проверьте интернет и настройки."

    def _format_user_data(self, data: Dict) -> str:
        # (без изменений, твой старый код)
        lines = []
        sleep = data.get("sleep", [])
        if sleep:
            lines.append("🛌 СОН:")
            for s in sleep[-10:]:
                woke = "да" if s.get('woke_night') else "нет"
                lines.append(f"  • {s.get('date')}: лёг в {s.get('bed_time')}, встал в {s.get('wake_time')}, качество {s.get('quality')}/10, просыпался ночью: {woke}")
                if s.get('note'):
                    lines.append(f"       заметка: {s['note'][:100]}")
        else:
            lines.append("🛌 Данные о сне отсутствуют.")
        checkins = data.get("checkins", [])
        if checkins:
            lines.append("\n⚡️ ЧЕК-ИНЫ:")
            for c in checkins[-10:]:
                emotions = ', '.join(c.get('emotions', [])) or 'не указаны'
                lines.append(f"  • {c.get('date')} {c.get('time')}: энергия {c.get('energy')}/10, стресс {c.get('stress')}/10, эмоции: {emotions}")
                if c.get('note'):
                    lines.append(f"       заметка: {c['note'][:100]}")
        else:
            lines.append("\n⚡️ Чек-ины отсутствуют.")
        summaries = data.get("day_summary", [])
        if summaries:
            lines.append("\n📝 ИТОГИ ДНЯ:")
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
            lines.append("\n📋 ЗАМЕТКИ:")
            for n in notes[-15:]:
                lines.append(f"  • {n.get('date')}: {n.get('text')[:120]}{'...' if len(n.get('text', '')) > 120 else ''}")
        else:
            lines.append("\n📋 Заметки отсутствуют.")
        food = data.get("food", [])
        if food:
            lines.append("\n🍽 ЕДА:")
            for f in food[-10:]:
                lines.append(f"  • {f.get('date')} {f.get('time')}: {f.get('meal_type')} — {f.get('food_text')[:100]}")
        else:
            lines.append("\n🍽 Данные о еде отсутствуют.")
        drinks = data.get("drinks", [])
        if drinks:
            lines.append("\n🥤 НАПИТКИ:")
            for d in drinks[-10:]:
                lines.append(f"  • {d.get('date')} {d.get('time')}: {d.get('drink_type')} — {d.get('amount')}")
        else:
            lines.append("\n🥤 Данные о напитках отсутствуют.")
        reminders = data.get("reminders", [])
        active_reminders = [r for r in reminders if r.get('is_active')]
        if active_reminders:
            lines.append("\n⏰ АКТИВНЫЕ НАПОМИНАНИЯ:")
            for r in active_reminders[-5:]:
                lines.append(f"  • {r.get('date')} {r.get('time')}: {r.get('text')[:100]}")
        else:
            lines.append("\n⏰ Активных напоминаний нет.")
        return "\n".join(lines)

ai_advisor = None
