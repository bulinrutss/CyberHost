from datetime import datetime

from pydantic import BaseModel, Field


class HostFileEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified_at: datetime | None = None


class HostFileListResponse(BaseModel):
    path: str
    parent: str | None = None
    entries: list[HostFileEntry]


class HostFileContent(BaseModel):
    path: str
    content: str
    size: int


class HostFileWrite(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=4_000_000)


class HostMkdirRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=255)


class HostRenameRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    new_name: str = Field(min_length=1, max_length=255)


class HostShellTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int
    ws_path: str
    available: bool
    message: str | None = None
