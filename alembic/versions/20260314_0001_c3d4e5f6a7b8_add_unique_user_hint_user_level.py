"""add unique constraint on user_hints(user_id, level_id)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-14 00:01:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any duplicate (user_id, level_id) rows before adding constraint,
    # keeping the row with the highest hint_count for each pair.
    conn = op.get_bind()
    conn.execute(
        text("""
        DELETE FROM user_hints
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id, level_id) id
            FROM user_hints
            ORDER BY user_id, level_id, hint_count DESC, id DESC
        )
    """)
    )
    op.create_unique_constraint(
        "uq_user_hint_user_level", "user_hints", ["user_id", "level_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_hint_user_level", "user_hints", type_="unique")
