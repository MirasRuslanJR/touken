"""Сводка по школе — то, что видит завуч и администрация.

Здесь нет и не должно быть данных отдельных детей: ни имён, ни карточек, ни
списков изолятов. Завучу для управленческого решения нужен класс («в 8Б
падает связность, сходите к психологу»), а не ребёнок. Лишний доступ к данным
несовершеннолетних — лишний риск, поэтому граница проведена в коде, а не в
регламенте.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit, reports, snapshots
from ..database import get_db
from ..models import Activity, Alert, Psychologist, School, SchoolClass, Student, Survey
from ..participation import consent_status_bulk
from ..permissions import require_school_view, require_school_view_download

router = APIRouter(prefix="/api/school", tags=["school"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _rows(db, school_id):
    classes = (
        db.query(SchoolClass)
        .filter(SchoolClass.school_id == school_id)
        .order_by(SchoolClass.name)
        .all()
    )
    ids = [c.id for c in classes] or [0]
    counts = dict(
        db.query(Student.class_id, func.count(Student.id))
        .filter(Student.class_id.in_(ids), Student.is_active.is_(True))
        .group_by(Student.class_id).all()
    )
    open_alerts = dict(
        db.query(Alert.class_id, func.count(Alert.id))
        .filter(Alert.class_id.in_(ids), Alert.resolved_at.is_(None))
        .group_by(Alert.class_id).all()
    )
    # Профилактика: сколько запланировано и проведено по каждому классу. Это
    # отчётность психолога перед завучем, поэтому она в сводке школы.
    planned = dict(
        db.query(Activity.class_id, func.count(Activity.id))
        .filter(Activity.class_id.in_(ids), Activity.status == "planned")
        .group_by(Activity.class_id).all()
    )
    conducted = dict(
        db.query(Activity.class_id, func.count(Activity.id))
        .filter(Activity.class_id.in_(ids), Activity.status == "done")
        .group_by(Activity.class_id).all()
    )
    staff = dict(
        db.query(Psychologist.id, Psychologist.full_name)
        .filter(Psychologist.school_id == school_id).all()
    )
    consents = consent_status_bulk(db, ids)

    latest = snapshots.last_closed_surveys(db, ids)

    rows = []
    for c in classes:
        last = latest.get(c.id)
        row = {
            "class_id": c.id,
            "class_name": c.name,
            "psychologist": staff.get(c.psychologist_id),
            "students": counts.get(c.id, 0),
            # Число оповещений — управленческий сигнал «сходите в этот класс».
            # Кто именно в них фигурирует, завучу не показывается.
            "open_alerts": open_alerts.get(c.id, 0),
            "consent_missing": len(consents.get(c.id, {}).get("missing", [])),
            "activities_planned": planned.get(c.id, 0),
            "activities_done": conducted.get(c.id, 0),
            "last_survey": None,
            "participation": None,
            "reliability": None,
            "wellbeing_index": None,
            "isolates": None,
        }
        if last is not None:
            gm = snapshots.analysis_for_survey(db, last)["graph_metrics"]
            row.update({
                "last_survey": last.conducted_on.isoformat() if last.conducted_on else None,
                "last_survey_title": last.title,
                "participation": gm["participation"],
                "reliability": gm["reliability"],
                "wellbeing_index": gm["wellbeing_index"],
                "isolates": gm["isolates"],
            })
        rows.append(row)
    return classes, rows


@router.get("/summary")
def summary(user: Psychologist = Depends(require_school_view), db: Session = Depends(get_db)):
    school = db.get(School, user.school_id)
    _, rows = _rows(db, user.school_id)

    graded = [r for r in rows if r["wellbeing_index"] is not None]
    totals = {
        "classes": len(rows),
        "students": sum(r["students"] for r in rows),
        "classes_without_surveys": sum(1 for r in rows if not r["last_survey"]),
        "open_alerts": sum(r["open_alerts"] for r in rows),
        "consent_missing": sum(r["consent_missing"] for r in rows),
        "avg_wellbeing": round(sum(r["wellbeing_index"] for r in graded) / len(graded)) if graded else None,
        "low_reliability": sum(1 for r in rows if r["reliability"] == "low"),
        "activities_planned": sum(r["activities_planned"] for r in rows),
        "activities_done": sum(r["activities_done"] for r in rows),
        # Классы, где есть тревожные сигналы, но профилактика не запланирована,
        # — главный управленческий вопрос завуча к психологу.
        "alerts_without_activities": sum(
            1 for r in rows
            if r["open_alerts"] and not r["activities_planned"] and not r["activities_done"]
        ),
    }
    # Сначала классы, которым нужно внимание.
    rows.sort(key=lambda r: (
        -(r["open_alerts"] or 0),
        r["wellbeing_index"] if r["wellbeing_index"] is not None else 999,
        r["class_name"],
    ))
    db.commit()  # снапшоты, посчитанные по дороге
    return {
        "school": {"id": school.id, "name": school.name, "city": school.city} if school else None,
        "totals": totals,
        "classes": rows,
    }


@router.get("/export.xlsx")
def export_summary(request: Request, user: Psychologist = Depends(require_school_view_download), db: Session = Depends(get_db)):
    school = db.get(School, user.school_id)
    _, rows = _rows(db, user.school_id)
    buf = reports.school_report(school.name if school else "", rows)
    audit.log(db, user, audit.EXPORT_CLASS, "school", user.school_id, request)
    db.commit()
    return StreamingResponse(
        buf, media_type=XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="izolyat_school.xlsx"'},
    )
