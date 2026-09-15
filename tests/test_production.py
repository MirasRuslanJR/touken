"""
Тесты продуктовых механизмов: согласия, одноразовые билеты, серверные
оповещения, снапшоты и срок хранения данных.
"""
from datetime import date, timedelta

from app.database import SessionLocal
from app.models import (
    Alert,
    AuditLog,
    Choice,
    Consent,
    SchoolClass,
    Student,
    SurveyResponse,
    SurveySnapshot,
)
from app.retention import purge_class
from tests.helpers import (
    auth,
    close_survey,
    fresh_client,
    grant_consent,
    make_class,
    make_school,
    open_survey,
    register,
    register_in_school,
    submit,
    tickets,
)

NAMES = ["Алина А", "Борис Б", "Вера В", "Глеб Г", "Дана Д"]


# ------------------------------------------------------------- согласия
def test_survey_cannot_start_without_any_consent():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES, consent=False)
    r = client.post("/api/classes/%d/surveys" % cid, json={"title": "Срез"}, headers=auth(token))
    assert r.status_code == 409
    assert "согласие" in r.json()["detail"].lower()


def test_student_without_consent_is_excluded_from_the_survey():
    """Не «участвует, но помечен», а именно не участвует: нет билета и его
    нет в списке для выбора у одноклассников."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES, consent=False)
    for name in ("Борис Б", "Вера В", "Глеб Г", "Дана Д"):
        grant_consent(client, token, st[name]["id"])
    # Алине согласие не оформлено.

    r = client.post("/api/classes/%d/surveys" % cid, json={"title": "Срез"}, headers=auth(token))
    assert r.status_code == 200, r.text
    svid = r.json()["survey"]["id"]
    assert [e["full_name"] for e in r.json()["excluded"]] == ["Алина А"]

    codes = tickets(client, token, svid)
    assert "Алина А" not in codes

    started = client.post("/api/public/surveys/%d/start" % svid, json={"code": codes["Борис Б"]})
    roster = [x["full_name"] for x in started.json()["roster"]]
    assert "Алина А" not in roster

    # И выбрать её нельзя, даже зная id.
    submit(client, svid, codes["Борис Б"], cinema=[st["Алина А"]["id"], st["Вера В"]["id"]])
    a = client.get("/api/surveys/%d/analytics" % svid, headers=auth(token)).json()
    assert a["per_student"][str(st["Алина А"]["id"])]["in_degree"] == 0
    assert a["per_student"][str(st["Вера В"]["id"])]["in_degree"] == 1


def test_revoking_consent_removes_student_from_next_survey():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    card = client.get("/api/students/%d/card" % st["Алина А"]["id"], headers=auth(token)).json()
    consent_id = card["consents"][0]["id"]

    assert client.delete("/api/consents/%d" % consent_id, headers=auth(token)).status_code == 200
    r = client.post("/api/classes/%d/surveys" % cid, json={"title": "Новый срез"}, headers=auth(token))
    assert [e["full_name"] for e in r.json()["excluded"]] == ["Алина А"]


# --------------------------------------------------------------- билеты
def test_ticket_is_valid_only_inside_its_own_survey():
    """Раньше кодом служил постоянный Student.code и работал во всех срезах."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    first = open_survey(client, token, cid, "Первый")
    code_first = tickets(client, token, first)["Борис Б"]
    close_survey(client, token, first)

    second = open_survey(client, token, cid, "Второй")
    # Код от прошлого среза во втором не действует.
    assert submit(client, second, code_first, cinema=[st["Вера В"]["id"]]).status_code == 404
    # Постоянный код ученика тоже не является пропуском.
    assert submit(client, second, st["Борис Б"]["code"], cinema=[st["Вера В"]["id"]]).status_code == 404


def test_reissue_unblocks_a_student_and_drops_the_fake_answers():
    """Одноклассник подсмотрел код и ответил за другого. Раньше это блокировало
    ученика навсегда (409) и оставляло чужие ответы в графе."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)

    # Чужие ответы от имени Алины.
    submit(client, svid, code["Алина А"], cinema=[st["Глеб Г"]["id"]])
    a = client.get("/api/surveys/%d/analytics" % svid, headers=auth(token)).json()
    assert a["per_student"][str(st["Глеб Г"]["id"])]["in_degree"] == 1

    r = client.post("/api/surveys/%d/students/%d/reissue" % (svid, st["Алина А"]["id"]), headers=auth(token))
    assert r.status_code == 200, r.text
    new_code = r.json()["code"]
    assert new_code != code["Алина А"]

    # Подложные выборы удалены, и Алина снова может пройти опрос.
    a = client.get("/api/surveys/%d/analytics" % svid, headers=auth(token)).json()
    assert a["per_student"][str(st["Глеб Г"]["id"])]["in_degree"] == 0
    assert submit(client, svid, new_code, cinema=[st["Вера В"]["id"]]).status_code == 200
    assert submit(client, svid, code["Алина А"], cinema=[st["Вера В"]["id"]]).status_code == 404


# ----------------------------------------------------------- оповещения
def _full_survey(client, token, cid, st, title, chooser_map, alone=()):
    """Проводит срез: все ученики отвечают по схеме chooser_map."""
    svid = open_survey(client, token, cid, title)
    code = tickets(client, token, svid)
    for name, targets in chooser_map.items():
        submit(client, svid, code[name],
               cinema=[st[t]["id"] for t in targets],
               alone=[st[t]["id"] for t in alone])
    close_survey(client, token, svid)
    return svid


def test_alerts_are_created_on_close_and_land_in_the_inbox():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)

    # Первый срез: Борис популярен.
    _full_survey(client, token, cid, st, "Первый", {
        "Алина А": ["Борис Б"], "Борис Б": ["Вера В"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Борис Б"], "Дана Д": ["Борис Б"],
    })
    # Второй срез: Бориса не выбирает никто — он стал изолятом.
    _full_survey(client, token, cid, st, "Второй", {
        "Алина А": ["Вера В"], "Борис Б": ["Вера В"], "Вера В": ["Алина А"],
        "Глеб Г": ["Вера В"], "Дана Д": ["Алина А"],
    })

    inbox = client.get("/api/alerts", headers=auth(token))
    assert inbox.status_code == 200, inbox.text
    data = inbox.json()
    boris = [a for a in data["alerts"] if a["student_name"] == "Борис Б"]
    assert boris, "по Борису должно быть оповещение"
    assert boris[0]["kind"] in ("isolate", "drop")
    assert boris[0]["from_value"] == 4 and boris[0]["to_value"] == 0
    assert data["unseen"] >= 1

    aid = boris[0]["id"]
    assert client.post("/api/alerts/%d/resolve" % aid, headers=auth(token)).status_code == 200
    assert not [a for a in client.get("/api/alerts", headers=auth(token)).json()["alerts"] if a["id"] == aid]
    assert [a for a in client.get("/api/alerts?resolved=true", headers=auth(token)).json()["alerts"] if a["id"] == aid]


def test_no_alerts_from_a_survey_with_low_turnout():
    """Сравнивать срезы с низкой явкой бессмысленно: «падение связей» тогда
    означает лишь то, что ответило меньше детей."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)

    _full_survey(client, token, cid, st, "Первый", {
        "Алина А": ["Борис Б"], "Борис Б": ["Вера В"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Борис Б"], "Дана Д": ["Борис Б"],
    })
    # Во втором срезе отвечает только один из пяти.
    svid = open_survey(client, token, cid, "Второй")
    code = tickets(client, token, svid)
    submit(client, svid, code["Алина А"], cinema=[st["Вера В"]["id"]])
    close_survey(client, token, svid)

    alerts = client.get("/api/alerts", headers=auth(token)).json()["alerts"]
    assert not [a for a in alerts if a["survey_id"] == svid], "на недостоверном срезе оповещений быть не должно"


def test_alerts_are_not_duplicated_on_reclose():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = _full_survey(client, token, cid, st, "Первый", {
        "Алина А": ["Борис Б"], "Борис Б": ["Вера В"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Борис Б"], "Дана Д": ["Борис Б"],
    })
    before = len(client.get("/api/alerts", headers=auth(token)).json()["alerts"])
    client.put("/api/surveys/%d" % svid, json={"is_open": True}, headers=auth(token))
    close_survey(client, token, svid)
    after = len(client.get("/api/alerts", headers=auth(token)).json()["alerts"])
    assert before == after


# ------------------------------------------------------------ снапшоты
def test_closing_a_survey_stores_a_snapshot_and_reopening_clears_it():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    submit(client, svid, tickets(client, token, svid)["Борис Б"], cinema=[st["Вера В"]["id"]])

    db = SessionLocal()
    try:
        assert db.query(SurveySnapshot).filter(SurveySnapshot.survey_id == svid).count() == 0
        close_survey(client, token, svid)
        assert db.query(SurveySnapshot).filter(SurveySnapshot.survey_id == svid).count() == 1
        client.put("/api/surveys/%d" % svid, json={"is_open": True}, headers=auth(token))
        db.expire_all()
        assert db.query(SurveySnapshot).filter(SurveySnapshot.survey_id == svid).count() == 0
    finally:
        db.close()


# -------------------------------------------------------------- ретеншн
def test_retention_purges_raw_answers_but_keeps_the_dynamics():
    """Сырые ответы удаляются по сроку хранения, динамика класса остаётся."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    _full_survey(client, token, cid, st, "Первый", {
        "Алина А": ["Борис Б"], "Борис Б": ["Вера В"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Борис Б"], "Дана Д": ["Борис Б"],
    })

    before = client.get("/api/students/%d/card" % st["Борис Б"]["id"], headers=auth(token)).json()
    assert before["dynamics"][-1]["in_degree"] == 4

    db = SessionLocal()
    try:
        cls = db.get(SchoolClass, cid)
        cls.retention_until = date.today() - timedelta(days=1)
        purge_class(db, cls)
        db.commit()
        assert db.query(Choice).count() == 0, "сырые выборы должны быть удалены"
        assert db.query(SurveyResponse).count() == 0
    finally:
        db.close()

    after = client.get("/api/students/%d/card" % st["Борис Б"]["id"], headers=auth(token)).json()
    assert after["dynamics"][-1]["in_degree"] == 4, "динамика должна пережить удаление сырых данных"
    assert after["dynamics"][-1]["archived"] is True


def test_default_retention_is_set_on_new_classes():
    client = fresh_client()
    token = register(client)
    r = client.post("/api/classes", json={"name": "7 «В»"}, headers=auth(token))
    assert r.json()["class"]["retention_until"] is not None, "политика хранения должна проставляться сразу"


# --------------------------------------------------------------- аудит
def test_opening_a_student_card_is_written_to_the_audit_log():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    client.get("/api/students/%d/card" % st["Алина А"]["id"], headers=auth(token))

    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter(AuditLog.action == "view_student_card").all()
        assert len(rows) == 1
        assert rows[0].target_id == st["Алина А"]["id"]
        assert rows[0].target_type == "student"
    finally:
        db.close()


# ----------------------------------------------------------- домашний экран
def test_overview_ranks_classes_by_attention_needed():
    client = fresh_client()
    token = register(client)
    quiet_cid, quiet_st = make_class(client, token, NAMES, class_name="Спокойный")
    _full_survey(client, token, quiet_cid, quiet_st, "Срез", {
        "Алина А": ["Борис Б"], "Борис Б": ["Алина А"], "Вера В": ["Глеб Г"],
        "Глеб Г": ["Вера В"], "Дана Д": ["Алина А", "Вера В"],
    })

    risky_cid, risky_st = make_class(client, token, NAMES, class_name="Тревожный")
    _full_survey(client, token, risky_cid, risky_st, "Первый", {
        "Алина А": ["Борис Б"], "Борис Б": ["Вера В"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Борис Б"], "Дана Д": ["Борис Б"],
    })
    _full_survey(client, token, risky_cid, risky_st, "Второй", {
        "Алина А": ["Вера В"], "Борис Б": ["Вера В"], "Вера В": ["Алина А"],
        "Глеб Г": ["Вера В"], "Дана Д": ["Алина А"],
    })

    data = client.get("/api/overview", headers=auth(token)).json()
    assert data["classes"][0]["class"]["name"] == "Тревожный", "класс с оповещениями должен быть первым"
    assert data["classes"][0]["open_alerts"] >= 1
    assert data["classes"][0]["wellbeing_index"] is not None


# ------------------------------------------------- импорт списка учеников
def test_import_parses_csv_on_the_server():
    """Разбор файла на сервере: раньше это делала библиотека с CDN, и в
    школьной сети без cdnjs импорт не работал вовсе."""
    client = fresh_client()
    token = register(client)
    r = client.post("/api/classes", json={"name": "5 «А»"}, headers=auth(token))
    cid = r.json()["class"]["id"]

    csv_bytes = "ФИО;Пол;Дата рождения\nАлина Смирнова;ж;2011-05-14\nБорис Кузнецов;м;12.03.2011\n".encode("utf-8")
    up = client.post(
        "/api/classes/%d/students/import" % cid,
        files={"file": ("spisok.csv", csv_bytes, "text/csv")},
        headers=auth(token),
    )
    assert up.status_code == 200, up.text
    students = up.json()["students"]
    assert [s["full_name"] for s in students] == ["Алина Смирнова", "Борис Кузнецов"]
    assert students[0]["gender"] == "f" and students[1]["gender"] == "m"
    # Дата в обоих распространённых форматах приводится к ISO.
    assert students[0]["birth_date"] == "2011-05-14"
    assert students[1]["birth_date"] == "2011-03-12"


def test_import_reads_cp1251_and_headerless_files():
    """Школьные выгрузки приходят и в cp1251, и вовсе без заголовков."""
    client = fresh_client()
    token = register(client)
    cid = client.post("/api/classes", json={"name": "5 «Б»"}, headers=auth(token)).json()["class"]["id"]

    raw = "Вера Попова,ж\nГлеб Соколов,м\n".encode("cp1251")
    up = client.post(
        "/api/classes/%d/students/import" % cid,
        files={"file": ("list.csv", raw, "text/csv")},
        headers=auth(token),
    )
    assert up.status_code == 200, up.text
    assert [s["full_name"] for s in up.json()["students"]] == ["Вера Попова", "Глеб Соколов"]


def test_import_of_an_empty_file_is_rejected():
    client = fresh_client()
    token = register(client)
    cid = client.post("/api/classes", json={"name": "5 «В»"}, headers=auth(token)).json()["class"]["id"]
    up = client.post(
        "/api/classes/%d/students/import" % cid,
        files={"file": ("empty.csv", b"\n\n", "text/csv")},
        headers=auth(token),
    )
    assert up.status_code == 400


# ------------------------------------------------ согласия пачкой и архив
def test_bulk_consent_marks_the_whole_class_at_once():
    """Бланки приносят стопкой с родительского собрания — отмечать по одному
    никто не станет."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES, consent=False)

    r = client.post("/api/classes/%d/consents/bulk" % cid, headers=auth(token),
                    json={"obtained_on": "2025-09-05", "document_ref": "собрание 05.09"})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == len(NAMES)
    assert r.json()["consent"]["missing"] == []

    # Повторный вызов ничего не дублирует.
    again = client.post("/api/classes/%d/consents/bulk" % cid, headers=auth(token), json={})
    assert again.json()["count"] == 0

    svid = open_survey(client, token, cid)
    assert len(tickets(client, token, svid)) == len(NAMES)


def test_bulk_consent_respects_the_selected_subset():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES, consent=False)
    picked = [st["Алина А"]["id"], st["Борис Б"]["id"]]

    r = client.post("/api/classes/%d/consents/bulk" % cid, headers=auth(token),
                    json={"student_ids": picked})
    assert r.json()["count"] == 2
    assert len(r.json()["consent"]["missing"]) == len(NAMES) - 2


def test_archived_student_leaves_the_survey_but_keeps_history():
    """Выбывший ученик не участвует в новых срезах, но его история остаётся:
    удаление снесло бы и метрики класса за прошлые периоды."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    first = _full_survey(client, token, cid, st, "Первый", {
        "Алина А": ["Борис Б"], "Борис Б": ["Алина А"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Вера В"], "Дана Д": ["Вера В"],
    })

    boris = st["Борис Б"]
    client.put("/api/students/%d" % boris["id"], headers=auth(token),
               json={"full_name": boris["full_name"], "is_active": False})

    second = open_survey(client, token, cid, "Второй")
    assert "Борис Б" not in tickets(client, token, second)

    card = client.get("/api/students/%d/card" % boris["id"], headers=auth(token)).json()
    assert card["student"]["is_active"] is False
    first_row = [d for d in card["dynamics"] if d["survey_id"] == first][0]
    assert first_row["in_degree"] == 2, "история прошлого среза должна сохраниться"


# -------------------------------------------- срок хранения в настройках
def test_retention_can_be_shortened_but_not_extended():
    client = fresh_client()
    token = register(client)
    cid, _ = make_class(client, token, NAMES)

    soon = (date.today() + timedelta(days=30)).isoformat()
    r = client.put("/api/classes/%d/settings" % cid, headers=auth(token), json={"retention_until": soon})
    assert r.status_code == 200, r.text
    assert r.json()["class"]["retention_until"] == soon

    far = (date.today() + timedelta(days=365 * 5)).isoformat()
    bad = client.put("/api/classes/%d/settings" % cid, headers=auth(token), json={"retention_until": far})
    assert bad.status_code == 409, "продлевать дальше политики школы нельзя"


def test_closed_survey_cannot_be_altered_through_tickets():
    """Закрытый срез — зафиксированный результат: по нему уже посчитан
    снапшот, созданы оповещения и, возможно, запланирована профилактика.
    Перевыпуск кода удалял бы ответы задним числом, не пересчитывая снапшот."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = _full_survey(client, token, cid, st, "Осенний", {
        "Алина А": ["Борис Б"], "Борис Б": ["Алина А"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Вера В"], "Дана Д": ["Вера В"],
    })

    reissue = client.post("/api/surveys/%d/students/%d/reissue" % (svid, st["Алина А"]["id"]),
                          headers=auth(token))
    assert reissue.status_code == 409
    refresh = client.post("/api/surveys/%d/tickets/refresh" % svid, headers=auth(token))
    assert refresh.status_code == 409

    # Данные среза не тронуты.
    a = client.get("/api/surveys/%d/analytics" % svid, headers=auth(token)).json()
    assert a["per_student"][str(st["Борис Б"]["id"])]["in_degree"] == 2

    # После переоткрытия исправить можно.
    client.put("/api/surveys/%d" % svid, json={"is_open": True}, headers=auth(token))
    assert client.post("/api/surveys/%d/students/%d/reissue" % (svid, st["Алина А"]["id"]),
                       headers=auth(token)).status_code == 200


# ------------------------------------------------- целостность при удалении
def test_deleting_a_class_removes_its_students_and_answers():
    """Каскад должен реально отрабатывать, а не оставлять сирот.

    На SQLite внешние ключи по умолчанию выключены, и удаление класса
    оставляло учеников и срезы висеть с несуществующим class_id. Поскольку
    SQLite переиспользует освободившиеся id, следующий созданный класс
    «наследовал» чужих учеников — демо-класс из 14 человек показывал 28.
    """
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    _full_survey(client, token, cid, st, "Срез", {
        "Алина А": ["Борис Б"], "Борис Б": ["Алина А"], "Вера В": ["Борис Б"],
        "Глеб Г": ["Вера В"], "Дана Д": ["Вера В"],
    })

    db = SessionLocal()
    try:
        assert db.query(Student).count() == len(NAMES)
        assert db.query(Choice).count() > 0
    finally:
        db.close()

    assert client.delete("/api/classes/%d" % cid, headers=auth(token)).status_code == 200

    db = SessionLocal()
    try:
        assert db.query(Student).count() == 0, "ученики удалённого класса не должны оставаться"
        assert db.query(Choice).count() == 0
        assert db.query(SurveyResponse).count() == 0
        assert db.query(Consent).count() == 0
    finally:
        db.close()

    # Новый класс с тем же именем начинается пустым, а не «наследует» прежних.
    new_cid, _ = make_class(client, token, ["Один Ученик"])
    fresh = client.get("/api/classes/%d" % new_cid, headers=auth(token)).json()
    assert len(fresh["students"]) == 1


# --------------------------------------------------------- журнал доступа
def test_admin_can_read_the_audit_log_of_own_school_only():
    client = fresh_client()
    school = make_school(client, "Школа А")
    admin = register_in_school(client, school["invite_code"], "admin@a.kz")
    cid, st = make_class(client, admin, NAMES)
    client.get("/api/students/%d/card" % st["Алина А"]["id"], headers=auth(admin))

    log = client.get("/api/audit", headers=auth(admin))
    assert log.status_code == 200, log.text
    entries = log.json()["entries"]
    assert any(e["action"] == "view_student_card" and e["target_name"] == "Алина А" for e in entries)
    assert entries[0]["action_title"], "действие должно быть подписано по-человечески"

    # Психолог из другой школы журнал не видит.
    other = make_school(client, "Школа Б")
    outsider = register_in_school(client, other["invite_code"], "admin@b.kz")
    theirs = client.get("/api/audit", headers=auth(outsider)).json()["entries"]
    assert not [e for e in theirs if e["target_name"] == "Алина А"]


def test_plain_psychologist_cannot_read_the_audit_log():
    client = fresh_client()
    school = make_school(client)
    register_in_school(client, school["invite_code"], "admin@school.kz")   # первый = админ
    psy = register_in_school(client, school["invite_code"], "psy@school.kz")
    assert client.get("/api/audit", headers=auth(psy)).status_code == 403


# ------------------------------------------------- сброс пароля админом
def test_admin_resets_password_and_kills_existing_sessions():
    client = fresh_client()
    school = make_school(client)
    admin = register_in_school(client, school["invite_code"], "admin@school.kz")
    psy = register_in_school(client, school["invite_code"], "psy@school.kz")
    assert client.get("/api/auth/me", headers=auth(psy)).status_code == 200

    staff = client.get("/api/auth/staff", headers=auth(admin)).json()["staff"]
    target = [u for u in staff if u["email"] == "psy@school.kz"][0]

    r = client.post("/api/auth/staff/%d/reset-password" % target["id"], headers=auth(admin))
    assert r.status_code == 200, r.text
    temp = r.json()["temporary_password"]

    # Старая сессия и старый пароль больше не работают, временный — работает.
    assert client.get("/api/auth/me", headers=auth(psy)).status_code == 401
    assert client.post("/api/auth/login", json={"email": "psy@school.kz", "password": "secret12345"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "psy@school.kz", "password": temp}).status_code == 200


def test_admin_cannot_reset_own_password_through_staff_list():
    client = fresh_client()
    school = make_school(client)
    admin = register_in_school(client, school["invite_code"], "admin@school.kz")
    me = client.get("/api/auth/me", headers=auth(admin)).json()["user"]
    r = client.post("/api/auth/staff/%d/reset-password" % me["id"], headers=auth(admin))
    assert r.status_code == 400


# --------------------------------------------------- казахский язык опроса
def test_survey_questions_are_returned_in_both_languages():
    """Ученик переключает язык прямо на странице опроса, поэтому оба текста
    приходят сразу — лишний запрос посреди прохождения не нужен."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)["Борис Б"]

    started = client.post("/api/public/surveys/%d/start" % svid, json={"code": code}).json()
    for q in started["questions"]:
        assert q["text"] and q["text_kk"], "у каждого вопроса должен быть текст на обоих языках"
    assert started["questions"][0]["text_kk"] != started["questions"][0]["text"]


def test_custom_kazakh_wording_is_saved_per_survey():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    r = client.post("/api/classes/%d/surveys" % cid, headers=auth(token), json={
        "title": "Осенний срез",
        "questions": [{"key": "cinema", "text": "С кем в кино?", "text_kk": "Киноға кіммен?"}],
    })
    assert r.status_code == 200, r.text
    qs = {q["key"]: q for q in r.json()["survey"]["questions"]}
    assert qs["cinema"]["text"] == "С кем в кино?"
    assert qs["cinema"]["text_kk"] == "Киноға кіммен?"
    # Незаданный вопрос остаётся с формулировкой по умолчанию на обоих языках.
    assert qs["alone"]["text_kk"]
