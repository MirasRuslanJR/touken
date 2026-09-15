"""Продуктовая схема: школы и роли, согласия, билеты на срез, снапшоты,
оповещения, журнал доступа, ретеншн.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------- школы
    op.create_table(
        "schools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("city", sa.String(255)),
        sa.Column("invite_code", sa.String(32), nullable=False),
        sa.Column("retention_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_schools_invite_code", "schools", ["invite_code"], unique=True)

    # ------------------------------------------------- пользователи и роли
    with op.batch_alter_table("psychologists") as b:
        b.add_column(sa.Column("school_id", sa.Integer()))
        b.add_column(sa.Column("role", sa.String(20), nullable=False, server_default="psychologist"))
        b.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        # Версия токенов: инкремент обесценивает все выданные токены — так
        # работает серверный logout без хранилища сессий.
        b.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"))
        b.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True)))
        b.create_foreign_key("fk_psychologists_school", "schools", ["school_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_psychologists_school_id", "psychologists", ["school_id"])

    with op.batch_alter_table("classes") as b:
        b.add_column(sa.Column("school_id", sa.Integer()))
        # Дата, после которой сырые ответы класса удаляются (см. app/retention.py).
        b.add_column(sa.Column("retention_until", sa.Date()))
        b.create_foreign_key("fk_classes_school", "schools", ["school_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_classes_school_id", "classes", ["school_id"])

    with op.batch_alter_table("students") as b:
        b.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table("surveys") as b:
        b.add_column(sa.Column("closed_at", sa.DateTime(timezone=True)))

    # ------------------------------------------------------------ согласия
    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="parent"),
        sa.Column("obtained_on", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("document_ref", sa.String(255)),
        sa.Column("revoked_on", sa.Date()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("psychologists.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_consents_student_id", "consents", ["student_id"])

    # ------------------------------------------------- одноразовые билеты
    op.create_table(
        "survey_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("survey_id", sa.Integer(), sa.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("survey_id", "student_id", name="uq_ticket_survey_student"),
    )
    op.create_index("ix_survey_tickets_survey_id", "survey_tickets", ["survey_id"])
    op.create_index("ix_survey_tickets_student_id", "survey_tickets", ["student_id"])
    op.create_index("ix_survey_tickets_code", "survey_tickets", ["code"], unique=True)

    # --------------------------------------------------- снапшоты аналитики
    op.create_table(
        "survey_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("survey_id", sa.Integer(), sa.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_purged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_survey_snapshots_survey_id", "survey_snapshots", ["survey_id"], unique=True)

    # ---------------------------------------------------------- оповещения
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("psychologist_id", sa.Integer(),
                  sa.ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("survey_id", sa.Integer(), sa.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prev_survey_id", sa.Integer(), sa.ForeignKey("surveys.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("from_value", sa.Integer()),
        sa.Column("to_value", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("seen_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("survey_id", "student_id", "kind", name="uq_alert_survey_student_kind"),
    )
    for col in ("psychologist_id", "class_id", "student_id", "survey_id"):
        op.create_index("ix_alerts_%s" % col, "alerts", [col])
    op.create_index("ix_alerts_inbox", "alerts", ["psychologist_id", "seen_at"])

    # ------------------------------------------------------ журнал доступа
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("psychologist_id", sa.Integer(), sa.ForeignKey("psychologists.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer()),
        sa.Column("ip", sa.String(64)),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_psychologist_id", "audit_log", ["psychologist_id"])
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.create_index("ix_audit_target", "audit_log", ["target_type", "target_id"])


def downgrade() -> None:
    for table in ("audit_log", "alerts", "survey_snapshots", "survey_tickets", "consents"):
        op.drop_table(table)
    with op.batch_alter_table("surveys") as b:
        b.drop_column("closed_at")
    with op.batch_alter_table("students") as b:
        b.drop_column("is_active")
    with op.batch_alter_table("classes") as b:
        b.drop_column("retention_until")
        b.drop_column("school_id")
    with op.batch_alter_table("psychologists") as b:
        for col in ("last_login_at", "token_version", "is_active", "role", "school_id"):
            b.drop_column(col)
    op.drop_table("schools")
