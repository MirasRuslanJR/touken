"""Pydantic request models (Pydantic v2)."""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# Верхние границы длины стоят везде, где значение уходит в базу: без них
# PostgreSQL отвергает вставку ошибкой 500 вместо понятного сообщения, а
# неограниченный пароль ещё и заставляет PBKDF2 считать хэш сколь угодно долго.
class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)
    invite_code: Optional[str] = Field(default=None, max_length=32)


class SchoolIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    city: Optional[str] = Field(default=None, max_length=255)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserRoleIn(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


# Длины совпадают с колонками в models.py: без ограничения PostgreSQL
# отвергает вставку с ошибкой 500, вместо понятного «слишком длинное имя».
class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)


class StudentIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    gender: Optional[str] = Field(default=None, max_length=1)
    birth_date: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=4000)
    is_active: Optional[bool] = None


class BulkStudentsIn(BaseModel):
    """Массовое добавление учеников.

    Ограничение на 500 записей: класс — это десятки человек, а не тысячи, и
    без него один запрос мог бы вставить сколько угодно строк.
    """
    students: List[StudentIn] = Field(default_factory=list, max_length=500)


class ConsentIn(BaseModel):
    """Согласие на обработку данных ученика. document_ref — куда подшит
    бумажный оригинал (журнал, папка, скан)."""
    kind: str = Field(default="parent", max_length=20)
    obtained_on: Optional[str] = None
    document_ref: Optional[str] = Field(default=None, max_length=255)


class BulkConsentIn(ConsentIn):
    """Согласия пачкой. Пустой student_ids = всем активным ученикам класса:
    бланки приносят стопкой с родительского собрания."""
    student_ids: Optional[List[int]] = Field(default=None, max_length=500)


class ClassSettingsIn(BaseModel):
    """Срок хранения сырых ответов класса (ISO-дата)."""
    retention_until: Optional[str] = None


class SurveyIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    conducted_on: Optional[str] = None
    questions: Optional[List[dict]] = Field(default=None, max_length=10)


class SurveyPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    conducted_on: Optional[str] = None
    is_open: Optional[bool] = None
    questions: Optional[List[dict]] = Field(default=None, max_length=10)


class ActivityIn(BaseModel):
    """Профилактическое мероприятие: тренинг, классный час, работа с родителями."""
    title: str = Field(min_length=1, max_length=255)
    kind: str = "training"
    target: str = "class"
    goal: Optional[str] = Field(default=None, max_length=4000)
    plan: Optional[str] = Field(default=None, max_length=8000)
    planned_on: Optional[str] = None
    # Занятие длиннее школьного дня — почти наверняка опечатка.
    duration_min: Optional[int] = Field(default=None, ge=5, le=480)
    source_survey_id: Optional[int] = None
    # Пустой список при target="class" означает весь класс — состав
    # подставляется на сервере на момент проведения.
    student_ids: Optional[List[int]] = Field(default=None, max_length=500)


class ActivityPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    kind: Optional[str] = None
    target: Optional[str] = None
    goal: Optional[str] = Field(default=None, max_length=4000)
    plan: Optional[str] = Field(default=None, max_length=8000)
    planned_on: Optional[str] = None
    duration_min: Optional[int] = Field(default=None, ge=5, le=480)
    student_ids: Optional[List[int]] = Field(default=None, max_length=500)


class ActivityCompleteIn(BaseModel):
    """Отметка о проведении: дата, охват и что получилось."""
    conducted_on: Optional[str] = None
    outcome: Optional[str] = Field(default=None, max_length=8000)
    effectiveness: Optional[int] = Field(default=None, ge=1, le=5)
    duration_min: Optional[int] = Field(default=None, ge=5, le=480)
    adults_count: Optional[int] = Field(default=None, ge=0, le=1000)
    # Кто фактически был. None = все запланированные участники.
    attended_ids: Optional[List[int]] = Field(default=None, max_length=500)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class MeetingIn(BaseModel):
    met_on: Optional[str] = None
    summary: Optional[str] = Field(default=None, max_length=8000)


class InterventionIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=8000)
    started_on: Optional[str] = None
    ended_on: Optional[str] = None
    effectiveness: Optional[int] = Field(default=None, ge=1, le=5)
    outcome: Optional[str] = Field(default=None, max_length=8000)


class SurveyStartIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class SurveySubmitIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    # { "cinema": [id, ...], "project": [...], "alone": [...] }
    #
    # Верхняя граница на список: сервер всё равно отсечёт лишние выборы по
    # лимиту вопроса, но принимать и разбирать тысячи элементов от анонимного
    # запроса не нужно — это бесплатная нагрузка для любого желающего.
    answers: Dict[str, List[int]] = Field(default_factory=dict)

    @field_validator("answers")
    @classmethod
    def _limit_answers(cls, value):
        if len(value) > 10:
            raise ValueError("слишком много вопросов в ответе")
        for key, ids in value.items():
            if len(ids) > 100:
                raise ValueError("слишком много выборов по одному вопросу")
        return value
