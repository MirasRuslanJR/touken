"""
Конфигурация приложения.

Секреты (строка подключения к Supabase и ключ подписи токенов) читаются из
переменных окружения — они НЕ хранятся в коде. Локально задай их через файл
`.env` в корне проекта (см. `.env.example`), на проде — через настройки
хостинга (Render/Railway/etc задают env vars в своей панели).
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()  # подхватывает .env в корне проекта, если он есть

# ============================================================================
#  ПОДКЛЮЧЕНИЕ К SUPABASE
# ----------------------------------------------------------------------------
#  Supabase -> Project Settings -> Database -> Connection string -> URI
#  Замени схему на  postgresql+psycopg2://  и подставь свой пароль.
#  Если прямое подключение (db.<ref>.supabase.co) не коннектится —
#  возьми строку "Session pooler" (порт 5432), она работает по IPv4.
#  Вставь готовую строку в .env как DATABASE_URL=... (см. .env.example).
# ============================================================================
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Секрет для подписи токенов входа. Задаётся в .env как SECRET_KEY=...
SECRET_KEY = os.environ.get("SECRET_KEY", "")

if not DATABASE_URL or not SECRET_KEY:
    raise RuntimeError(
        "Не заданы переменные окружения DATABASE_URL и/или SECRET_KEY.\n"
        "Скопируй .env.example в .env и впиши свои значения:\n"
        "  DATABASE_URL — Supabase -> Project Settings -> Database -> "
        "Connection string -> URI (схема postgresql+psycopg2://)\n"
        "  SECRET_KEY   — любая длинная случайная строка "
        "(например: python -c \"import secrets; print(secrets.token_hex(32))\")"
    )

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