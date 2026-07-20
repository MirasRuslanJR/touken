"""
Конфигурация приложения.

ЕДИНСТВЕННОЕ, что нужно отредактировать — строка DATABASE_URL ниже.
Никаких .env файлов: вставил строку подключения Supabase — и всё работает.
"""
import json

# ============================================================================
#  ПОДКЛЮЧЕНИЕ К SUPABASE  ←  ВСТАВЬ СВОЮ СТРОКУ СЮДА (это всё, что нужно)
# ----------------------------------------------------------------------------
#  Supabase -> Project Settings -> Database -> Connection string -> URI
#  Замени схему на  postgresql+psycopg2://  и подставь свой пароль.
#  Если прямое подключение (db.<ref>.supabase.co) не коннектится —
#  возьми строку "Session pooler" (порт 5432), она работает по IPv4.
# ============================================================================
DATABASE_URL = "postgresql+psycopg2://postgres.ssymhuuhrfzrdejkeeep:[YourPassword]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
# Секрет для подписи токенов входа. Поменяй на длинную случайную строку.
SECRET_KEY = "49bd3bd4-cf6d-4250-ab3b-442637f89fa4"

# Срок жизни токена входа (7 дней).
TOKEN_TTL = 7 * 24 * 3600

# Три социометрических вопроса. Тексты можно переопределять для каждого среза
# (адаптация под возраст класса) — ключи и типы при этом фиксированы.
QUESTIONS = [
    {"key": "cinema", "text": "С кем бы ты пошёл в кино?", "type": "positive", "max": 3},
    {"key": "project", "text": "С кем хотел бы делать проект?", "type": "positive", "max": 3},
    {"key": "alone", "text": "Кто в классе часто остаётся один?", "type": "isolation", "max": 3},
]
QUESTION_KEYS = [q["key"] for q in QUESTIONS]
POSITIVE_KEYS = [q["key"] for q in QUESTIONS if q["type"] == "positive"]


def effective_questions(survey):
    """
    Вопросы для конкретного среза. Ключи/типы фиксированы (чтобы аналитика
    не ломалась), но текст и max можно менять под возраст. Фолбэк — дефолты.
    """
    overrides = {}
    raw = getattr(survey, "questions", None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for q in data:
                    if isinstance(q, dict) and q.get("key"):
                        overrides[q["key"]] = q
        except Exception:
            overrides = {}
    result = []
    for base in QUESTIONS:
        ov = overrides.get(base["key"], {})
        text = str(ov.get("text") or "").strip() or base["text"]
        try:
            mx = int(ov.get("max") or base["max"])
        except (TypeError, ValueError):
            mx = base["max"]
        result.append({"key": base["key"], "text": text, "type": base["type"], "max": max(1, min(10, mx))})
    return result


def serialize_questions(raw_list):
    """Валидирует входящие вопросы -> JSON-строка (или None). Ключи ограничены
    дефолтными; кастомизируются только текст и max."""
    valid_keys = {q["key"] for q in QUESTIONS}
    out = []
    for q in raw_list or []:
        if not isinstance(q, dict):
            continue
        key, text = q.get("key"), str(q.get("text") or "").strip()
        if key not in valid_keys or not text:
            continue
        try:
            mx = int(q.get("max") or 3)
        except (TypeError, ValueError):
            mx = 3
        out.append({"key": key, "text": text, "max": max(1, min(10, mx))})
    return json.dumps(out, ensure_ascii=False) if out else None
