from datetime import datetime

from pydantic import BaseModel, Field


class WebPresetResponse(BaseModel):
    id: int
    slug: str
    name: str
    ram_mb: int
    disk_mb: int
    cpu_percent: int
    php_enabled: bool
    price_cents: int
    cloud_bonus_gb: int = 0
    is_popular: bool
    sort_order: int

    model_config = {"from_attributes": True}


class WebQuoteRequest(BaseModel):
    preset_id: int
    coupon_code: str | None = None


class WebQuoteResponse(BaseModel):
    preset_id: int
    ram_mb: int
    disk_mb: int
    cpu_percent: int
    php_enabled: bool
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    monthly_cents: int
    coupon_code: str | None = None


class WebOrderCreate(BaseModel):
    preset_id: int
    site_slug: str = Field(min_length=2, max_length=63)
    domain: str | None = Field(default=None, max_length=253)
    coupon_code: str | None = None


class WebRenewQuoteRequest(BaseModel):
    months: int = Field(ge=1, le=12)


class WebRenewQuoteResponse(BaseModel):
    months: int
    monthly_cents: int
    subtotal_cents: int
    discount_cents: int
    discount_percent: float
    total_cents: int
    paid_until: datetime
    new_paid_until: datetime
    billing: "WebBillingInfo"


class WebOrderResponse(BaseModel):
    id: int
    order_type: str = "new"
    target_site_id: int | None = None
    renewal_months: int | None = None
    preset_id: int | None
    site_slug: str
    domain: str | None
    ram_mb: int
    disk_mb: int
    cpu_percent: int
    php_enabled: bool
    subtotal_cents: int | None = None
    discount_cents: int = 0
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
    def from_order(cls, order) -> "WebOrderResponse":
        data = cls.model_validate(order)
        data.order_type = (
            order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type or "new")
        )
        data.status = order.status.value if hasattr(order.status, "value") else str(order.status)
        labels = {
            "payment_pending": "Aguardando pagamento",
            "payment_confirmed": "Pagamento confirmado",
            "allocating": "Reservando porta e pasta",
            "writing_files": "Criando o site",
            "starting": "Ligando o serviço",
            "nginx": "Publicando no nginx",
            "failed": "Falha",
            "cancelled_by_user": "Cancelado",
            "configuring": "Aplicando renovação",
            "ready": "Renovação concluída",
        }
        data.provision_label = labels.get(order.provision_step or "", order.provision_step)
        return data


class WebBillingInfo(BaseModel):
    billing_state: str
    billing_label: str
    paid_until: datetime | None
    grace_ends_at: datetime | None = None
    billing_day: int
    monthly_cents: int
    suspended_for_billing: bool
    days_until_due: int = 0
    days_in_grace_left: int = 0
    can_power_on: bool = True


class WebHostingDnsResponse(BaseModel):
    dns_target: str


class WebSiteResponse(BaseModel):
    id: int
    site_slug: str
    domain: str | None
    path_url: str
    ram_mb: int
    disk_mb: int
    cpu_percent: int
    php_enabled: bool
    port: int
    status: str
    is_provisioning: bool
    error_message: str | None
    public_url: str
    dns_target: str
    ssl_active: bool = False
    billing: WebBillingInfo | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WebSiteDetail(WebSiteResponse):
    data_used_bytes: int = 0
    provision_progress: int | None = None
    provision_label: str | None = None


class WebSiteAdminResponse(WebSiteResponse):
    user_id: int
    user_phone: str
    user_name: str


class WebSiteAdminDetailResponse(WebSiteDetail):
    user_id: int
    user_phone: str
    user_name: str


class WebDomainUpdate(BaseModel):
    domain: str | None = Field(default=None, max_length=253)


class WebFileEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int


class WebFileContent(BaseModel):
    path: str
    content: str


class WebFileWrite(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=2_000_000)


class WebFileMkdir(BaseModel):
    path: str = Field(default="", max_length=512)
    name: str = Field(min_length=1, max_length=120)


class WebLogsResponse(BaseModel):
    lines: str
    tail: int


WebRenewQuoteResponse.model_rebuild()
