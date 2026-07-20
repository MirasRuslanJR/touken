"""
Demo data generator for Изолят.

Creates a demo psychologist and a class of 14 students, then simulates three
срезы of anonymous student responses so the graph, metrics and dynamics have
real signal immediately. One student (Алина) starts isolated and integrates
over time, which also demonstrates intervention effectiveness.

Run:  python -m app.seed
"""
from datetime import date

from .database import Base, SessionLocal, engine
from .models import (
    Choice,
    Intervention,
    Meeting,
    Note,
    Psychologist,
    SchoolClass,
    Student,
    Survey,
    SurveyResponse,
)
from .security import generate_code, hash_password

DEMO_EMAIL = "demo@izolyat.local"
DEMO_PASSWORD = "demo12345"
DEMO_CLASS = "Демо: 8 «А» класс"

NAMES = [
    "Алина Смирнова", "Борис Кузнецов", "Вера Попова", "Глеб Соколов",
    "Дарья Морозова", "Егор Волков", "Жанна Лебедева", "Иван Козлов",
    "Ксения Новикова", "Лев Морозов", "Мария Орлова", "Никита Павлов",
    "Ольга Белова", "Пётр Фомин",
]
SURVEYS = [("Осенний срез", "2025-09-15"), ("Зимний срез", "2025-12-15"), ("Весенний срез", "2026-03-16")]


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(Psychologist).filter(Psychologist.email == DEMO_EMAIL).first()
        if not user:
            user = Psychologist(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), full_name="Демо-психолог")
            db.add(user)
            db.commit()
            db.refresh(user)

        old = db.query(SchoolClass).filter(
            SchoolClass.psychologist_id == user.id, SchoolClass.name == DEMO_CLASS
        ).first()
        if old:
            db.delete(old)
            db.commit()

        cls = SchoolClass(psychologist_id=user.id, name=DEMO_CLASS, description="Демонстрационный класс со сгенерированными ответами")
        db.add(cls)
        db.commit()
        db.refresh(cls)

        students = []
        used = set()
        for i, name in enumerate(NAMES, 1):
            code = generate_code()
            while code in used or db.query(Student).filter(Student.code == code).first():
                code = generate_code()
            used.add(code)
            s = Student(class_id=cls.id, psychologist_id=user.id, full_name=name, code=code, gender="f" if i % 2 == 0 else "m")
            db.add(s)
            students.append(s)
        db.commit()
        for s in students:
            db.refresh(s)

        ids = [s.id for s in students]
        n = len(ids)

        def wrap(x):
            return ((x - 1) % n) + 1

        for k, (title, dt) in enumerate(SURVEYS, start=1):
            sv = Survey(class_id=cls.id, psychologist_id=user.id, title=title, conducted_on=date.fromisoformat(dt), is_open=False)
            db.add(sv)
            db.commit()
            db.refresh(sv)

            pos = set()   # (from_idx, to_idx, question)
            alone = set() # (from_idx, to_idx)
            for i in range(1, n + 1):
                for t in (wrap(i + 1), wrap(i + 2)):
                    if t != i:
                        pos.add((i, t, "cinema"))
                for t in (wrap(i + 2), wrap(i + 3 + k)):
                    if t != i:
                        pos.add((i, t, "project"))
                a = wrap(i + n // 2 + k)
                if a != i:
                    alone.add((i, a))

            # Engineer Алина (#1): isolated -> integrated across срезы.
            if k == 1:
                pos = {p for p in pos if p[1] != 1}
                for frm in (4, 6, 9):
                    alone.add((frm, 1))
            elif k == 2:
                alone = {a for a in alone if a[1] != 1}
                for frm in (3, 8):
                    pos.add((frm, 1, "cinema"))
            elif k == 3:
                alone = {a for a in alone if a[1] != 1}
                for frm in (3, 8, 5, 11):
                    pos.add((frm, 1, "cinema"))
                    pos.add((frm, 1, "project"))

            for s in students:
                db.add(SurveyResponse(survey_id=sv.id, student_id=s.id))
            for (fi, ti, q) in pos:
                db.add(Choice(survey_id=sv.id, from_student=ids[fi - 1], to_student=ids[ti - 1], question=q))
            for (fi, ti) in alone:
                db.add(Choice(survey_id=sv.id, from_student=ids[fi - 1], to_student=ids[ti - 1], question="alone"))
            db.commit()

        a = students[0].id
        leader = students[5].id
        db.add_all([
            Note(student_id=a, psychologist_id=user.id, body="Социальная изоляция: держится в стороне, на переменах одна. По опросу — нет входящих выборов, есть номинации «часто один»."),
            Note(student_id=a, psychologist_id=user.id, body="После групповых занятий появились взаимные выборы. Настроение ровнее."),
            Note(student_id=leader, psychologist_id=user.id, body="Лидер класса, много входящих выборов. Привлечь как наставника."),
        ])
        db.add_all([
            Meeting(student_id=a, psychologist_id=user.id, met_on=date.fromisoformat("2025-09-22"), summary="Первичная диагностическая беседа. Запрос — трудности в общении."),
            Meeting(student_id=a, psychologist_id=user.id, met_on=date.fromisoformat("2025-10-13"), summary="Занятие по развитию коммуникативных навыков (1/6)."),
            Meeting(student_id=a, psychologist_id=user.id, met_on=date.fromisoformat("2026-02-16"), summary="Поддерживающая встреча, закрепление результата."),
        ])
        db.add(Intervention(
            student_id=a, psychologist_id=user.id,
            title="Программа развития коммуникативных навыков",
            description="Цикл из 6 групповых занятий + включение в проектную деятельность с более принимаемыми одноклассниками.",
            started_on=date.fromisoformat("2025-10-01"), ended_on=date.fromisoformat("2025-12-20"),
            effectiveness=4, outcome="Из изолята — в принятые, появились взаимные выборы. Изоляция преодолена.",
        ))
        db.commit()

        print("Демо-данные готовы.")
        print(f"  Вход:   {DEMO_EMAIL}")
        print(f"  Пароль: {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
