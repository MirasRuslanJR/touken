"""Профилактическая работа: мероприятия и охват.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("psychologist_id", sa.Integer(),
                  sa.ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        # Срез, по итогам которого назначено мероприятие: «до» для оценки эффекта.
        sa.Column("source_survey_id", sa.Integer(), sa.ForeignKey("surveys.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="training"),
        sa.Column("target", sa.String(20), nullable=False, server_default="class"),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column("goal", sa.Text()),
        sa.Column("plan", sa.Text()),
        sa.Column("outcome", sa.Text()),
        sa.Column("effectiveness", sa.Integer()),
        sa.Column("planned_on", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("conducted_on", sa.Date()),
        sa.Column("duration_min", sa.Integer()),
        sa.Column("adults_count", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_activities_psychologist_id", "activities", ["psychologist_id"])
    op.create_index("ix_activities_class_id", "activities", ["class_id"])
    op.create_index("ix_activities_source_survey_id", "activities", ["source_survey_id"])
    op.create_index("ix_activities_schedule", "activities", ["psychologist_id", "planned_on"])

    op.create_table(
        "activity_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attended", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("activity_id", "student_id", name="uq_activity_student"),
    )
    op.create_index("ix_activity_participants_activity_id", "activity_participants", ["activity_id"])
    op.create_index("ix_activity_participants_student_id", "activity_participants", ["student_id"])


def downgrade() -> None:
    op.drop_table("activity_participants")
    op.drop_table("activities")
