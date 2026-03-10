"""add ctfd_challenge_id to levels

Revision ID: a1b2c3d4e5f6
Revises: 88ddf00f7a0e
Create Date: 2026-03-10 22:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '88ddf00f7a0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add ctfd_challenge_id if it doesn't already exist
    conn.execute(text(
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS ctfd_challenge_id INTEGER"
    ))

    # Add flag_pool if it doesn't already exist (may have been added outside migrations)
    conn.execute(text(
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS flag_pool TEXT"
    ))


def downgrade() -> None:
    op.drop_column('levels', 'ctfd_challenge_id')
