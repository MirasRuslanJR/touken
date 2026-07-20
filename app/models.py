"""SQLAlchemy ORM models. Works on both SQLite and PostgreSQL (Supabase)."""
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


class Psychologist(Base):
    __tablename__ = "psychologists"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SchoolClass(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    students = relationship("Student", backref="school_class", cascade="all, delete-orphan", passive_deletes=True)
    surveys = relationship("Survey", backref="school_class", cascade="all, delete-orphan", passive_deletes=True)


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    psychologist_id = Column(Integer, ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    code = Column(String(16), unique=True, nullable=False, index=True)
    gender = Column(String(1))
    birth_date = Column(Date)
    note = Column(Text)
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    responses = relationship("SurveyResponse", backref="survey", cascade="all, delete-orphan", passive_deletes=True)
    choices = relationship("Choice", backref="survey", cascade="all, delete-orphan", passive_deletes=True)


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
