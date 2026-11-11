"""Armazenamento de fragmentos via API REST do Discord (suporta múltiplos bots)."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Iterator

import httpx
from fastapi import HTTPException

from app.config import Settings, get_settings
from app.services import bandwidth_limiter
from app.services.cloud_log import TAG_DISCORD, fmt_bytes, log_info

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
MAX_RETRIES_PER_BOT = 2

_meta_lock = threading.Lock()
_bot_locks: dict[int, threading.Lock] = {}
_bot_last_request: dict[int, float] = {}
_bot_cooldown_until: dict[int, float] = {}
_health_cache: dict | None = None
_health_cache_at: float = 0.0
_health_refresh_running = False
HEALTH_CACHE_SECONDS = 45.0


def _min_interval() -> float:
    return max(get_settings().discord_upload_interval_seconds, 0.5)


def _bot_lock(bot_index: int) -> threading.Lock:
    with _meta_lock:
        if bot_index not in _bot_locks:
            _bot_locks[bot_index] = threading.Lock()
        return _bot_locks[bot_index]


def _mark_bot_cooldown(bot_index: int, seconds: float) -> None:
    with _meta_lock:
        _bot_cooldown_until[bot_index] = time.monotonic() + seconds


def _is_bot_in_cooldown(bot_index: int) -> bool:
    with _meta_lock:
        until = _bot_cooldown_until.get(bot_index, 0.0)
    return time.monotonic() < until


def _throttle(bot_index: int) -> None:
    interval = _min_interval()
    with _bot_lock(bot_index):
        now = time.monotonic()
        cooldown_until = _bot_cooldown_until.get(bot_index, 0.0)
        if now < cooldown_until:
            time.sleep(cooldown_until - now)
        last = _bot_last_request.get(bot_index, 0.0)
        wait = interval - (now - last)
        if wait > 0:
            time.sleep(wait)
        _bot_last_request[bot_index] = time.monotonic()


def _parse_retry_after(response: httpx.Response) -> float:
    minimum = _min_interval() * 2
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(float(header), minimum)
        except ValueError:
            pass
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("retry_after") is not None:
            return max(float(body["retry_after"]), minimum)
    except Exception:
        pass
    return minimum


class DiscordStorageService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def tokens(self) -> list[str]:
        return self.settings.discord_bot_token_list

    @property
    def bot_count(self) -> int:
        return len(self.tokens)

    @property
    def configured(self) -> bool:
        return self.bot_count > 0 and bool(self.settings.discord_storage_channel_id.strip())

    @property
    def channel_id(self) -> str:
        return self.settings.discord_storage_channel_id.strip()

    @property
    def url_cache_seconds(self) -> int:
        return self.settings.discord_url_cache_seconds

    def pick_bot_index(self, chunk_index: int) -> int:
        if self.bot_count == 0:
            raise HTTPException(status_code=503, detail="Nenhum bot Discord configurado")
        preferred = chunk_index % self.bot_count
        return self._best_available_bot(preferred)

    def _best_available_bot(self, preferred: int) -> int:
        candidates = list(range(self.bot_count))
        available = [i for i in candidates if not _is_bot_in_cooldown(i)]
        pool = available if available else candidates
        return min(pool, key=lambda i: _bot_last_request.get(i, 0.0))

    def _bot_try_order(self, preferred: int) -> list[int]:
        """Ordem de tentativa: preferred, depois os demais (disponíveis primeiro)."""
        order: list[int] = []
        for offset in range(self.bot_count):
            idx = (preferred + offset) % self.bot_count
            if idx not in order:
                order.append(idx)
        available = [i for i in order if not _is_bot_in_cooldown(i)]
        cooled = [i for i in order if _is_bot_in_cooldown(i)]
        return available + cooled

    def resolve_bot_index(self, chunk_index: int, stored_index: int | None) -> int:
        if stored_index is not None and 0 <= stored_index < self.bot_count:
            return stored_index
        return self.pick_bot_index(chunk_index)

    def url_cache_valid(self, cached_at) -> bool:
        if cached_at is None:
            return False
        from datetime import datetime

        age = (datetime.utcnow() - cached_at).total_seconds()
        return age < self.url_cache_seconds

    def _require_config(self) -> None:
        if not self.configured:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Discord não configurado: defina DISCORD_BOT_TOKENS (ou DISCORD_BOT_TOKEN) "
                    "e DISCORD_STORAGE_CHANNEL_ID no .env"
                ),
            )

    def _token_for(self, bot_index: int) -> str:
        tokens = self.tokens
        if not tokens:
            raise HTTPException(status_code=503, detail="Nenhum bot Discord configurado")
        return tokens[bot_index % len(tokens)]

    def _headers(self, bot_index: int) -> dict[str, str]:
        return {"Authorization": f"Bot {self._token_for(bot_index)}"}

    def _client(self, bot_index: int) -> httpx.Client:
        return httpx.Client(
            base_url=DISCORD_API_BASE,
            headers=self._headers(bot_index),
            timeout=httpx.Timeout(90.0, connect=20.0),
        )

    def _request(
        self, client: httpx.Client, bot_index: int, method: str, path: str, **kwargs
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(MAX_RETRIES_PER_BOT):
            _throttle(bot_index)
            try:
                response = client.request(method, path, **kwargs)
            except httpx.TimeoutException as exc:
                log_info(logger, TAG_DISCORD, "Timeout bot #%d: %s", bot_index + 1, exc)
                raise HTTPException(
                    status_code=504,
                    detail=f"Timeout no bot #{bot_index + 1}",
                ) from exc
            last_response = response
            if response.status_code != 429:
                return response
            retry_after = _parse_retry_after(response)
            _mark_bot_cooldown(bot_index, retry_after)
            log_info(
                logger,
                TAG_DISCORD,
                "Rate limit bot #%d (tentativa %d/%d), cooldown %.1fs",
                bot_index + 1,
                attempt + 1,
                MAX_RETRIES_PER_BOT,
                retry_after,
            )
            if attempt + 1 < MAX_RETRIES_PER_BOT:
                time.sleep(retry_after)
        raise HTTPException(
            status_code=429,
            detail=f"Bot #{bot_index + 1} em rate limit",
        )

    def _raise_for_status(self, response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        detail = action
        try:
            body = response.json()
            if isinstance(body, dict) and body.get("message"):
                detail = f"{action}: {body['message']}"
        except Exception:
            detail = f"{action}: HTTP {response.status_code}"
        log_info(logger, TAG_DISCORD, "Erro API Discord: %s", detail)
        raise HTTPException(status_code=502, detail=detail)

    def _upload_with_bot(
        self,
        bot_idx: int,
        *,
        file_id: int,
        chunk_index: int,
        data: bytes,
        target_channel: str,
    ) -> tuple[str, str, str, str, int]:
        filename = f"ch{file_id}_{chunk_index:06d}.bin"
        payload = {"content": f"cyberhost f={file_id} c={chunk_index} b={bot_idx}"}

        log_info(
            logger,
            TAG_DISCORD,
            "Enviando fragmento file_id=%s chunk=%s bot=#%s tamanho=%s",
            file_id,
            chunk_index + 1,
            bot_idx + 1,
            fmt_bytes(len(data)),
        )
        bandwidth_limiter.acquire(len(data))
        with self._client(bot_idx) as client:
            response = self._request(
                client,
                bot_idx,
                "POST",
                f"/channels/{target_channel}/messages",
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": (filename, data, "application/octet-stream")},
            )
            self._raise_for_status(response, f"Falha ao enviar fragmento (bot #{bot_idx + 1})")

            message = response.json()
            attachments = message.get("attachments") or []
            if not attachments:
                raise HTTPException(status_code=502, detail="Discord não retornou anexo na mensagem")

            attachment = attachments[0]
            message_id = str(message["id"])
            attachment_id = str(attachment["id"])
            url = attachment.get("url")
            if not url:
                raise HTTPException(status_code=502, detail="Discord não retornou URL do anexo")
            log_info(
                logger,
                TAG_DISCORD,
                "Fragmento enviado file_id=%s chunk=%s bot=#%s msg=%s",
                file_id,
                chunk_index + 1,
                bot_idx + 1,
                message_id,
            )
            return target_channel, message_id, attachment_id, url, bot_idx

    def upload_chunk(
        self,
        *,
        file_id: int,
        chunk_index: int,
        data: bytes,
        channel_id: str | None = None,
        bot_index: int | None = None,
    ) -> tuple[str, str, str, str, int]:
        """Envia fragmento tentando vários bots se um estiver em rate limit."""
        self._require_config()
        preferred = self.resolve_bot_index(chunk_index, bot_index)
        target_channel = (channel_id or self.channel_id).strip()
        errors: list[str] = []

        log_info(
            logger,
            TAG_DISCORD,
            "Upload chunk file_id=%s chunk=%s prefer_bot=#%s bots=%s",
            file_id,
            chunk_index + 1,
            preferred + 1,
            self.bot_count,
        )
        for bot_idx in self._bot_try_order(preferred):
            try:
                result = self._upload_with_bot(
                    bot_idx,
                    file_id=file_id,
                    chunk_index=chunk_index,
                    data=data,
                    target_channel=target_channel,
                )
                if bot_idx != preferred:
                    log_info(
                        logger,
                        TAG_DISCORD,
                        "Fallback upload file_id=%s chunk=%s bot=#%d (preferido era #%d)",
                        file_id,
                        chunk_index + 1,
                        bot_idx + 1,
                        preferred + 1,
                    )
                return result
            except HTTPException as exc:
                errors.append(f"bot #{bot_idx + 1}: {exc.detail}")
                if exc.status_code in (429, 502, 504):
                    continue
                raise

        raise HTTPException(
            status_code=502,
            detail=f"Todos os {self.bot_count} bots falharam: {'; '.join(errors[:3])}",
        )

    def resolve_attachment_url(
        self,
        channel_id: str,
        message_id: str,
        attachment_id: str | None,
        bot_index: int,
        chunk_index: int = 0,
    ) -> str:
        """Obtém URL fresca do anexo via API (links CDN expiram ~24 h)."""
        self._require_config()
        preferred = self.resolve_bot_index(chunk_index, bot_index)
        errors: list[str] = []

        log_info(
            logger,
            TAG_DISCORD,
            "Resolvendo URL msg=%s chunk=%s prefer_bot=#%s",
            message_id,
            chunk_index + 1,
            preferred + 1,
        )
        for bot_idx in self._bot_try_order(preferred):
            try:
                with self._client(bot_idx) as client:
                    response = self._request(
                        client, bot_idx, "GET", f"/channels/{channel_id}/messages/{message_id}"
                    )
                    self._raise_for_status(response, "Falha ao buscar mensagem no Discord")

                    message = response.json()
                    attachments = message.get("attachments") or []
                    if not attachments:
                        raise HTTPException(
                            status_code=404, detail="Anexo não encontrado na mensagem Discord"
                        )

                    if attachment_id:
                        for item in attachments:
                            if str(item.get("id")) == attachment_id:
                                url = item.get("url")
                                if url:
                                    log_info(
                                        logger,
                                        TAG_DISCORD,
                                        "URL obtida msg=%s bot=#%s",
                                        message_id,
                                        bot_idx + 1,
                                    )
                                    return url
                        raise HTTPException(
                            status_code=404, detail="Anexo específico não encontrado"
                        )

                    url = attachments[0].get("url")
                    if not url:
                        raise HTTPException(status_code=404, detail="URL do anexo indisponível")
                    log_info(
                        logger,
                        TAG_DISCORD,
                        "URL obtida msg=%s bot=#%s",
                        message_id,
                        bot_idx + 1,
                    )
                    return url
            except HTTPException as exc:
                errors.append(f"bot #{bot_idx + 1}: {exc.detail}")
                if exc.status_code in (429, 502, 504):
                    continue
                raise

        raise HTTPException(
            status_code=502,
            detail=f"Falha ao buscar URL: {'; '.join(errors[:3])}",
        )

    def download_attachment(self, url: str, max_bytes: int | None = None) -> Iterator[bytes]:
        log_info(logger, TAG_DISCORD, "Download CDN iniciado url=%s…", url[:80])
        limit = max_bytes if max_bytes is not None else get_settings().discord_attachment_limit_bytes
        total = 0
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
                with client.stream("GET", url) as response:
                    if response.status_code == 429:
                        retry_after = _parse_retry_after(response)
                        log_info(
                            logger,
                            TAG_DISCORD,
                            "Rate limit CDN, aguardando %.1fs",
                            retry_after,
                        )
                        time.sleep(retry_after)
                        with client.stream("GET", url) as retry_response:
                            self._raise_for_status(
                                retry_response, "Falha ao baixar fragmento do Discord"
                            )
                            for block in bandwidth_limiter.iter_capped(
                                retry_response.iter_bytes(), limit
                            ):
                                total += len(block)
                                yield block
                        log_info(
                            logger, TAG_DISCORD, "Download CDN OK tamanho=%s", fmt_bytes(total)
                        )
                        return
                    self._raise_for_status(response, "Falha ao baixar fragmento do Discord")
                    for block in bandwidth_limiter.iter_capped(response.iter_bytes(), limit):
                        total += len(block)
                        yield block
            log_info(logger, TAG_DISCORD, "Download CDN OK tamanho=%s", fmt_bytes(total))
        except bandwidth_limiter.TransferLimitExceeded:
            raise HTTPException(
                status_code=502,
                detail="Fragmento Discord excede o limite permitido",
            )

    def delete_message(self, channel_id: str, message_id: str, bot_index: int = 0) -> None:
        self._require_config()
        bot_idx = bot_index if 0 <= bot_index < self.bot_count else 0
        with self._client(bot_idx) as client:
            response = self._request(
                client, bot_idx, "DELETE", f"/channels/{channel_id}/messages/{message_id}"
            )
            if response.status_code == 404:
                return
            self._raise_for_status(response, "Falha ao excluir mensagem no Discord")

    def try_delete_message(self, channel_id: str, message_id: str, bot_index: int = 0) -> bool:
        """True se a mensagem não existe mais; False se o purge deve tentar de novo."""
        try:
            self.delete_message(channel_id, message_id, bot_index)
            return True
        except HTTPException:
            return False
        except Exception:
            log_info(
                logger,
                TAG_DISCORD,
                "Exclusão Discord falhou channel=%s message=%s",
                channel_id,
                message_id,
            )
            return False

    def get_cached_health(self) -> dict | None:
        global _health_cache, _health_cache_at
        if _health_cache is None:
            return None
        if time.monotonic() - _health_cache_at >= HEALTH_CACHE_SECONDS:
            return None
        return dict(_health_cache)

    def refresh_health_async(self) -> None:
        """Dispara health check em thread separada para não bloquear requests HTTP."""
        global _health_refresh_running
        with _meta_lock:
            if _health_refresh_running:
                return
            _health_refresh_running = True

        def _run() -> None:
            global _health_refresh_running
            try:
                self.health_check(force=True)
            except Exception as exc:
                log_info(logger, TAG_DISCORD, "Health check em background falhou: %s", exc)
            finally:
                with _meta_lock:
                    _health_refresh_running = False

        threading.Thread(target=_run, daemon=True, name="discord-health").start()

    def health_check(self, *, force: bool = False) -> dict:
        self._require_config()
        global _health_cache, _health_cache_at
        now = time.monotonic()
        if (
            not force
            and _health_cache is not None
            and now - _health_cache_at < HEALTH_CACHE_SECONDS
        ):
            cached = dict(_health_cache)
            cached["cached"] = True
            return cached

        log_info(logger, TAG_DISCORD, "Health check iniciado bots=%s canal=%s", self.bot_count, self.channel_id)
        bots: list[dict] = []
        channel_name: str | None = None

        for bot_idx in range(self.bot_count):
            entry: dict = {"index": bot_idx, "ok": False, "in_cooldown": _is_bot_in_cooldown(bot_idx)}
            try:
                with self._client(bot_idx) as client:
                    response = self._request(client, bot_idx, "GET", "/users/@me")
                    self._raise_for_status(response, f"Token do bot #{bot_idx + 1} inválido")
                    bot = response.json()
                    entry["username"] = bot.get("username")
                    entry["bot_id"] = bot.get("id")

                    channel_resp = self._request(
                        client, bot_idx, "GET", f"/channels/{self.channel_id}"
                    )
                    self._raise_for_status(
                        channel_resp, f"Canal inacessível para bot #{bot_idx + 1}"
                    )
                    if channel_name is None:
                        channel_name = channel_resp.json().get("name")
                    entry["ok"] = True
            except HTTPException as exc:
                entry["error"] = exc.detail
            bots.append(entry)

        ok_count = sum(1 for b in bots if b.get("ok"))
        first_ok = next((b for b in bots if b.get("ok")), None)

        log_info(
            logger,
            TAG_DISCORD,
            "Health check concluído bots_ok=%s/%s canal=%s",
            ok_count,
            self.bot_count,
            channel_name or self.channel_id,
        )
        result = {
            "ok": ok_count > 0,
            "bot_count": self.bot_count,
            "bots_ok": ok_count,
            "bots": bots,
            "bot_username": first_ok.get("username") if first_ok else None,
            "bot_id": first_ok.get("bot_id") if first_ok else None,
            "channel_id": self.channel_id,
            "channel_name": channel_name,
            "cached": False,
        }
        _health_cache = result
        _health_cache_at = time.monotonic()
        return result


_discord_storage: DiscordStorageService | None = None


def get_discord_storage() -> DiscordStorageService:
    global _discord_storage
    if _discord_storage is None:
        _discord_storage = DiscordStorageService()
    return _discord_storage
