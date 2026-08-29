"""add replan insights, exam time, and priority chapters"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exams") as batch_op:
        batch_op.add_column(sa.Column("exam_time", sa.String(length=5), nullable=False, server_default="09:00"))
        batch_op.add_column(sa.Column("priority_chapters", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("last_replan_summary", sa.String(length=700), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("pace_advice", sa.String(length=700), nullable=False, server_default=""))
        batch_op.create_index("idx_exams_exam_date_time", ["exam_date", "exam_time"])
    with op.batch_alter_table("study_tasks") as batch_op:
        batch_op.create_index("idx_study_tasks_date_time", ["study_date", "suggested_start_time"])


def downgrade() -> None:
    with op.batch_alter_table("study_tasks") as batch_op:
        batch_op.drop_index("idx_study_tasks_date_time")
    with op.batch_alter_table("exams") as batch_op:
        batch_op.drop_index("idx_exams_exam_date_time")
        batch_op.drop_column("pace_advice")
        batch_op.drop_column("last_replan_summary")
        batch_op.drop_column("priority_chapters")
        batch_op.drop_column("exam_time")
