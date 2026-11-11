"""Criador de página estilo Linktree — modelos, JSON e HTML."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.models.web_site import WebSite
from app.schemas.web_page import (
    WebPageConfig,
    WebPageEditorResponse,
    WebPageLink,
    WebPageLinkIconInfo,
    WebPageTemplateInfo,
)
from app.services.web_page_icons import link_icon_html, normalize_link_icon
from app.services.web_files import _assert_quota, _site_root, tree_used_bytes
from app.config import get_settings
from app.services.web_slug import path_prefix, platform_subdomain_for_site, resolved_public_base

CONFIG_NAME = "page.json"
CONFIG_DIR = ".cyberhost"
AVATAR_DIR = "assets"
AVATAR_BASENAME = "avatar"
MAX_AVATAR_BYTES = 2 * 1024 * 1024
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

TEMPLATES: list[WebPageTemplateInfo] = [
    WebPageTemplateInfo(
        id="minimal",
        name="Minimal",
        description="Fundo escuro limpo, tipografia simples e links em cartões discretos.",
        preview_accent="#38bdf8",
        preview_background="#0b1220",
    ),
    WebPageTemplateInfo(
        id="sunset",
        name="Sunset",
        description="Gradiente quente, avatar em destaque e botões arredondados.",
        preview_accent="#fb923c",
        preview_background="#431407",
    ),
    WebPageTemplateInfo(
        id="neon",
        name="Neon",
        description="Visual cyber com brilho, bordas luminosas e contraste forte.",
        preview_accent="#a78bfa",
        preview_background="#090014",
    ),
]

_TEMPLATE_IDS = {item.id for item in TEMPLATES}

_LINK_ICON_LABELS: dict[str, str] = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "whatsapp": "WhatsApp",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "x": "X (Twitter)",
    "linkedin": "LinkedIn",
    "maps": "Google Maps",
    "telegram": "Telegram",
    "spotify": "Spotify",
    "github": "GitHub",
    "link": "Link",
    "email": "E-mail",
    "phone": "Telefone",
}

_DEFAULTS: dict[str, dict[str, str]] = {
    "minimal": {
        "accent_color": "#38bdf8",
        "background_color": "#0b1220",
        "text_color": "#e2e8f0",
    },
    "sunset": {
        "accent_color": "#fb923c",
        "background_color": "#1c0a00",
        "text_color": "#fff7ed",
    },
    "neon": {
        "accent_color": "#a78bfa",
        "background_color": "#090014",
        "text_color": "#f5f3ff",
    },
}


def _config_path(site: WebSite) -> Path:
    return Path(site.data_path).resolve() / CONFIG_DIR / CONFIG_NAME


def _asset_base(site: WebSite) -> str:
    if site.domain:
        return "/"
    if platform_subdomain_for_site(site):
        return "/"
    return f"{path_prefix(site.site_slug)}/"


def _normalize_color(value: str, *, fallback: str) -> str:
    raw = (value or "").strip()
    if _HEX_COLOR.match(raw):
        return raw.lower()
    return fallback


def _load_raw(site: WebSite) -> dict | None:
    path = _config_path(site)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_config(site: WebSite) -> WebPageConfig | None:
    raw = _load_raw(site)
    if not raw:
        return None
    try:
        return WebPageConfig.model_validate(raw)
    except Exception:
        return None


def _link_icons_catalog() -> list[WebPageLinkIconInfo]:
    return [WebPageLinkIconInfo(id=key, label=label) for key, label in _LINK_ICON_LABELS.items()]


def editor_state(site: WebSite) -> WebPageEditorResponse:
    config = load_config(site)
    avatar_url = None
    if config and config.avatar_path:
        base = _asset_base(site).rstrip("/")
        avatar_url = f"{base}/{config.avatar_path.lstrip('/')}"
    return WebPageEditorResponse(
        templates=TEMPLATES,
        link_icons=_link_icons_catalog(),
        config=config,
        using_builder=config is not None,
        avatar_url=avatar_url,
    )


def _write_config(site: WebSite, config: WebPageConfig) -> None:
    path = _config_path(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _api_base() -> str:
    settings = get_settings()
    return f"{resolved_public_base(settings).rstrip('/')}/api/web-sites"


def _click_href(site: WebSite, link: WebPageLink) -> str:
    return f"{_api_base()}/r/{site.site_slug}/{link.id}"


def _tracking_script(site: WebSite) -> str:
    slug_js = json.dumps(site.site_slug)
    api_js = json.dumps(_api_base())
    return f"""<script>
(function(){{
  var slug={slug_js};
  var api={api_js};
  var k="ch_ws_"+slug;
  var v=localStorage.getItem(k);
  if(!v){{v=Math.random().toString(36).slice(2)+Date.now().toString(36);localStorage.setItem(k,v);}}
  var u=api+"/public/pv/"+encodeURIComponent(slug)+"?v="+encodeURIComponent(v);
  if(navigator.sendBeacon){{navigator.sendBeacon(u);}}
  else{{(new Image()).src=u;}}
}})();
</script>"""


def _links_html(site: WebSite, links: list[WebPageLink], *, accent: str, variant: str) -> str:
    if not links:
        return '<p class="empty">Adicione links no painel CyberHost.</p>'
    items = []
    for link in links:
        label = _esc(link.label)
        url = _esc(_click_href(site, link))
        icon_markup = link_icon_html(link.icon)
        icon_block = f'<span class="link-icon">{icon_markup}</span>' if icon_markup else ""
        label_block = f'<span class="link-label">{label}</span>'
        inner = f"{icon_block}{label_block}"
        css_class = f"link {variant}"
        if icon_markup:
            css_class += " with-icon"
        items.append(
            f'<a class="{css_class}" href="{url}" target="_blank" rel="noopener noreferrer">{inner}</a>'
        )
    return "\n".join(items)


def _avatar_html(config: WebPageConfig, base: str) -> str:
    if not config.avatar_path:
        initials = _esc((config.title or "?")[:1].upper())
        return f'<div class="avatar placeholder" aria-hidden="true">{initials}</div>'
    src = _esc(f"{base.rstrip('/')}/{config.avatar_path.lstrip('/')}")
    alt = _esc(config.title or "Avatar")
    return f'<img class="avatar" src="{src}" alt="{alt}" loading="lazy" />'


def render_html(site: WebSite, config: WebPageConfig) -> str:
    template_id = config.template_id if config.template_id in _TEMPLATE_IDS else "minimal"
    defaults = _DEFAULTS[template_id]
    accent = _normalize_color(config.accent_color, fallback=defaults["accent_color"])
    background = _normalize_color(config.background_color, fallback=defaults["background_color"])
    text = _normalize_color(config.text_color, fallback=defaults["text_color"])
    base = _asset_base(site)
    title = _esc(config.title or site.site_slug)
    subtitle = _esc(config.subtitle)
    links_block = _links_html(site, config.links, accent=accent, variant=template_id)
    tracking = _tracking_script(site)
    avatar = _avatar_html(config, base)

    if template_id == "sunset":
        body_bg = (
            f"linear-gradient(160deg, {background} 0%, #7c2d12 45%, {accent}22 100%)"
        )
        extra_css = """
    .wrap { background: BODY_BG; }
    .avatar { border: 3px solid ACCENT; box-shadow: 0 12px 40px ACCENT44; }
    .avatar.placeholder { background: ACCENT33; color: TEXT; font-size: 2.4rem; font-weight: 700; }
    .link.sunset { background: #fff7ed14; border: 1px solid #fff7ed33; border-radius: 999px; }
    .link.sunset:hover { background: ACCENT; color: #1c0a00; border-color: ACCENT; transform: translateY(-2px); }
        """
    elif template_id == "neon":
        body_bg = (
            f"radial-gradient(circle at top, ACCENT33 0%, {background} 55%)"
        ).replace("ACCENT", accent)
        extra_css = """
    .wrap { background: BODY_BG; }
    .avatar { border: 2px solid ACCENT; box-shadow: 0 0 24px ACCENT88, inset 0 0 20px ACCENT33; }
    .avatar.placeholder { background: #1a1033; color: ACCENT; font-size: 2.4rem; font-weight: 700; }
    .link.neon { background: #ffffff08; border: 1px solid ACCENT88; box-shadow: 0 0 12px ACCENT33; }
    .link.neon:hover { box-shadow: 0 0 22px ACCENT; border-color: ACCENT; transform: translateY(-2px); }
        """
    else:
        body_bg = background
        extra_css = """
    .wrap { background: BODY_BG; }
    .avatar { border: 2px solid #ffffff18; }
    .avatar.placeholder { background: #ffffff10; color: TEXT; font-size: 2.4rem; font-weight: 700; }
    .link.minimal { background: #ffffff0c; border: 1px solid #ffffff14; }
    .link.minimal:hover { border-color: ACCENT; color: ACCENT; transform: translateY(-1px); }
        """

    extra_css = (
        extra_css.replace("ACCENT", accent)
        .replace("TEXT", text)
        .replace("BODY_BG", body_bg if template_id != "neon" else body_bg)
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{subtitle}">
  <base href="{_esc(base)}">
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      color: {text};
      background: {background};
    }}
    .wrap {{
      min-height: 100vh;
      display: flex;
      justify-content: center;
      padding: 2.5rem 1.25rem 3rem;
    }}
    main {{
      width: min(28rem, 100%);
      text-align: center;
    }}
    .avatar {{
      width: 6.5rem;
      height: 6.5rem;
      border-radius: 999px;
      object-fit: cover;
      margin: 0 auto 1.25rem;
      display: grid;
      place-items: center;
    }}
    h1 {{
      margin: 0 0 0.5rem;
      font-size: clamp(1.6rem, 4vw, 2rem);
      line-height: 1.2;
    }}
    .subtitle {{
      margin: 0 0 1.75rem;
      color: {text}cc;
      line-height: 1.5;
      font-size: 0.98rem;
    }}
    .links {{
      display: grid;
      gap: 0.75rem;
    }}
    .link {{
      display: block;
      padding: 0.95rem 1.1rem;
      border-radius: 0.9rem;
      text-decoration: none;
      color: inherit;
      font-weight: 600;
      transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
      word-break: break-word;
    }}
    .link.with-icon {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.65rem;
      text-align: left;
    }}
    .link-icon {{
      width: 1.25rem;
      height: 1.25rem;
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .link-icon svg {{
      width: 100%;
      height: 100%;
      fill: currentColor;
    }}
    .link-label {{
      min-width: 0;
    }}
    .empty {{
      opacity: 0.65;
      font-size: 0.9rem;
    }}
    .footer {{
      margin-top: 2rem;
      font-size: 0.75rem;
      opacity: 0.45;
    }}
    {extra_css}
  </style>
</head>
<body>
  <div class="wrap">
    <main>
      {avatar}
      <h1>{title}</h1>
      {"<p class='subtitle'>" + subtitle + "</p>" if subtitle else ""}
      <div class="links">
        {links_block}
      </div>
      <p class="footer">Feito com CyberHost</p>
    </main>
  </div>
  {tracking}
</body>
</html>
"""


def save_page(site: WebSite, config: WebPageConfig) -> WebPageConfig:
    if config.template_id not in _TEMPLATE_IDS:
        raise HTTPException(status_code=400, detail="Modelo inválido")
    if site.php_enabled:
        raise HTTPException(
            status_code=400,
            detail="O criador de página só está disponível em sites estáticos (Starter e Plus).",
        )
    defaults = _DEFAULTS[config.template_id]
    normalized = WebPageConfig(
        template_id=config.template_id,
        title=(config.title or "").strip()[:120],
        subtitle=(config.subtitle or "").strip()[:280],
        avatar_path=config.avatar_path,
        accent_color=_normalize_color(config.accent_color, fallback=defaults["accent_color"]),
        background_color=_normalize_color(
            config.background_color, fallback=defaults["background_color"]
        ),
        text_color=_normalize_color(config.text_color, fallback=defaults["text_color"]),
        links=[WebPageLink.model_validate({**link.model_dump(), "icon": normalize_link_icon(link.icon)}) for link in config.links[:24]],
    )
    _write_config(site, normalized)
    root = _site_root(site)
    index = root / "index.html"
    index.write_text(render_html(site, normalized), encoding="utf-8")
    return normalized


def save_avatar(site: WebSite, file: UploadFile) -> str:
    if site.php_enabled:
        raise HTTPException(status_code=400, detail="Avatar indisponível neste plano")
    content_type = (file.content_type or "").lower()
    ext = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Use JPG, PNG, WebP ou GIF")
    data = file.file.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Imagem até 2 MB")
    assets = _site_root(site) / AVATAR_DIR
    assets.mkdir(parents=True, exist_ok=True)
    for old in assets.glob(f"{AVATAR_BASENAME}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    dest = assets / f"{AVATAR_BASENAME}{ext}"
    _assert_quota(site, len(data), dest)
    dest.write_bytes(data)
    rel = f"{AVATAR_DIR}/{AVATAR_BASENAME}{ext}"
    config = load_config(site)
    if config:
        updated = config.model_copy(update={"avatar_path": rel})
        save_page(site, updated)
    return rel
