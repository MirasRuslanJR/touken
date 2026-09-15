"""Роли и доступ к данным.

Модель простая и намеренно жёсткая:

* **psychologist** работает со своими классами: граф, карточки, заметки.
  Чужой класс не откроет — фильтр по psychologist_id, как и раньше.
* **head** (завуч, администрация) видит сводку по школе: какие классы в
  порядке, где падает связность, где низкая явка. И **не может** открыть
  карточку ученика или узнать имена изолятов. Это не забытая проверка, а
  осознанное решение: завучу для управленческого решения нужен класс, а не
  ребёнок, а лишний доступ к данным несовершеннолетних — лишний риск.
* **admin** — психолог, который завёл аккаунт школы: ведёт свои классы как
  обычный психолог и дополнительно управляет сотрудниками и видит сводку.
  В казахстанской школе аккаунт заводит именно психолог, поэтому лишать
  администратора его собственной работы было бы неверно.

Данные конкретных детей видит только тот, кто с ними работает. Границу
держит код, а не регламент.
"""
from fastapi import Depends, HTTPException

from .models import ROLE_ADMIN, ROLE_HEAD, ROLE_PSYCHOLOGIST, Psychologist
from .security import get_current_psychologist, get_psychologist_for_download

# Кто может владеть классами и видеть данные конкретных детей.
CASE_ROLES = (ROLE_PSYCHOLOGIST, ROLE_ADMIN)
# Кто видит сводку по школе (без данных отдельных детей).
SCHOOL_ROLES = (ROLE_HEAD, ROLE_ADMIN)


def _check(user, roles, message):
    if (user.role or ROLE_PSYCHOLOGIST) not in roles:
        raise HTTPException(status_code=403, detail=message)
    return user


def require_casework(user: Psychologist = Depends(get_current_psychologist)) -> Psychologist:
    """Доступ к данным конкретных учеников — только для психолога."""
    return _check(
        user, CASE_ROLES,
        "Доступ к данным учеников есть только у психолога. "
        "Завучу доступна сводка по школе без персональных данных.",
    )


def require_school_view(user: Psychologist = Depends(get_current_psychologist)) -> Psychologist:
    """Сводка по школе — завуч и администратор."""
    if not user.school_id:
        raise HTTPException(status_code=403, detail="Пользователь не привязан к школе")
    return _check(user, SCHOOL_ROLES, "Сводка по школе доступна завучу и администратору")


def require_admin(user: Psychologist = Depends(get_current_psychologist)) -> Psychologist:
    return _check(user, (ROLE_ADMIN,), "Действие доступно только администратору школы")


# --- те же права, но для скачивания файлов (токен приходит параметром) ---
def require_casework_download(user: Psychologist = Depends(get_psychologist_for_download)) -> Psychologist:
    return _check(user, CASE_ROLES, "Доступ к данным учеников есть только у психолога")


def require_school_view_download(user: Psychologist = Depends(get_psychologist_for_download)) -> Psychologist:
    if not user.school_id:
        raise HTTPException(status_code=403, detail="Пользователь не привязан к школе")
    return _check(user, SCHOOL_ROLES, "Сводка по школе доступна завучу и администратору")
