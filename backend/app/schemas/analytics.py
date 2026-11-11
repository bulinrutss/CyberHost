from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsEventIn(BaseModel):
    name: str = Field(max_length=32)
    path: str = Field(default="/", max_length=400)
    label: str = Field(default="", max_length=120)
    target: str = Field(default="", max_length=120)
    href: str = Field(default="", max_length=400)
    visitor_id: str = Field(default="", max_length=64)
    session_id: str = Field(default="", max_length=64)
    referrer: str = Field(default="", max_length=400)
    language: str = Field(default="", max_length=32)
    timezone: str = Field(default="", max_length=64)
    ua: str = Field(default="", max_length=300)
    viewport_w: int = Field(default=0, ge=0, le=16000)
    viewport_h: int = Field(default=0, ge=0, le=16000)
    duration_ms: int = Field(default=0, ge=0, le=86_400_000)
    scroll_pct: int = Field(default=0, ge=0, le=100)


class AnalyticsCollectRequest(BaseModel):
    events: list[AnalyticsEventIn] = Field(default_factory=list, max_length=20)


class AnalyticsCountRow(BaseModel):
    key: str
    count: int
    unique: int = 0


class AnalyticsDayRow(BaseModel):
    date: str
    page_views: int = 0
    clicks: int = 0
    forms: int = 0
    visitors: int = 0


class AnalyticsHourRow(BaseModel):
    hour: str
    page_views: int = 0
    clicks: int = 0


class AnalyticsRecentRow(BaseModel):
    at: datetime
    name: str
    path: str
    label: str = ""
    user_name: str | None = None
    is_admin: bool = False


class AnalyticsTotals(BaseModel):
    page_views: int = 0
    clicks: int = 0
    forms: int = 0
    page_leaves: int = 0
    unique_visitors: int = 0
    unique_sessions: int = 0
    identified_users: int = 0
    avg_duration_ms: int = 0
    avg_scroll_pct: int = 0


class AnalyticsAuthSplit(BaseModel):
    anonymous: int = 0
    logged_in: int = 0
    admin: int = 0


class AdminAnalyticsResponse(BaseModel):
    days: int
    generated_at: datetime
    totals: AnalyticsTotals
    auth: AnalyticsAuthSplit
    daily: list[AnalyticsDayRow]
    hourly: list[AnalyticsHourRow]
    top_pages: list[AnalyticsCountRow]
    top_clicks: list[AnalyticsCountRow]
    top_forms: list[AnalyticsCountRow]
    top_entry: list[AnalyticsCountRow]
    browsers: list[AnalyticsCountRow]
    systems: list[AnalyticsCountRow]
    languages: list[AnalyticsCountRow]
    referrers: list[AnalyticsCountRow]
    viewports: list[AnalyticsCountRow]
    recent: list[AnalyticsRecentRow]
