"""Профилактическая работа психолога: план, проведение, охват, эффект.

Что здесь есть и чего нет:

* мероприятия планируются, проводятся и отмечаются — это то, за что психолог
  отчитывается перед завучем;
* рекомендации строятся по данным среза и только на достоверном срезе;
* эффект считается сравнением «до/после» по охваченным ученикам, честно
  помеченным как наблюдение, а не доказательство.

Индивидуальная работа с одним ребёнком по-прежнему живёт в карточке ученика
(Intervention) — здесь групповая, у которой есть план и охват.
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .. import audit, snapshots
from ..database import get_db
from ..models import (
    ACTIVITY_KINDS,
    ACTIVITY_TARGETS,
    TARGET_ADULTS,
    TARGET_CLASS,
    Activity,
    ActivityParticipant,
    Psychologist,
    SchoolClass,
    Student,
    Survey,
)
from ..permissions import require_casework
from ..prevention import PLAYBOOK, effect_report, recommendations
from ..schemas import ActivityCompleteIn, ActivityIn, ActivityPatch

router = APIRouter(prefix="/api/prevention", tags=["prevention"])

KIND_TITLES = {
    "training": "Тренинг / групповое занятие",
    "class_hour": "Классный час",
    "diagnostics": "Групповая диагностика",
    "parents": "Работа с родителями",
    "teachers": "Работа с педагогами",
    "individual": "Индивидуальная беседа",
    "other": "Другое",
}
TARGET_TITLES = {
    "class": "Весь класс",
    "group": "Группа учеников",
    "student": "Один ученик",
    "adults": "Родители / педагоги",
}
STATUS_TITLES = {"planned": "Запланировано", "done": "Проведено", "cancelled": "Отменено"}


# ----------------------------------------------------------------- helpers
def iso(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def require_date(s, field="дата"):
    """Явная ошибка вместо тихой подмены: психолог указывает дату занятия и
    должен узнать, если она не разобралась, а не получить «сегодня»."""
    if s is None or str(s).strip() == "":
        return None
    parsed = parse_date(s)
    if parsed is None:
        raise HTTPException(400, "Неверная %s: ожидается формат ГГГГ-ММ-ДД" % field)
    return parsed


def clean(s):
    if s is None:
        return None
    s = str(s).strip()
    return s or None


def owned_class(db, cid, user):
    c = db.get(SchoolClass, cid)
    if not c or c.psychologist_id != user.id:
        raise HTTPException(404, "Класс не найден")
    return c


def owned_activity(db, aid, user):
    a = db.get(Activity, aid)
    if not a or a.psychologist_id != user.id:
        raise HTTPException(404, "Мероприятие не найдено")
    return a


def _validate(kind, target):
    if kind not in ACTIVITY_KINDS:
        raise HTTPException(400, "Неизвестный вид мероприятия")
    if target not in ACTIVITY_TARGETS:
        raise HTTPException(400, "Неизвестный адресат мероприятия")


def load_participants(db, activities):
    """Участники сразу для пачки мероприятий: {activity_id: [ActivityParticipant]}.

    Нужна, чтобы списки не делали по запросу на каждое мероприятие: на экране
    плана их до 300, и N+1 там ощущается сразу.
    """
    ids = [a.id for a in activities] or [0]
    grouped = {a.id: [] for a in activities}
    for p in db.query(ActivityParticipant).filter(ActivityParticipant.activity_id.in_(ids)).all():
        grouped.setdefault(p.activity_id, []).append(p)
    return grouped


def activity_dict(db, a, names=None, parts=None):
    if parts is None:
        parts = db.query(ActivityParticipant).filter(ActivityParticipant.activity_id == a.id).all()
    names = names if names is not None else dict(
        db.query(Student.id, Student.full_name)
        .filter(Student.id.in_([p.student_id for p in parts] or [0])).all()
    )
    return {
        "id": a.id,
        "class_id": a.class_id,
        "source_survey_id": a.source_survey_id,
        "title": a.title,
        "kind": a.kind,
        "kind_title": KIND_TITLES.get(a.kind, a.kind),
        "target": a.target,
        "target_title": TARGET_TITLES.get(a.target, a.target),
        "status": a.status,
        "status_title": STATUS_TITLES.get(a.status, a.status),
        "goal": a.goal,
        "plan": a.plan,
        "outcome": a.outcome,
        "effectiveness": a.effectiveness,
        "planned_on": iso(a.planned_on),
        "conducted_on": iso(a.conducted_on),
        "duration_min": a.duration_min,
        "adults_count": a.adults_count,
        "participants": [{
            "student_id": p.student_id,
            "full_name": names.get(p.student_id, "—"),
            "attended": bool(p.attended),
        } for p in parts],
        "attended_count": sum(1 for p in parts if p.attended),
        "planned_count": len(parts),
    }


def _set_participants(db, activity, student_ids, class_id):
    """Пересобирает список участников.

    Для мероприятия на весь класс состав не фиксируем на этапе плана: к дате
    проведения он мог измениться. Он подставляется в момент отметки.
    """
    db.query(ActivityParticipant).filter(
        ActivityParticipant.activity_id == activity.id
    ).delete(synchronize_session=False)
    if not student_ids:
        return
    allowed = {
        row[0] for row in db.query(Student.id).filter(Student.class_id == class_id).all()
    }
    for sid in dict.fromkeys(student_ids):  # порядок сохраняем, дубли убираем
        if sid in allowed:
            db.add(ActivityParticipant(activity_id=activity.id, student_id=sid))


# ------------------------------------------------------------- расписание
@router.get("/schedule")
def schedule(
    status: str = None,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """План профилактической работы по всем классам психолога.

    Это его рабочий календарь: что запланировано, что просрочено, что проведено.
    """
    q = db.query(Activity).filter(Activity.psychologist_id == user.id)
    if status in ("planned", "done", "cancelled"):
        q = q.filter(Activity.status == status)
    rows = q.order_by(Activity.planned_on.desc(), Activity.id.desc()).limit(300).all()

    class_names = dict(
        db.query(SchoolClass.id, SchoolClass.name)
        .filter(SchoolClass.psychologist_id == user.id).all()
    )
    part_names = dict(
        db.query(Student.id, Student.full_name)
        .filter(Student.psychologist_id == user.id).all()
    )

    parts_by_activity = load_participants(db, rows)
    today = date.today()
    items = []
    for a in rows:
        d = activity_dict(db, a, part_names, parts_by_activity.get(a.id, []))
        d["class_name"] = class_names.get(a.class_id, "—")
        # Просрочено — запланировано, но дата прошла и отметки нет.
        d["overdue"] = a.status == "planned" and a.planned_on is not None and a.planned_on < today
        items.append(d)

    done = [i for i in items if i["status"] == "done"]
    return {
        "activities": items,
        "totals": {
            "planned": sum(1 for i in items if i["status"] == "planned"),
            "overdue": sum(1 for i in items if i["overdue"]),
            "done": len(done),
            "students_covered": len({
                p["student_id"] for i in done for p in i["participants"] if p["attended"]
            }),
            "adults_covered": sum(i["adults_count"] or 0 for i in done),
        },
        "kinds": [{"key": k, "title": v} for k, v in KIND_TITLES.items()],
        "targets": [{"key": k, "title": v} for k, v in TARGET_TITLES.items()],
    }


@router.get("/classes/{cid}/activities")
def class_activities(
    cid: int,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    owned_class(db, cid, user)
    rows = (
        db.query(Activity)
        .filter(Activity.class_id == cid)
        .order_by(Activity.planned_on.desc(), Activity.id.desc())
        .all()
    )
    names = dict(db.query(Student.id, Student.full_name).filter(Student.class_id == cid).all())
    parts_by_activity = load_participants(db, rows)
    today = date.today()
    items = []
    for a in rows:
        d = activity_dict(db, a, names, parts_by_activity.get(a.id, []))
        d["overdue"] = a.status == "planned" and a.planned_on is not None and a.planned_on < today
        items.append(d)
    return {"activities": items}


# ----------------------------------------------------------- рекомендации
@router.get("/classes/{cid}/recommendations")
def class_recommendations(
    cid: int,
    survey_id: int = None,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Что делать по итогам среза.

    По умолчанию берётся последний закрытый срез класса: рекомендовать что-то
    по незакрытому опросу рано — данные ещё меняются.
    """
    owned_class(db, cid, user)
    q = db.query(Survey).filter(Survey.class_id == cid, Survey.is_open.is_(False))
    if survey_id:
        q = q.filter(Survey.id == survey_id)
    sv = q.order_by(Survey.conducted_on.desc(), Survey.id.desc()).first()

    if sv is None:
        return {
            "survey": None,
            "available": False,
            "reason": "Нет ни одного закрытого среза. Проведите опрос и закройте его — "
                      "тогда система предложит, с чего начать.",
            "items": [],
        }

    analysis = snapshots.analysis_for_survey(db, sv)
    names = dict(db.query(Student.id, Student.full_name).filter(Student.class_id == cid).all())
    result = recommendations(analysis, names)
    result["survey"] = {"id": sv.id, "title": sv.title, "conducted_on": iso(sv.conducted_on)}
    db.commit()  # снапшот, если считался по дороге
    return result


@router.get("/playbook")
def playbook(user: Psychologist = Depends(require_casework)):
    """Библиотека готовых сценариев — доступна и без среза."""
    return {
        "items": [dict(code=code, **tmpl) for code, tmpl in PLAYBOOK.items()],
        "kinds": [{"key": k, "title": v} for k, v in KIND_TITLES.items()],
        "targets": [{"key": k, "title": v} for k, v in TARGET_TITLES.items()],
    }


# ----------------------------------------------------- создание и правка
@router.post("/classes/{cid}/activities")
def create_activity(
    cid: int,
    data: ActivityIn,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    owned_class(db, cid, user)
    _validate(data.kind, data.target)

    if data.source_survey_id:
        sv = db.get(Survey, data.source_survey_id)
        if not sv or sv.class_id != cid:
            raise HTTPException(400, "Срез не относится к этому классу")

    a = Activity(
        psychologist_id=user.id, class_id=cid,
        source_survey_id=data.source_survey_id,
        title=data.title.strip(), kind=data.kind, target=data.target,
        goal=clean(data.goal), plan=clean(data.plan),
        planned_on=require_date(data.planned_on, "дата проведения") or date.today(),
        duration_min=data.duration_min,
        status="planned",
    )
    db.add(a)
    db.flush()
    _set_participants(db, a, data.student_ids, cid)
    db.commit()
    db.refresh(a)
    return {"activity": activity_dict(db, a)}


@router.put("/activities/{aid}")
def update_activity(
    aid: int,
    data: ActivityPatch,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    a = owned_activity(db, aid, user)
    if data.kind is not None or data.target is not None:
        _validate(data.kind or a.kind, data.target or a.target)
    if data.title is not None:
        a.title = data.title.strip() or a.title
    if data.kind is not None:
        a.kind = data.kind
    if data.target is not None:
        a.target = data.target
    if data.goal is not None:
        a.goal = clean(data.goal)
    if data.plan is not None:
        a.plan = clean(data.plan)
    if data.planned_on is not None:
        a.planned_on = require_date(data.planned_on, "дата проведения") or a.planned_on
    if data.duration_min is not None:
        a.duration_min = data.duration_min
    if data.student_ids is not None:
        _set_participants(db, a, data.student_ids, a.class_id)
    db.commit()
    db.refresh(a)
    return {"activity": activity_dict(db, a)}


@router.post("/activities/{aid}/complete")
def complete_activity(
    aid: int,
    data: ActivityCompleteIn,
    request: Request,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Отметка о проведении: дата, охват, что получилось.

    Для мероприятия на весь класс охват подставляется на момент проведения, а
    не на момент планирования: за две недели состав класса мог измениться.
    """
    a = owned_activity(db, aid, user)

    if data.attended_ids is not None:
        _set_participants(db, a, data.attended_ids, a.class_id)
    elif a.target == TARGET_CLASS:
        active = [
            row[0] for row in db.query(Student.id)
            .filter(Student.class_id == a.class_id, Student.is_active.is_(True)).all()
        ]
        _set_participants(db, a, active, a.class_id)
    db.flush()

    a.status = "done"
    a.conducted_on = require_date(data.conducted_on, "дата проведения") or date.today()
    a.outcome = clean(data.outcome)
    if data.duration_min is not None:
        a.duration_min = data.duration_min
    if data.adults_count is not None:
        a.adults_count = data.adults_count
    eff = data.effectiveness
    a.effectiveness = eff if eff is not None and 1 <= eff <= 5 else None

    audit.log(db, user, audit.ACTIVITY_DONE, "activity", a.id, request)
    db.commit()
    db.refresh(a)
    return {"activity": activity_dict(db, a)}


@router.post("/activities/{aid}/cancel")
def cancel_activity(
    aid: int,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Отмена запланированного мероприятия.

    Проведённое отменить нельзя: занятие состоялось, охват зафиксирован и
    посчитан в отчётности перед завучем. «Отменить» его задним числом значило
    бы стереть факт выполненной работы — для исправления ошибки есть удаление.
    """
    a = owned_activity(db, aid, user)
    if a.status == "done":
        raise HTTPException(
            409,
            "Мероприятие уже отмечено как проведённое — отменить его нельзя. "
            "Если оно было записано по ошибке, удалите запись.",
        )
    a.status = "cancelled"
    db.commit()
    return {"activity": activity_dict(db, a)}


@router.delete("/activities/{aid}")
def delete_activity(
    aid: int,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    a = owned_activity(db, aid, user)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------- оценка эффекта
@router.get("/activities/{aid}/effect")
def activity_effect(
    aid: int,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Сравнение «до/после» по охваченным ученикам.

    «До» — срез, по итогам которого мероприятие назначено (или последний до
    даты проведения). «После» — первый закрытый срез после проведения.
    """
    a = owned_activity(db, aid, user)
    if a.status != "done":
        return {"available": False, "reason": "Мероприятие ещё не отмечено как проведённое."}

    conducted = a.conducted_on or a.planned_on

    if a.source_survey_id:
        before = db.get(Survey, a.source_survey_id)
    else:
        before = (
            db.query(Survey)
            .filter(Survey.class_id == a.class_id, Survey.is_open.is_(False),
                    Survey.conducted_on <= conducted)
            .order_by(Survey.conducted_on.desc(), Survey.id.desc())
            .first()
        )

    # «После» — первый срез, проведённый позже точки отсчёта. Сравнение идёт по
    # паре (дата, id), а не по одной дате: несколько срезов класса могут стоять
    # одним днём, и тогда сравнение только по дате возвращало бы сам же срез
    # «до» — отчёт показывал нули при реально выросших связях.
    after_q = db.query(Survey).filter(
        Survey.class_id == a.class_id, Survey.is_open.is_(False),
    )
    if before is not None:
        after_q = after_q.filter(
            Survey.id != before.id,
            or_(
                Survey.conducted_on > before.conducted_on,
                and_(Survey.conducted_on == before.conducted_on, Survey.id > before.id),
            ),
        )
    else:
        after_q = after_q.filter(Survey.conducted_on > conducted)
    after = after_q.order_by(Survey.conducted_on, Survey.id).first()

    if before is None or after is None:
        return {
            "available": False,
            "reason": "Нужны два закрытых среза — до мероприятия и после него. "
                      "Проведите следующий срез, чтобы увидеть динамику.",
        }

    covered = [
        p.student_id for p in
        db.query(ActivityParticipant).filter(
            ActivityParticipant.activity_id == a.id, ActivityParticipant.attended.is_(True)
        ).all()
    ]
    report = effect_report(
        snapshots.analysis_for_survey(db, before),
        snapshots.analysis_for_survey(db, after),
        covered,
    )
    names = dict(db.query(Student.id, Student.full_name).filter(Student.class_id == a.class_id).all())
    for row in report.get("details", []):
        row["full_name"] = names.get(row["student_id"], "—")
    report["before"] = {"id": before.id, "title": before.title, "conducted_on": iso(before.conducted_on)}
    report["after"] = {"id": after.id, "title": after.title, "conducted_on": iso(after.conducted_on)}
    db.commit()
    return report
