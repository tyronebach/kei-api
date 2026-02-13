from typing import Literal

from pydantic import BaseModel


class StrictInput(BaseModel):
    """Base for all input schemas. Rejects unknown fields so agents get
    a clear error instead of silently losing data."""

    model_config = {"extra": "forbid"}


# --- Entities ---


class EntityCreate(StrictInput):
    scope: str
    name: str
    type: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class EntityUpdate(StrictInput):
    scope: str | None = None
    name: str | None = None
    type: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class EntityOut(BaseModel):
    id: str
    scope: str
    name: str
    type: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class EntitySearchOut(EntityOut):
    score: float
    match_type: str


# --- Transactions ---


class TransactionCreate(StrictInput):
    scope: str
    type: Literal["income", "expense"]
    amount: float
    category: str
    description: str | None = None
    date: str
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    meta: dict | None = None


class TransactionUpdate(StrictInput):
    scope: str | None = None
    type: Literal["income", "expense"] | None = None
    amount: float | None = None
    category: str | None = None
    description: str | None = None
    date: str | None = None
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    meta: dict | None = None


class TransactionOut(BaseModel):
    id: str
    scope: str
    type: str
    amount: float
    category: str
    description: str | None = None
    date: str
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    meta: dict | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


# --- Items ---


class ItemCreate(StrictInput):
    scope: str
    name: str
    category: str | None = None
    quantity: float = 0
    unit: str = "unit"
    reorder_threshold: float | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class ItemUpdate(StrictInput):
    scope: str | None = None
    name: str | None = None
    category: str | None = None
    quantity: float | None = None
    unit: str | None = None
    reorder_threshold: float | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class ItemOut(BaseModel):
    id: str
    scope: str
    name: str
    category: str | None = None
    quantity: float
    unit: str
    reorder_threshold: float | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class ItemSearchOut(ItemOut):
    score: float
    match_type: str


# --- Lists ---


class ListItemCreate(StrictInput):
    scope: str
    list: str
    content: str
    position: int | None = None


class ListItemUpdate(StrictInput):
    content: str | None = None
    checked: bool | None = None
    position: int | None = None
    list: str | None = None


class ListItemOut(BaseModel):
    id: str
    scope: str
    list: str
    content: str
    checked: bool
    position: int
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class ItemAdjust(StrictInput):
    type: Literal["in", "out", "adjustment"]
    quantity: float
    reason: str | None = None
    transaction_id: str | None = None


class ItemMovementOut(BaseModel):
    id: str
    item_id: str
    type: str
    quantity: float
    reason: str | None = None
    transaction_id: str | None = None
    created_at: int

    model_config = {"from_attributes": True}
