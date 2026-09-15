"""SQLAlchemy ORM models. Works on both SQLite and PostgreSQL (Supabase).

Схема меняется только через миграции Alembic (`alembic revision`, `alembic
upgrade head`) — `create_all` существующие таблицы не трогает и на живой базе
школы бесполезен. См. README, раздел «Миграции».
"""
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base

# Роли пользователей школы.
#   psychologist — работает со своими классами: граф, карточки, заметки.
#   head         — завуч/администрация: сводка по школе БЕЗ данных отдельных
#                  детей. Видит, какому классу нужно внимание, но не может
#                  открыть карточку ученика — это принципиально, а не забыто.
#   admin        — то же, что head, плюс управление пользователями школы.
ROLE_PSYCHOLOGIST = "psychologist"
ROLE_HEAD = "head"
ROLE_ADMIN = "admin"
ROLES = (ROLE_PSYCHOLOGIST, ROLE_HEAD, ROLE_ADMIN)


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    city = Column(String(255))
    # Код приглашения: по нему сотрудник регистрируется и попадает именно в эту
    # школу. Без него регистрация в системе с данными детей была бы открыта всем.
    invite_code = Column(String(32), unique=True, nullable=False, index=True)
    # Сколько месяцев хранить сырые ответы после проведения среза.
    retention_months = Column(Integer, nullable=False, default=12, server_default="12")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Psychologist(Base):
    __tablename__ = "psychologists"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="SET NULL"), index=True)
    role = Column(String(20), nullable=False, default=ROLE_PSYCHOLOGIST, server_default=ROLE_PSYCHOLOGIST)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    # Версия токенов. Кладётся в подписанный токен и сверяется при каждом
    # запросе; инкремент мгновенно обесценивает все выданные ранее токены.
    # Так серверный logout работает без хранилища сессий: одно число вместо
    # списка активных сессий. Важно для школьного компьютера, за которым
    # психолог не один, и для смены пароля.
    token_version = Column(Integer, nullable=False, default=1, server_default="1")
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SchoolClass(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="SET NULL"), index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    # До какой даты хранятся сырые ответы этого класса. После — остаются только
    # агрегаты в survey_snapshots (см. app/retention.py).
    retention_until = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    students = relationship("Student", backref="school_class", cascade="all, delete-orphan", passive_deletes=True)
    surveys = relationship("Survey", backref="school_class", cascade="all, delete-orphan", passive_deletes=True)


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    # Постоянный идентификатор ученика внутри класса. НЕ пароль: для участия в
    # срезе выдаётся отдельный одноразовый билет (SurveyTicket).
    code = Column(String(16), unique=True, nullable=False, index=True)
    gender = Column(String(1))
    birth_date = Column(Date)
    note = Column(Text)
    # Выбывшие ученики: остаются в истории срезов, но в новые не попадают.
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    consents = relationship("Consent", backref="student", cascade="all, delete-orphan", passive_deletes=True)


class Consent(Base):
    """Согласие на обработку персональных данных ученика.

    Без действующего согласия ученик не участвует в срезе вообще: ему не
    выдаётся билет, и одноклассники не видят его в списке для выбора. Это не
    формальность — в базе лежат ФИО, дата рождения и заметки психолога о
    состоянии несовершеннолетнего.
    """
    __tablename__ = "consents"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="parent", server_default="parent")
    obtained_on = Column(Date, nullable=False, server_default=func.current_date())
    # Куда подшит бумажный оригинал: номер журнала, папка, скан.
    document_ref = Column(String(255))
    revoked_on = Column(Date)
    created_by = Column(Integer, ForeignKey("psychologists.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Survey(Base):
    __tablename__ = "surveys"

    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    conducted_on = Column(Date, nullable=False, server_default=func.current_date())
    is_open = Column(Boolean, nullable=False, default=True)
    questions = Column(Text)  # JSON with per-survey question wording; NULL -> defaults
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    responses = relationship("SurveyResponse", backref="survey", cascade="all, delete-orphan", passive_deletes=True)
    choices = relationship("Choice", backref="survey", cascade="all, delete-orphan", passive_deletes=True)
    tickets = relationship("SurveyTicket", backref="survey", cascade="all, delete-orphan", passive_deletes=True)


class SurveyTicket(Base):
    """Одноразовый код ученика на конкретный срез.

    Раньше кодом служил постоянный Student.code: подсмотревший его одноклассник
    мог ответить за другого и заблокировать ему прохождение навсегда. Билет
    живёт только внутри своего среза, и психолог может перевыпустить его одному
    ученику, не трогая остальных.
    """
    __tablename__ = "survey_tickets"
    __table_args__ = (
        UniqueConstraint("survey_id", "student_id", name="uq_ticket_survey_student"),
    )

    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(16), unique=True, nullable=False, index=True)
    used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SurveyResponse(Base):
    """One row per student who completed a survey — enforces 'no re-take'."""
    __tablename__ = "survey_responses"
    __table_args__ = (UniqueConstraint("survey_id", "student_id", name="uq_response_survey_student"),)

    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())


class Choice(Base):
    """A directed sociometric choice: from_student nominated to_student for `question`."""
    __tablename__ = "choices"
    __table_args__ = (
        UniqueConstraint("survey_id", "from_student", "to_student", "question", name="uq_choice"),
    )

    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True)
    from_student = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    to_student = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    question = Column(String(20), nullable=False)  # 'cinema' | 'project' | 'alone'


class SurveySnapshot(Base):
    """Посчитанная аналитика закрытого среза.

    Две задачи сразу. Первая — кэш: закрытый срез неизменяем, а betweenness
    считается O(V·E), и без кэша каждое движение Time Slider пересчитывало граф
    заново. Вторая — ретеншн: сырые выборы удаляются по истечении срока
    хранения, а динамика по классу должна остаться.
    """
    __tablename__ = "survey_snapshots"

    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    payload = Column(Text, nullable=False)          # JSON: полный результат build_analysis
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    # Сырые ответы удалены ретеншн-политикой — снапшот стал единственным источником.
    raw_purged = Column(Boolean, nullable=False, default=False, server_default="0")


class Alert(Base):
    """Оповещение психологу, созданное сервером при закрытии среза.

    Раньше «алерт» был баннером, который считался в браузере и был виден,
    только если психолог сам откроет нужный класс. При 250-300 учениках его
    никто не находил.
    """
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_inbox", "psychologist_id", "seen_at"),
        UniqueConstraint("survey_id", "student_id", "kind", name="uq_alert_survey_student_kind"),
    )

    id = Column(Integer, primary_key=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True)
    prev_survey_id = Column(Integer, ForeignKey("surveys.id", ondelete="SET NULL"))
    kind = Column(String(30), nullable=False)   # 'drop' | 'isolated' | 'alone_spike'
    from_value = Column(Integer)
    to_value = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    seen_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))


class AuditLog(Base):
    """Журнал доступа к персональным данным.

    Требование проверки: нужно уметь ответить, кто и когда открывал карточку
    конкретного ребёнка и кто выгружал данные класса.
    """
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_target", "target_type", "target_id"),)

    id = Column(Integer, primary_key=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="SET NULL"), index=True)
    action = Column(String(40), nullable=False)       # 'view_student_card' | 'export' | ...
    target_type = Column(String(20), nullable=False)  # 'student' | 'class' | 'survey'
    target_id = Column(Integer)
    ip = Column(String(64))
    at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# Виды профилактической работы. Список закрытый: по нему психолог отчитывается
# перед завучем, и свободный текст в отчёте свёл бы сводку на нет.
ACTIVITY_KINDS = (
    "training",       # тренинг / групповое занятие
    "class_hour",     # классный час
    "diagnostics",    # групповая диагностика
    "parents",        # работа с родителями (собрание, консультация)
    "teachers",       # работа с педагогами / классным руководителем
    "individual",     # индивидуальная профилактическая беседа
    "other",
)

ACTIVITY_STATUSES = ("planned", "done", "cancelled")

# Адресат мероприятия.
TARGET_CLASS = "class"        # весь класс
TARGET_GROUP = "group"        # подгруппа (например, группа риска)
TARGET_STUDENT = "student"    # один ученик
TARGET_ADULTS = "adults"      # родители / педагоги
ACTIVITY_TARGETS = (TARGET_CLASS, TARGET_GROUP, TARGET_STUDENT, TARGET_ADULTS)


class Activity(Base):
    """Профилактическое мероприятие: тренинг, классный час, работа с родителями.

    Отличается от Intervention тем, что оно ГРУППОВОЕ и планируемое:
    Intervention — индивидуальная программа по одному ребёнку, Activity —
    занятие на класс или подгруппу, у которого есть план, дата, охват и
    отметка о проведении. Индивидуальная работа с конкретным ребёнком в рамках
    мероприятия связывается через ActivityParticipant.

    Это то, за что психолог отчитывается перед завучем: план на четверть,
    сколько проведено, какой охват. Поэтому вид и статус — из закрытых
    списков, иначе сводку по школе было бы не собрать.
    """
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_schedule", "psychologist_id", "planned_on"),
    )

    id = Column(Integer, primary_key=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    # Срез, по итогам которого мероприятие назначено. Нужен для оценки
    # эффективности: «до» берётся отсюда, «после» — из следующего среза.
    source_survey_id = Column(Integer, ForeignKey("surveys.id", ondelete="SET NULL"), index=True)

    title = Column(String(255), nullable=False)
    kind = Column(String(20), nullable=False, default="training", server_default="training")
    target = Column(String(20), nullable=False, default=TARGET_CLASS, server_default=TARGET_CLASS)
    status = Column(String(20), nullable=False, default="planned", server_default="planned")

    goal = Column(Text)          # какую задачу решает
    plan = Column(Text)          # ход занятия, материалы
    outcome = Column(Text)       # что получилось по факту
    effectiveness = Column(Integer)  # 1..5, субъективная оценка психолога

    planned_on = Column(Date, nullable=False, server_default=func.current_date())
    conducted_on = Column(Date)
    duration_min = Column(Integer)
    # Для мероприятий с родителями и педагогами охват не по ученикам —
    # записываем числом, участников поимённо не заводим.
    adults_count = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    participants = relationship(
        "ActivityParticipant", backref="activity",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class ActivityParticipant(Base):
    """Охват: кто из учеников участвовал в мероприятии.

    Хранится отдельной таблицей, а не списком id в поле, чтобы охват можно
    было считать запросом и чтобы удаление ученика чистило его само.
    """
    __tablename__ = "activity_participants"
    __table_args__ = (
        UniqueConstraint("activity_id", "student_id", name="uq_activity_student"),
    )

    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    attended = Column(Boolean, nullable=False, default=True, server_default="1")


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False)
    met_on = Column(Date, nullable=False, server_default=func.current_date())
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Intervention(Base):
    __tablename__ = "interventions"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    started_on = Column(Date, nullable=False, server_default=func.current_date())
    ended_on = Column(Date)
    effectiveness = Column(Integer)  # 1..5
    outcome = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
