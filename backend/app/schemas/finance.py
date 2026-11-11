from datetime import date, datetime

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.services.finance import (
    EVENT_CATEGORIES,
    EXPENSE_CATEGORIES,
    GOAL_KINDS,
    INCOME_CATEGORIES,
    PAYMENT_METHODS,
    TRANSACTION_KINDS,
)


def _norm_choice(value: str, allowed: set[str], label: str) -> str:
    key = (value or "").strip().lower()
    if key not in allowed:
        raise ValueError(f"{label} inválido")
    return key


def _optional_title(value: str) -> str:
    return value.strip()[:120]


def _require_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise ValueError("Título é obrigatório")
    return title


class FinanceTransactionCreate(BaseModel):
    kind: str
    title: str = Field(default="", max_length=120)
    amount_cents: int = Field(gt=0, le=1_000_000_000)
    category: str
    payment_method: str = "pix"
    notes: str = Field(default="", max_length=2000)
    occurred_on: date

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        return _norm_choice(value, TRANSACTION_KINDS, "Tipo")

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _optional_title(value)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str) -> str:
        return value.strip()

    @field_validator("payment_method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        return _norm_choice(value, PAYMENT_METHODS, "Forma de pagamento")

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        allowed = INCOME_CATEGORIES | EXPENSE_CATEGORIES
        return _norm_choice(value, allowed, "Categoria")


class FinanceTransactionUpdate(BaseModel):
    kind: str | None = None
    title: str | None = Field(default=None, max_length=120)
    amount_cents: int | None = Field(default=None, gt=0, le=1_000_000_000)
    category: str | None = None
    payment_method: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    occurred_on: date | None = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _norm_choice(value, TRANSACTION_KINDS, "Tipo")

    @field_validator("title", "notes")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("payment_method")
    @classmethod
    def validate_method(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _norm_choice(value, PAYMENT_METHODS, "Forma de pagamento")

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None:
            return value
        allowed = INCOME_CATEGORIES | EXPENSE_CATEGORIES
        return _norm_choice(value, allowed, "Categoria")


class FinanceTransactionOut(BaseModel):
    id: int
    kind: str
    title: str
    amount_cents: int
    category: str
    payment_method: str
    notes: str
    occurred_on: date
    receipt_ext: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def has_receipt(self) -> bool:
        return bool(self.receipt_ext)


class FinanceEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: str = "pessoal"
    notes: str = Field(default="", max_length=2000)
    starts_at: datetime
    duration_min: int = Field(default=60, ge=0, le=24 * 60)
    all_day: bool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _require_title(value)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str) -> str:
        return value.strip()

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        return _norm_choice(value, EVENT_CATEGORIES, "Categoria")


class FinanceEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    starts_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=0, le=24 * 60)
    all_day: bool | None = None

    @field_validator("title", "notes")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _norm_choice(value, EVENT_CATEGORIES, "Categoria")


class FinanceEventOut(BaseModel):
    id: int
    title: str
    category: str
    notes: str
    starts_at: datetime
    duration_min: int
    all_day: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FinanceCategoryOption(BaseModel):
    id: str
    label: str


class FinanceMeta(BaseModel):
    income_categories: list[FinanceCategoryOption]
    expense_categories: list[FinanceCategoryOption]
    event_categories: list[FinanceCategoryOption]
    payment_methods: list[FinanceCategoryOption]
    vapid_public_key: str | None = None
    push_available: bool = False


class FinanceMonthPoint(BaseModel):
    year: int
    month: int
    label: str
    income_cents: int
    expense_cents: int
    balance_cents: int


class FinanceCategoryTotal(BaseModel):
    id: str
    label: str
    amount_cents: int
    kind: str


class FinanceStats(BaseModel):
    income_cents: int
    expense_cents: int
    balance_cents: int
    all_time_balance_cents: int
    transaction_count: int
    avg_daily_expense_cents: int
    month_label: str
    months: list[FinanceMonthPoint]
    by_category: list[FinanceCategoryTotal]
    upcoming_events: list[FinanceEventOut]


class FinanceGoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: str = "savings"
    target_cents: int = Field(gt=0, le=1_000_000_000)
    saved_cents: int = Field(default=0, ge=0, le=1_000_000_000)
    due_day: int | None = Field(default=None, ge=1, le=31)
    deadline: date | None = None
    notes: str = Field(default="", max_length=2000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _require_title(value)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        return _norm_choice(value, GOAL_KINDS, "Tipo de meta")

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def monthly_needs_day(self):
        if self.kind == "monthly" and self.due_day is None:
            raise ValueError("Informe o dia do mês para concluir a meta")
        return self


class FinanceGoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    kind: str | None = None
    target_cents: int | None = Field(default=None, gt=0, le=1_000_000_000)
    saved_cents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    due_day: int | None = Field(default=None, ge=1, le=31)
    deadline: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return _require_title(value) if value is not None else value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _norm_choice(value, GOAL_KINDS, "Tipo de meta")

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class FinanceGoalDeposit(BaseModel):
    amount_cents: int = Field(gt=0, le=1_000_000_000)


class FinanceGoalOut(BaseModel):
    id: int
    title: str
    kind: str = "savings"
    target_cents: int
    saved_cents: int
    remaining_cents: int
    progress_percent: int
    due_day: int | None = None
    due_on: date | None = None
    days_left: int | None = None
    deadline: date | None
    notes: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FinancePushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=64)


class FinancePushSubscribe(BaseModel):
    endpoint: str = Field(min_length=20, max_length=768)
    keys: FinancePushKeys

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint.startswith("https://"):
            raise ValueError("Inscrição inválida")
        return endpoint
