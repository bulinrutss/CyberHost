from datetime import datetime

from pydantic import BaseModel


class WebSiteLinkClickStat(BaseModel):
    link_id: str
    label: str
    clicks: int


class WebSiteAnalyticsDayRow(BaseModel):
    date: str
    page_views: int = 0
    link_clicks: int = 0
    unique_visitors: int = 0


class WebSiteAnalyticsResponse(BaseModel):
    days: int
    generated_at: datetime
    page_views: int = 0
    link_clicks: int = 0
    unique_visitors: int = 0
    click_rate_pct: float = 0.0
    daily: list[WebSiteAnalyticsDayRow] = []
    links: list[WebSiteLinkClickStat] = []
