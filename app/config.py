"""
Конфигурация приложения.

Задай два секрета через файл .env в корне проекта (см. .env.example):
DATABASE_URL (строка подключения Supabase) и SECRET_KEY. Файл .env не
коммитится — пароль и секрет не попадут в репозиторий.
"""
import json
import os
import secrets
import sys

# Автозагрузка файла .env (если он есть и установлен python-dotenv). Так можно
# держать реальный пароль в .env (он не коммитится, см. .gitignore), а не в коде.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================================
#  ПОДКЛЮЧЕНИЕ К SUPABASE — три способа задать строку (в порядке приоритета):
# ----------------------------------------------------------------------------
#  1) Файл .env в корне проекта:  DATABASE_URL=postgresql+psycopg2://...
#     (рекомендуется — пароль не попадёт в публичный репозиторий).
#  2) Переменная окружения DATABASE_URL (например, в панели Render).
#  3) Прямо в строке-заглушке ниже (удобно, но не коммить реальный пароль).
#
#  Строку берёшь в Supabase -> Project Settings -> Database -> Connection
#  string -> URI, схему меняешь на postgresql+psycopg2://. Если прямое
#  подключение не коннектится — бери "Session pooler" (порт 5432, IPv4).
# ============================================================================
DATABASE_URL = os.environ.get("DATABASE_URL") or \
    "postgresql+psycopg2://postgres:PASSWORD@db.YOUR-PROJECT-REF.supabase.co:5432/postgres"

# Секрет для подписи токенов входа. Задай через .env или переменную окружения.
# Если он не задан (или оставлен дефолтным), НЕ используем предсказуемый ключ:
# генерируем случайный на время работы процесса. Так демо не падает, но и
# подделать токен по известному секрету нельзя. Токены сбросятся при
# перезапуске — для продакшена обязательно задай постоянный SECRET_KEY.
_DEFAULT_SECRET = "change-me-to-a-long-random-string-please"
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == _DEFAULT_SECRET:
    print(
        "⚠️  SECRET_KEY не задан — использую временный случайный ключ. "
        "Токены входа сбросятся при перезапуске сервера. Для продакшена "
        "задай постоянный SECRET_KEY в .env.",
        file=sys.stderr,
    )
    SECRET_KEY = secrets.token_urlsafe(48)

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
