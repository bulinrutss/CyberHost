"""Headers para impedir cache compartilhado de respostas da API."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response


async def api_no_store_cache(request: Request, call_next) -> Response:
    """Impede CDN/browser de reutilizar resposta autenticada entre usuários.

    Sem Cache-Control, um GET /api/auth/me (ou lista de VPS) cacheado na borda
    pode fazer o cliente A ver o JSON do cliente B — inclusive em cidades
    diferentes — enquanto o cookie dele continua o correto.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"
        vary = response.headers.get("Vary")
        extra = "Cookie, Authorization"
        response.headers["Vary"] = f"{vary}, {extra}" if vary else extra
    return response
