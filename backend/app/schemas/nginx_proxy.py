from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProxyKind = Literal["manual", "web_site", "vps_connection"]
ProxyMode = Literal["reverse_proxy", "redirect"]


class NginxProxyEntry(BaseModel):
    key: str
    kind: ProxyKind
    reference_id: int | None = None
    domain: str
    mode: ProxyMode
    target: str
    include_www: bool = False
    ssl_active: bool = False
    editable: bool = True
    deletable: bool = True
    label: str = ""
    notes: str | None = None
    created_at: datetime | None = None


class NginxProxyManualCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    mode: ProxyMode = "reverse_proxy"
    upstream_url: str | None = Field(default=None, max_length=512)
    redirect_url: str | None = Field(default=None, max_length=512)
    include_www: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_targets(self) -> "NginxProxyManualCreate":
        if self.mode == "reverse_proxy":
            if not (self.upstream_url or "").strip():
                raise ValueError("Informe a URL de destino do proxy (upstream_url)")
        elif self.mode == "redirect":
            if not (self.redirect_url or "").strip():
                raise ValueError("Informe a URL de redirecionamento (redirect_url)")
        return self


class NginxProxyManualUpdate(BaseModel):
    domain: str | None = Field(default=None, min_length=3, max_length=253)
    mode: ProxyMode | None = None
    upstream_url: str | None = Field(default=None, max_length=512)
    redirect_url: str | None = Field(default=None, max_length=512)
    include_www: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class NginxProxySystemUpdate(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
