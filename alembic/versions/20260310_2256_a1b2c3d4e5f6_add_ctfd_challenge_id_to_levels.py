"""add ctfd_challenge_id to levels

Revision ID: a1b2c3d4e5f6
Revises: 88ddf00f7a0e
Create Date: 2026-03-10 22:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '88ddf00f7a0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable column — existing rows get NULL, no data loss, re-seeding fills values
    op.add_column('levels', sa.Column('ctfd_challenge_id', sa.Integer(), nullable=True))

    # Also add flag_pool column if missing (added after initial migration)
    with op.batch_alter_table('levels') as batch_op:
        try:
            batch_op.add_column(sa.Column('flag_pool', sa.Text(), nullable=True))
        except Exception:
            pass  # Column already exists on newer deployments


def downgrade() -> None:
    op.drop_column('levels', 'ctfd_challenge_id')
