"""item_images.item_id NOT NULL

Revision ID: 0002_item_images_not_null
Revises: 0001_initial
Create Date: 2026-10-15

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_item_images_not_null"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 清理历史上未挂到物品的孤儿图片行
    op.execute("DELETE FROM item_images WHERE item_id IS NULL")
    op.alter_column("item_images", "item_id", nullable=False)


def downgrade() -> None:
    op.alter_column("item_images", "item_id", nullable=True)
