from pydantic import BaseModel, Field, field_validator

from app.services.web_page_icons import ALLOWED_LINK_ICONS


class WebPageLink(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=2048)
    icon: str | None = Field(default=None, max_length=32)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        raw = (value or "").strip()
        if not raw.startswith(("http://", "https://")):
            raise ValueError("URL deve começar com http:// ou https://")
        return raw

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str | None) -> str | None:
        if value is None:
            return None
        raw = (value or "").strip().lower()
        if not raw or raw == "none":
            return None
        if raw not in ALLOWED_LINK_ICONS:
            raise ValueError("Ícone inválido")
        return raw


class WebPageConfig(BaseModel):
    template_id: str = Field(min_length=1, max_length=40)
    title: str = Field(default="", max_length=120)
    subtitle: str = Field(default="", max_length=280)
    avatar_path: str | None = Field(default=None, max_length=256)
    accent_color: str = Field(default="#38bdf8", max_length=32)
    background_color: str = Field(default="#0b1220", max_length=32)
    text_color: str = Field(default="#e2e8f0", max_length=32)
    links: list[WebPageLink] = Field(default_factory=list, max_length=24)


class WebPageTemplateInfo(BaseModel):
    id: str
    name: str
    description: str
    preview_accent: str
    preview_background: str


class WebPageLinkIconInfo(BaseModel):
    id: str
    label: str


class WebPageEditorResponse(BaseModel):
    templates: list[WebPageTemplateInfo]
    link_icons: list[WebPageLinkIconInfo] = []
    config: WebPageConfig | None
    using_builder: bool
    avatar_url: str | None = None
