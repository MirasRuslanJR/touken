"""Кабинет психолога: классы, ученики, согласия, срезы, билеты, аналитика,
карточка ученика, отчёты.

Все эндпоинты этого роутера требуют роли психолога: здесь персональные данные
конкретных детей. Завуч работает со сводкой по школе (routers/school.py), где
поимённой информации нет вовсе.
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import alerts as alerts_service
from .. import audit, reports, snapshots
from ..analytics import ALONE_MIN_REPORT, student_survey_summary
from ..config import QUESTIONS, effective_questions, serialize_questions
from ..database import get_db
from ..imports import parse_student_file
from ..models import (
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
    SurveySnapshot,
    SurveyTicket,
)
from ..participation import (
    consent_status,
    consent_status_bulk,
    issue_tickets,
    reissue_ticket,
    students_with_consent,
)
from ..permissions import require_casework, require_casework_download
from ..retention import DEFAULT_RETENTION_MONTHS, default_retention_until
from ..schemas import (
    BulkConsentIn,
    BulkStudentsIn,
    ClassIn,
    ClassSettingsIn,
    ConsentIn,
    InterventionIn,
    MeetingIn,
    NoteIn,
    StudentIn,
    SurveyIn,
    SurveyPatch,
)
from ..security import generate_code

router = APIRouter(prefix="/api", tags=["dashboard"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ------------------------------------------------------------- helpers
def iso(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def parse_date(s):
    """ISO-дата или None. Пустая строка = не задано."""
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def require_date(s, field="дата"):
    """То же, но с явной ошибкой вместо тихой подмены.

    Раньше битая дата молча превращалась в None и подменялась «сегодня»:
    психолог указывал дату среза, получал другую и об этом не узнавал.
    """
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


def safe_filename(name, suffix):
    """ASCII-имя файла: кириллица в заголовке Content-Disposition ломает
    скачивание в части браузеров."""
    base = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (name or "class"))
    base = base.encode("ascii", "ignore").decode("ascii").strip("_") or "izolyat"
    return "izolyat_%s%s" % (base, suffix)


def class_dict(c):
    return {
        "id": c.id, "name": c.name, "description": c.description,
        "retention_until": iso(c.retention_until), "created_at": iso(c.created_at),
    }


def student_dict(s):
    return {
        "id": s.id, "class_id": s.class_id, "full_name": s.full_name, "code": s.code,
        "gender": s.gender, "birth_date": iso(s.birth_date), "note": s.note,
        "is_active": bool(s.is_active),
    }


def survey_dict(sv, response_count=None, participant_count=None):
    d = {
        "id": sv.id, "class_id": sv.class_id, "title": sv.title,
        "conducted_on": iso(sv.conducted_on), "is_open": bool(sv.is_open),
        "questions": effective_questions(sv),
        "closed_at": iso(sv.closed_at),
        "created_at": iso(sv.created_at),
    }
    if response_count is not None:
        d["response_count"] = response_count
    if participant_count is not None:
        d["participant_count"] = participant_count
    return d


def consent_dict(c):
    return {
        "id": c.id, "kind": c.kind, "obtained_on": iso(c.obtained_on),
        "document_ref": c.document_ref, "revoked_on": iso(c.revoked_on),
    }


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


def unique_code(db, used=None):
    used = used if used is not None else set()
    for _ in range(80):
        code = generate_code()
        if code in used:
            continue
        if db.query(Student).filter(Student.code == code).first():
            continue
        if db.query(SurveyTicket).filter(SurveyTicket.code == code).first():
            continue
        used.add(code)
        return code
    raise HTTPException(500, "Не удалось сгенерировать код")


# ---------------------------------------------------------------- classes
@router.get("/classes")
def list_classes(user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    rows = db.query(SchoolClass).filter(SchoolClass.psychologist_id == user.id).order_by(SchoolClass.created_at).all()
    return {"classes": [class_dict(c) for c in rows]}


@router.get("/overview")
def overview(user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Домашний экран: все классы психолога, отсортированные по риску.

    Работа психолога — 250-300 учеников в десятке классов. Открывать каждый
    класс по очереди, чтобы понять, где что-то происходит, невозможно; поэтому
    сводка считается по снапшотам и показывает, куда смотреть в первую очередь.
    """
    classes = db.query(SchoolClass).filter(SchoolClass.psychologist_id == user.id).order_by(SchoolClass.name).all()
    class_ids = [c.id for c in classes]

    counts = dict(
        db.query(Student.class_id, func.count(Student.id))
        .filter(Student.class_id.in_(class_ids or [0]), Student.is_active.is_(True))
        .group_by(Student.class_id).all()
    )
    open_alerts = dict(
        db.query(alerts_service.Alert.class_id, func.count(alerts_service.Alert.id))
        .filter(alerts_service.Alert.psychologist_id == user.id,
                alerts_service.Alert.resolved_at.is_(None))
        .group_by(alerts_service.Alert.class_id).all()
    )

    consents = consent_status_bulk(db, class_ids)
    latest = snapshots.last_closed_surveys(db, class_ids)

    rows = []
    for c in classes:
        last = latest.get(c.id)
        row = {
            "class": class_dict(c),
            "students": counts.get(c.id, 0),
            "open_alerts": open_alerts.get(c.id, 0),
            "consent": consents.get(c.id, {"total": 0, "with_consent": 0, "missing": []}),
            "last_survey": None,
            "wellbeing_index": None,
            "isolates": None,
            "participation": None,
            "reliability": None,
        }
        if last is not None:
            gm = snapshots.analysis_for_survey(db, last)["graph_metrics"]
            row.update({
                "last_survey": {"id": last.id, "title": last.title, "conducted_on": iso(last.conducted_on)},
                "wellbeing_index": gm["wellbeing_index"],
                "isolates": gm["isolates"],
                "participation": gm["participation"],
                "reliability": gm["reliability"],
            })
        rows.append(row)

    # Сортировка по «нужности внимания»: сначала классы с оповещениями, затем с
    # изолятами, затем с низким индексом. Классы без срезов — в конце, но с
    # явным призывом провести срез.
    def risk(r):
        return (
            -(r["open_alerts"] or 0),
            -(r["isolates"] or 0),
            r["wellbeing_index"] if r["wellbeing_index"] is not None else 999,
            r["class"]["name"],
        )

    rows.sort(key=risk)
    db.commit()  # снапшоты, посчитанные по дороге
    return {"classes": rows, "alone_threshold": ALONE_MIN_REPORT}


@router.post("/classes")
def create_class(data: ClassIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    school = db.get(School, user.school_id) if user.school_id else None
    c = SchoolClass(
        psychologist_id=user.id,
        school_id=user.school_id,
        name=data.name.strip(),
        description=clean(data.description),
        # Срок хранения сырых ответов проставляется сразу: политика по умолчанию
        # лучше, чем её отсутствие (см. app/retention.py).
        retention_until=default_retention_until(school),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"class": class_dict(c)}


@router.put("/classes/{cid}")
def update_class(cid: int, data: ClassIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    c = owned_class(db, cid, user)
    c.name = data.name.strip()
    c.description = clean(data.description)
    db.commit()
    return {"class": class_dict(c)}


@router.put("/classes/{cid}/settings")
def update_class_settings(
    cid: int,
    data: ClassSettingsIn,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Срок хранения сырых ответов класса.

    Дату можно только приблизить, но не отодвинуть дальше политики школы:
    иначе «хранить бессрочно» ставилось бы одним кликом, и весь смысл
    ограничения пропадал бы.
    """
    c = owned_class(db, cid, user)
    school = db.get(School, c.school_id) if c.school_id else None
    limit = default_retention_until(school)
    requested = require_date(data.retention_until, "дата хранения")
    if requested is None:
        raise HTTPException(400, "Укажите дату в формате ГГГГ-ММ-ДД")
    if requested > limit:
        raise HTTPException(
            409,
            "Срок хранения нельзя продлить дальше %s — это политика школы (%d мес.)."
            % (limit.isoformat(), (school.retention_months if school else DEFAULT_RETENTION_MONTHS)),
        )
    c.retention_until = requested
    db.commit()
    return {"class": class_dict(c)}


@router.delete("/classes/{cid}")
def delete_class(cid: int, request: Request, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    c = owned_class(db, cid, user)
    audit.log(db, user, audit.DELETE_CLASS, "class", cid, request)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/classes/{cid}")
def class_overview(cid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    c = owned_class(db, cid, user)
    students = db.query(Student).filter(Student.class_id == cid).order_by(Student.full_name).all()
    # Сортировка по паре (дата, id): в один день можно провести два среза, и
    # без вторичного ключа их порядок был бы произвольным — а от него зависит
    # и Time Slider, и то, какой срез считается предыдущим.
    surveys = db.query(Survey).filter(Survey.class_id == cid).order_by(Survey.conducted_on, Survey.id).all()

    # Один GROUP BY вместо COUNT(*) на каждый срез.
    counts = dict(
        db.query(SurveyResponse.survey_id, func.count(SurveyResponse.id))
        .filter(SurveyResponse.survey_id.in_([sv.id for sv in surveys] or [0]))
        .group_by(SurveyResponse.survey_id).all()
    )
    ticket_counts = dict(
        db.query(SurveyTicket.survey_id, func.count(SurveyTicket.id))
        .filter(SurveyTicket.survey_id.in_([sv.id for sv in surveys] or [0]))
        .group_by(SurveyTicket.survey_id).all()
    )
    survey_list = [
        survey_dict(sv, response_count=counts.get(sv.id, 0), participant_count=ticket_counts.get(sv.id, 0))
        for sv in surveys
    ]

    consents = {}
    for row in db.query(Consent).filter(Consent.student_id.in_([s.id for s in students] or [0])).all():
        consents.setdefault(row.student_id, []).append(consent_dict(row))

    return {
        "class": class_dict(c),
        "students": [dict(student_dict(s), consents=consents.get(s.id, [])) for s in students],
        "surveys": survey_list,
        "consent": consent_status(db, cid),
    }


# --------------------------------------------------------------- students
@router.post("/classes/{cid}/students")
def create_student(cid: int, data: StudentIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    owned_class(db, cid, user)
    s = Student(
        class_id=cid, psychologist_id=user.id, full_name=data.full_name.strip(),
        code=unique_code(db), gender=clean(data.gender),
        birth_date=require_date(data.birth_date, "дата рождения"),
        note=clean(data.note),
    )
    db.add(s)
    snapshots.invalidate_class(db, cid)
    db.commit()
    db.refresh(s)
    return {"student": student_dict(s)}


@router.put("/students/{sid}")
def update_student(sid: int, data: StudentIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    s = owned_student(db, sid, user)
    s.full_name = data.full_name.strip()
    s.gender = clean(data.gender)
    s.birth_date = require_date(data.birth_date, "дата рождения")
    s.note = clean(data.note)
    if data.is_active is not None:
        s.is_active = bool(data.is_active)
        snapshots.invalidate_class(db, s.class_id)
    db.commit()
    return {"student": student_dict(s)}


@router.delete("/students/{sid}")
def delete_student(sid: int, request: Request, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    s = owned_student(db, sid, user)
    audit.log(db, user, audit.DELETE_STUDENT, "student", sid, request)
    snapshots.invalidate_class(db, s.class_id)
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/classes/{cid}/students/import")
async def import_students(
    cid: int,
    file: UploadFile = File(...),
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Разбор списка учеников из .xlsx/.csv — на сервере.

    Раньше файл разбирался в браузере библиотекой SheetJS с CDN: в школьной
    сети без доступа к cdnjs импорт просто не работал. openpyxl уже стоит ради
    экспорта, так что дополнительной зависимости это не добавляет.
    """
    owned_class(db, cid, user)
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "Файл слишком большой (максимум 2 МБ)")
    try:
        rows = parse_student_file(file.filename or "", raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not rows:
        raise HTTPException(400, "В файле не найдено ни одного имени")
    return {"students": rows}


@router.post("/classes/{cid}/students/bulk")
def bulk_create_students(
    cid: int,
    data: BulkStudentsIn,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Массовое добавление учеников (импорт из Excel/CSV/списка).

    Количество ограничено схемой: класс в школе — это десятки человек, а не
    тысячи, и без ограничения один запрос мог бы вставить сколько угодно строк.
    """
    owned_class(db, cid, user)
    used = set()
    created = []
    seen_names = set()
    for it in data.students:
        name = (it.full_name or "").strip()
        if not name:
            continue
        # Один и тот же ученик дважды в списке — обычное дело при копировании
        # из журнала. Заводить его двумя записями нельзя: он попадёт в срез
        # дважды и исказит явку.
        key = name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        s = Student(
            class_id=cid, psychologist_id=user.id, full_name=name[:255], code=unique_code(db, used),
            gender=clean(it.gender), birth_date=parse_date(it.birth_date),
        )
        db.add(s)
        db.flush()
        created.append(s)
    snapshots.invalidate_class(db, cid)
    db.commit()
    return {"count": len(created), "students": [student_dict(s) for s in created]}


# --------------------------------------------------------------- consents
@router.post("/students/{sid}/consent")
def add_consent(sid: int, data: ConsentIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Отметить полученное согласие на обработку данных ученика.

    Без него ученик не участвует в срезах вообще — ему не выдаётся билет и
    одноклассники не видят его в списке выбора.
    """
    s = owned_student(db, sid, user)
    c = Consent(
        student_id=s.id,
        kind=(data.kind or "parent").strip()[:20],
        obtained_on=require_date(data.obtained_on, "дата получения согласия") or date.today(),
        document_ref=clean(data.document_ref),
        created_by=user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"consent": consent_dict(c)}


@router.post("/classes/{cid}/consents/bulk")
def bulk_consent(
    cid: int,
    data: BulkConsentIn,
    user: Psychologist = Depends(require_casework),
    db: Session = Depends(get_db),
):
    """Отметить согласия сразу нескольким ученикам класса.

    Согласия собирают пачкой — на родительском собрании приносят стопку
    подписанных бланков. Отмечать их по одному в интерфейсе никто не станет,
    и в итоге срез запустили бы вообще без отметок.

    Идемпотентно: у кого действующее согласие уже есть, тому второе не заводим.
    """
    owned_class(db, cid, user)
    today = date.today()
    obtained = require_date(data.obtained_on, "дата получения согласия") or today

    ids = set(data.student_ids or [])
    q = db.query(Student).filter(Student.class_id == cid, Student.is_active.is_(True))
    if ids:
        q = q.filter(Student.id.in_(ids))
    targets = q.all()

    already = {s.id for s in students_with_consent(db, cid, today)}
    created = []
    for s in targets:
        if s.id in already:
            continue
        db.add(Consent(
            student_id=s.id, kind=(data.kind or "parent").strip()[:20],
            obtained_on=obtained, document_ref=clean(data.document_ref), created_by=user.id,
        ))
        created.append(s.id)
    db.commit()
    return {"count": len(created), "consent": consent_status(db, cid)}


@router.delete("/consents/{consent_id}")
def revoke_consent(consent_id: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Отзыв согласия. Ученик перестаёт участвовать в новых срезах; прошлые
    данные удаляются по общей политике хранения."""
    c = db.get(Consent, consent_id)
    if not c:
        raise HTTPException(404, "Согласие не найдено")
    owned_student(db, c.student_id, user)
    c.revoked_on = date.today()
    db.commit()
    return {"consent": consent_dict(c)}


# ---------------------------------------------------------------- surveys
@router.post("/classes/{cid}/surveys")
def create_survey(cid: int, data: SurveyIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    owned_class(db, cid, user)
    status = consent_status(db, cid)
    if status["with_consent"] == 0:
        raise HTTPException(
            409,
            "Нельзя запустить срез: ни у одного ученика класса не отмечено согласие "
            "на обработку персональных данных.",
        )
    sv = Survey(
        class_id=cid, psychologist_id=user.id, title=data.title.strip(),
        conducted_on=require_date(data.conducted_on, "дата проведения") or date.today(), is_open=True,
        questions=serialize_questions(data.questions),
    )
    db.add(sv)
    db.flush()
    tickets = issue_tickets(db, sv)
    db.commit()
    db.refresh(sv)
    return {
        "survey": survey_dict(sv, response_count=0, participant_count=len(tickets)),
        "excluded": status["missing"],
    }


@router.put("/surveys/{svid}")
def update_survey(svid: int, data: SurveyPatch, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    sv = owned_survey(db, svid, user)
    was_open = bool(sv.is_open)

    if data.title is not None:
        sv.title = data.title.strip() or sv.title
    if data.conducted_on is not None:
        sv.conducted_on = require_date(data.conducted_on, "дата проведения") or sv.conducted_on
    if data.questions is not None:
        if db.query(SurveyResponse).filter(SurveyResponse.survey_id == sv.id).first():
            raise HTTPException(409, "Нельзя менять вопросы: по срезу уже есть ответы")
        sv.questions = serialize_questions(data.questions)

    created_alerts = []
    if data.is_open is not None and bool(data.is_open) != was_open:
        sv.is_open = bool(data.is_open)
        if not sv.is_open:
            # Срез закрыт: фиксируем снапшот и создаём оповещения. Именно здесь,
            # а не в браузере при открытии класса, — иначе их никто не находит.
            sv.closed_at = datetime.now(timezone.utc)
            db.flush()
            snapshots.store_snapshot(db, sv)
            created_alerts = alerts_service.generate_for_survey(db, sv)
        else:
            # Опрос снова открыт — посчитанный результат больше не окончателен.
            sv.closed_at = None
            snapshots.invalidate(db, sv.id)

    db.commit()
    rc = db.query(SurveyResponse).filter(SurveyResponse.survey_id == sv.id).count()
    tc = db.query(SurveyTicket).filter(SurveyTicket.survey_id == sv.id).count()
    return {
        "survey": survey_dict(sv, response_count=rc, participant_count=tc),
        "alerts_created": len(created_alerts),
    }


@router.delete("/surveys/{svid}")
def delete_survey(svid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    sv = owned_survey(db, svid, user)
    db.delete(sv)
    db.commit()
    return {"ok": True}


@router.get("/surveys/{svid}/tickets")
def survey_tickets(svid: int, request: Request, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Коды для раздачи ученикам. Одноразовые и действуют только в этом срезе."""
    sv = owned_survey(db, svid, user)
    audit.log(db, user, audit.VIEW_CODES, "survey", svid, request)
    rows = (
        db.query(SurveyTicket, Student)
        .join(Student, Student.id == SurveyTicket.student_id)
        .filter(SurveyTicket.survey_id == svid)
        .order_by(Student.full_name)
        .all()
    )
    responded = {
        r.student_id for r in db.query(SurveyResponse).filter(SurveyResponse.survey_id == svid).all()
    }
    db.commit()
    return {
        "survey": survey_dict(sv),
        "class": class_dict(db.get(SchoolClass, sv.class_id)),
        "tickets": [{
            "student_id": s.id, "full_name": s.full_name, "code": t.code,
            "done": s.id in responded,
        } for (t, s) in rows],
        "excluded": consent_status(db, sv.class_id)["missing"],
    }


@router.post("/surveys/{svid}/tickets/refresh")
def refresh_tickets(svid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Довыдать билеты — например, если после запуска среза добавили ученика
    или отметили согласие."""
    sv = owned_survey(db, svid, user)
    if not sv.is_open:
        raise HTTPException(
            409, "Срез закрыт — новые коды не выдаются. Откройте опрос, если нужно дособрать ответы.")
    tickets = issue_tickets(db, sv)
    db.commit()
    return {"count": len(tickets)}


@router.post("/surveys/{svid}/students/{sid}/reissue")
def reissue(svid: int, sid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    """Перевыпуск кода одному ученику: код подсмотрели или ответили за него.

    Заодно снимает отметку о прохождении и удаляет его ответы — иначе чужие
    ответы остались бы в графе.

    Только на открытом срезе. На закрытом это удалило бы ответы из уже
    зафиксированного результата: снапшот посчитан, по нему созданы оповещения
    и, возможно, запланирована профилактика — менять его задним числом нельзя.
    """
    sv = owned_survey(db, svid, user)
    if not sv.is_open:
        raise HTTPException(
            409,
            "Срез закрыт — перевыпустить код нельзя. Результат уже зафиксирован. "
            "Если нужно исправить данные, откройте опрос заново.",
        )
    owned_student(db, sid, user)
    db.query(Choice).filter(Choice.survey_id == svid, Choice.from_student == sid).delete(synchronize_session=False)
    db.query(SurveyResponse).filter(
        SurveyResponse.survey_id == svid, SurveyResponse.student_id == sid
    ).delete(synchronize_session=False)
    ticket = reissue_ticket(db, svid, sid)
    snapshots.invalidate(db, svid)
    db.commit()
    return {"code": ticket.code}


@router.get("/surveys/{svid}/analytics")
def survey_analytics(svid: int, request: Request, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    sv = owned_survey(db, svid, user)
    result = snapshots.analysis_for_survey(db, sv)

    students = db.query(Student).filter(Student.class_id == sv.class_id).order_by(Student.full_name).all()
    responded = [r.student_id for r in db.query(SurveyResponse).filter(SurveyResponse.survey_id == svid).all()]
    rc = len(responded)
    tc = db.query(SurveyTicket).filter(SurveyTicket.survey_id == svid).count()

    result["survey"] = survey_dict(sv, response_count=rc, participant_count=tc)
    result["students"] = [{"id": s.id, "full_name": s.full_name} for s in students]
    result["responded_ids"] = responded
    result["questions"] = effective_questions(sv)
    result["alone_threshold"] = ALONE_MIN_REPORT

    audit.log(db, user, audit.VIEW_ANALYTICS, "survey", svid, request)
    db.commit()
    return result


@router.get("/surveys/{svid}/export.xlsx")
def export_survey(svid: int, request: Request, user: Psychologist = Depends(require_casework_download), db: Session = Depends(get_db)):
    """Отчёт по срезу в Excel — собирается на сервере.

    Раньше файл строился в браузере библиотекой с CDN: без интернета кнопка не
    работала, а школьные сети cdnjs фильтруют.
    """
    sv = owned_survey(db, svid, user)
    cls = db.get(SchoolClass, sv.class_id)
    analysis = snapshots.analysis_for_survey(db, sv)
    students = db.query(Student).filter(Student.class_id == sv.class_id).order_by(Student.full_name).all()

    buf = reports.class_report(
        cls.name if cls else "",
        {"title": sv.title, "conducted_on": iso(sv.conducted_on)},
        analysis,
        [{"id": s.id, "full_name": s.full_name} for s in students],
        threshold=ALONE_MIN_REPORT,
    )
    audit.log(db, user, audit.EXPORT_CLASS, "survey", svid, request)
    db.commit()
    fname = safe_filename(cls.name if cls else "class", "_%s.xlsx" % iso(sv.conducted_on))
    return StreamingResponse(
        buf, media_type=XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="%s"' % fname},
    )


# ---------------------------------------------------------- student card
@router.get("/students/{sid}/card")
def student_card(sid: int, request: Request, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    student = owned_student(db, sid, user)
    school_class = db.get(SchoolClass, student.class_id)
    roster = db.query(Student).filter(Student.class_id == student.class_id).order_by(Student.full_name).all()
    roster_min = [{"id": r.id, "full_name": r.full_name} for r in roster]
    name_by_id = {r["id"]: r["full_name"] for r in roster_min}
    surveys = (
        db.query(Survey)
        .filter(Survey.class_id == student.class_id)
        .order_by(Survey.conducted_on, Survey.id)
        .all()
    )

    survey_ids = [sv.id for sv in surveys]
    choices_by_survey = {sv.id: [] for sv in surveys}
    responded_by_survey = {sv.id: [] for sv in surveys}
    purged = set()
    if survey_ids:
        for c in db.query(Choice).filter(Choice.survey_id.in_(survey_ids)).all():
            choices_by_survey.setdefault(c.survey_id, []).append(
                {"from_student": c.from_student, "to_student": c.to_student, "question": c.question}
            )
        for r in db.query(SurveyResponse).filter(SurveyResponse.survey_id.in_(survey_ids)).all():
            responded_by_survey.setdefault(r.survey_id, []).append(r.student_id)
        purged = {
            s.survey_id for s in db.query(SurveySnapshot)
            .filter(SurveySnapshot.survey_id.in_(survey_ids), SurveySnapshot.raw_purged.is_(True)).all()
        }

    # Сырые выборы (кто кого выбрал) наружу НЕ отдаются — только агрегаты и
    # взаимные пары, см. заголовок app/analytics.py. Поимённый список «кто
    # отметил тебя одиноким» здесь был раньше и снят сознательно: ученику на
    # странице опроса обещано, что этого не увидит никто.
    dynamics = []
    for sv in surveys:
        if sv.id in purged:
            # Сырые данные удалены по сроку хранения — берём из снапшота.
            snap = snapshots.analysis_for_survey(db, sv)
            m = snap["per_student"].get(str(sid))
            if not m:
                continue
            dynamics.append({
                "survey_id": sv.id, "title": sv.title, "date": iso(sv.conducted_on),
                "in_degree": m["in_degree"], "out_degree": m["out_degree"], "mutual": m["mutual"],
                "mutual_names": [], "alone_count": m["alone_votes"] if m["alone_reportable"] else None,
                "status": m["status"], "is_isolate": m["is_isolate"], "responded": m["responded"],
                "participation": snap["graph_metrics"]["participation"],
                "reliability": snap["graph_metrics"]["reliability"],
                "betweenness": m["betweenness"], "community": m["community"], "archived": True,
            })
            continue

        s = student_survey_summary(
            sid, roster_min, choices_by_survey.get(sv.id, []), responded_by_survey.get(sv.id, [])
        )
        dynamics.append({
            "survey_id": sv.id, "title": sv.title, "date": iso(sv.conducted_on),
            "in_degree": s["in_count"], "out_degree": s["out_count"], "mutual": s["mutual_count"],
            "mutual_names": [name_by_id[mid] for mid in s["mutual_ids"] if mid in name_by_id],
            "alone_count": s["alone_count"], "status": s["status"],
            "is_isolate": s["status"] == "isolate", "responded": s["responded"],
            "participation": s["participation"], "reliability": s["reliability"],
            "betweenness": None, "community": None, "archived": False,
        })

    # Полный граф (betweenness, сообщество) строим один раз — только для
    # последнего среза. Раньше он строился по разу на каждый срез, то есть
    # betweenness O(V·E) считался N раз при каждом открытии карточки.
    if dynamics and not dynamics[-1]["archived"]:
        full = snapshots.analysis_for_survey(db, surveys[-1])
        m = full["per_student"].get(str(sid))
        if m:
            dynamics[-1]["betweenness"] = m["betweenness"]
            dynamics[-1]["community"] = m["community"]

    notes = db.query(Note).filter(Note.student_id == sid).order_by(Note.created_at.desc()).all()
    meetings = db.query(Meeting).filter(Meeting.student_id == sid).order_by(Meeting.met_on.desc()).all()
    interventions = db.query(Intervention).filter(Intervention.student_id == sid).order_by(Intervention.started_on.desc()).all()
    consents = db.query(Consent).filter(Consent.student_id == sid).order_by(Consent.obtained_on.desc()).all()

    audit.log(db, user, audit.VIEW_STUDENT_CARD, "student", sid, request)
    db.commit()

    return {
        "student": student_dict(student),
        "class": class_dict(school_class) if school_class else None,
        "consents": [consent_dict(c) for c in consents],
        "surveys": [{"id": sv.id, "title": sv.title, "conducted_on": iso(sv.conducted_on)} for sv in surveys],
        "dynamics": dynamics,
        "alone_threshold": ALONE_MIN_REPORT,
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
def add_note(sid: int, data: NoteIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    owned_student(db, sid, user)
    n = Note(student_id=sid, psychologist_id=user.id, body=data.body.strip())
    db.add(n)
    db.commit()
    db.refresh(n)
    return {"note": {"id": n.id, "body": n.body, "created_at": iso(n.created_at)}}


@router.delete("/notes/{nid}")
def delete_note(nid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    n = db.get(Note, nid)
    if not n or n.psychologist_id != user.id:
        raise HTTPException(404, "Заметка не найдена")
    db.delete(n)
    db.commit()
    return {"ok": True}


@router.post("/students/{sid}/meetings")
def add_meeting(sid: int, data: MeetingIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    owned_student(db, sid, user)
    m = Meeting(student_id=sid, psychologist_id=user.id, met_on=require_date(data.met_on, "дата встречи") or date.today(), summary=clean(data.summary))
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"meeting": {"id": m.id, "met_on": iso(m.met_on), "summary": m.summary}}


@router.delete("/meetings/{mid}")
def delete_meeting(mid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    m = db.get(Meeting, mid)
    if not m or m.psychologist_id != user.id:
        raise HTTPException(404, "Встреча не найдена")
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("/students/{sid}/interventions")
def add_intervention(sid: int, data: InterventionIn, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    owned_student(db, sid, user)
    eff = data.effectiveness
    if eff is not None and (eff < 1 or eff > 5):
        eff = None
    iv = Intervention(
        student_id=sid, psychologist_id=user.id, title=data.title.strip(),
        description=clean(data.description),
        started_on=require_date(data.started_on, "дата начала") or date.today(),
        ended_on=require_date(data.ended_on, "дата окончания"), effectiveness=eff, outcome=clean(data.outcome),
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
def delete_intervention(iid: int, user: Psychologist = Depends(require_casework), db: Session = Depends(get_db)):
    iv = db.get(Intervention, iid)
    if not iv or iv.psychologist_id != user.id:
        raise HTTPException(404, "Вмешательство не найдено")
    db.delete(iv)
    db.commit()
    return {"ok": True}
