"""Кто участвует в срезе: согласия и одноразовые билеты.

Два правила, которые делают продукт пригодным для реальной школы.

**Согласие.** Ученик без действующего согласия на обработку персональных
данных не участвует в срезе вообще: ему не выдаётся билет и одноклассники не
видят его в списке для выбора. Не «участвует, но помечен» — именно не
участвует, иначе система обрабатывала бы его данные без основания.

**Билет.** Код на срез одноразовый и живёт только внутри своего среза.
Раньше кодом служил постоянный Student.code: подсмотревший его одноклассник
мог ответить за другого и заблокировать ему прохождение навсегда (уникальный
индекс на ответ отдавал 409). Теперь психолог перевыпускает билет одному
ученику, не трогая остальных.
"""
from datetime import date

from sqlalchemy import or_

from .models import Consent, Student, SurveyTicket
from .security import generate_code


def consent_ok_filter(today=None):
    """Условие SQL: у ученика есть действующее согласие."""
    today = today or date.today()
    return or_(Consent.revoked_on.is_(None), Consent.revoked_on > today)


def students_with_consent(db, class_id, today=None):
    """Активные ученики класса с действующим согласием — участники среза."""
    today = today or date.today()
    return (
        db.query(Student)
        .join(Consent, Consent.student_id == Student.id)
        .filter(
            Student.class_id == class_id,
            Student.is_active.is_(True),
            Consent.obtained_on <= today,
            consent_ok_filter(today),
        )
        .order_by(Student.full_name)
        .distinct()
        .all()
    )


def consent_status(db, class_id, today=None):
    """Сводка по согласиям класса: сколько есть, кого не хватает."""
    today = today or date.today()
    active = (
        db.query(Student)
        .filter(Student.class_id == class_id, Student.is_active.is_(True))
        .order_by(Student.full_name)
        .all()
    )
    with_consent = {s.id for s in students_with_consent(db, class_id, today)}
    missing = [s for s in active if s.id not in with_consent]
    return {
        "total": len(active),
        "with_consent": len(with_consent),
        "missing": [{"id": s.id, "full_name": s.full_name} for s in missing],
    }


def consent_status_bulk(db, class_ids, today=None):
    """consent_status сразу для нескольких классов: {class_id: сводка}.

    Экраны «Мои классы» и сводка школы показывают согласия по каждому классу.
    Поштучный вызов давал по два запроса на класс — в школе на сорок классов
    это восемьдесят запросов на одно открытие страницы.
    """
    today = today or date.today()
    ids = list(class_ids) or [0]

    active = (
        db.query(Student)
        .filter(Student.class_id.in_(ids), Student.is_active.is_(True))
        .order_by(Student.full_name)
        .all()
    )
    with_consent = {
        row[0] for row in
        db.query(Student.id)
        .join(Consent, Consent.student_id == Student.id)
        .filter(
            Student.class_id.in_(ids),
            Student.is_active.is_(True),
            Consent.obtained_on <= today,
            consent_ok_filter(today),
        )
        .distinct()
        .all()
    }

    result = {cid: {"total": 0, "with_consent": 0, "missing": []} for cid in ids}
    for s in active:
        bucket = result.setdefault(s.class_id, {"total": 0, "with_consent": 0, "missing": []})
        bucket["total"] += 1
        if s.id in with_consent:
            bucket["with_consent"] += 1
        else:
            bucket["missing"].append({"id": s.id, "full_name": s.full_name})
    return result


def unique_ticket_code(db, used=None):
    """Код билета, не совпадающий ни с одним существующим.

    Проверяем и по students.code тоже: ученик вводит одно поле, и коллизия
    между постоянным кодом и билетом привела бы к неоднозначности.
    """
    used = used if used is not None else set()
    for _ in range(80):
        code = generate_code()
        if code in used:
            continue
        if db.query(SurveyTicket).filter(SurveyTicket.code == code).first():
            continue
        if db.query(Student).filter(Student.code == code).first():
            continue
        used.add(code)
        return code
    raise RuntimeError("Не удалось сгенерировать уникальный код билета")


def issue_tickets(db, survey, today=None):
    """Выдаёт билеты всем участникам среза. Идемпотентна: у кого билет уже
    есть, тому новый не выдаётся."""
    participants = students_with_consent(db, survey.class_id, today)
    existing = {
        t.student_id: t
        for t in db.query(SurveyTicket).filter(SurveyTicket.survey_id == survey.id).all()
    }
    used = set()
    issued = []
    for s in participants:
        if s.id in existing:
            issued.append(existing[s.id])
            continue
        ticket = SurveyTicket(survey_id=survey.id, student_id=s.id, code=unique_ticket_code(db, used))
        db.add(ticket)
        issued.append(ticket)
    db.flush()
    return issued


def reissue_ticket(db, survey_id, student_id):
    """Перевыпуск билета одному ученику — например, если код подсмотрели."""
    ticket = (
        db.query(SurveyTicket)
        .filter(SurveyTicket.survey_id == survey_id, SurveyTicket.student_id == student_id)
        .first()
    )
    if ticket is None:
        ticket = SurveyTicket(survey_id=survey_id, student_id=student_id, code=unique_ticket_code(db))
        db.add(ticket)
    else:
        ticket.code = unique_ticket_code(db)
        ticket.used_at = None
    db.flush()
    return ticket
