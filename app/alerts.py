"""Оповещения психологу — считаются на сервере при закрытии среза.

Раньше это был баннер, который вычислялся в браузере из двух загруженных
срезов и был виден, только если психолог сам откроет нужный класс. При
250-300 учениках в десятке классов его никто не находил. Теперь оповещения
создаются один раз при закрытии среза, живут в БД и ждут во «Входящих».

Главное правило: на недостоверном срезе не срабатывает ничего. Сравнивать
срезы с разной и низкой явкой бессмысленно — «падение связей» тогда означает
лишь то, что во втором срезе ответило меньше детей, и оповещение отправило бы
психолога работать с ребёнком без проблемы.
"""
from sqlalchemy import and_, or_

from .models import Alert, Survey
from .snapshots import analysis_for_survey

# Резкое падение входящих связей: минус два и больше либо падение вдвое.
DROP_ABS = 2
DROP_RATIO = 0.5

KIND_DROP = "drop"              # резко упало число входящих выборов
KIND_BECAME_ISOLATE = "isolate"  # был со связями — стал изолятом
KIND_ALONE = "alone"            # набрал номинаций «часто остаётся один»

TITLES = {
    KIND_DROP: "Резкое падение связей",
    KIND_BECAME_ISOLATE: "Стал изолятом",
    KIND_ALONE: "Отмечают как одинокого",
}


def _is_sharp_drop(before, after):
    return after < before and ((before - after) >= DROP_ABS or (before >= 2 and after <= before * DROP_RATIO))


def generate_for_survey(db, survey):
    """Создаёт оповещения по закрытому срезу. Возвращает список созданных.

    Идемпотентна: уникальный индекс (survey_id, student_id, kind) не даёт
    продублировать оповещение при повторном закрытии среза.
    """
    if survey.is_open:
        return []

    current = analysis_for_survey(db, survey)
    if current["graph_metrics"]["reliability"] == "low":
        return []

    # Предыдущий срез. Сравнение идёт по паре (дата, id), а не по одной дате:
    # два среза можно провести и в один день, и тогда сравнение только по дате
    # не находит предыдущий вовсе — оповещения молча не создавались бы.
    prev = (
        db.query(Survey)
        .filter(
            Survey.class_id == survey.class_id,
            Survey.is_open.is_(False),
            Survey.id != survey.id,
            or_(
                Survey.conducted_on < survey.conducted_on,
                and_(Survey.conducted_on == survey.conducted_on, Survey.id < survey.id),
            ),
        )
        .order_by(Survey.conducted_on.desc(), Survey.id.desc())
        .first()
    )
    prev_analysis = None
    if prev is not None:
        prev_analysis = analysis_for_survey(db, prev)
        if prev_analysis["graph_metrics"]["reliability"] == "low":
            prev_analysis = None

    existing = {
        (a.student_id, a.kind)
        for a in db.query(Alert).filter(Alert.survey_id == survey.id).all()
    }

    created = []

    def add(student_id, kind, from_value=None, to_value=None):
        if (student_id, kind) in existing:
            return
        existing.add((student_id, kind))
        alert = Alert(
            psychologist_id=survey.psychologist_id,
            class_id=survey.class_id,
            student_id=student_id,
            survey_id=survey.id,
            prev_survey_id=prev.id if prev is not None else None,
            kind=kind,
            from_value=from_value,
            to_value=to_value,
        )
        db.add(alert)
        created.append(alert)

    for key, now in current["per_student"].items():
        sid = int(key)

        # Ученик со статусом "unknown" не классифицирован — по нему молчим.
        if now["status"] == "unknown":
            continue

        if now["alone_reportable"]:
            add(sid, KIND_ALONE, to_value=now["alone_votes"])

        if prev_analysis is None:
            # Первый достоверный срез: сравнивать не с чем, но факт изоляции
            # сам по себе уже повод посмотреть на ребёнка.
            if now["status"] == "isolate":
                add(sid, KIND_BECAME_ISOLATE, to_value=0)
            continue

        before = prev_analysis["per_student"].get(key)
        if not before or before["status"] == "unknown":
            continue

        if before["status"] != "isolate" and now["status"] == "isolate":
            add(sid, KIND_BECAME_ISOLATE, from_value=before["in_degree"], to_value=now["in_degree"])
        elif _is_sharp_drop(before["in_degree"], now["in_degree"]):
            add(sid, KIND_DROP, from_value=before["in_degree"], to_value=now["in_degree"])

    return created
