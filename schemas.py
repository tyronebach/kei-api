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


class TransactionCreate(StrictInput):
    scope: str
    type: Literal["income", "expense"]
    amount: float = Field(gt=0)
    category: str
    description: str | None = None
    date: str
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    meta: dict | None = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _validate_date_str(value)


class TransactionUpdate(StrictInput):
    scope: str | None = None
    type: Literal["income", "expense"] | None = None
    amount: float | None = Field(default=None, gt=0)
    category: str | None = None
    description: str | None = None
    date: str | None = None
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
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
    amount: float
    category: str
    description: str | None = None
    date: str
    entity_id: str | None = None
    tags: list[str] | None = None
    payment_method: str | None = None
    meta: dict | None = None
    rule_id: str | None = None
    rule_date: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


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


# --- Recurring Rules ---

_VALID_FREQUENCIES = {"monthly", "weekly", "biweekly", "yearly", "custom"}


class RecurringRuleCreate(StrictInput):
    scope: str
    name: str = Field(min_length=1)
    type: Literal["income", "expense"]
    amount: float = Field(gt=0)
    category: str = Field(min_length=1)
    frequency: str
    interval: int = Field(default=1, ge=1)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    start_date: str
    end_date: str | None = None
    description: str | None = None
    entity_id: str | None = None
    payment_method: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in _VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of: {', '.join(sorted(_VALID_FREQUENCIES))}")
        return v

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_dates(cls, v):
        if v is not None:
            _validate_date_str(v)
        return v


class RecurringRuleUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=1)
    amount: float | None = Field(default=None, gt=0)
    category: str | None = None
    frequency: str | None = None
    interval: int | None = Field(default=None, ge=1)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    end_date: str | None = None
    description: str | None = None
    entity_id: str | None = None
    payment_method: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of: {', '.join(sorted(_VALID_FREQUENCIES))}")
        return v

    @field_validator("end_date", mode="before")
    @classmethod
    def validate_end_date(cls, v):
        if v is not None:
            _validate_date_str(v)
        return v


class RecurringRuleOut(BaseModel):
    id: str
    scope: str
    name: str
    type: str
    amount: float
    category: str
    frequency: str
    interval: int
    day_of_month: int | None = None
    start_date: str
    end_date: str | None = None
    description: str | None = None
    entity_id: str | None = None
    payment_method: str | None = None
    tags: list[str] | None = None
    meta: dict | None = None
    next_due: str | None = None       # computed, not stored
    created_by: str | None = None
    updated_by: str | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class RecurringInstanceOut(BaseModel):
    """One occurrence of a recurring rule — either projected or materialised."""
    rule_id: str
    rule_date: str                    # canonical occurrence date
    status: str                       # projected | confirmed | skipped
    # Actual transaction fields (null when projected)
    transaction_id: str | None = None
    amount: float
    type: str
    category: str
    date: str                         # actual date (may differ if overridden)
    description: str | None = None
    entity_id: str | None = None
    payment_method: str | None = None
