from datetime import datetime

from pydantic import BaseModel, Field


class HostCpuMetrics(BaseModel):
    percent: float | None = None
    cores: int
    load_1: float | None = None
    load_5: float | None = None
    load_15: float | None = None
    per_cpu: list[float] = Field(default_factory=list)


class HostMemoryMetrics(BaseModel):
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent: float
    swap_total_bytes: int = 0
    swap_used_bytes: int = 0
    swap_percent: float = 0.0


class HostDiskMetrics(BaseModel):
    mount: str
    fstype: str = ""
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


class HostDiskIoMetrics(BaseModel):
    read_bytes_per_sec: float | None = None
    write_bytes_per_sec: float | None = None


class HostNetIfaceMetrics(BaseModel):
    name: str
    rx_bytes: int
    tx_bytes: int
    rx_bytes_per_sec: float | None = None
    tx_bytes_per_sec: float | None = None
    rx_errors: int = 0
    tx_errors: int = 0
    rx_dropped: int = 0
    tx_dropped: int = 0


class HostProcessMetrics(BaseModel):
    pid: int
    name: str
    rss_bytes: int


class HostMetricsResponse(BaseModel):
    collected_at: datetime
    hostname: str
    pretty_name: str | None = None
    kernel: str
    architecture: str
    uptime_seconds: float
    process_count: int
    cpu: HostCpuMetrics
    memory: HostMemoryMetrics
    disks: list[HostDiskMetrics] = Field(default_factory=list)
    disk_io: HostDiskIoMetrics = Field(default_factory=HostDiskIoMetrics)
    network: list[HostNetIfaceMetrics] = Field(default_factory=list)
    top_memory: list[HostProcessMetrics] = Field(default_factory=list)
    temperature_c: float | None = None
