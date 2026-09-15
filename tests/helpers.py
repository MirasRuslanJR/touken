"""Обвязка для API-тестов.

Тестовая база (временный SQLite) настраивается в корневом conftest.py — он
обязан отработать раньше первого импорта app.config, иначе тесты уйдут в
боевую базу Supabase из .env.
"""
from datetime import date

from fastapi.testclient import TestClient

from app import ratelimit
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import ROLE_HEAD, Consent, Psychologist, School
from app.security import generate_code


def fresh_client():
    """Чистая база и обнулённые счётчики rate-limit на каждый тест.

    Счётчики глобальны для процесса, и без сброса тесты начали бы получать 429
    друг от друга (лимит регистрации — 5 в час на адрес).
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ratelimit._hits.clear()
    return TestClient(app)


def auth(token):
    return {"Authorization": "Bearer " + token}


def make_school(client, name="Тестовая школа"):
    r = client.post("/api/auth/schools", json={"name": name, "city": "Уральск"})
    assert r.status_code == 200, r.text
    return r.json()["school"]


def register(client, email="psy@school.kz", password="secret12345", invite=None):
    payload = {"email": email, "password": password}
    if invite:
        payload["invite_code"] = invite
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def register_in_school(client, invite, email, password="secret12345"):
    return register(client, email=email, password=password, invite=invite)


def make_head(client, invite, email="head@school.kz"):
    """Регистрирует сотрудника и переводит его в роль завуча.

    Роль меняем напрямую в БД: делать это через API пришлось бы от имени
    администратора школы, а тесту важна сама проверка доступа, а не путь.
    """
    token = register(client, email=email, invite=invite)
    db = SessionLocal()
    try:
        u = db.query(Psychologist).filter(Psychologist.email == email).first()
        u.role = ROLE_HEAD
        db.commit()
    finally:
        db.close()
    # Роль поменялась — перелогиниваемся, чтобы токен точно был актуален.
    r = client.post("/api/auth/login", json={"email": email, "password": "secret12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def grant_consent(client, token, student_id, obtained_on=None):
    r = client.post(
        "/api/students/%d/consent" % student_id,
        json={"kind": "parent", "obtained_on": (obtained_on or date(2025, 9, 1)).isoformat(),
              "document_ref": "тест"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["consent"]


def make_class(client, token, names, class_name="8 «А»", consent=True):
    """Класс с учениками. По умолчанию всем сразу проставляется согласие —
    иначе они не участвуют в срезе. Возвращает (class_id, {имя: student})."""
    r = client.post("/api/classes", json={"name": class_name}, headers=auth(token))
    assert r.status_code == 200, r.text
    cid = r.json()["class"]["id"]
    students = {}
    for nm in names:
        s = client.post("/api/classes/%d/students" % cid, json={"full_name": nm}, headers=auth(token))
        assert s.status_code == 200, s.text
        student = s.json()["student"]
        students[nm] = student
        if consent:
            grant_consent(client, token, student["id"])
    return cid, students


def open_survey(client, token, cid, title="Осенний срез"):
    r = client.post("/api/classes/%d/surveys" % cid, json={"title": title}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["survey"]["id"]


def tickets(client, token, svid):
    """{имя ученика: код билета} — то, что психолог раздаёт классу."""
    r = client.get("/api/surveys/%d/tickets" % svid, headers=auth(token))
    assert r.status_code == 200, r.text
    return {t["full_name"]: t["code"] for t in r.json()["tickets"]}


def close_survey(client, token, svid):
    r = client.put("/api/surveys/%d" % svid, json={"is_open": False}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def submit(client, svid, code, cinema=(), project=(), alone=()):
    return client.post("/api/public/surveys/%d/submit" % svid, json={
        "code": code,
        "answers": {"cinema": list(cinema), "project": list(project), "alone": list(alone)},
    })
