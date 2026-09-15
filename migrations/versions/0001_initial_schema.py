"""Исходная схема «Изолята» (состояние до перехода на миграции).

Эта ревизия описывает базу такой, какой её создавал Base.metadata.create_all
до появления Alembic. На уже работающей базе её НЕ надо применять — вместо
этого один раз выполните:

    alembic stamp 0001

после чего `alembic upgrade head` доведёт схему до актуальной.

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "psychologists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_psychologists_email", "psychologists", ["email"], unique=True)

    op.create_table(
        "classes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("psychologist_id", sa.Integer(),
                  sa.ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_classes_psychologist_id", "classes", ["psychologist_id"])

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("psychologist_id", sa.Integer(),
                  sa.ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("gender", sa.String(1)),
        sa.Column("birth_date", sa.Date()),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_students_class_id", "students", ["class_id"])
    op.create_index("ix_students_psychologist_id", "students", ["psychologist_id"])
    op.create_index("ix_students_code", "students", ["code"], unique=True)

    op.create_table(
        "surveys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("psychologist_id", sa.Integer(),
                  sa.ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("conducted_on", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("questions", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_surveys_class_id", "surveys", ["class_id"])
    op.create_index("ix_surveys_psychologist_id", "surveys", ["psychologist_id"])

    op.create_table(
        "survey_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("survey_id", sa.Integer(), sa.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("survey_id", "student_id", name="uq_response_survey_student"),
    )
    op.create_index("ix_survey_responses_survey_id", "survey_responses", ["survey_id"])
    op.create_index("ix_survey_responses_student_id", "survey_responses", ["student_id"])

    op.create_table(
        "choices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("survey_id", sa.Integer(), sa.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_student", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_student", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.String(20), nullable=False),
        sa.UniqueConstraint("survey_id", "from_student", "to_student", "question", name="uq_choice"),
    )
    op.create_index("ix_choices_survey_id", "choices", ["survey_id"])

    for table, extra in (
        ("meetings", [sa.Column("met_on", sa.Date(), nullable=False, server_default=sa.func.current_date()),
                      sa.Column("summary", sa.Text())]),
        ("notes", [sa.Column("body", sa.Text(), nullable=False)]),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
            sa.Column("psychologist_id", sa.Integer(),
                      sa.ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False),
            *extra,
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_%s_student_id" % table, table, ["student_id"])

    op.create_table(
        "interventions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("psychologist_id", sa.Integer(),
                  sa.ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("started_on", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("ended_on", sa.Date()),
        sa.Column("effectiveness", sa.Integer()),
        sa.Column("outcome", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_interventions_student_id", "interventions", ["student_id"])


def downgrade() -> None:
    for table in ("interventions", "notes", "meetings", "choices", "survey_responses",
                  "surveys", "students", "classes", "psychologists"):
        op.drop_table(table)
