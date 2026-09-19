"""
Demo data generator for Изолят.

Creates a demo psychologist and a class of 14 students, then simulates three
срезы of anonymous student responses so the graph, metrics and dynamics have
real signal immediately. One student (Алина) starts isolated and integrates
over time, which also demonstrates intervention effectiveness.

Run:  python -m app.seed
"""
from datetime import date, datetime, timezone

from .alerts import generate_for_survey as generate_alerts
from .database import SessionLocal
from .models import (
    ROLE_ADMIN,
    ROLE_HEAD,
    Activity,
    ActivityParticipant,
    Choice,
    Consent,
    Intervention,
    Meeting,
    Note,
    Psychologist,
    School,
    SchoolClass,
    Student,
    Survey,
    SurveyResponse,
)
from .participation import issue_tickets
from .retention import default_retention_until
from .security import generate_code, hash_password
from .snapshots import store_snapshot

DEMO_EMAIL = "demo@izolyat.local"
DEMO_HEAD_EMAIL = "zavuch@izolyat.local"
DEMO_PASSWORD = "demo12345"
DEMO_SCHOOL = "Демо-школа (НИШ ЕМН)"
DEMO_INVITE = "DEMO2026"
DEMO_CLASS = "Демо: 8 «А» класс"

NAMES = [
    "Алина Смирнова", "Борис Кузнецов", "Вера Попова", "Глеб Соколов",
    "Дарья Морозова", "Егор Волков", "Жанна Лебедева", "Иван Козлов",
    "Ксения Новикова", "Лев Морозов", "Мария Орлова", "Никита Павлов",
    "Ольга Белова", "Пётр Фомин",
]
SURVEYS = [("Осенний срез", "2025-09-15"), ("Зимний срез", "2025-12-15"), ("Весенний срез", "2026-03-16")]


def run():
    # Схему создаёт ТОЛЬКО Alembic (`alembic upgrade head`; на Render — в
    # buildCommand перед этим сидом). Здесь стоял create_all, и это тот же
    # механизм, который однажды сломал боевую базу: create_all создаёт
    # таблицы, не записав версию в alembic_version, после чего upgrade падает
    # на уже существующих таблицах, а новые КОЛОНКИ в старые таблицы он не
    # добавляет никогда. Подробности — в README, раздел «Миграции».
    db = SessionLocal()
    try:
        school = db.query(School).filter(School.invite_code == DEMO_INVITE).first()
        if not school:
            school = School(name=DEMO_SCHOOL, city="Уральск", invite_code=DEMO_INVITE)
            db.add(school)
            db.commit()
            db.refresh(school)

        # Демо-психолог заводится администратором — так же, как первый
        # сотрудник настоящей школы. Иначе в демо не было бы ни одного
        # администратора, и «Сотрудники» с «Журналом» никто бы не увидел.
        user = db.query(Psychologist).filter(Psychologist.email == DEMO_EMAIL).first()
        if not user:
            user = Psychologist(
                email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD),
                full_name="Демо-психолог", school_id=school.id, role=ROLE_ADMIN,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.role = ROLE_ADMIN
            db.commit()

        # Завуч: та же школа, роль head — видит сводку без данных детей.
        head = db.query(Psychologist).filter(Psychologist.email == DEMO_HEAD_EMAIL).first()
        if not head:
            head = Psychologist(
                email=DEMO_HEAD_EMAIL, password_hash=hash_password(DEMO_PASSWORD),
                full_name="Демо-завуч", school_id=school.id, role=ROLE_HEAD,
            )
            db.add(head)
            db.commit()

        drop_demo_class(db, user, DEMO_CLASS)

        cls = SchoolClass(
            psychologist_id=user.id, school_id=school.id, name=DEMO_CLASS,
            description="Демонстрационный класс со сгенерированными ответами",
            retention_until=default_retention_until(school),
        )
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

        # Согласия родителей: без них ученик не участвует в срезе вообще.
        for s in students:
            db.add(Consent(student_id=s.id, kind="parent", obtained_on=date(2025, 9, 1),
                           document_ref="Демо: журнал согласий, стр. 1", created_by=user.id))
        db.commit()

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

            # Билеты выдаются как в жизни — всем участникам среза, и сразу
            # помечаются использованными: в демо опрос прошли все.
            for ticket in issue_tickets(db, sv):
                ticket.used_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
            for s in students:
                db.add(SurveyResponse(survey_id=sv.id, student_id=s.id))
            for (fi, ti, q) in pos:
                db.add(Choice(survey_id=sv.id, from_student=ids[fi - 1], to_student=ids[ti - 1], question=q))
            for (fi, ti) in alone:
                db.add(Choice(survey_id=sv.id, from_student=ids[fi - 1], to_student=ids[ti - 1], question="alone"))
            db.commit()

            # Срез закрыт: считаем снапшот и создаём оповещения — ровно то же,
            # что происходит при закрытии среза в интерфейсе.
            store_snapshot(db, sv)
            generate_alerts(db, sv)
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

        seed_prevention(db, user, cls, students)
        seed_quiet_class(db, user, school)
        seed_pending_class(db, user, school)

        print("Демо-данные готовы.\n")
        print("  Психолог (он же администратор школы):")
        print(f"    {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print("  Завуч — видит сводку по школе без данных детей:")
        print(f"    {DEMO_HEAD_EMAIL} / {DEMO_PASSWORD}")
        print(f"  Код приглашения школы: {DEMO_INVITE}")
    finally:
        db.close()


def seed_prevention(db, user, cls, students):
    """Профилактическая работа демо-класса.

    История та же, что и в графе: осенью Алина изолят, по итогам осеннего среза
    психолог проводит два мероприятия, к зимнему срезу связи появляются. Так на
    экране «Эффект» видно реальное сравнение «до/после», а не пустую заглушку.
    """
    surveys = (
        db.query(Survey)
        .filter(Survey.class_id == cls.id)
        .order_by(Survey.conducted_on, Survey.id)
        .all()
    )
    if not surveys:
        return
    autumn = surveys[0]
    alina = students[0]

    group = Activity(
        psychologist_id=user.id, class_id=cls.id, source_survey_id=autumn.id,
        title="Включение в группу через взаимную пару",
        kind="training", target="group", status="done",
        goal="Дать ребёнку без входящих выборов опыт принятия в малой группе.",
        plan="Малые группы 3-4 человека, общее задание с распределением ролей, "
             "рефлексия по кругу о результате группы, а не каждого лично.",
        outcome="Алина включилась в работу группы, к концу занятия сама предложила идею.",
        effectiveness=4,
        planned_on=date(2025, 10, 1), conducted_on=date(2025, 10, 6), duration_min=45,
    )
    db.add(group)
    db.flush()
    # Охват: Алина и те, с кем её объединяли.
    for s in (students[0], students[2], students[7]):
        db.add(ActivityParticipant(activity_id=group.id, student_id=s.id))

    hour = Activity(
        psychologist_id=user.id, class_id=cls.id, source_survey_id=autumn.id,
        title="Классный час о принятии и границах",
        kind="class_hour", target="class", status="done",
        goal="Снять закрепившийся за ребёнком ярлык «одиночки», не называя его имени.",
        plan="Разговор о том, почему человек может держаться в стороне; разбор ситуаций; "
             "договорённость класса о делении на группы по жребию.",
        outcome="Класс принял правило «никто не остаётся вне пары» при делении на группы.",
        effectiveness=4,
        planned_on=date(2025, 10, 15), conducted_on=date(2025, 10, 20), duration_min=40,
    )
    db.add(hour)
    db.flush()
    for s in students:
        db.add(ActivityParticipant(activity_id=hour.id, student_id=s.id))

    db.add(Activity(
        psychologist_id=user.id, class_id=cls.id,
        title="Выступление на родительском собрании",
        kind="parents", target="adults", status="done",
        goal="Объяснить родителям, как поддержать ребёнка в отношениях с классом.",
        outcome="Пришли 19 родителей, четверо записались на индивидуальную консультацию.",
        effectiveness=3, adults_count=19,
        planned_on=date(2025, 11, 12), conducted_on=date(2025, 11, 12), duration_min=30,
    ))

    # Одно мероприятие в плане — чтобы экран показывал не только историю.
    db.add(Activity(
        psychologist_id=user.id, class_id=cls.id, source_survey_id=surveys[-1].id,
        title="Тренинг на сплочение класса",
        kind="training", target="class", status="planned",
        goal="Закрепить результат: увеличить число взаимных связей в классе.",
        plan="Разминка на перемешивание, командная задача, упражнение «общее и разное».",
        planned_on=date(2026, 4, 14), duration_min=45,
    ))
    db.commit()


def drop_demo_class(db, user, name):
    """Удаляет ВСЕ демо-классы с таким именем.

    Раньше удалялся только первый найденный, и повторный запуск сида оставлял
    второй экземпляр: класс показывал вдвое больше учеников и срезов, явка
    падала до 50%, индекс переставал считаться. Сид должен быть идемпотентным —
    его запускают повторно.
    """
    rows = db.query(SchoolClass).filter(
        SchoolClass.psychologist_id == user.id, SchoolClass.name == name
    ).all()
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()


def seed_quiet_class(db, user, school):
    """Благополучный класс — чтобы на главном экране было с чем сравнить.

    Без него сортировка «сначала там, где нужно внимание» не видна: один
    класс всегда первый.
    """
    name = "Демо: 9 «Б» класс"
    drop_demo_class(db, user, name)

    cls = SchoolClass(
        psychologist_id=user.id, school_id=school.id, name=name,
        description="Сплочённый класс без тревожных сигналов",
        retention_until=default_retention_until(school),
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)

    names = ["Асель Жумабаева", "Данияр Ахметов", "Ерке Сагындык", "Ильяс Бектуров",
             "Камила Садыкова", "Мирас Оспанов", "Нурай Темирова", "Санжар Ибраев"]
    students = []
    for i, nm in enumerate(names, 1):
        code = generate_code()
        while db.query(Student).filter(Student.code == code).first():
            code = generate_code()
        s = Student(class_id=cls.id, psychologist_id=user.id, full_name=nm,
                    code=code, gender="f" if i % 2 else "m")
        db.add(s)
        students.append(s)
    db.commit()
    for s in students:
        db.refresh(s)
        db.add(Consent(student_id=s.id, kind="parent", obtained_on=date(2025, 9, 1),
                       document_ref="Демо: журнал согласий, стр. 2", created_by=user.id))
    db.commit()

    sv = Survey(class_id=cls.id, psychologist_id=user.id, title="Осенний срез",
                conducted_on=date(2025, 9, 16), is_open=False)
    db.add(sv)
    db.commit()
    db.refresh(sv)

    # Все выбирают соседей по кругу в обе стороны -> взаимные пары, изолятов нет.
    ids = [s.id for s in students]
    n = len(ids)
    for i in range(n):
        for t in (ids[(i + 1) % n], ids[(i - 1) % n]):
            db.add(Choice(survey_id=sv.id, from_student=ids[i], to_student=t, question="cinema"))
        db.add(Choice(survey_id=sv.id, from_student=ids[i], to_student=ids[(i + 2) % n], question="project"))
    for ticket in issue_tickets(db, sv):
        ticket.used_at = datetime(2025, 9, 16, tzinfo=timezone.utc)
    for s in students:
        db.add(SurveyResponse(survey_id=sv.id, student_id=s.id))
    db.commit()
    store_snapshot(db, sv)
    generate_alerts(db, sv)
    db.commit()


def seed_pending_class(db, user, school):
    """Класс, где согласия собраны не у всех и срез ещё не проводился.

    Показывает состояние «нужно доделать»: именно в нём видно, что ученик без
    согласия в срез не попадает.
    """
    name = "Демо: 7 «В» класс"
    drop_demo_class(db, user, name)

    cls = SchoolClass(
        psychologist_id=user.id, school_id=school.id, name=name,
        description="Согласия собраны не у всех — срез ещё не запускали",
        retention_until=default_retention_until(school),
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)

    names = ["Айгерим Нурланова", "Бекзат Сериков", "Гульмира Досова",
             "Диас Жаксылык", "Жанель Куанышева", "Тимур Алиев"]
    for i, nm in enumerate(names, 1):
        code = generate_code()
        while db.query(Student).filter(Student.code == code).first():
            code = generate_code()
        s = Student(class_id=cls.id, psychologist_id=user.id, full_name=nm,
                    code=code, gender="f" if i % 2 else "m")
        db.add(s)
        db.flush()
        # Двоим согласие ещё не оформлено — в срез они не попадут.
        if i <= len(names) - 2:
            db.add(Consent(student_id=s.id, kind="parent", obtained_on=date(2025, 9, 3),
                           document_ref="Демо: журнал согласий, стр. 3", created_by=user.id))
    db.commit()


if __name__ == "__main__":
    run()
