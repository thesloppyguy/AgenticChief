"""OutboundMessage people targeting + ChatMessage artifacts.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbound_message") as batch:
        batch.add_column(sa.Column("person_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("to_email", sa.String(length=200), nullable=True))
        batch.alter_column("company_code", existing_type=sa.String(length=32), nullable=True)
        batch.create_foreign_key(
            "fk_outbound_message_person_id",
            "person",
            ["person_id"],
            ["id"],
        )
        batch.create_index("ix_outbound_message_person_id", ["person_id"])

    with op.batch_alter_table("chat_message") as batch:
        batch.add_column(sa.Column("artifacts", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_message") as batch:
        batch.drop_column("artifacts")

    with op.batch_alter_table("outbound_message") as batch:
        batch.drop_index("ix_outbound_message_person_id")
        batch.drop_constraint("fk_outbound_message_person_id", type_="foreignkey")
        batch.drop_column("to_email")
        batch.drop_column("person_id")
        batch.alter_column("company_code", existing_type=sa.String(length=32), nullable=False)
