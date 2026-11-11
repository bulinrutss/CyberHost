from pydantic import BaseModel, Field


class DiscoverVmItem(BaseModel):
    vm_name: str
    vm_moid: str
    hostname: str
    suggested_name: str
    vcpu: int
    ram_mb: int
    disk_gb: int
    ip_address: str | None
    power_state: str
    guest_os: str | None
    suggested_plan_slug: str


class DiscoverVmsResponse(BaseModel):
    template_name: str
    unregistered: list[DiscoverVmItem]
    already_registered: list[str]
    skipped: list[dict]


class ImportVmItem(BaseModel):
    vm_name: str = Field(min_length=1, max_length=80)
    user_id: int = Field(ge=1)
    plan_slug: str | None = None


class ImportVmsRequest(BaseModel):
    vms: list[ImportVmItem] = Field(min_length=1)


class ImportedVmResult(BaseModel):
    vm_name: str
    user_id: int
    instance_id: int
    phone: str
    name: str
    email: str | None = None
    plan_slug: str


class ImportVmsResponse(BaseModel):
    imported: list[ImportedVmResult]
    errors: list[dict]
