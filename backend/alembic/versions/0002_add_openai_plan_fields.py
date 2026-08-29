"""add OpenAI plan fields"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exams") as batch_op:
        batch_op.add_column(sa.Column("ai_summary", sa.String(length=500), nullable=False, server_default=""))
    with op.batch_alter_table("study_tasks") as batch_op:
        batch_op.add_column(sa.Column("suggested_start_time", sa.String(length=5), nullable=False, server_default="19:00"))
        batch_op.add_column(sa.Column("suggested_end_time", sa.String(length=5), nullable=False, server_default="20:00"))


def downgrade() -> None:
    with op.batch_alter_table("study_tasks") as batch_op:
        batch_op.drop_column("suggested_end_time")
        batch_op.drop_column("suggested_start_time")
    with op.batch_alter_table("exams") as batch_op:
        batch_op.drop_column("ai_summary")
