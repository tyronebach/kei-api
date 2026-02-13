from typing import Literal

from pydantic import BaseModel


# --- Entities ---


class EntityCreate(BaseModel):
    name: str
    type: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class EntityUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class EntityOut(BaseModel):
    id: str
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


# --- Transactions ---


class TransactionCreate(BaseModel):
    type: Literal["income", "expense"]
    amount: float
    category: str
    description: str | None = None
    date: str
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    meta: dict | None = None


class TransactionUpdate(BaseModel):
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


class ItemCreate(BaseModel):
    name: str
    category: str | None = None
    quantity: float = 0
    unit: str = "unit"
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class ItemUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    quantity: float | None = None
    unit: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class ItemOut(BaseModel):
    id: str
    name: str
    category: str | None = None
    quantity: float
    unit: str
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}
