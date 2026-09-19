"""
ИИ-подсказка психологу: «как помочь этому подростку».

ЧТО ЭТО. Рекомендации по правилам (app/prevention.py) отвечают на вопрос
«что вообще делают в такой ситуации». Этот модуль отвечает на вопрос «что
делать с ЭТИМ случаем»: учитывает динамику по срезам, возраст, явку и
сочетание показателей, которое в закрытый список не уложить.

ГЛАВНОЕ ОГРАНИЧЕНИЕ: НАРУЖУ НЕ УХОДЯТ ПЕРСОНАЛЬНЫЕ ДАННЫЕ.

Groq — сторонний сервис за пределами Казахстана. В базе «Изолята» лежат
ФИО несовершеннолетних, даты рождения и заметки психолога об их состоянии;
отправлять это наружу нельзя ни при каких настройках. Поэтому модель
получает только обезличенный профиль ситуации:

    возраст, пол, входящие/исходящие/взаимные выборы, динамика этих
    чисел по срезам, явка класса, размер класса

Ни имени, ни кода ученика, ни названия класса и школы, ни заметок, ни
имён одноклассников. Модель отвечает на вопрос «что делать с ребёнком,
у которого такие показатели», а не «что делать с Русланом». Профиль,
который уходит в запрос, возвращается вызывающему коду как есть, чтобы
психолог мог увидеть своими глазами, что именно было отправлено.

ОТВЕТСТВЕННОСТЬ. Ответ модели — материал для размышления специалиста, а
не заключение. Это закреплено и в системном промпте, и в тексте на
экране: решение принимает психолог.

Ключ берётся из GROQ_API_KEY (.env). Не задан — функция возвращает
понятный отказ, а интерфейс продолжает работать на правилах.
"""
import json
import os
import urllib.error
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Модель Groq. Инструктивная и быстрая — психолог не должен ждать ответа
# дольше нескольких секунд. Переопределяется через GROQ_MODEL: набор
# моделей у Groq меняется, и список доступных отличается между аккаунтами
# (проверить свой: GET /openai/v1/models с тем же ключом).
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# Сколько ждём ответа. Дольше — психолог решит, что интерфейс завис.
TIMEOUT_SECONDS = 25


def is_configured() -> bool:
    """Задан ли ключ. Интерфейс по этому флагу решает, показывать ли кнопку."""
    return bool((os.environ.get("GROQ_API_KEY") or "").strip())


SYSTEM_PROMPT = """Ты — методист-супервизор, который помогает школьному психологу в Казахстане.

Тебе дают ОБЕЗЛИЧЕННЫЕ данные социометрии одного ученика: сколько одноклассников его выбрали, кого выбрал он, сколько взаимных связей, как это менялось между срезами. Имени ученика ты не знаешь и знать не должен.

Твоя задача — предложить психологу конкретные шаги.

Правила:
1. Ты НЕ ставишь диагнозов и не делаешь выводов о психическом состоянии. Низкое число выборов — это социометрический факт, а не расстройство. Причины могут быть любые: переход из другой школы, застенчивость, конфликт, болезнь, особенности класса.
2. Пиши для специалиста: без общих слов вроде «проявите заботу», только выполнимые действия с указанием, как именно их сделать.
3. Учитывай возраст: то, что работает с 7-классником, не работает с 10-классником.
4. Если явка класса низкая, прямо скажи, что данным нельзя доверять, и первым шагом предложи повторить срез.
5. Обязательно укажи, при каких признаках нужно привлекать не психолога, а другого специалиста или родителей.
6. Отвечай на русском языке.

Формат ответа — строго JSON, без markdown и пояснений вокруг:
{
  "reading": "2-3 предложения: что показывают цифры и чего они НЕ показывают",
  "steps": [
    {"title": "Короткое название шага", "how": "Как именно сделать, 1-2 предложения"}
  ],
  "watch": ["признак, при котором нужно насторожиться"],
  "escalate": "когда и к кому обращаться помимо психолога"
}
Шагов — от 3 до 5. Признаков в watch — от 2 до 4."""


def build_profile(student, dynamics, class_size):
    """
    Собирает обезличенный профиль ситуации.

    Осознанно НЕ включает: ФИО, код ученика, дату рождения (только возраст
    в годах), заметки психолога, названия срезов, класса и школы, имена
    одноклассников. Всё это — персональные данные несовершеннолетнего, и
    стороннему сервису они не нужны, чтобы предложить методику.
    """
    latest = dynamics[-1] if dynamics else None

    age = None
    if getattr(student, "birth_date", None):
        from datetime import date
        today = date.today()
        age = today.year - student.birth_date.year - (
            (today.month, today.day) < (student.birth_date.month, student.birth_date.day)
        )

    trend = []
    for d in dynamics[-5:]:  # последние пять срезов: дальше динамика не читается
        trend.append({
            "in": d.get("in_degree"),
            "out": d.get("out_degree"),
            "mutual": d.get("mutual"),
            "status": d.get("status"),
        })

    profile = {
        "age": age,
        "gender": {"m": "мальчик", "f": "девочка"}.get(getattr(student, "gender", None)),
        "class_size": class_size,
        "surveys_count": len(dynamics),
    }
    if latest:
        profile.update({
            "in_degree": latest.get("in_degree"),
            "out_degree": latest.get("out_degree"),
            "mutual": latest.get("mutual"),
            "status": latest.get("status"),
            "participation": latest.get("participation"),
            "reliability": latest.get("reliability"),
            # Сколько одноклассников отметили «часто остаётся один». Передаём
            # только если число выше порога раскрытия — ниже него сервер и
            # психологу его не показывает (см. ALONE_MIN_REPORT).
            "alone_count": latest.get("alone_count"),
        })
    if len(trend) > 1:
        profile["trend"] = trend
    return profile


def _profile_to_text(p):
    """Человекочитаемое описание ситуации для модели."""
    lines = []
    who = []
    if p.get("age"):
        who.append("%d лет" % p["age"])
    if p.get("gender"):
        who.append(p["gender"])
    lines.append("Ученик: " + (", ".join(who) if who else "возраст не указан"))
    lines.append("Класс: %s учеников" % p.get("class_size", "?"))

    if p.get("in_degree") is None:
        lines.append("Срезов ещё не было — данных социометрии нет.")
        return "\n".join(lines)

    lines.append(
        "Последний срез: входящих выборов %s, исходящих %s, взаимных %s"
        % (p.get("in_degree"), p.get("out_degree"), p.get("mutual"))
    )
    status_ru = {
        "isolate": "нет входящих выборов (социометрический статус «изолят»)",
        "unknown": "данных не хватает для вывода",
        "connected": "связи есть",
    }.get(p.get("status"))
    if status_ru:
        lines.append("Статус: " + status_ru)

    if p.get("participation") is not None:
        lines.append("Явка класса на срезе: %d%%" % round(p["participation"] * 100))
    if p.get("reliability") == "low":
        lines.append("ВНИМАНИЕ: явка низкая, показателям доверять нельзя.")
    if p.get("alone_count"):
        lines.append(
            "Одноклассники отмечали его как «часто остаётся один»: %d раз" % p["alone_count"]
        )

    trend = p.get("trend")
    if trend and len(trend) > 1:
        seq = " -> ".join(str(t.get("in")) for t in trend)
        lines.append("Динамика входящих выборов по срезам: %s" % seq)

    return "\n".join(lines)


def suggest(profile):
    """
    Запрашивает рекомендации у Groq.

    Возвращает (result, error). result — разобранный JSON модели либо None.
    Сеть, ключ и формат ответа могут подвести в любой момент, поэтому любая
    ошибка возвращается текстом для психолога, а не роняет запрос: кнопка
    «как помочь» не должна ломать карточку ученика.
    """
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        return None, "ИИ-помощник не настроен: не задан GROQ_API_KEY."

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _profile_to_text(profile)},
        ],
        # Температура низкая: нужен воспроизводимый методический ответ,
        # а не творчество на данных о ребёнке.
        "temperature": 0.3,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
            # Без явного User-Agent Cloudflare перед Groq отдаёт 403 (код
            # 1010): заголовок по умолчанию "Python-urllib/3.x" попадает
            # под блокировку автоматических клиентов.
            "User-Agent": "izolyat/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        if e.code == 401:
            return None, "Ключ Groq недействителен. Проверьте GROQ_API_KEY в .env."
        if e.code == 429:
            return None, "Лимит запросов к Groq исчерпан. Попробуйте позже."
        if e.code == 404:
            return None, (
                "Модель «%s» недоступна для этого ключа. Список моделей аккаунта "
                "различается — задайте доступную в GROQ_MODEL." % GROQ_MODEL
            )
        return None, "Сервис рекомендаций недоступен (%s). %s" % (e.code, detail)
    except urllib.error.URLError:
        return None, "Нет связи с сервисом рекомендаций. Проверьте интернет."
    except Exception:
        return None, "Не удалось получить рекомендации."

    try:
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
    except Exception:
        return None, "Сервис вернул ответ в неожиданном формате."

    # Приводим к ожидаемой форме: модель может опустить поле или прислать
    # строку там, где ждём список. Интерфейс не должен об этом думать.
    steps = []
    for s in (data.get("steps") or [])[:5]:
        if isinstance(s, dict) and s.get("title"):
            steps.append({
                "title": str(s.get("title"))[:200],
                "how": str(s.get("how") or "")[:600],
            })
    watch = [str(w)[:300] for w in (data.get("watch") or [])[:4] if w]

    if not steps:
        return None, "Сервис не вернул рекомендаций. Попробуйте ещё раз."

    return {
        "reading": str(data.get("reading") or "")[:900],
        "steps": steps,
        "watch": watch,
        "escalate": str(data.get("escalate") or "")[:600],
        "model": GROQ_MODEL,
    }, None
