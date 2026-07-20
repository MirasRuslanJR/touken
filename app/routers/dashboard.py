"""All authenticated psychologist endpoints: classes, students, codes,
surveys, analytics and the student card."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import analytics
from ..config import QUESTIONS, effective_questions, serialize_questions
from ..database import get_db
from ..models import (
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
from ..schemas import (
    ClassIn,
    InterventionIn,
    MeetingIn,
    NoteIn,
    StudentIn,
    SurveyIn,
    SurveyPatch,
)
from ..security import generate_code, get_current_psychologist

router = APIRouter(prefix="/api", tags=["dashboard"])


# ------------------------------------------------------------- helpers
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


def clean(s):
    if s is None:
        return None
    s = str(s).strip()
    return s or None


def class_dict(c):
    return {"id": c.id, "name": c.name, "description": c.description, "created_at": iso(c.created_at)}


def student_dict(s):
    return {
        "id": s.id, "class_id": s.class_id, "full_name": s.full_name, "code": s.code,
        "gender": s.gender, "birth_date": iso(s.birth_date), "note": s.note,
    }


def survey_dict(sv, response_count=None):
    d = {
        "id": sv.id, "class_id": sv.class_id, "title": sv.title,
        "conducted_on": iso(sv.conducted_on), "is_open": bool(sv.is_open),
        "questions": effective_questions(sv),
        "created_at": iso(sv.created_at),
    }
    if response_count is not None:
        d["response_count"] = response_count
    return d


def owned_class(db, cid, user):
    c = db.get(SchoolClass, cid)
    if not c or c.psychologist_id != user.id:
        raise HTTPException(404, "Класс не найден")
    return c


def owned_student(db, sid, user):
    s = db.get(Student, sid)
    if not s or s.psychologist_id != user.id:
        raise HTTPException(404, "Ученик не найден")
    return s


def owned_survey(db, svid, user):
    sv = db.get(Survey, svid)
    if not sv or sv.psychologist_id != user.id:
        raise HTTPException(404, "Срез не найден")
    return sv


def unique_code(db):
    for _ in range(50):
        code = generate_code()
        if not db.query(Student).filter(Student.code == code).first():
            return code
    raise HTTPException(500, "Не удалось сгенерировать код")


# ---------------------------------------------------------------- classes
@router.get("/classes")
def list_classes(user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    rows = db.query(SchoolClass).filter(SchoolClass.psychologist_id == user.id).order_by(SchoolClass.created_at).all()
    return {"classes": [class_dict(c) for c in rows]}


@router.post("/classes")
def create_class(data: ClassIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    c = SchoolClass(psychologist_id=user.id, name=data.name.strip(), description=clean(data.description))
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"class": class_dict(c)}


@router.put("/classes/{cid}")
def update_class(cid: int, data: ClassIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    c = owned_class(db, cid, user)
    c.name = data.name.strip()
    c.description = clean(data.description)
    db.commit()
    return {"class": class_dict(c)}


@router.delete("/classes/{cid}")
def delete_class(cid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    c = owned_class(db, cid, user)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/classes/{cid}")
def class_overview(cid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    c = owned_class(db, cid, user)
    students = db.query(Student).filter(Student.class_id == cid).order_by(Student.full_name).all()
    surveys = db.query(Survey).filter(Survey.class_id == cid).order_by(Survey.conducted_on).all()
    survey_list = []
    for sv in surveys:
        rc = db.query(SurveyResponse).filter(SurveyResponse.survey_id == sv.id).count()
        survey_list.append(survey_dict(sv, response_count=rc))
    return {
        "class": class_dict(c),
        "students": [student_dict(s) for s in students],
        "surveys": survey_list,
    }


@router.get("/classes/{cid}/codes")
def class_codes(cid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    c = owned_class(db, cid, user)
    students = db.query(Student).filter(Student.class_id == cid).order_by(Student.full_name).all()
    return {"class": class_dict(c), "codes": [{"full_name": s.full_name, "code": s.code} for s in students]}


# --------------------------------------------------------------- students
@router.post("/classes/{cid}/students")
def create_student(cid: int, data: StudentIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    owned_class(db, cid, user)
    s = Student(
        class_id=cid, psychologist_id=user.id, full_name=data.full_name.strip(),
        code=unique_code(db), gender=clean(data.gender), birth_date=parse_date(data.birth_date),
        note=clean(data.note),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"student": student_dict(s)}


@router.put("/students/{sid}")
def update_student(sid: int, data: StudentIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    s = owned_student(db, sid, user)
    s.full_name = data.full_name.strip()
    s.gender = clean(data.gender)
    s.birth_date = parse_date(data.birth_date)
    s.note = clean(data.note)
    db.commit()
    return {"student": student_dict(s)}


@router.delete("/students/{sid}")
def delete_student(sid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    s = owned_student(db, sid, user)
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/students/{sid}/regenerate-code")
def regenerate_code(sid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    s = owned_student(db, sid, user)
    s.code = unique_code(db)
    db.commit()
    return {"student": student_dict(s)}


@router.post("/classes/{cid}/students/bulk")
def bulk_create_students(cid: int, data: dict, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    """Массовое добавление учеников (импорт из Excel/CSV/списка)."""
    owned_class(db, cid, user)
    items = data.get("students") or []
    used = set()

    def new_code():
        for _ in range(80):
            c = generate_code()
            if c in used or db.query(Student).filter(Student.code == c).first():
                continue
            used.add(c)
            return c
        raise HTTPException(500, "Не удалось сгенерировать код")

    created = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = (it.get("full_name") or "").strip()
        if not name:
            continue
        s = Student(
            class_id=cid, psychologist_id=user.id, full_name=name, code=new_code(),
            gender=clean(it.get("gender")), birth_date=parse_date(it.get("birth_date")),
        )
        db.add(s)
        db.flush()
        created.append(s)
    db.commit()
    return {"count": len(created), "students": [student_dict(s) for s in created]}


# ---------------------------------------------------------------- surveys
@router.post("/classes/{cid}/surveys")
def create_survey(cid: int, data: SurveyIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    owned_class(db, cid, user)
    sv = Survey(
        class_id=cid, psychologist_id=user.id, title=data.title.strip(),
        conducted_on=parse_date(data.conducted_on) or date.today(), is_open=True,
        questions=serialize_questions(data.questions),
    )
    db.add(sv)
    db.commit()
    db.refresh(sv)
    return {"survey": survey_dict(sv, response_count=0)}


@router.put("/surveys/{svid}")
def update_survey(svid: int, data: SurveyPatch, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    sv = owned_survey(db, svid, user)
    if data.title is not None:
        sv.title = data.title.strip() or sv.title
    if data.conducted_on is not None:
        sv.conducted_on = parse_date(data.conducted_on) or sv.conducted_on
    if data.is_open is not None:
        sv.is_open = bool(data.is_open)
    if data.questions is not None:
        if db.query(SurveyResponse).filter(SurveyResponse.survey_id == sv.id).first():
            raise HTTPException(409, "Нельзя менять вопросы: по срезу уже есть ответы")
        sv.questions = serialize_questions(data.questions)
    db.commit()
    rc = db.query(SurveyResponse).filter(SurveyResponse.survey_id == sv.id).count()
    return {"survey": survey_dict(sv, response_count=rc)}


@router.delete("/surveys/{svid}")
def delete_survey(svid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    sv = owned_survey(db, svid, user)
    db.delete(sv)
    db.commit()
    return {"ok": True}


@router.get("/surveys/{svid}/analytics")
def survey_analytics(svid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    sv = owned_survey(db, svid, user)
    students = db.query(Student).filter(Student.class_id == sv.class_id).order_by(Student.full_name).all()
    st = [{"id": s.id, "full_name": s.full_name} for s in students]
    choices = db.query(Choice).filter(Choice.survey_id == svid).all()
    ch = [{"from_student": c.from_student, "to_student": c.to_student, "question": c.question} for c in choices]
    responded = [r.student_id for r in db.query(SurveyResponse).filter(SurveyResponse.survey_id == svid).all()]

    result = analytics.build_analysis(st, ch)
    result["survey"] = survey_dict(sv, response_count=len(responded))
    result["students"] = st
    result["responded_ids"] = responded
    result["questions"] = effective_questions(sv)
    return result


# ---------------------------------------------------------- student card
@router.get("/students/{sid}/card")
def student_card(sid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    student = owned_student(db, sid, user)
    school_class = db.get(SchoolClass, student.class_id)
    roster = db.query(Student).filter(Student.class_id == student.class_id).order_by(Student.full_name).all()
    roster_min = [{"id": r.id, "full_name": r.full_name} for r in roster]
    surveys = db.query(Survey).filter(Survey.class_id == student.class_id).order_by(Survey.conducted_on).all()

    survey_ids = [sv.id for sv in surveys]
    choices_by_survey = {sv.id: [] for sv in surveys}
    if survey_ids:
        all_choices = db.query(Choice).filter(Choice.survey_id.in_(survey_ids)).all()
        for c in all_choices:
            choices_by_survey.setdefault(c.survey_id, []).append(
                {"from_student": c.from_student, "to_student": c.to_student, "question": c.question}
            )

    dynamics = []
    for sv in surveys:
        m = analytics.metrics_for_student(sid, roster_min, choices_by_survey.get(sv.id, []))
        if not m:
            continue
        dynamics.append({
            "survey_id": sv.id, "title": sv.title, "date": iso(sv.conducted_on),
            "in_degree": m["in_degree"], "out_degree": m["out_degree"], "mutual": m["mutual"],
            "alone_votes": m["alone_votes"], "betweenness": m["betweenness"],
            "is_isolate": m["is_isolate"], "community": m["community"],
        })

    notes = db.query(Note).filter(Note.student_id == sid).order_by(Note.created_at.desc()).all()
    meetings = db.query(Meeting).filter(Meeting.student_id == sid).order_by(Meeting.met_on.desc()).all()
    interventions = db.query(Intervention).filter(Intervention.student_id == sid).order_by(Intervention.started_on.desc()).all()

    return {
        "student": student_dict(student),
        "class": class_dict(school_class) if school_class else None,
        "roster": roster_min,
        "surveys": [{"id": sv.id, "title": sv.title, "conducted_on": iso(sv.conducted_on)} for sv in surveys],
        "choices_by_survey": {str(k): v for k, v in choices_by_survey.items()},
        "dynamics": dynamics,
        "notes": [{"id": n.id, "body": n.body, "created_at": iso(n.created_at)} for n in notes],
        "meetings": [{"id": m.id, "met_on": iso(m.met_on), "summary": m.summary} for m in meetings],
        "interventions": [{
            "id": iv.id, "title": iv.title, "description": iv.description,
            "started_on": iso(iv.started_on), "ended_on": iso(iv.ended_on),
            "effectiveness": iv.effectiveness, "outcome": iv.outcome,
        } for iv in interventions],
        "questions": QUESTIONS,
    }


# ----------------------------------------------- notes / meetings / interv.
@router.post("/students/{sid}/notes")
def add_note(sid: int, data: NoteIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    owned_student(db, sid, user)
    n = Note(student_id=sid, psychologist_id=user.id, body=data.body.strip())
    db.add(n)
    db.commit()
    db.refresh(n)
    return {"note": {"id": n.id, "body": n.body, "created_at": iso(n.created_at)}}


@router.delete("/notes/{nid}")
def delete_note(nid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    n = db.get(Note, nid)
    if n and n.psychologist_id == user.id:
        db.delete(n)
        db.commit()
    return {"ok": True}


@router.post("/students/{sid}/meetings")
def add_meeting(sid: int, data: MeetingIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    owned_student(db, sid, user)
    m = Meeting(student_id=sid, psychologist_id=user.id, met_on=parse_date(data.met_on) or date.today(), summary=clean(data.summary))
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"meeting": {"id": m.id, "met_on": iso(m.met_on), "summary": m.summary}}


@router.delete("/meetings/{mid}")
def delete_meeting(mid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    m = db.get(Meeting, mid)
    if m and m.psychologist_id == user.id:
        db.delete(m)
        db.commit()
    return {"ok": True}


@router.post("/students/{sid}/interventions")
def add_intervention(sid: int, data: InterventionIn, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    owned_student(db, sid, user)
    eff = data.effectiveness
    if eff is not None and (eff < 1 or eff > 5):
        eff = None
    iv = Intervention(
        student_id=sid, psychologist_id=user.id, title=data.title.strip(),
        description=clean(data.description), started_on=parse_date(data.started_on) or date.today(),
        ended_on=parse_date(data.ended_on), effectiveness=eff, outcome=clean(data.outcome),
    )
    db.add(iv)
    db.commit()
    db.refresh(iv)
    return {"intervention": {
        "id": iv.id, "title": iv.title, "description": iv.description,
        "started_on": iso(iv.started_on), "ended_on": iso(iv.ended_on),
        "effectiveness": iv.effectiveness, "outcome": iv.outcome,
    }}


@router.delete("/interventions/{iid}")
def delete_intervention(iid: int, user: Psychologist = Depends(get_current_psychologist), db: Session = Depends(get_db)):
    iv = db.get(Intervention, iid)
    if iv and iv.psychologist_id == user.id:
        db.delete(iv)
        db.commit()
    return {"ok": True}
