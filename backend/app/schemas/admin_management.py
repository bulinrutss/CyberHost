from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ChargeMode = Literal["no_charge", "charge_now", "defer_renewal"]


class ProrationInfo(BaseModel):
    monthly_delta_cents: int = 0
    amount_cents: int = 0
    days_remaining: int = 0
    period_days: int = 30
    prorated: bool = False


class AdminCloudQuotaInfo(BaseModel):
    used_bytes: int
    quota_bytes: int
    base_bytes: int
    vps_bonus_bytes: int
    subscribed_bytes: int = 0
    bonus_bytes: int = 0
    extra_bytes: int
    contracted_gb: int = 0
    cloud_paid_until: datetime | None = None
    cloud_billing_day: int = 1
    cloud_monthly_cents: int = 0
    cloud_suspended_for_billing: bool = False
    admin_pending_cloud_charge_cents: int = 0
    billing: dict | None = None


class AdminVpsSummary(BaseModel):
    id: int
    vm_name: str
    vcpu: int
    ram_mb: int
    disk_gb: int
    status: str
    ip_address: str | None
    paid_until: datetime | None
    monthly_cents: int | None = None
    custom_monthly_cents: int | None = None
    admin_pending_charge_cents: int = 0
    suspended_for_billing: bool = False


class AdminWebSiteSummary(BaseModel):
    id: int
    site_slug: str
    domain: str | None = None
    ram_mb: int
    disk_mb: int
    php_enabled: bool = False
    port: int
    status: str
    paid_until: datetime | None = None
    suspended_for_billing: bool = False


class AdminWebSiteDeleteResponse(BaseModel):
    site_id: int
    message: str


class AdminOrderSummary(BaseModel):
    kind: str
    id: int
    title: str
    description: str
    status: str
    total_cents: int
    created_at: datetime
    error_message: str | None = None
    can_delete: bool = False


class AdminUserDetailResponse(BaseModel):
    id: int
    phone: str
    email: str | None = None
    name: str
    is_active: bool
    is_admin: bool
    mfa_enabled: bool = False
    created_at: datetime
    cloud: AdminCloudQuotaInfo
    vps_instances: list[AdminVpsSummary]
    web_sites: list[AdminWebSiteSummary] = []
    orders: list[AdminOrderSummary] = []


class AdminCloudQuotaAdjustRequest(BaseModel):
    extra_gb: int = Field(ge=1, le=10000)
    charge_mode: ChargeMode = "no_charge"
    note: str | None = Field(default=None, max_length=200)


class AdminCloudQuotaAdjustResponse(BaseModel):
    extra_gb_added: int
    charge_mode: ChargeMode
    charged_cents: int = 0
    deferred_cents: int = 0
    checkout_url: str | None = None
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    order_id: int | None = None
    cloud: AdminCloudQuotaInfo


class AdminVpsUpdateRequest(BaseModel):
    target_vcpu: int = Field(ge=1, le=32)
    target_ram_mb: int = Field(ge=1024, le=65536)
    target_disk_gb: int = Field(ge=30, le=2000)
    charge_mode: ChargeMode = "no_charge"
    apply_vmware: bool = True
    paid_until: datetime | None = None
    clear_suspension: bool = False


class AdminVpsUpdateResponse(BaseModel):
    instance_id: int
    charge_mode: ChargeMode
    charged_cents: int = 0
    deferred_cents: int = 0
    checkout_url: str | None = None
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    order_id: int | None = None
    proration: ProrationInfo | None = None
    vcpu: int
    ram_mb: int
    disk_gb: int


class AdminVpsBillingUpdateRequest(BaseModel):
    paid_until: datetime | None = None
    clear_suspension: bool = False
    clear_pending_charge: bool = False
    custom_monthly_cents: int | None = Field(default=None, ge=0, description="Sobrescreve o valor mensal de renovação")
    clear_custom_monthly_cents: bool = Field(default=False, description="Se True, remove o valor personalizado e volta ao preço do plano")


class AdminAccountDeletionVps(BaseModel):
    id: int
    vm_name: str
    status: str
    ip_address: str | None = None
    vcpu: int
    ram_mb: int
    disk_gb: int


class AdminAccountDeletionGame(BaseModel):
    id: int
    server_name: str
    game_type: str
    status: str
    port: int


class AdminAccountDeletionWebSite(BaseModel):
    id: int
    site_slug: str
    domain: str | None = None
    status: str
    port: int


class AdminAccountDeletionCloud(BaseModel):
    files: int
    folders: int
    used_bytes: int


class AdminAccountDeletionOrders(BaseModel):
    vps: int
    cloud: int
    game: int
    web: int = 0
    pending_payment: int


class AdminAccountDeletionPreview(BaseModel):
    id: int
    name: str
    phone: str
    email: str | None = None
    is_admin: bool
    created_at: datetime
    vps: list[AdminAccountDeletionVps]
    game_servers: list[AdminAccountDeletionGame]
    web_sites: list[AdminAccountDeletionWebSite] = []
    cloud: AdminAccountDeletionCloud
    orders: AdminAccountDeletionOrders
    warnings: list[str] = []


class AdminAccountDeleteRequest(BaseModel):
    confirm_phone: str = Field(min_length=10, max_length=20)


class AdminAccountDeleteResponse(BaseModel):
    deleted_user_id: int
    destroyed_vms: list[str]
    stopped_game_servers: int
    deleted_web_sites: int = 0
    deleted_cloud_files: int


class AdminCloudBillingUpdateRequest(BaseModel):
    paid_until: datetime | None = None
    cloud_contracted_gb: int | None = Field(default=None, ge=0, le=10000)
    cloud_monthly_cents: int | None = Field(default=None, ge=0)
    clear_suspension: bool = False
    clear_pending_charge: bool = False


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


class AdminCreateVpsRequest(BaseModel):
    user_id: int = Field(ge=1)
    hostname: str
    os_template: str = "sv2016"
    plan_id: int | None = None
    preset_id: int | None = None
    vcpu: int = Field(default=2, ge=1, le=32)
    ram_mb: int = Field(default=4096, ge=1024, le=65536)
    disk_gb: int = Field(default=40, ge=30, le=2000)
