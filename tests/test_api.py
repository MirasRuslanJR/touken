"""
Тесты API: изоляция данных между психологами, правила прохождения опроса,
защита от перебора и серверный выход.
"""
from app import ratelimit
from tests.helpers import (
    auth,
    close_survey,
    fresh_client,
    make_class,
    open_survey,
    register,
    submit,
    tickets,
)

NAMES = ["Алина А", "Борис Б", "Вера В", "Глеб Г"]


def test_other_psychologist_cannot_open_someone_elses_class():
    """Изоляция данных: подстановка чужого id в URL даёт 404, а не чужой класс."""
    client = fresh_client()
    token_a = register(client, "a@school.kz")
    cid, st = make_class(client, token_a, NAMES)
    svid = open_survey(client, token_a, cid)

    token_b = register(client, "b@school.kz")
    assert client.get("/api/classes/%d" % cid, headers=auth(token_b)).status_code == 404
    assert client.get("/api/surveys/%d/tickets" % svid, headers=auth(token_b)).status_code == 404
    assert client.get("/api/surveys/%d/analytics" % svid, headers=auth(token_b)).status_code == 404
    assert client.get("/api/students/%d/card" % st["Алина А"]["id"], headers=auth(token_b)).status_code == 404
    assert client.get("/api/surveys/%d/export.xlsx" % svid, headers=auth(token_b)).status_code == 404
    # Свой класс при этом открывается.
    assert client.get("/api/classes/%d" % cid, headers=auth(token_a)).status_code == 200


def test_survey_cannot_be_taken_twice():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)["Борис Б"]

    assert submit(client, svid, code, cinema=[st["Вера В"]["id"]]).status_code == 200
    second = submit(client, svid, code, cinema=[st["Глеб Г"]["id"]])
    assert second.status_code == 409
    # Повторная попытка не должна дописать выборы в граф.
    a = client.get("/api/surveys/%d/analytics" % svid, headers=auth(token)).json()
    assert a["per_student"][str(st["Глеб Г"]["id"])]["in_degree"] == 0


def test_closed_survey_rejects_start_and_submit():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)["Борис Б"]
    close_survey(client, token, svid)

    start = client.post("/api/public/surveys/%d/start" % svid, json={"code": code})
    assert start.status_code == 403
    assert submit(client, svid, code, cinema=[st["Вера В"]["id"]]).status_code == 403


def test_wrong_code_is_rate_limited_on_submit():
    """Раньше лимит стоял только на /start, и перебор кодов можно было вести
    прямо на /submit, минуя защищённый шаг."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)

    statuses = [submit(client, svid, "ZZZZZZ").status_code for _ in range(60)]
    assert 404 in statuses, "неверный код должен давать 404"
    assert 429 in statuses, "перебор кодов на /submit должен упираться в лимит"


def test_survey_info_does_not_leak_class_name():
    """Публичный эндпоинт, id срезов перебираются — название класса до ввода
    кода не отдаём."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES, class_name="11 «Б» школы №5")
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)["Алина А"]

    info = client.get("/api/public/surveys/%d/info" % svid).json()
    assert "class_name" not in info
    assert info["is_open"] is True

    # После ввода корректного кода класс уже виден — ученику он и так известен.
    started = client.post("/api/public/surveys/%d/start" % svid, json={"code": code})
    assert started.json()["class_name"] == "11 «Б» школы №5"


def test_logout_invalidates_the_token_immediately():
    """Токен подписан и живёт 7 дней; серверный выход обесценивает его сразу
    через инкремент token_version."""
    client = fresh_client()
    token = register(client)
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200

    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 200
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401
    assert client.get("/api/classes", headers=auth(token)).status_code == 401


def test_password_change_invalidates_old_sessions():
    """Пароль меняют в том числе потому, что его узнали, — старый вход должен
    перестать работать сразу."""
    client = fresh_client()
    token = register(client, password="oldpassword1")
    r = client.post("/api/auth/password",
                    json={"current_password": "oldpassword1", "new_password": "newpassword1"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    new_token = r.json()["token"]

    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401
    assert client.get("/api/auth/me", headers=auth(new_token)).status_code == 200
    assert client.post("/api/auth/login",
                       json={"email": "psy@school.kz", "password": "oldpassword1"}).status_code == 401


def test_registration_is_rate_limited():
    client = fresh_client()
    ratelimit._hits.clear()
    codes = [
        client.post("/api/auth/register",
                    json={"email": "p%d@school.kz" % i, "password": "secret12345"}).status_code
        for i in range(8)
    ]
    assert 429 in codes, "массовое создание аккаунтов с одного адреса должно упираться в лимит"


def test_submit_ignores_self_choice_foreign_students_and_over_limit():
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    # Ученик из другого класса того же психолога — выбирать его нельзя.
    other_cid, other_st = make_class(client, token, ["Чужой Ч"], class_name="9 «В»")
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)["Борис Б"]

    boris = st["Борис Б"]
    submit(
        client, svid, code,
        cinema=[boris["id"], other_st["Чужой Ч"]["id"], st["Вера В"]["id"], st["Вера В"]["id"]],
    )
    a = client.get("/api/surveys/%d/analytics" % svid, headers=auth(token)).json()
    per = a["per_student"]
    assert per[str(boris["id"])]["out_degree"] == 1        # остался только выбор Веры
    assert per[str(st["Вера В"]["id"])]["in_degree"] == 1  # и он засчитан ровно один раз


def test_broken_date_is_rejected_instead_of_silently_replaced():
    """Раньше «31.02.2026» молча превращалась в None и подменялась на сегодня:
    психолог указывал дату среза, получал другую и об этом не узнавал."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)

    bad = client.post("/api/classes/%d/surveys" % cid, headers=auth(token),
                      json={"title": "Срез", "conducted_on": "31.02.2026"})
    assert bad.status_code == 400
    assert "ГГГГ-ММ-ДД" in bad.json()["detail"]

    bad_birth = client.post("/api/classes/%d/students" % cid, headers=auth(token),
                            json={"full_name": "Новый Н", "birth_date": "вчера"})
    assert bad_birth.status_code == 400

    # Пустая строка по-прежнему означает «не задано», а не ошибку.
    ok = client.post("/api/classes/%d/students" % cid, headers=auth(token),
                     json={"full_name": "Без даты", "birth_date": ""})
    assert ok.status_code == 200
    assert ok.json()["student"]["birth_date"] is None


def test_submit_rejects_an_absurd_number_of_choices():
    """Публичный эндпоинт: принимать и разбирать тысячи выборов от анонимного
    запроса не нужно, лимит вопроса всё равно отсечёт лишнее."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)["Борис Б"]

    r = client.post("/api/public/surveys/%d/submit" % svid, json={
        "code": code, "answers": {"cinema": list(range(1, 5000))},
    })
    assert r.status_code == 422


def test_bulk_import_is_capped_and_deduplicated():
    client = fresh_client()
    token = register(client)
    cid, _ = make_class(client, token, NAMES)

    too_many = client.post("/api/classes/%d/students/bulk" % cid, headers=auth(token),
                           json={"students": [{"full_name": "A"}] * 600})
    assert too_many.status_code == 422

    # Дубли в списке — обычное дело при копировании из журнала: ученик не
    # должен попасть в срез дважды и исказить явку.
    dup = client.post("/api/classes/%d/students/bulk" % cid, headers=auth(token), json={
        "students": [{"full_name": "Пётр Петров"}, {"full_name": "пётр петров"},
                     {"full_name": "Иван Иванов"}],
    })
    assert dup.status_code == 200
    assert dup.json()["count"] == 2


def test_excel_export_is_built_on_the_server():
    """Экспорт больше не зависит от библиотеки с CDN: файл собирает сервер."""
    client = fresh_client()
    token = register(client)
    cid, st = make_class(client, token, NAMES)
    svid = open_survey(client, token, cid)
    code = tickets(client, token, svid)
    submit(client, svid, code["Борис Б"], cinema=[st["Вера В"]["id"]])

    r = client.get("/api/surveys/%d/export.xlsx" % svid, headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.content[:2] == b"PK"  # xlsx — это zip
