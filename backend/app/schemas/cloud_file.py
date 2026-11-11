from datetime import datetime

from pydantic import BaseModel, Field


class CloudFileResponse(BaseModel):
    id: int
    parent_id: int | None
    name: str
    is_folder: bool
    size_bytes: int
    mime_type: str | None
    chunk_count: int
    storage_backend: str
    upload_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CloudFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None


class CloudMoveRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    parent_id: int | None = None


class CloudUploadStart(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None
    size_bytes: int = Field(ge=0)
    total_chunks: int = Field(ge=1)
    mime_type: str | None = None
    replace_existing: bool = False


class CloudUploadStartResponse(BaseModel):
    file_id: int
    name: str
    chunk_size_bytes: int
    resumed: bool = False
    renamed_from: str | None = None


class CloudUploadProgressResponse(BaseModel):
    file_id: int
    chunk_count: int
    received_chunks: int
    synced_chunks: int
    received_indices: list[int]
    synced_indices: list[int]
    upload_status: str


class CloudQuotaResponse(BaseModel):
    used_bytes: int
    reserved_bytes: int = 0
    uploading_count: int = 0
    max_concurrent_uploads: int = 5
    quota_bytes: int
    base_bytes: int
    vps_bonus_bytes: int
    subscribed_bytes: int = 0
    bonus_bytes: int = 0
    extra_bytes: int
    contracted_gb: int = 0
    billing: dict | None = None
    chunk_size_bytes: int
    max_upload_bytes: int


class CloudStoragePackageResponse(BaseModel):
    slug: str
    gb: int
    price_cents: int


class CloudStorageRenewQuoteRequest(BaseModel):
    months: int = Field(ge=1, le=12)


class CloudStorageRenewQuoteResponse(BaseModel):
    months: int
    monthly_cents: int
    total_cents: int
    pending_cents: int = 0
    new_paid_until: datetime
    contracted_gb: int
    billing: dict


class CloudStorageRenewResponse(BaseModel):
    order_id: int
    checkout_url: str | None = None
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    renewal_months: int
    total_cents: int
    status: str


class CloudStoragePurchaseRequest(BaseModel):
    package_slug: str = Field(min_length=1, max_length=32)


class CloudStorageQuoteResponse(BaseModel):
    slug: str
    gb: int
    list_price_cents: int
    total_cents: int
    monthly_price_cents: int
    paid_until: str | None = None
    monthly_delta_cents: int = 0
    amount_cents: int = 0
    days_remaining: int = 0
    period_days: int = 30
    prorated: bool = False


class CloudStoragePurchaseResponse(BaseModel):
    order_id: int
    checkout_url: str | None = None
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    extra_gb: int
    total_cents: int
    status: str


class CloudStorageSyncResponse(BaseModel):
    order_id: int
    status: str
    extra_gb: int
    quota_bytes: int
    extra_bytes: int
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    total_cents: int = 0


class CloudStorageOrderResponse(BaseModel):
    id: int
    extra_gb: int
    renewal_months: int | None = None
    total_cents: int
    status: str
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CloudStorageSyncPendingResponse(BaseModel):
    credited_orders: int
    credited_gb: int
    quota_bytes: int
    extra_bytes: int


class CloudFilesLimitsResponse(BaseModel):
    max_upload_bytes: int
    chunk_size_bytes: int


class CloudStorageStatusResponse(BaseModel):
    storage_backend: str
    discord_configured: bool
    bandwidth_limit_mbps: float = 0.0
    max_upload_bytes: int = 0
    chunk_size_bytes: int = 0
    discord_ok: bool
    bot_count: int = 0
    bots_ok: int = 0
    bots: list[dict] = Field(default_factory=list)
    bot_username: str | None = None
    channel_name: str | None = None
    discord_error: str | None = None
    api_features: list[str] = Field(default_factory=list)
    discord_check_pending: bool = False
