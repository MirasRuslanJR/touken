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
    # Без эмодзи: в консоли Windows sys.stderr отдаёт их как \-последовательности.
    print(
        "ВНИМАНИЕ: SECRET_KEY не задан, использую временный случайный ключ. "
        "Токены входа сбросятся при перезапуске сервера. Для продакшена "
        "задай постоянный SECRET_KEY в .env.",
        file=sys.stderr,
    )
    SECRET_KEY = secrets.token_urlsafe(48)

# Срок жизни токена входа (7 дней).
TOKEN_TTL = 7 * 24 * 3600

# Код приглашения оператора сервиса. Пока он не задан, любой посетитель может
# зарегистрировать школу прямо из интерфейса — удобно для локального демо.
# Если код задан, форма регистрации школы отключается, и завести аккаунт можно
# только по коду: доступ к персональным данным несовершеннолетних не должен
# выдаваться самообслуживанием.
REGISTRATION_INVITE_CODE = (os.environ.get("REGISTRATION_INVITE_CODE") or "").strip()
if not REGISTRATION_INVITE_CODE:
    print(
        "⚠️  REGISTRATION_INVITE_CODE не задан: зарегистрировать школу может любой "
        "посетитель. Это нормально для локального демо; для публичного стенда "
        "задай код в .env — тогда форма регистрации школы отключится.",
        file=sys.stderr,
    )

# Разрешённые источники для CORS. По умолчанию — только тот же origin, что и
# фронтенд (он отдаётся этим же приложением), поэтому список пуст. Для демо с
# другого устройства задай ALLOWED_ORIGINS через запятую.
ALLOWED_ORIGINS = [o.strip() for o in (os.environ.get("ALLOWED_ORIGINS") or "").split(",") if o.strip()]

# Три социометрических вопроса. Тексты можно переопределять для каждого среза
# (адаптация под возраст класса) — ключи и типы при этом фиксированы.
#
# Казахский обязателен, а не «приятное дополнение»: в НИШ и в большинстве
# региональных школ часть класса думает и отвечает на казахском, а неточно
# понятый вопрос портит сами данные, ради которых всё и делается.
QUESTIONS = [
    {"key": "cinema", "type": "positive", "max": 3,
     "text": "С кем бы ты пошёл в кино?",
     "text_kk": "Киноға кіммен барар едің?"},
    {"key": "project", "type": "positive", "max": 3,
     "text": "С кем хотел бы делать проект?",
     "text_kk": "Жобаны кіммен бірге жасағың келеді?"},
    {"key": "alone", "type": "isolation", "max": 3,
     "text": "Кто в классе часто остаётся один?",
     "text_kk": "Сыныпта кім жиі жалғыз қалады?"},
]
QUESTION_KEYS = [q["key"] for q in QUESTIONS]
POSITIVE_KEYS = [q["key"] for q in QUESTIONS if q["type"] == "positive"]

LANGUAGES = ("ru", "kk")


def effective_questions(survey):
    """
    Вопросы для конкретного среза. Ключи/типы фиксированы (чтобы аналитика
    не ломалась), но текст и max можно менять под возраст. Фолбэк — дефолты.

    Возвращаются оба языка сразу: ученик переключает язык на самой странице
    опроса, и лишний запрос к серверу посреди прохождения не нужен.
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
        text_kk = str(ov.get("text_kk") or "").strip() or base["text_kk"]
        try:
            mx = int(ov.get("max") or base["max"])
        except (TypeError, ValueError):
            mx = base["max"]
        result.append({
            "key": base["key"], "text": text, "text_kk": text_kk,
            "type": base["type"], "max": max(1, min(10, mx)),
        })
    return result


def serialize_questions(raw_list):
    """Валидирует входящие вопросы -> JSON-строка (или None). Ключи ограничены
    дефолтными; кастомизируются только тексты (ru/kk) и max."""
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
        item = {"key": key, "text": text, "max": max(1, min(10, mx))}
        text_kk = str(q.get("text_kk") or "").strip()
        if text_kk:
            item["text_kk"] = text_kk
        out.append(item)
    return json.dumps(out, ensure_ascii=False) if out else None
