"""
Профилактическая работа: рекомендации по данным среза, план и проведение
мероприятий, охват и оценка эффекта.
"""
from app.database import SessionLocal
from app.models import Activity, ActivityParticipant, AuditLog
from tests.helpers import (
    auth,
    close_survey,
    fresh_client,
    make_class,
    make_head,
    make_school,
    open_survey,
    register,
    register_in_school,
    submit,
    tickets,
)

NAMES = ["Алина А", "Борис Б", "Вера В", "Глеб Г", "Дана Д", "Ерлан Е"]


def _survey(client, token, cid, st, title, chooser_map, alone=()):
    svid = open_survey(client, token, cid, title)
    code = tickets(client, token, svid)
    for name in st:
        if name not in code:
            continue
        targets = chooser_map.get(name, [])
        submit(client, svid, code[name],
               cinema=[st[t]["id"] for t in targets],
               alone=[st[t]["id"] for t in alone])
    close_survey(client, token, svid)
    return svid


# Алину не выбирает никто и трое отмечают её одинокой -> изолят + ярлык.
ISOLATED_PLAN = {
    "Алина А": ["Борис Б"], "Борис Б": ["Вера В"], "Вера В": ["Борис Б"],
    "Глеб Г": ["Борис Б"], "Дана Д": ["Вера В"], "Ерлан Е": ["Вера В"],
}


# ------------------------------------------------------------ рекомендации
def test_recommendations_point_at_the_isolated_student_and_suggest_a_partner():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    _survey(client, token, cid, st, "Осенний", ISOLATED_PLAN,
            alone=["Алина А"])

    r = client.get("/api/prevention/classes/%d/recommendations" % cid, headers=auth(token))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["available"] is True
    codes = [i["code"] for i in d["items"]]
    assert "isolated" in codes, "изолят — самая срочная рекомендация"
    assert codes[0] == "isolated", "она должна идти первой"

    iso = [i for i in d["items"] if i["code"] == "isolated"][0]
    assert st["Алина А"]["id"] in iso["student_ids"]
    pair = [p for p in iso["pairs"] if p["student_id"] == st["Алина А"]["id"]][0]
    # Алина выбрала Бориса — его и предлагаем в пару: одностороннюю симпатию
    # проще превратить во взаимную, чем строить связь с нуля.
    assert pair["partner_name"] == "Борис Б"


def test_alone_recommendation_is_class_wide_and_names_nobody():
    """Занятие по ярлыку «одиночки» адресуется классу: указать на ребёнка
    пальцем значит усилить изоляцию, а не снять её."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    _survey(client, token, cid, st, "Осенний", ISOLATED_PLAN, alone=["Алина А"])

    d = client.get("/api/prevention/classes/%d/recommendations" % cid, headers=auth(token)).json()
    alone = [i for i in d["items"] if i["code"] == "alone_marked"]
    assert alone, "устойчивые номинации «часто один» должны давать рекомендацию"
    assert alone[0]["target"] == "class"
    assert alone[0]["student_ids"] == [], "ребёнок в мероприятии не называется"
    assert "имя ребёнка не называется" in alone[0]["plan"].lower()


def test_no_recommendations_from_an_unreliable_survey():
    """По срезу, где ответила половина класса, советовать «включить изолята
    в группу» значит отправить психолога к ребёнку без проблемы."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid, "Мало ответов")
    code = tickets(client, token, svid)
    submit(client, svid, code["Борис Б"], cinema=[st["Вера В"]["id"]])
    close_survey(client, token, svid)

    d = client.get("/api/prevention/classes/%d/recommendations" % cid, headers=auth(token)).json()
    assert d["available"] is False
    assert d["items"] == []
    assert "70" in d["reason"]


def test_recommendations_without_any_survey_explain_what_to_do():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    d = client.get("/api/prevention/classes/%d/recommendations" % cid, headers=auth(token)).json()
    assert d["available"] is False
    assert d["survey"] is None
    assert "закрыт" in d["reason"].lower()


def test_no_recommendations_for_a_class_too_small_for_sociometry():
    """«Низкая плотность» в классе из трёх человек — арифметика, а не проблема.
    Предлагать по ней тренинг на сплочение было бы шумом."""
    client = fresh_client()
    token = register(client)
    small = ["Алина А", "Борис Б", "Вера В"]
    cid, st = make_class(client, token, small)
    _survey(client, token, cid, st, "Срез", {"Алина А": ["Борис Б"], "Борис Б": ["Алина А"],
                                             "Вера В": ["Алина А"]})

    d = client.get("/api/prevention/classes/%d/recommendations" % cid, headers=auth(token)).json()
    assert d["available"] is False
    assert d["items"] == []
    assert "мало" in d["reason"].lower()


def test_no_recommendations_when_nobody_chose_anybody():
    """Опрос прошли, но ни одного положительного выбора — рекомендации строить
    не по чему, и пять пунктов сразу были бы шумом."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    # Все отвечают, но никого не выбирают.
    _survey(client, token, cid, st, "Пустой", {})

    d = client.get("/api/prevention/classes/%d/recommendations" % cid, headers=auth(token)).json()
    assert d["available"] is False
    assert "выбор" in d["reason"].lower()


def test_playbook_is_available_without_any_data():
    client = fresh_client()
    token = register(client)
    d = client.get("/api/prevention/playbook", headers=auth(token)).json()
    assert len(d["items"]) >= 5
    assert all(i["title"] and i["plan"] and i["goal"] for i in d["items"])


# --------------------------------------------------- план и проведение
def test_activity_lifecycle_plan_conduct_and_coverage():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)

    created = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Тренинг на сплочение", "kind": "training", "target": "class",
        "goal": "Увеличить число связей", "planned_on": "2026-02-10", "duration_min": 45,
    })
    assert created.status_code == 200, created.text
    a = created.json()["activity"]
    assert a["status"] == "planned"
    assert a["kind_title"] == "Тренинг / групповое занятие"
    # Для мероприятия на весь класс состав не фиксируется на этапе плана.
    assert a["planned_count"] == 0

    done = client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token),
                       json={"conducted_on": "2026-02-11", "outcome": "Прошло активно", "effectiveness": 4})
    assert done.status_code == 200, done.text
    d = done.json()["activity"]
    assert d["status"] == "done"
    assert d["effectiveness"] == 4
    # Охват подставился на момент проведения — весь активный класс.
    assert d["attended_count"] == len(NAMES)


def test_completing_counts_only_those_who_actually_came():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Занятие", "kind": "training", "target": "class",
    }).json()["activity"]

    present = [st["Алина А"]["id"], st["Борис Б"]["id"]]
    d = client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token),
                    json={"attended_ids": present}).json()["activity"]
    assert d["attended_count"] == 2
    assert sorted(p["student_id"] for p in d["participants"]) == sorted(present)


def test_group_activity_keeps_its_roster():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    picked = [st["Алина А"]["id"], st["Вера В"]["id"]]
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Группа поддержки", "kind": "training", "target": "group",
        "student_ids": picked,
    }).json()["activity"]
    assert a["planned_count"] == 2
    assert sorted(p["student_id"] for p in a["participants"]) == sorted(picked)


def test_activity_rejects_unknown_kind_and_foreign_students():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    other_cid, other_st = make_class(client, token, ["Чужой Ч"], class_name="9 «В»")

    bad = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token),
                      json={"title": "X", "kind": "магия", "target": "class"})
    assert bad.status_code == 400

    # Ученик чужого класса молча отбрасывается, а не попадает в охват.
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Группа", "kind": "training", "target": "group",
        "student_ids": [st["Алина А"]["id"], other_st["Чужой Ч"]["id"]],
    }).json()["activity"]
    assert a["planned_count"] == 1
    assert a["participants"][0]["student_id"] == st["Алина А"]["id"]


def test_adults_activity_counts_participants_as_a_number():
    """Родителей поимённо мы не заводим — у нас нет и не должно быть их данных."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Родительское собрание", "kind": "parents", "target": "adults",
    }).json()["activity"]

    d = client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token),
                    json={"adults_count": 18}).json()["activity"]
    assert d["adults_count"] == 18
    assert d["attended_count"] == 0


def test_schedule_marks_overdue_and_counts_coverage():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)

    client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Просроченное", "kind": "training", "target": "class", "planned_on": "2020-01-01",
    })
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Проведённое", "kind": "class_hour", "target": "class",
    }).json()["activity"]
    client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token), json={})

    d = client.get("/api/prevention/schedule", headers=auth(token)).json()
    assert d["totals"]["planned"] == 1
    assert d["totals"]["overdue"] == 1
    assert d["totals"]["done"] == 1
    assert d["totals"]["students_covered"] == len(NAMES)
    assert [x["title"] for x in d["activities"] if x["overdue"]] == ["Просроченное"]


def test_conducted_activity_cannot_be_cancelled():
    """Занятие состоялось и посчитано в отчётности перед завучем. «Отменить»
    его задним числом значило бы стереть факт выполненной работы."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token),
                    json={"title": "Занятие", "kind": "training", "target": "class"}).json()["activity"]
    client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token), json={})

    r = client.post("/api/prevention/activities/%d/cancel" % a["id"], headers=auth(token))
    assert r.status_code == 409
    sched = client.get("/api/prevention/schedule", headers=auth(token)).json()
    assert sched["totals"]["done"] == 1, "факт проведения должен сохраниться"

    # Ошибочную запись можно удалить — это явное действие, а не «отмена».
    assert client.delete("/api/prevention/activities/%d" % a["id"], headers=auth(token)).status_code == 200


def test_cancelled_activity_leaves_the_plan():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token),
                    json={"title": "Отменим", "kind": "training", "target": "class"}).json()["activity"]
    client.post("/api/prevention/activities/%d/cancel" % a["id"], headers=auth(token))
    d = client.get("/api/prevention/schedule", headers=auth(token)).json()
    assert d["totals"]["planned"] == 0
    assert [x["status"] for x in d["activities"]] == ["cancelled"]


# ------------------------------------------------------- оценка эффекта
def test_effect_compares_covered_students_against_the_rest_of_class():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)

    before = _survey(client, token, cid, st, "Осенний", ISOLATED_PLAN, alone=["Алина А"])

    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Включение в группу", "kind": "training", "target": "group",
        "student_ids": [st["Алина А"]["id"]], "source_survey_id": before,
        "planned_on": "2026-01-10",
    }).json()["activity"]
    client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token),
                json={"conducted_on": "2026-01-10"})

    # После занятия Алину начинают выбирать.
    _survey(client, token, cid, st, "Зимний", {
        "Алина А": ["Борис Б"], "Борис Б": ["Алина А"], "Вера В": ["Алина А"],
        "Глеб Г": ["Алина А"], "Дана Д": ["Вера В"], "Ерлан Е": ["Вера В"],
    })

    d = client.get("/api/prevention/activities/%d/effect" % a["id"], headers=auth(token)).json()
    assert d["available"] is True, d.get("reason")
    assert d["covered"]["students"] == 1
    assert d["covered"]["avg_in_delta"] > 0
    assert d["covered"]["left_isolation"] == 1
    # Контроль: остальной класс считается отдельно, иначе рост нельзя было бы
    # отличить от общего изменения в классе.
    assert d["rest_of_class"]["students"] == len(NAMES) - 1
    assert "наблюдение" in d["disclaimer"].lower()
    assert d["details"][0]["full_name"] == "Алина А"


def test_effect_needs_a_survey_after_the_activity():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    _survey(client, token, cid, st, "Осенний", ISOLATED_PLAN)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token),
                    json={"title": "Занятие", "kind": "training", "target": "class"}).json()["activity"]
    client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token), json={})

    d = client.get("/api/prevention/activities/%d/effect" % a["id"], headers=auth(token)).json()
    assert d["available"] is False
    assert "срез" in d["reason"].lower()


def test_effect_is_not_available_before_the_activity_is_conducted():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token),
                    json={"title": "Ещё не было", "kind": "training", "target": "class"}).json()["activity"]
    d = client.get("/api/prevention/activities/%d/effect" % a["id"], headers=auth(token)).json()
    assert d["available"] is False


# ------------------------------------------------------- доступ и роли
def test_prevention_is_isolated_between_psychologists():
    client = fresh_client()
    token_a = register(client, "a@school.kz")
    cid, st = make_class(client, token_a, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token_a),
                    json={"title": "Моё", "kind": "training", "target": "class"}).json()["activity"]

    token_b = register(client, "b@school.kz")
    assert client.get("/api/prevention/classes/%d/activities" % cid, headers=auth(token_b)).status_code == 404
    assert client.get("/api/prevention/classes/%d/recommendations" % cid, headers=auth(token_b)).status_code == 404
    assert client.put("/api/prevention/activities/%d" % a["id"], headers=auth(token_b),
                      json={"title": "Чужое"}).status_code == 404
    assert client.delete("/api/prevention/activities/%d" % a["id"], headers=auth(token_b)).status_code == 404
    # В чужом расписании мероприятия не видно.
    assert client.get("/api/prevention/schedule", headers=auth(token_b)).json()["activities"] == []


def test_head_sees_prevention_totals_but_not_student_names():
    """Завучу профилактика нужна как отчётность: сколько проведено и где её
    нет. Поимённого охвата он по-прежнему не видит."""
    client = fresh_client()
    school = make_school(client)
    psy = register_in_school(client, school["invite_code"], "psy@school.kz")
    cid, st = make_class(client, psy, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(psy),
                    json={"title": "Тренинг", "kind": "training", "target": "class"}).json()["activity"]
    client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(psy), json={})

    head = make_head(client, school["invite_code"])
    assert client.get("/api/prevention/schedule", headers=auth(head)).status_code == 403

    summary = client.get("/api/school/summary", headers=auth(head))
    assert summary.status_code == 200
    data = summary.json()
    assert data["totals"]["activities_done"] == 1
    assert data["classes"][0]["activities_done"] == 1
    blob = str(data)
    for name in NAMES:
        assert name not in blob


def test_school_summary_flags_alerts_without_prevention():
    """Есть сигналы, а профилактика не запланирована — главный управленческий
    вопрос завуча к психологу."""
    client = fresh_client()
    school = make_school(client)
    psy = register_in_school(client, school["invite_code"], "psy@school.kz")
    cid, st = make_class(client, psy, NAMES)
    _survey(client, psy, cid, st, "Осенний", ISOLATED_PLAN, alone=["Алина А"])

    head = make_head(client, school["invite_code"])
    totals = client.get("/api/school/summary", headers=auth(head)).json()["totals"]
    assert totals["open_alerts"] > 0
    assert totals["alerts_without_activities"] == 1

    client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(psy),
                json={"title": "Реакция на сигнал", "kind": "training", "target": "class"})
    totals = client.get("/api/school/summary", headers=auth(head)).json()["totals"]
    assert totals["alerts_without_activities"] == 0


def test_conducting_an_activity_is_written_to_the_audit_log():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    a = client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token),
                    json={"title": "Занятие", "kind": "training", "target": "class"}).json()["activity"]
    client.post("/api/prevention/activities/%d/complete" % a["id"], headers=auth(token), json={})

    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter(AuditLog.action == "activity_done").all()
        assert len(rows) == 1
        assert rows[0].target_id == a["id"]
    finally:
        db.close()


def test_deleting_a_class_removes_its_activities():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    client.post("/api/prevention/classes/%d/activities" % cid, headers=auth(token), json={
        "title": "Группа", "kind": "training", "target": "group",
        "student_ids": [st["Алина А"]["id"]],
    })

    db = SessionLocal()
    try:
        assert db.query(Activity).count() == 1
        assert db.query(ActivityParticipant).count() == 1
    finally:
        db.close()

    client.delete("/api/classes/%d" % cid, headers=auth(token))

    db = SessionLocal()
    try:
        assert db.query(Activity).count() == 0
        assert db.query(ActivityParticipant).count() == 0
    finally:
        db.close()
