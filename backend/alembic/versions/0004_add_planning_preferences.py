"""add freeform planning preferences"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exams") as batch_op:
        batch_op.add_column(sa.Column("planning_preferences", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("exams") as batch_op:
        batch_op.drop_column("planning_preferences")
