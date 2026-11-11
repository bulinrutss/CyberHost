from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    description: str = ""
    discount_percent: int | None = Field(default=None, ge=1, le=100)
    discount_cents: int | None = Field(default=None, ge=1)
    max_uses: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def check_discount_type(self):
        if bool(self.discount_percent) == bool(self.discount_cents):
            raise ValueError("Informe desconto em percentual OU valor fixo, não ambos")
        return self


class CouponUpdate(BaseModel):
    description: str | None = None
    discount_percent: int | None = Field(default=None, ge=1, le=100)
    discount_cents: int | None = Field(default=None, ge=1)
    max_uses: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None


class CouponResponse(BaseModel):
    id: int
    code: str
    description: str
    discount_percent: int | None
    discount_cents: int | None
    max_uses: int | None
    used_count: int
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
