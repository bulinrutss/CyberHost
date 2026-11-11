"""TLS para o ESXi: CA confiável ou pin SHA-256 do certificado."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


def normalize_esxi_pin(value: str | None) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", value or "").lower()


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def assert_peer_pin(ssock: ssl.SSLSocket, pin_sha256: str) -> None:
    der = ssock.getpeercert(binary_form=True)
    if not der:
        raise ssl.SSLError("Host não apresentou certificado TLS")
    digest = hashlib.sha256(der).hexdigest()
    if not hmac.compare_digest(digest, pin_sha256):
        raise ssl.SSLError("Pin TLS do host não confere")


def build_esxi_ssl_context(settings: Settings) -> ssl.SSLContext:
    if settings.esxi_disable_ssl_verify:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    pin = normalize_esxi_pin(settings.esxi_ssl_pin_sha256)
    ca_file = settings.esxi_ssl_ca_file.strip()
    if not pin and not ca_file:
        raise ssl.SSLError(
            "TLS do host exige ESXI_SSL_PIN_SHA256 ou ESXI_SSL_CA_FILE"
        )

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if ca_file:
        context.load_verify_locations(cafile=ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = not _is_ip_address(settings.esxi_host)
    else:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if pin:
        original_wrap = context.wrap_socket

        def wrap_socket(sock, *args, **kwargs):
            ssock = original_wrap(sock, *args, **kwargs)
            assert_peer_pin(ssock, pin)
            return ssock

        context.wrap_socket = wrap_socket  # type: ignore[method-assign]
    return context


DEFAULT_ESXI_HTTPS_TIMEOUT = 15.0
DEFAULT_ESXI_HTTPS_MAX_BYTES = 64 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "redirect bloqueado",
            headers,
            fp,
        )


def assert_esxi_https_url(url: str, settings: Settings) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Transferência guest exige HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("URL de transferência guest inválida")
    host = (parsed.hostname or "").lower()
    expected_host = settings.esxi_host.strip().lower()
    if host != expected_host:
        raise ValueError("URL de transferência guest inválida")
    port = parsed.port or 443
    if port != int(settings.esxi_port):
        raise ValueError("URL de transferência guest inválida")
    return parsed


def read_esxi_https(
    url: str,
    settings: Settings,
    *,
    timeout: float = DEFAULT_ESXI_HTTPS_TIMEOUT,
    max_bytes: int = DEFAULT_ESXI_HTTPS_MAX_BYTES,
) -> bytes:
    assert_esxi_https_url(url, settings)
    context = build_esxi_ssl_context(settings)
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        _NoRedirect(),
    )
    chunks: list[bytes] = []
    total = 0
    with opener.open(request, timeout=timeout) as response:
        while True:
            chunk = response.read(8192)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Transferência guest excedeu o limite")
            chunks.append(chunk)
    return b"".join(chunks)
