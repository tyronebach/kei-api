"""recurring rules and transaction linkage

Revision ID: b3f1a2c4d5e6
Revises: 5724eca6fd16
Create Date: 2026-02-28

"""
from alembic import op
import sqlalchemy as sa

revision = "b3f1a2c4d5e6"
down_revision = "7af2e8e2bb4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_rules",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("scope", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("frequency", sa.String, nullable=False),
        sa.Column("interval", sa.Integer, nullable=False, server_default="1"),
        sa.Column("day_of_month", sa.Integer),
        sa.Column("start_date", sa.String, nullable=False),
        sa.Column("end_date", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("entity_id", sa.String, sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("payment_method", sa.String),
        sa.Column("tags", sa.JSON),
        sa.Column("meta", sa.JSON),
        sa.Column("created_by", sa.String),
        sa.Column("updated_by", sa.String),
        sa.Column("deleted_at", sa.Integer),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.Integer, nullable=False),
    )
    op.create_index("idx_recurring_rules_scope", "recurring_rules", ["scope"])
    op.create_index("idx_recurring_rules_active", "recurring_rules", ["scope", "deleted_at"])

    op.create_table(
        "recurring_skips",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("rule_id", sa.String, sa.ForeignKey("recurring_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skip_date", sa.String, nullable=False),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.UniqueConstraint("rule_id", "skip_date", name="uq_recurring_skip_rule_date"),
    )
    op.create_index("idx_recurring_skips_rule", "recurring_skips", ["rule_id"])

    # Add recurring linkage columns to transactions (SQLite: no inline FK in batch mode)
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("rule_id", sa.String))
        batch_op.add_column(sa.Column("rule_date", sa.String))
        batch_op.create_index("idx_transactions_rule", ["rule_id"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("idx_transactions_rule")
        batch_op.drop_column("rule_date")
        batch_op.drop_column("rule_id")

    op.drop_table("recurring_skips")
    op.drop_table("recurring_rules")
