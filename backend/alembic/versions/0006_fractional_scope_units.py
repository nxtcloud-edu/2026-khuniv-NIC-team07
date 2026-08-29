"""allow fractional chapter scope units"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exams") as batch_op:
        batch_op.alter_column("scope_start", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)
        batch_op.alter_column("scope_end", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)
    with op.batch_alter_table("study_tasks") as batch_op:
        batch_op.alter_column("scope_start", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)
        batch_op.alter_column("scope_end", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)
        batch_op.alter_column("planned_units", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)
    with op.batch_alter_table("study_logs") as batch_op:
        batch_op.alter_column("completed_units", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)
        batch_op.alter_column("actual_scope_end", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("study_logs") as batch_op:
        batch_op.alter_column("actual_scope_end", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=True)
        batch_op.alter_column("completed_units", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False)
    with op.batch_alter_table("study_tasks") as batch_op:
        batch_op.alter_column("planned_units", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False)
        batch_op.alter_column("scope_end", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False)
        batch_op.alter_column("scope_start", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False)
    with op.batch_alter_table("exams") as batch_op:
        batch_op.alter_column("scope_end", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False)
        batch_op.alter_column("scope_start", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False)
