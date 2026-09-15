"""Аналитика среза: расчёт, кэш и то, что переживает удаление сырых данных.

Единая точка входа `analysis_for_survey()` — все роутеры ходят за аналитикой
только сюда. Зачем нужен кэш:

* закрытый срез неизменяем, а betweenness_centrality считается O(V·E);
* Time Slider и карточка ученика перебирают все срезы класса подряд.

Зачем нужен снапшот сверх кэша: по истечении срока хранения сырые выборы
удаляются (app/retention.py), а динамика класса за прошлые годы должна
остаться. Снапшот и есть то, что остаётся.
"""
import json

from .analytics import build_analysis
from .models import Choice, Student, Survey, SurveyResponse, SurveySnapshot


def _raw_inputs(db, survey):
    """Ученики, выборы и явка одного среза — в виде, который ждёт analytics."""
    students = (
        db.query(Student)
        .filter(Student.class_id == survey.class_id)
        .order_by(Student.full_name)
        .all()
    )
    st = [{"id": s.id, "full_name": s.full_name} for s in students]
    choices = db.query(Choice).filter(Choice.survey_id == survey.id).all()
    ch = [{"from_student": c.from_student, "to_student": c.to_student, "question": c.question} for c in choices]
    responded = [
        r.student_id for r in db.query(SurveyResponse).filter(SurveyResponse.survey_id == survey.id).all()
    ]
    return st, ch, responded


def analysis_for_survey(db, survey, use_cache=True):
    """Результат build_analysis для среза.

    Закрытый срез считается один раз и сохраняется в снапшот. Открытый
    считается каждый раз: по нему ещё идут ответы, кэшировать нечего.
    """
    snap = None
    if use_cache:
        snap = db.query(SurveySnapshot).filter(SurveySnapshot.survey_id == survey.id).first()
        if snap is not None:
            return json.loads(snap.payload)

    st, ch, responded = _raw_inputs(db, survey)
    result = build_analysis(st, ch, responded)

    if not survey.is_open:
        # Срез закрыт — результат окончателен, сохраняем.
        store_snapshot(db, survey, result)
    return result


def last_closed_surveys(db, class_ids):
    """Последний закрытый срез каждого класса: {class_id: Survey}.

    Один запрос вместо запроса на класс — сводка школы и главный экран
    перебирают все классы сразу. Сравнение идёт по паре (дата, id): несколько
    срезов класса могут стоять одним днём, и по одной дате «последний»
    выбирался бы произвольно.
    """
    ids = list(class_ids) or [0]
    rows = (
        db.query(Survey)
        .filter(Survey.class_id.in_(ids), Survey.is_open.is_(False))
        .order_by(Survey.class_id, Survey.conducted_on.desc(), Survey.id.desc())
        .all()
    )
    latest = {}
    for sv in rows:
        latest.setdefault(sv.class_id, sv)  # первый в группе — самый свежий
    return latest


def store_snapshot(db, survey, result=None):
    """Сохраняет (или пересохраняет) снапшот закрытого среза."""
    if result is None:
        st, ch, responded = _raw_inputs(db, survey)
        result = build_analysis(st, ch, responded)
    snap = db.query(SurveySnapshot).filter(SurveySnapshot.survey_id == survey.id).first()
    payload = json.dumps(result, ensure_ascii=False)
    if snap is None:
        snap = SurveySnapshot(survey_id=survey.id, payload=payload)
        db.add(snap)
        # Сессия создана с autoflush=False, поэтому без явного flush следующий
        # запрос снапшота не увидит эту запись и добавит вторую — уникальный
        # индекс по survey_id тогда падает при коммите.
        db.flush()
    else:
        snap.payload = payload
    return snap


def invalidate(db, survey_id):
    """Сбрасывает кэш среза — при переоткрытии опроса или правке данных.

    Снапшот с raw_purged=True не трогаем: сырых данных больше нет, пересчитать
    его нельзя, и он остался единственным источником по этому срезу.
    """
    snap = db.query(SurveySnapshot).filter(SurveySnapshot.survey_id == survey_id).first()
    if snap is not None and not snap.raw_purged:
        db.delete(snap)


def invalidate_class(db, class_id):
    """Сброс кэша всех срезов класса — например при удалении ученика: он
    меняет знаменатель явки и состав графа во всех срезах сразу."""
    ids = [row[0] for row in db.query(Survey.id).filter(Survey.class_id == class_id).all()]
    if not ids:
        return
    (db.query(SurveySnapshot)
       .filter(SurveySnapshot.survey_id.in_(ids), SurveySnapshot.raw_purged.is_(False))
       .delete(synchronize_session=False))
