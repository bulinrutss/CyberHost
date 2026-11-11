from datetime import datetime

from pydantic import BaseModel, Field


class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=80)
    body: str = Field(min_length=3, max_length=4000)


class SupportMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    mention_ids: list[int] = Field(default_factory=list, max_length=20)


class SupportStaffItem(BaseModel):
    id: int
    name: str


class SupportMessageOut(BaseModel):
    id: int
    author_id: int | None
    author_name: str
    author_is_admin: bool
    body: str
    is_system: bool
    mentioned_user_ids: list[int]
    created_at: datetime


class SupportTicketListItem(BaseModel):
    id: int
    subject: str
    status: str
    user_id: int
    user_name: str
    accepted_by_id: int | None
    accepted_by_name: str | None
    last_message_preview: str
    last_message_at: datetime
    created_at: datetime
    waiting_on_staff: bool


class SupportTicketDetail(SupportTicketListItem):
    messages: list[SupportMessageOut]
