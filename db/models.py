import time
import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from db.connection import Base


def _generate_id() -> str:
    return uuid.uuid4().hex


def _now() -> int:
    return int(time.time())


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (Index("idx_entities_scope", "scope"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_scope", "scope"),
        Index("idx_transactions_date", "date"),
        Index("idx_transactions_type", "type"),
        Index("idx_transactions_category", "category"),
        # Unique constraint for external identity (partial: only when both are non-null)
        # Enforced at API layer for SQLite compatibility; DB constraint added via migration
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # integer cents
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    date: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("entities.id", ondelete="SET NULL"),
    )
    external_source: Mapped[str | None] = mapped_column(String)
    external_id: Mapped[str | None] = mapped_column(String)
    tags: Mapped[list | None] = mapped_column(JSON)
    payment_method: Mapped[str | None] = mapped_column(String)
    manually_enriched: Mapped[bool] = mapped_column(Integer, default=False, server_default="0", nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (Index("idx_items_scope", "scope"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String, default="unit")
    reorder_threshold: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)


class ListItem(Base):
    __tablename__ = "list_items"
    __table_args__ = (
        Index("idx_list_items_scope", "scope"),
        Index("idx_list_items_list", "list"),
        Index("idx_list_items_scope_list", "scope", "list"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    list: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    checked: Mapped[bool] = mapped_column(Integer, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)


class ItemMovement(Base):
    __tablename__ = "item_movements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    item_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String, nullable=False)  # in, out, adjustment
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    transaction_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("transactions.id", ondelete="SET NULL"),
    )
    created_at: Mapped[int] = mapped_column(Integer, default=_now)


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (Index("idx_services_scope", "scope"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)


class AgentToken(Base):
    __tablename__ = "agent_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    agent_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    allowed_scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    permissions: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["read", "write"],
    )
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
