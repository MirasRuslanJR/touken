"""Срок хранения сырых данных.

В базе лежат ответы несовершеннолетних о том, с кем они дружат и кого считают
одиноким. Хранить это бессрочно нельзя и не нужно: психологу для работы важна
динамика показателей, а не то, кто именно кого выбрал три года назад.

Политика: по истечении срока хранения класса сырые выборы и отметки о
прохождении удаляются, а посчитанная аналитика остаётся снапшотом. Графики
динамики продолжают работать, восстановить по ним отдельные ответы нельзя.

Запуск (обычно из cron раз в сутки):

    python -m app.retention          # показать, что будет удалено
    python -m app.retention --apply  # удалить
"""
import argparse
from datetime import date

from .database import SessionLocal
from .models import Choice, SchoolClass, Survey, SurveyResponse, SurveySnapshot, SurveyTicket
from .snapshots import store_snapshot

DEFAULT_RETENTION_MONTHS = 12


def default_retention_until(school=None, today=None):
    """Дата, до которой хранятся сырые ответы класса."""
    today = today or date.today()
    months = (school.retention_months if school is not None else None) or DEFAULT_RETENTION_MONTHS
    year = today.year + (today.month - 1 + months) // 12
    month = (today.month - 1 + months) % 12 + 1
    day = min(today.day, 28)  # 28 — безопасно для любого месяца
    return date(year, month, day)


def expired_classes(db, today=None):
    today = today or date.today()
    return (
        db.query(SchoolClass)
        .filter(SchoolClass.retention_until.isnot(None), SchoolClass.retention_until < today)
        .all()
    )


def purge_class(db, school_class):
    """Удаляет сырые данные класса, сохранив аналитику снапшотами.

    Порядок важен: сначала снапшот (пока сырые данные ещё на месте), потом
    удаление. Иначе при сбое посередине можно потерять и то и другое.
    """
    surveys = db.query(Survey).filter(Survey.class_id == school_class.id).all()
    purged = 0
    for sv in surveys:
        snap = db.query(SurveySnapshot).filter(SurveySnapshot.survey_id == sv.id).first()
        if snap is not None and snap.raw_purged:
            continue  # уже вычищен
        snap = store_snapshot(db, sv)
        db.flush()
        snap.raw_purged = True

        n = db.query(Choice).filter(Choice.survey_id == sv.id).delete(synchronize_session=False)
        db.query(SurveyResponse).filter(SurveyResponse.survey_id == sv.id).delete(synchronize_session=False)
        db.query(SurveyTicket).filter(SurveyTicket.survey_id == sv.id).delete(synchronize_session=False)
        purged += n
    return purged


def run(apply=False, today=None):
    db = SessionLocal()
    try:
        classes = expired_classes(db, today)
        if not classes:
            print("Классов с истёкшим сроком хранения нет.")
            return 0
        total = 0
        for c in classes:
            if apply:
                n = purge_class(db, c)
                total += n
                print("Класс «%s» (id=%s): удалено выборов — %d" % (c.name, c.id, n))
            else:
                n = db.query(Choice).join(Survey, Choice.survey_id == Survey.id) \
                      .filter(Survey.class_id == c.id).count()
                total += n
                print("Класс «%s» (id=%s): срок истёк %s, под удаление попадёт выборов — %d"
                      % (c.name, c.id, c.retention_until, n))
        if apply:
            db.commit()
            print("Готово. Аналитика сохранена снапшотами, сырые ответы удалены.")
        else:
            print("\nЭто предпросмотр. Для удаления запустите с --apply.")
        return total
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Удаление сырых ответов с истёкшим сроком хранения.")
    parser.add_argument("--apply", action="store_true", help="действительно удалить (без флага — предпросмотр)")
    args = parser.parse_args()
    run(apply=args.apply)
