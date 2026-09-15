"""Просмотр журнала доступа к персональным данным.

Журнал без возможности его прочитать бесполезен: смысл в том, чтобы можно
было ответить на вопрос проверки «кто и когда открывал данные этого ребёнка».
Доступ — у администратора школы, и только по своей школе.

Сам журнал персональных данных не содержит: в нём id объекта и действие, а
имена подставляются при показе и только для своей школы.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..audit import ACTION_TITLES
from ..database import get_db
from ..models import AuditLog, Psychologist, SchoolClass, Student, Survey
from ..permissions import require_admin

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(200, ge=1, le=1000),
    student_id: int = Query(None),
    user: Psychologist = Depends(require_admin),
    db: Session = Depends(get_db),
):
    staff_ids = [
        row[0] for row in db.query(Psychologist.id).filter(Psychologist.school_id == user.school_id).all()
    ] or [0]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = db.query(AuditLog).filter(AuditLog.psychologist_id.in_(staff_ids), AuditLog.at >= since)
    if student_id:
        q = q.filter(AuditLog.target_type == "student", AuditLog.target_id == student_id)
    rows = q.order_by(AuditLog.at.desc()).limit(limit).all()

    staff = dict(db.query(Psychologist.id, Psychologist.full_name).filter(Psychologist.id.in_(staff_ids)).all())
    emails = dict(db.query(Psychologist.id, Psychologist.email).filter(Psychologist.id.in_(staff_ids)).all())

    # Подписи целей подтягиваем только для показанных записей.
    by_type = {"student": set(), "class": set(), "survey": set()}
    for r in rows:
        if r.target_type in by_type and r.target_id:
            by_type[r.target_type].add(r.target_id)
    names = {
        "student": dict(db.query(Student.id, Student.full_name)
                        .filter(Student.id.in_(by_type["student"] or {0})).all()),
        "class": dict(db.query(SchoolClass.id, SchoolClass.name)
                      .filter(SchoolClass.id.in_(by_type["class"] or {0})).all()),
        "survey": dict(db.query(Survey.id, Survey.title)
                       .filter(Survey.id.in_(by_type["survey"] or {0})).all()),
    }

    return {
        "days": days,
        "entries": [{
            "id": r.id,
            "at": r.at.isoformat() if r.at else None,
            "action": r.action,
            "action_title": ACTION_TITLES.get(r.action, r.action),
            "who": staff.get(r.psychologist_id) or emails.get(r.psychologist_id) or "—",
            "target_type": r.target_type,
            "target_id": r.target_id,
            "target_name": names.get(r.target_type, {}).get(r.target_id, "—"),
            "ip": r.ip,
        } for r in rows],
    }
