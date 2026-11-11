from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

GameTypeSlug = Literal["samp", "mta", "minecraft", "fivem"]

from app.services.game_meta import game_type_label, provision_step_label


class GameTypeInfo(BaseModel):
    slug: GameTypeSlug
    label: str
    description: str
    default_port: int


class GamePresetResponse(BaseModel):
    id: int
    game_type: str
    slug: str
    name: str
    slots: int
    ram_mb: int
    price_cents: int
    is_popular: bool
    sort_order: int

    model_config = {"from_attributes": True}


class GameQuoteRequest(BaseModel):
    game_type: GameTypeSlug
    preset_id: int


class GameQuoteResponse(BaseModel):
    game_type: str
    preset_id: int
    slots: int
    ram_mb: int
    total_cents: int
    monthly_cents: int


class GameOrderCreate(BaseModel):
    game_type: GameTypeSlug
    preset_id: int
    server_name: str = Field(min_length=3, max_length=63, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*[a-zA-Z0-9]$")


class GameOrderResponse(BaseModel):
    id: int
    game_type: str
    preset_id: int | None
    slots: int
    ram_mb: int
    server_name: str
    total_cents: int
    status: str
    payment_checkout_url: str | None
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    provision_progress: int
    provision_step: str | None
    provision_label: str | None = None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_order(cls, order) -> "GameOrderResponse":
        data = cls.model_validate(order)
        data.provision_label = provision_step_label(order.provision_step)
        return data


class GameBillingInfo(BaseModel):
    paid_until: datetime | None
    billing_day: int
    monthly_cents: int
    suspended_for_billing: bool


class GameServerResponse(BaseModel):
    id: int
    game_type: str
    game_label: str
    server_name: str
    slots: int
    ram_mb: int
    port: int
    query_port: int | None
    public_ip: str
    address: str
    status: str
    is_provisioning: bool
    config_file: str
    error_message: str | None
    billing: GameBillingInfo | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GameServerDetail(GameServerResponse):
    provision_progress: int | None = None
    provision_label: str | None = None


class GameFileEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int


class GameFileContent(BaseModel):
    path: str
    content: str


class GameFileWrite(BaseModel):
    path: str
    content: str = Field(max_length=2 * 1024 * 1024)


class GameLogsResponse(BaseModel):
    lines: str
    tail: int
