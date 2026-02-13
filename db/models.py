import time
import uuid

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from db.connection import Base


def _generate_id() -> str:
    return uuid.uuid4().hex


def _now() -> int:
    return int(time.time())


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_date", "date"),
        Index("idx_transactions_type", "type"),
        Index("idx_transactions_category", "category"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    date: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String)
    tags: Mapped[list | None] = mapped_column(JSON)
    payment_method: Mapped[str | None] = mapped_column(String)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String, default="unit")
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now, onupdate=_now)
