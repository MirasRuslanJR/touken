"""Публичные эндпоинты опроса — то, чем пользуется ученик.

Ученик не является пользователем системы: у него нет аккаунта и он физически
не может открыть аналитику. Он вводит одноразовый код на срез (билет) и
видит только список одноклассников, чтобы сделать выбор.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import QUESTION_KEYS, effective_questions
from ..database import get_db
from ..models import Choice, SchoolClass, Student, Survey, SurveyResponse, SurveyTicket
from ..participation import students_with_consent
from ..ratelimit import check as rate_limit, client_ip
from ..schemas import SurveyStartIn, SurveySubmitIn
from ..snapshots import invalidate

router = APIRouter(prefix="/api/public", tags=["public"])

# Лимит подобран так, чтобы целый класс за одним школьным Wi-Fi (общий IP через
# NAT) спокойно проходил опрос, но автоматический перебор кодов был непрактичен.
CODE_ATTEMPTS, CODE_WINDOW = 40, 60


def _survey_or_404(db, svid):
    sv = db.get(Survey, svid)
    if not sv:
        raise HTTPException(404, "Опрос не найден")
    return sv


def _ticket_or_404(db, sv, code):
    """Находит билет по коду. Билет действителен только внутри своего среза —
    код от прошлого среза или от другого класса не подойдёт."""
    code = (code or "").strip().upper()
    ticket = (
        db.query(SurveyTicket)
        .filter(SurveyTicket.survey_id == sv.id, SurveyTicket.code == code)
        .first()
    )
    if not ticket:
        raise HTTPException(404, "Код не найден. Проверьте правильность ввода.")
    return ticket


def _already_done(db, svid, student_id):
    return (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == svid, SurveyResponse.student_id == student_id)
        .first()
        is not None
    )


@router.get("/surveys/{svid}/info")
def survey_info(svid: int, request: Request, db: Session = Depends(get_db)):
    # Эндпоинт публичный, а id срезов перебираются (1, 2, 3...). Поэтому здесь
    # лимит и минимум данных: название класса отдаётся только после ввода кода,
    # в /start. До этого посторонний не узнаёт, какой класс где учится.
    rate_limit("info:" + client_ip(request), limit=60, window=60)
    sv = _survey_or_404(db, svid)
    return {"title": sv.title, "is_open": bool(sv.is_open)}


@router.post("/surveys/{svid}/start")
def survey_start(svid: int, payload: SurveyStartIn, request: Request, db: Session = Depends(get_db)):
    # Защита от перебора кодов учеников скриптом.
    rate_limit("start:" + client_ip(request), limit=CODE_ATTEMPTS, window=CODE_WINDOW)
    sv = _survey_or_404(db, svid)
    if not sv.is_open:
        raise HTTPException(403, "Опрос закрыт.")
    ticket = _ticket_or_404(db, sv, payload.code)
    if _already_done(db, svid, ticket.student_id):
        raise HTTPException(409, "Вы уже проходили этот опрос. Повторно пройти нельзя.")

    # В списке для выбора — только участники среза: активные ученики с
    # действующим согласием на обработку данных.
    roster = [s for s in students_with_consent(db, sv.class_id) if s.id != ticket.student_id]
    cls = db.get(SchoolClass, sv.class_id)
    return {
        "title": sv.title,
        "class_name": cls.name if cls else "",
        "questions": effective_questions(sv),
        "roster": [{"id": r.id, "full_name": r.full_name} for r in roster],
    }


@router.post("/surveys/{svid}/submit")
def survey_submit(svid: int, payload: SurveySubmitIn, request: Request, db: Session = Depends(get_db)):
    # Тот же лимит, что и на /start. Без него перебор кодов и отправку ответов
    # можно было вести прямо здесь, минуя защищённый /start.
    rate_limit("submit:" + client_ip(request), limit=CODE_ATTEMPTS, window=CODE_WINDOW)
    sv = _survey_or_404(db, svid)
    if not sv.is_open:
        raise HTTPException(403, "Опрос закрыт.")
    ticket = _ticket_or_404(db, sv, payload.code)
    student_id = ticket.student_id
    if _already_done(db, svid, student_id):
        raise HTTPException(409, "Вы уже проходили этот опрос. Повторно пройти нельзя.")

    answers = payload.answers or {}
    # Выбирать можно только участников среза — тех же, кого ученик видел в списке.
    valid_ids = {s.id for s in students_with_consent(db, sv.class_id)}
    question_max = {q["key"]: q["max"] for q in effective_questions(sv)}

    # Record completion first so the unique constraint blocks double submits.
    db.add(SurveyResponse(survey_id=svid, student_id=student_id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Вы уже проходили этот опрос. Повторно пройти нельзя.")

    for key in QUESTION_KEYS:
        seen = set()
        limit = question_max.get(key, 3)
        # Схема уже гарантирует, что это список int — остаётся отсечь выбор
        # самого себя, неучастников среза, дубли и превышение лимита выборов.
        for tid in answers.get(key) or []:
            if tid == student_id or tid not in valid_ids or tid in seen:
                continue
            if len(seen) >= limit:
                break
            seen.add(tid)
            db.add(Choice(survey_id=svid, from_student=student_id, to_student=tid, question=key))

    ticket.used_at = datetime.now(timezone.utc)
    # Пришёл новый ответ — посчитанная аналитика этого среза устарела.
    invalidate(db, svid)
    db.commit()
    return {"ok": True}
