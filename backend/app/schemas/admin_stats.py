from datetime import datetime

from pydantic import BaseModel, Field


class AdminStatsClients(BaseModel):
    total: int
    active: int
    admins: int


class AdminStatsOrders(BaseModel):
    total: int
    completed: int
    pending: int
    denied: int
    error: int
    other: int = 0
    revenue_cents: int
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


class AdminStatsHost(BaseModel):
    vps_total: int
    vps_running: int
    vps_stopped: int
    vps_error: int
    vps_suspended: int
    vps_by_status: dict[str, int] = Field(default_factory=dict)
    allocated_vcpu: int
    allocated_ram_mb: int
    allocated_disk_gb: int
    game_servers: int = 0
    cloud_used_bytes: int = 0
    cloud_files: int = 0
    cloud_contracted_gb: int = 0
    cloud_suspended_users: int = 0


class AdminStatsDay(BaseModel):
    date: str
    completed: int = 0
    pending: int = 0
    denied: int = 0
    error: int = 0
    other: int = 0
    revenue_cents: int = 0
    total: int = 0


class AdminStatsClientRow(BaseModel):
    id: int
    name: str
    phone: str
    is_active: bool
    vps_count: int
    vps_running: int
    vps_error: int
    orders: int
    spent_cents: int
    order_errors: int
    cloud_gb: int = 0
    cloud_suspended: bool = False


class AdminStatsMachineRow(BaseModel):
    id: int
    vm_name: str
    status: str
    vcpu: int
    ram_mb: int
    disk_gb: int
    ip_address: str | None = None
    paid_until: datetime | None = None
    suspended_for_billing: bool = False
    error_message: str | None = None
    user_id: int
    user_name: str
    user_phone: str


class AdminStatsEvent(BaseModel):
    at: datetime | None = None
    level: str
    source: str
    title: str
    subject: str | None = None
    status: str
    detail: str | None = None
    user_id: int | None = None
    user_name: str
    user_phone: str = ""
    total_cents: int = 0
    instance_id: int | None = None
    order_id: int | None = None
    can_delete: bool = False


class AdminStatsResponse(BaseModel):
    days: int
    generated_at: datetime
    clients: AdminStatsClients
    orders: AdminStatsOrders
    host: AdminStatsHost
    daily: list[AdminStatsDay]
    top_clients: list[AdminStatsClientRow]
    machines: list[AdminStatsMachineRow]
    events: list[AdminStatsEvent]
