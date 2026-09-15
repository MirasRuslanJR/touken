"""
Регресс-тесты на приватность ответов ученика.

Что именно гарантируется (см. заголовок app/analytics.py):

* положительные выборы — это социограмма, психолог видит их направленными,
  и это нормальная часть метода;
* негативная номинация «кто часто остаётся один» не атрибутируется автору
  НИГДЕ: не порождает рёбер графа, не приходит в карточку ученика списком
  имён и вообще не выходит наружу иначе как числом — и только начиная с
  трёх номинаций.

Именно второе правило было нарушено: карточка ученика показывала поимённо,
кто отметил ребёнка одиноким. Тесты ниже не дают этому вернуться.
"""
import json

from app.analytics import ALONE_MIN_REPORT
from tests.helpers import (
    auth,
    fresh_client,
    make_class,
    open_survey,
    register,
    submit,
    tickets,
)

NAMES = ["Алина А", "Борис Б", "Вера В", "Глеб Г", "Дана Д"]


def _setup():
    """Класс из пяти учеников; четверо отмечают Алину как «часто одну»."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)
    alina = st["Алина А"]

    # Борис ↔ Вера — взаимная пара. Алину как одинокую отмечают четверо,
    # то есть выше порога ALONE_MIN_REPORT.
    submit(client, svid, code["Борис Б"], cinema=[st["Вера В"]["id"]], alone=[alina["id"]])
    submit(client, svid, code["Вера В"], cinema=[st["Борис Б"]["id"]], alone=[alina["id"]])
    submit(client, svid, code["Глеб Г"], cinema=[st["Борис Б"]["id"]], alone=[alina["id"]])
    submit(client, svid, code["Дана Д"], cinema=[st["Вера В"]["id"]], alone=[alina["id"]])
    submit(client, svid, code["Алина А"], cinema=[st["Вера В"]["id"]])
    return client, token, cid, svid, st


def test_student_card_has_no_raw_choice_records():
    client, token, cid, svid, st = _setup()
    card = client.get("/api/students/%d/card" % st["Алина А"]["id"], headers=auth(token))
    assert card.status_code == 200, card.text
    blob = json.dumps(card.json(), ensure_ascii=False)
    # Ключи старого контракта, отдававшего авторство выборов целиком.
    assert "from_student" not in blob
    assert "choices_by_survey" not in blob


def test_alone_nomination_is_never_attributed_to_its_author():
    client, token, cid, svid, st = _setup()
    alina_id = st["Алина А"]["id"]

    # Ни одно ребро графа не порождается вопросом «часто один»: иначе на
    # социограмме было бы видно, кто именно назвал ребёнка одиноким.
    a = client.get("/api/surveys/%d/analytics" % svid, headers=auth(token)).json()
    for edge in a["edges"]:
        assert "alone" not in edge["questions"]

    # Наружу номинации уходят только числом.
    assert a["per_student"][str(alina_id)]["alone_votes"] == 4
    assert a["per_student"][str(alina_id)]["alone_reportable"] is True

    # В карточке — тоже только число, без списка авторов.
    card = client.get("/api/students/%d/card" % alina_id, headers=auth(token)).json()
    last = card["dynamics"][-1]
    assert last["alone_count"] == 4
    assert "alone_by" not in last and "alone_names" not in last


def test_alone_count_hidden_below_threshold():
    """Одна-две номинации — мнение одного-двух детей, а не сигнал класса:
    точное число не отдаётся, чтобы психолог не вешал ярлык с чужих слов."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)
    alina = st["Алина А"]

    # Всего две номинации — ниже порога.
    submit(client, svid, code["Борис Б"], cinema=[st["Вера В"]["id"]], alone=[alina["id"]])
    submit(client, svid, code["Вера В"], cinema=[st["Борис Б"]["id"]], alone=[alina["id"]])
    submit(client, svid, code["Глеб Г"], cinema=[st["Борис Б"]["id"]])
    submit(client, svid, code["Дана Д"], cinema=[st["Вера В"]["id"]])
    submit(client, svid, code["Алина А"], cinema=[st["Вера В"]["id"]])

    assert 2 < ALONE_MIN_REPORT
    card = client.get("/api/students/%d/card" % alina["id"], headers=auth(token)).json()
    assert card["dynamics"][-1]["alone_count"] is None


def test_mutual_pairs_are_named_but_one_sided_choices_are_not():
    """Взаимные пары психолог видит поимённо — о такой связи знают оба
    ученика. Односторонние выборы в карточке остаются только счётчиком."""
    client, token, cid, svid, st = _setup()
    card = client.get("/api/students/%d/card" % st["Борис Б"]["id"], headers=auth(token)).json()
    last = card["dynamics"][-1]
    assert last["mutual_names"] == ["Вера В"]
    # Глеба, выбравшего Бориса в одностороннем порядке, в карточке нет.
    assert "Глеб Г" not in json.dumps(card, ensure_ascii=False)
    assert last["in_degree"] == 2   # Вера и Глеб
    assert last["mutual"] == 1


def test_head_cannot_reach_any_student_data():
    """Завуч видит сводку по школе и не может открыть данные ребёнка.
    Это граница продукта, а не забытая проверка."""
    from tests.helpers import make_head, make_school, register_in_school

    client = fresh_client()
    school = make_school(client)
    psy = register_in_school(client, school["invite_code"], "psy2@school.kz")
    cid, st = make_class(client, psy, NAMES)
    svid = open_survey(client, psy, cid)

    head = make_head(client, school["invite_code"])
    for url in (
        "/api/classes",
        "/api/overview",
        "/api/classes/%d" % cid,
        "/api/students/%d/card" % st["Алина А"]["id"],
        "/api/surveys/%d/analytics" % svid,
        "/api/surveys/%d/tickets" % svid,
        "/api/alerts",
    ):
        r = client.get(url, headers=auth(head))
        assert r.status_code == 403, "%s отдал %s вместо 403" % (url, r.status_code)

    # А сводка по школе ему доступна — и в ней нет имён учеников.
    summary = client.get("/api/school/summary", headers=auth(head))
    assert summary.status_code == 200, summary.text
    blob = json.dumps(summary.json(), ensure_ascii=False)
    for name in NAMES:
        assert name not in blob
