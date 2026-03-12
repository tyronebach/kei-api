from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _validate_date_str(value: str) -> str:
    try:
        date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date format: '{value}'. Expected YYYY-MM-DD.") from exc
    return value


class StrictInput(BaseModel):
    """Base for all input schemas. Rejects unknown fields so agents get
    a clear error instead of silently losing data."""

    model_config = {"extra": "forbid"}

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("*", mode="before")
    @classmethod
    def normalize_string_lists(cls, value):
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            cleaned: list[str] = []
            seen: set[str] = set()
            for item in value:
                normalized = item.strip()
                if not normalized:
                    raise ValueError("List values cannot be empty strings.")
                if normalized not in seen:
                    cleaned.append(normalized)
                    seen.add(normalized)
            return cleaned
        return value


# --- Entities ---


class EntityCreate(StrictInput):
    scope: str
    name: str = Field(min_length=1)
    type: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class EntityUpdate(StrictInput):
    scope: str | None = None
    name: str | None = Field(default=None, min_length=1)
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
    created_by: str | None = None
    updated_by: str | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class EntitySearchOut(EntityOut):
    score: float
    match_type: str


# --- Transactions ---
# Amounts are stored as integer cents internally.
# API input/output uses float dollars (e.g. 80.00).
# Conversion: dollars → cents on ingest, cents → dollars on output.


class TransactionCreate(StrictInput):
    scope: str
    type: Literal["income", "expense"]
    amount: float = Field(gt=0)  # dollars, converted to cents on write
    category: str
    description: str | None = None
    date: str
    entity_id: str | None = None
    external_source: str | None = None
    external_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    manually_enriched: bool = False
    meta: dict | None = None
    force_create: bool = False  # if True, skip fuzzy duplicate check

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _validate_date_str(value)

    @model_validator(mode="after")
    def validate_external_identity(self):
        if (self.external_source is None) != (self.external_id is None):
            raise ValueError("external_source and external_id must both be set or both be absent")
        return self


class TransactionUpdate(StrictInput):
    scope: str | None = None
    type: Literal["income", "expense"] | None = None
    amount: float | None = Field(default=None, gt=0)  # dollars
    category: str | None = None
    description: str | None = None
    date: str | None = None
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    manually_enriched: bool | None = None
    meta: dict | None = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_date_str(value)


class TransactionOut(BaseModel):
    id: str
    scope: str
    type: str
    amount: float  # dollars (cents / 100)
    category: str
    description: str | None = None
    date: str
    entity_id: str | None = None
    external_source: str | None = None
    external_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    manually_enriched: bool = False
    meta: dict | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_cents(cls, obj) -> "TransactionOut":
        """Convert ORM object with integer cents to dollar-based output."""
        data = {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
        data["amount"] = round(obj.amount / 100, 2)
        return cls.model_validate(data)


# --- Items ---


class ItemCreate(StrictInput):
    scope: str
    name: str = Field(min_length=1)
    category: str | None = None
    quantity: float = Field(default=0, ge=0)
    unit: str = "unit"
    reorder_threshold: float | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class ItemUpdate(StrictInput):
    scope: str | None = None
    name: str | None = Field(default=None, min_length=1)
    category: str | None = None
    quantity: float | None = Field(default=None, ge=0)
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
    created_by: str | None = None
    updated_by: str | None = None
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
    content: str = Field(min_length=1)
    position: int | None = None


class ListItemUpdate(StrictInput):
    content: str | None = Field(default=None, min_length=1)
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
    created_by: str | None = None
    updated_by: str | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class ItemAdjust(StrictInput):
    type: Literal["in", "out", "adjustment"]
    quantity: float = Field(ge=0)
    reason: str | None = None
    transaction_id: str | None = None

    @model_validator(mode="after")
    def validate_quantity_by_type(self):
        if self.type in {"in", "out"} and self.quantity <= 0:
            raise ValueError("Quantity must be greater than 0 for 'in' and 'out'.")
        if self.type == "adjustment" and self.quantity < 0:
            raise ValueError("Quantity cannot be negative for 'adjustment'.")
        return self


class ItemMovementOut(BaseModel):
    id: str
    item_id: str
    type: str
    quantity: float
    reason: str | None = None
    transaction_id: str | None = None
    created_at: int

    model_config = {"from_attributes": True}


# --- Services ---


class ServiceCreate(StrictInput):
    scope: str
    name: str = Field(min_length=1)
    category: str | None = None
    price: float = Field(gt=0)
    duration_minutes: int | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class ServiceUpdate(StrictInput):
    scope: str | None = None
    name: str | None = Field(default=None, min_length=1)
    category: str | None = None
    price: float | None = Field(default=None, gt=0)
    duration_minutes: int | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None


class ServiceOut(BaseModel):
    id: str
    scope: str
    name: str
    category: str | None = None
    price: float
    duration_minutes: int | None = None
    notes: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}
