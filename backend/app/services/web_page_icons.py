"""Ícones SVG para links do criador de página."""

from __future__ import annotations

ALLOWED_LINK_ICONS: frozenset[str] = frozenset(
    {
        "instagram",
        "facebook",
        "whatsapp",
        "youtube",
        "tiktok",
        "x",
        "linkedin",
        "maps",
        "telegram",
        "spotify",
        "github",
        "link",
        "email",
        "phone",
    }
)

_ICON_SVGS: dict[str, str] = {
    "instagram": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4zm5 4.5A4.5 4.5 0 1 0 16.5 12 4.5 4.5 0 0 0 12 7.5zm6-1.25a1 1 0 1 0-1 1 1 1 0 0 0 1-1zM12 9a3 3 0 1 1-3 3 3 3 0 0 1 3-3z"/>'
        "</svg>"
    ),
    "facebook": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M13 22v-8h3l1-4h-4V7.5A1 1 0 0 1 14 6.5h3V3h-3a5 5 0 0 0-5 5v2H6v4h3v8z"/>'
        "</svg>"
    ),
    "whatsapp": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M12 2a10 10 0 0 0-8.7 15l-1.3 4.8 4.9-1.3A10 10 0 1 0 12 2zm0 2a8 8 0 0 1 6.4 12.7l-.3.5-.2.5-2.9.8.8-2.8-.2-.5A8 8 0 1 1 12 4zm-1.1 3.5c.2 0 .5 0 .7.2.3.3.8 1 .9 1.2.1.3.1.6-.1.8l-.5.6c-.1.2-.1.3 0 .5.4.8 1.1 1.5 1.9 1.9.2.1.3.1.5 0l.6-.5c.2-.2.5-.2.8-.1.3.1 1 .6 1.2.9.2.2.2.5.2.7 0 .5-.4 1.1-.9 1.4-.4.2-1 .4-1.7.2A6.5 6.5 0 0 1 8 12.4c-.2-.7 0-1.3.2-1.7.3-.5.9-.9 1.4-.9z"/>'
        "</svg>"
    ),
    "youtube": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M21.6 7.2a3 3 0 0 0-2.1-2.1C17.5 4.5 12 4.5 12 4.5s-5.5 0-7.5.6A3 3 0 0 0 2.4 7.2 31 31 0 0 0 2 12a31 31 0 0 0 .4 4.8 3 3 0 0 0 2.1 2.1c2 .6 7.5.6 7.5.6s5.5 0 7.5-.6a3 3 0 0 0 2.1-2.1A31 31 0 0 0 22 12a31 31 0 0 0-.4-4.8zM10 15.5v-7l6 3.5z"/>'
        "</svg>"
    ),
    "tiktok": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M16.5 3c.3 2.2 1.6 4.2 3.5 5.4V12c-2.2 0-4.2-.7-5.9-1.9v6.4a6.5 6.5 0 1 1-5.6-6.4v3.2a3.2 3.2 0 1 0 2.3 3.1V3h5.7z"/>'
        "</svg>"
    ),
    "x": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M4 3l7.5 9.6L4.2 21h2.6l5.8-7.3L16.8 21H20l-7.9-10.2L19.3 3h-2.6l-5.4 6.8L7.2 3z"/>'
        "</svg>"
    ),
    "linkedin": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M5 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM4 8h3v13H4zm7 0h2.8v1.8h.1c.4-.8 1.5-1.8 3.1-1.8 3.3 0 3.9 2.2 3.9 5v7.9H15v-7c0-1.7 0-3.8-2.3-3.8-2.3 0-2.7 1.8-2.7 3.7V21h-3z"/>'
        "</svg>"
    ),
    "maps": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 14.5 9 2.5 2.5 0 0 1 12 11.5z"/>'
        "</svg>"
    ),
    "telegram": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M21.9 4.6 2.8 11.8c-1.1.4-1.1 1.1-.2 1.4l4.9 1.5 1.9 5.8c.2.6.5.8 1 .8.4 0 .6-.2.9-.6l2.7-2.6 5.6 4.1c1 .6 1.7.3 1.9-1l3.3-15.2c.3-1.3-.5-1.9-1.6-1.6zM8.5 13.7l9.8-6.1c.4-.3.8-.1.5.2L10.2 15l-.4 3.6z"/>'
        "</svg>"
    ),
    "spotify": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm4.3 14.4a.8.8 0 0 1-1.1.3c-3-1.9-6.8-2.3-11.3-1.2a.8.8 0 0 1-.4-1.5c4.9-1.2 9.1-.7 12.5 1.4a.8.8 0 0 1 .3 1zm1.5-3.4a1 1 0 0 1-1.3.4c-3.4-2.1-8.6-2.7-12.7-1.5a1 1 0 0 1-.6-1.9c4.7-1.4 10.5-.7 14.4 1.7a1 1 0 0 1 .2 1.3zm.1-3.6a1.2 1.2 0 0 1-1.6.5C13.7 7.8 8.2 7.6 4.8 8.8a1.2 1.2 0 0 1-.7-2.3c3.9-1.3 10-.9 13.7 1.4a1.2 1.2 0 0 1 .5 1.6z"/>'
        "</svg>"
    ),
    "github": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.8c-3 .7-3.7-1.4-3.7-1.4-.5-1.2-1.2-1.5-1.2-1.5-1-.7.1-.7.1-.7 1.1.1 1.7 1.1 1.7 1.1 1 .1.7 1.7 2.6 2.2 3.3.7 1.1 1.9.8 2.4.6.1-.5.4-.8.7-1-2.2-.3-4.5-1.1-4.5-5a3.9 3.9 0 0 1 1-2.7 3.6 3.6 0 0 1 .1-2.7s.9-.3 2.8 1a9.6 9.6 0 0 1 5.2 0c1.9-1.3 2.8-1 2.8-1 .6 1.4.2 2.4.1 2.7a3.9 3.9 0 0 1 1 2.7c0 3.9-2.3 4.7-4.5 5 .4.3.8 1 .8 2v3c0 .3.2.6.7.5A10 10 0 0 0 12 2z"/>'
        "</svg>"
    ),
    "link": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M10.6 13.4a1 1 0 0 1 0-1.4l2.8-2.8a3 3 0 0 1 4.2 4.2l-1.3 1.3a1 1 0 0 1-1.4-1.4l1.3-1.3a1 1 0 0 0-1.4-1.4l-2.8 2.8a1 1 0 0 1-1.4 0zM13.4 10.6a1 1 0 0 1 0 1.4l-2.8 2.8a3 3 0 1 1-4.2-4.2l1.3-1.3a1 1 0 1 1 1.4 1.4l-1.3 1.3a1 1 0 1 0 1.4 1.4l2.8-2.8a1 1 0 0 1 1.4 0z"/>'
        "</svg>"
    ),
    "email": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm0 2 8 5 8-5H4zm16 2.2-7.4 4.6a1 1 0 0 1-1.2 0L4 9.2V17h16z"/>'
        "</svg>"
    ),
    "phone": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11 11 0 0 0 3.5.55 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1 11 11 0 0 0 .55 3.5 1 1 0 0 1-.25 1z"/>'
        "</svg>"
    ),
}


def normalize_link_icon(icon: str | None) -> str | None:
    raw = (icon or "").strip().lower()
    if not raw or raw == "none":
        return None
    if raw not in ALLOWED_LINK_ICONS:
        return None
    return raw


def link_icon_html(icon: str | None) -> str:
    key = normalize_link_icon(icon)
    if not key:
        return ""
    return _ICON_SVGS.get(key, "")
