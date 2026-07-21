"""Public, unauthenticated survey endpoints used by students.

A student only ever provides a code. They never see analytics, and they only
see the class roster (to make their choices) after a valid code is supplied.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import QUESTION_KEYS, effective_questions
from ..database import get_db
from ..models import Choice, SchoolClass, Student, Survey, SurveyResponse
from ..ratelimit import check as rate_limit, client_ip

router = APIRouter(prefix="/api/public", tags=["public"])


def _survey_or_404(db, svid):
    sv = db.get(Survey, svid)
    if not sv:
        raise HTTPException(404, "Опрос не найден")
    return sv


def _student_by_code(db, sv, code):
    code = (code or "").strip().upper()
    student = db.query(Student).filter(Student.code == code).first()
    if not student or student.class_id != sv.class_id:
        raise HTTPException(404, "Код не найден. Проверьте правильность ввода.")
    return student


def _already_done(db, svid, student_id):
    return (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == svid, SurveyResponse.student_id == student_id)
        .first()
        is not None
    )


@router.get("/surveys/{svid}/info")
def survey_info(svid: int, db: Session = Depends(get_db)):
    sv = _survey_or_404(db, svid)
    cls = db.get(SchoolClass, sv.class_id)
    return {
        "title": sv.title,
        "class_name": cls.name if cls else "",
        "is_open": bool(sv.is_open),
    }


@router.post("/surveys/{svid}/start")
def survey_start(svid: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    # Защита от перебора кодов учеников скриптом. Лимит подобран так, чтобы
    # целый класс за одним школьным Wi-Fi (общий IP через NAT) спокойно
    # проходил опрос, но автоматический перебор был непрактичен.
    rate_limit("start:" + client_ip(request), limit=40, window=60)
    sv = _survey_or_404(db, svid)
    if not sv.is_open:
        raise HTTPException(403, "Опрос закрыт.")
    student = _student_by_code(db, sv, payload.get("code"))
    if _already_done(db, svid, student.id):
        raise HTTPException(409, "Вы уже проходили этот опрос. Повторно пройти нельзя.")
    roster = (
        db.query(Student)
        .filter(Student.class_id == sv.class_id, Student.id != student.id)
        .order_by(Student.full_name)
        .all()
    )
    cls = db.get(SchoolClass, sv.class_id)
    return {
        "title": sv.title,
        "class_name": cls.name if cls else "",
        "questions": effective_questions(sv),
        "roster": [{"id": r.id, "full_name": r.full_name} for r in roster],
    }


@router.post("/surveys/{svid}/submit")
def survey_submit(svid: int, payload: dict, db: Session = Depends(get_db)):
    sv = _survey_or_404(db, svid)
    if not sv.is_open:
        raise HTTPException(403, "Опрос закрыт.")
    student = _student_by_code(db, sv, payload.get("code"))
    if _already_done(db, svid, student.id):
        raise HTTPException(409, "Вы уже проходили этот опрос. Повторно пройти нельзя.")

    answers = payload.get("answers") or {}
    valid_ids = {row[0] for row in db.query(Student.id).filter(Student.class_id == sv.class_id).all()}

    question_max = {q["key"]: q["max"] for q in effective_questions(sv)}

    # Record completion first so the unique constraint blocks double submits.
    db.add(SurveyResponse(survey_id=svid, student_id=student.id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Вы уже проходили этот опрос. Повторно пройти нельзя.")

    for key in QUESTION_KEYS:
        targets = answers.get(key) or []
        seen = set()
        limit = question_max.get(key, 3)
        for raw in targets:
            try:
                tid = int(raw)
            except (TypeError, ValueError):
                continue
            if tid == student.id or tid not in valid_ids or tid in seen:
                continue
            seen.add(tid)
            if len(seen) > limit:
                break
            db.add(Choice(survey_id=svid, from_student=student.id, to_student=tid, question=key))

    db.commit()
    return {"ok": True}
