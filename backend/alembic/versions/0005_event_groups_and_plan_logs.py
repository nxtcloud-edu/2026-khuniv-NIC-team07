"""add recurring event groups and plan change logs"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.add_column(sa.Column("recurrence_group_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_calendar_events_recurrence_group_id", ["recurrence_group_id"])
    op.create_table(
        "plan_change_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id"), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("new_version", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.String(length=700), nullable=False, server_default=""),
        sa.Column("recommendation", sa.String(length=700), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plan_change_logs_exam_id", "plan_change_logs", ["exam_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_change_logs_exam_id", table_name="plan_change_logs")
    op.drop_table("plan_change_logs")
    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.drop_index("ix_calendar_events_recurrence_group_id")
        batch_op.drop_column("recurrence_group_id")
