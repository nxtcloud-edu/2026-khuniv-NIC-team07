"""create study planner tables"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("calendar_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(120), nullable=False), sa.Column("event_type", sa.String(30), nullable=False), sa.Column("starts_at", sa.DateTime(), nullable=False), sa.Column("ends_at", sa.DateTime(), nullable=False))
    op.create_table("exams", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("subject", sa.String(120), nullable=False), sa.Column("exam_date", sa.Date(), nullable=False), sa.Column("scope_start", sa.Integer(), nullable=False), sa.Column("scope_end", sa.Integer(), nullable=False), sa.Column("scope_unit", sa.String(20), nullable=False), sa.Column("target_passes", sa.Float(), nullable=False), sa.Column("plan_version", sa.Integer(), nullable=False))
    op.create_table("study_tasks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id"), nullable=False), sa.Column("study_date", sa.Date(), nullable=False), sa.Column("pass_number", sa.Integer(), nullable=False), sa.Column("scope_start", sa.Integer(), nullable=False), sa.Column("scope_end", sa.Integer(), nullable=False), sa.Column("planned_units", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("plan_version", sa.Integer(), nullable=False))
    op.create_table("study_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_id", sa.Integer(), sa.ForeignKey("study_tasks.id"), nullable=False), sa.Column("result", sa.String(20), nullable=False), sa.Column("completed_units", sa.Integer(), nullable=False), sa.Column("actual_scope_end", sa.Integer(), nullable=True), sa.Column("recorded_at", sa.DateTime(), nullable=False))


def downgrade() -> None:
    op.drop_table("study_logs")
    op.drop_table("study_tasks")
    op.drop_table("exams")
    op.drop_table("calendar_events")
