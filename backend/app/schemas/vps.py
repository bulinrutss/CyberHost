from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

OsTemplateSlug = Literal["sv2016", "sv2019"]

from app.models.vps import OrderStatus, VpsStatus
from app.services.provision_progress import STEP_LABELS, sanitize_customer_error


class PlanResponse(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    min_vcpu: int
    max_vcpu: int
    min_ram_mb: int
    max_ram_mb: int
    network_mbps: int
    default_disk_gb: int
    max_disk_gb: int
    price_per_vcpu_cents: int
    price_per_gb_ram_cents: int
    price_per_gb_disk_cents: int

    model_config = {"from_attributes": True}


class PlanPresetResponse(BaseModel):
    id: int
    plan_id: int
    slug: str
    name: str
    vcpu: int
    ram_mb: int
    disk_gb: int
    price_cents: int
    is_popular: bool
    sort_order: int
    cloud_bonus_gb: int = 0

    model_config = {"from_attributes": True}


class OsTemplateResponse(BaseModel):
    slug: OsTemplateSlug
    label: str
    template_name: str
    is_recommended: bool
    recommended_min_vcpu: int
    recommended_min_ram_mb: int
    recommended_min_disk_gb: int
    description: str


class PriceQuoteRequest(BaseModel):
    plan_id: int
    vcpu: int = Field(ge=1, le=32)
    ram_mb: int = Field(ge=1024, le=65536)
    disk_gb: int = Field(ge=30, le=2000)
    preset_id: int | None = None
    coupon_code: str | None = Field(default=None, max_length=32)
    os_template: OsTemplateSlug = "sv2016"


class PriceQuoteResponse(BaseModel):
    subtotal_cents: int
    discount_cents: int = 0
    total_cents: int
    monthly_cents: int
    coupon_code: str | None = None
    warnings: list[str] = []
    vcpu: int
    ram_mb: int
    disk_gb: int
    os_template: OsTemplateSlug = "sv2016"


class OrderCreate(BaseModel):
    plan_id: int = 1
    preset_id: int | None = None
    vcpu: int = Field(ge=1, le=32)
    ram_mb: int = Field(ge=1024, le=65536)
    disk_gb: int = Field(ge=30, le=2000)
    hostname: str
    coupon_code: str | None = Field(default=None, max_length=32)
    os_template: OsTemplateSlug = "sv2016"

    @field_validator("hostname")
    @classmethod
    def hostname_must_be_plain(cls, value: str) -> str:
        from app.services.hostname import validate_hostname

        return validate_hostname(value)


class WindowsCredentials(BaseModel):
    username: str
    password: str | None = None
    has_password: bool = False

    @model_validator(mode="after")
    def _infer_has_password(self) -> Self:
        if self.password:
            self.has_password = True
        return self


class PortMappingResponse(BaseModel):
    public_host: str
    public_port: int
    internal_host: str
    internal_port: int
    connection_address: str
    label: str


class VpsConnectionDomainResponse(BaseModel):
    id: int
    domain: str
    public_port: int
    internal_port: int
    http_proxy: bool = False
    ssl_active: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class VpsConnectionDomainCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    public_port: int = Field(ge=1, le=65535)


class BillingInfo(BaseModel):
    billing_state: str
    billing_label: str
    paid_until: datetime
    grace_ends_at: datetime
    billing_day: int
    monthly_cents: int | None = None
    suspended_for_billing: bool
    days_until_due: int
    days_in_grace_left: int
    can_power_on: bool


class RenewQuoteRequest(BaseModel):
    months: int = Field(ge=1, le=12)


class RenewQuoteResponse(BaseModel):
    months: int
    monthly_cents: int
    subtotal_cents: int
    discount_cents: int = 0
    discount_percent: float = 0
    total_cents: int
    paid_until: datetime
    new_paid_until: datetime
    billing: BillingInfo


class OrderResponse(BaseModel):
    id: int
    vcpu: int
    ram_mb: int
    disk_gb: int = 30
    subtotal_cents: int | None = None
    discount_cents: int = 0
    hostname: str
    order_type: str = "new"
    target_instance_id: int | None = None
    renewal_months: int | None = None
    status: OrderStatus
    total_cents: int
    payment_checkout_url: str | None
    payment_provider: str
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None
    provision_progress: int = 0
    provision_step: str | None = None
    provision_label: str | None = None
    error_message: str | None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def set_provision_label(self) -> Self:
        self.error_message = sanitize_customer_error(self.error_message)
        if self.provision_step:
            self.provision_label = STEP_LABELS.get(self.provision_step, self.provision_step)
        elif self.status == OrderStatus.PENDING_PAYMENT:
            self.provision_label = STEP_LABELS["payment_pending"]
        elif self.status == OrderStatus.PAID:
            self.provision_label = STEP_LABELS["payment_confirmed"]
        elif self.status == OrderStatus.PROVISIONING:
            self.provision_label = STEP_LABELS["preparing"]
        elif self.status == OrderStatus.ACTIVE:
            self.provision_label = STEP_LABELS["ready"]
        elif self.status == OrderStatus.FAILED:
            self.provision_label = STEP_LABELS["failed"]
        return self


class VpsMetrics(BaseModel):
    cpu_allocated: int
    ram_allocated_mb: int
    disk_allocated_gb: float | None = None
    cpu_usage_percent: float | None = None
    ram_used_mb: int | None = None
    ram_usage_percent: float | None = None
    disk_used_gb: float | None = None
    disk_free_gb: float | None = None
    disk_usage_percent: float | None = None
    disk_source: str = "none"
    uptime_seconds: int | None = None
    guest_os: str | None = None
    guest_ip: str | None = None


class UpgradeQuoteRequest(BaseModel):
    target_vcpu: int = Field(ge=1, le=32)
    target_ram_mb: int = Field(ge=1024, le=65536)
    target_disk_gb: int = Field(ge=30, le=2000)
    preset_id: int | None = None


class UpgradeQuoteResponse(BaseModel):
    current_vcpu: int
    current_ram_mb: int
    current_disk_gb: int
    target_vcpu: int
    target_ram_mb: int
    target_disk_gb: int
    total_cents: int
    monthly_delta_cents: int = 0
    current_monthly_cents: int = 0
    new_monthly_cents: int = 0
    days_remaining: int = 0
    period_days: int = 30
    prorated: bool = False
    paid_until: datetime | None = None
    plan: PlanResponse


class VpsInstanceResponse(BaseModel):
    id: int
    vm_name: str
    vcpu: int
    ram_mb: int
    disk_gb: int = 30
    os_template: str | None = None
    os_label: str | None = None
    network_mbps: int = 300
    plan_slug: str | None = None
    plan_name: str | None = None
    ip_address: str | None
    status: VpsStatus
    esxi_host: str
    error_message: str | None
    is_provisioning: bool = False
    provision_progress: int | None = None
    provision_label: str | None = None
    billing: BillingInfo | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VpsInstanceListResponse(VpsInstanceResponse):
    power_state: str
    cpu_usage_percent: float | None = None
    ram_usage_percent: float | None = None
    disk_allocated_gb: float | None = None
    disk_usage_percent: float | None = None


class VpsInstanceDetailResponse(VpsInstanceResponse):
    power_state: str
    tools_ok: bool
    metrics: VpsMetrics
    windows_credentials: WindowsCredentials | None = None
    port_mappings: list[PortMappingResponse] = []
    connection_domains: list[VpsConnectionDomainResponse] = []
    dns_target: str = ""
    rdp_connection_address: str | None = None


class VpsActionResponse(BaseModel):
    success: bool
    message: str
    instance: VpsInstanceResponse | None = None


class VpsConsoleResponse(BaseModel):
    available: bool
    power_state: str
    ws_path: str
    message: str | None = None


class VpsConsoleTicketResponse(BaseModel):
    wss_url: str
    host: str
    port: int
    expires_in_seconds: int = 1800


class VpsConsoleWsTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int
    ws_path: str


class ChangeIpRequest(BaseModel):
    ip_address: str = Field(pattern=r"^\d{1,3}(\.\d{1,3}){3}$")


class ChangePasswordRequest(BaseModel):
    username: str = Field(default="Administrador", min_length=1, max_length=64)
    new_password: str = Field(min_length=8, max_length=128)


class VpsInstanceAdminResponse(VpsInstanceResponse):
    user_id: int
    user_phone: str
    user_name: str
    custom_monthly_cents: int | None = None


class VpsInstanceAdminDetailResponse(VpsInstanceAdminResponse):
    power_state: str
    tools_ok: bool
    metrics: VpsMetrics
    windows_credentials: WindowsCredentials | None = None
    rdp_connection_address: str | None = None
