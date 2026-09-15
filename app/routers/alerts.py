"""Входящие психолога: оповещения, созданные сервером при закрытии среза."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..alerts import TITLES
from ..database import get_db
from ..models import Alert, Psychologist, SchoolClass, Student, Survey
from ..permissions import require_casework

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _dict(a, student_name, class_name, survey_title):
    return {
        "id": a.id,
        "kind": a.kind,
        "title": TITLES.get(a.kind, a.kind),
        "student_id": a.student_id,
        "student_name": student_name,
        "class_id": a.class_id,
        "class_name": class_name,
        "survey_id": a.survey_id,
        "survey_title": survey_title,
        "from_value": a.from_value,
        "to_value": a.to_value,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "seen": a.seen_at is not None,
        "resolved": a.resolved_at is not None,
    }


@router.get("")
def list_alerts(
    resolved: bool = False,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    q = db.query(Alert).filter(Alert.psychologist_id == user.id)
    q = q.filter(Alert.resolved_at.isnot(None)) if resolved else q.filter(Alert.resolved_at.is_(None))
    # id как вторичный ключ: все оповещения одного среза создаются в одну
    # секунду, и без него их порядок в списке менялся бы от запроса к запросу.
    rows = q.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(200).all()

    # Подписи тянем только для показанных оповещений. Раньше здесь грузились
    # ВСЕ ученики, классы и срезы базы — по всем школам сразу.
    student_ids = {a.student_id for a in rows} or {0}
    class_ids = {a.class_id for a in rows} or {0}
    survey_ids = {a.survey_id for a in rows} or {0}
    names = dict(db.query(Student.id, Student.full_name).filter(Student.id.in_(student_ids)).all())
    classes = dict(db.query(SchoolClass.id, SchoolClass.name).filter(SchoolClass.id.in_(class_ids)).all())
    surveys = dict(db.query(Survey.id, Survey.title).filter(Survey.id.in_(survey_ids)).all())

    unseen = (
        db.query(func.count(Alert.id))
        .filter(Alert.psychologist_id == user.id, Alert.resolved_at.is_(None), Alert.seen_at.is_(None))
        .scalar()
    )
    return {
        "unseen": unseen or 0,
        "alerts": [
            _dict(a, names.get(a.student_id, "—"), classes.get(a.class_id, "—"), surveys.get(a.survey_id, "—"))
            for a in rows
        ],
    }


@router.get("/count")
def unseen_count(user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Счётчик для значка во «Входящих» — дёргается на каждом экране."""
    n = (
        db.query(func.count(Alert.id))
        .filter(Alert.psychologist_id == user.id, Alert.resolved_at.is_(None), Alert.seen_at.is_(None))
        .scalar()
    )
    return {"unseen": n or 0}


@router.post("/seen")
def mark_seen(user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Пометить все непрочитанные как просмотренные — снимает значок, но
    оповещения остаются в работе, пока их не закроют явно."""
    (db.query(Alert)
       .filter(Alert.psychologist_id == user.id, Alert.seen_at.is_(None))
       .update({Alert.seen_at: datetime.now(timezone.utc)}, synchronize_session=False))
    db.commit()
    return {"ok": True}


@router.post("/{aid}/resolve")
def resolve(aid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Закрыть оповещение: психолог посмотрел ребёнка и принял решение."""
    a = db.get(Alert, aid)
    if not a or a.psychologist_id != user.id:
        raise HTTPException(404, "Оповещение не найдено")
    now = datetime.now(timezone.utc)
    a.resolved_at = now
    if a.seen_at is None:
        a.seen_at = now
    db.commit()
    return {"ok": True}


@router.post("/{aid}/reopen")
def reopen(aid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    a = db.get(Alert, aid)
    if not a or a.psychologist_id != user.id:
        raise HTTPException(404, "Оповещение не найдено")
    a.resolved_at = None
    db.commit()
    return {"ok": True}
