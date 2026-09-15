"""Журнал доступа к персональным данным.

Нужно уметь ответить на вопрос проверки: кто и когда открывал карточку
конкретного ребёнка, кто выгружал данные класса. Пишем факт доступа, а не
содержимое — в журнале не должно оказаться тех же данных ещё раз.
"""
from .models import AuditLog
from .ratelimit import client_ip

# Действия, которые логируем. Список закрытый: журнал должен оставаться
# читаемым человеком, а не превращаться в свалку событий.
VIEW_STUDENT_CARD = "view_student_card"
VIEW_ANALYTICS = "view_analytics"
EXPORT_CLASS = "export_class"
VIEW_CODES = "view_codes"
DELETE_STUDENT = "delete_student"
DELETE_CLASS = "delete_class"
PURGE_RAW = "purge_raw"
ACTIVITY_DONE = "activity_done"

# Подписи для журнала: он должен читаться завучем и проверяющим, а не только
# разработчиком.
ACTION_TITLES = {
    VIEW_STUDENT_CARD: "Открыл карточку ученика",
    VIEW_ANALYTICS: "Смотрел аналитику среза",
    EXPORT_CLASS: "Выгрузил данные",
    VIEW_CODES: "Смотрел коды на срез",
    DELETE_STUDENT: "Удалил ученика",
    DELETE_CLASS: "Удалил класс",
    PURGE_RAW: "Удалил сырые ответы по сроку хранения",
    ACTIVITY_DONE: "Отметил проведение мероприятия",
}


def log(db, user, action, target_type, target_id, request=None):
    """Записывает факт доступа. Коммит оставляем вызывающему коду: запись в
    журнал должна попасть в ту же транзакцию, что и само действие."""
    db.add(AuditLog(
        psychologist_id=getattr(user, "id", None),
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=client_ip(request) if request is not None else None,
    ))
