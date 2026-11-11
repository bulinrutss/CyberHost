"""Consulta mapeamentos de portas no Proxy Manager (port forwarding)."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import re
import ssl
from contextlib import contextmanager
from dataclasses import dataclass
from time import monotonic
from typing import Iterator

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300.0
_cache_at: float = 0.0
_cache_proxies: list[dict] | None = None
_mappings_by_ip_cache: dict[str, list[PortMapping]] | None = None

COMMON_PORT_LABELS: dict[int, str] = {
    3389: "RDP (Área de trabalho remota)",
    80: "HTTP",
    443: "HTTPS",
    3306: "MySQL",
    25565: "Minecraft",
    30120: "FiveM",
    40120: "txAdmin / FiveM",
    3000: "Aplicação web",
    8080: "HTTP alternativo",
    7788: "MTA:SA",
    7777: "SA-MP",
}


EMPTY_MACHINE_NAME = "máquina vazia"

_pages_cache_at: float = 0.0
_pages_cache: list["ProxyMachineSlot"] | None = None


@dataclass(frozen=True)
class ProxyMachineSlot:
    page: int
    name: str
    internal_ip: str
    online: bool | None = None


@dataclass(frozen=True)
class PortMapping:
    public_host: str
    public_port: int
    internal_host: str
    internal_port: int
    label: str

    @property
    def connection_address(self) -> str:
        return f"{self.public_host}:{self.public_port}"


def resolved_vps_public_ip(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if settings.vps_public_ip.strip():
        return settings.vps_public_ip.strip()
    return settings.game_host_public_ip.strip()


def _parse_pass(value: str) -> tuple[str, int] | None:
    raw = (value or "").strip()
    if not raw or ":" not in raw:
        return None
    host, _, port_str = raw.rpartition(":")
    host = host.strip()
    try:
        port = int(port_str.strip())
    except ValueError:
        return None
    if not host or port < 1 or port > 65535:
        return None
    return host, port


def _label_for_port(internal_port: int) -> str:
    return COMMON_PORT_LABELS.get(internal_port, f"Porta interna {internal_port}")


def _normalize_machine_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def is_empty_machine_name(name: str) -> bool:
    return _normalize_machine_name(name) == EMPTY_MACHINE_NAME


def _rdp_ip_from_proxies(proxies: list[dict]) -> str | None:
    for item in proxies:
        parsed = _parse_pass(str(item.get("pass") or ""))
        if parsed and parsed[1] == 3389:
            return parsed[0]
    for item in proxies:
        parsed = _parse_pass(str(item.get("pass") or ""))
        if parsed:
            return parsed[0]
    return None


def _invalidate_proxy_caches() -> None:
    global _cache_at, _cache_proxies, _pages_cache_at, _pages_cache, _mappings_by_ip_cache
    _cache_at = 0.0
    _cache_proxies = None
    _pages_cache_at = 0.0
    _pages_cache = None
    _mappings_by_ip_cache = None


def _proxy_api_base(settings: Settings) -> str:
    return settings.port_proxy_api_url.strip().rstrip("/")


def normalize_port_proxy_pin(value: str | None) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", value or "").lower()


def _assert_proxy_pin(ssock: ssl.SSLSocket, pin_sha256: str) -> None:
    der = ssock.getpeercert(binary_form=True)
    if not der:
        raise ssl.SSLError("Proxy Manager não apresentou certificado TLS")
    digest = hashlib.sha256(der).hexdigest()
    if not hmac.compare_digest(digest, pin_sha256):
        raise ssl.SSLError("Pin TLS do Proxy Manager não confere")


def build_port_proxy_ssl_context(settings: Settings) -> ssl.SSLContext:
    if settings.port_proxy_tls_insecure:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    pin = normalize_port_proxy_pin(settings.port_proxy_tls_pin_sha256)
    ca_file = settings.port_proxy_tls_ca_file.strip()
    if not pin and not ca_file:
        raise ssl.SSLError(
            "TLS do Proxy Manager exige PORT_PROXY_TLS_PIN_SHA256 ou PORT_PROXY_TLS_CA_FILE"
        )

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if ca_file:
        context.load_verify_locations(cafile=ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        host = httpx.URL(_proxy_api_base(settings)).host or ""
        try:
            ipaddress.ip_address(host)
            context.check_hostname = False
        except ValueError:
            context.check_hostname = True
    else:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if pin:
        original_wrap = context.wrap_socket

        def wrap_socket(sock, *args, **kwargs):
            ssock = original_wrap(sock, *args, **kwargs)
            _assert_proxy_pin(ssock, pin)
            return ssock

        context.wrap_socket = wrap_socket  # type: ignore[method-assign]
    return context


def _proxy_auth_headers(settings: Settings) -> dict[str, str]:
    token = settings.port_proxy_api_token.strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def _proxy_http_client(settings: Settings, timeout: float) -> Iterator[httpx.Client]:
    base = _proxy_api_base(settings)
    verify: ssl.SSLContext | bool = True
    if base.lower().startswith("https://"):
        verify = build_port_proxy_ssl_context(settings)
    with httpx.Client(
        timeout=timeout,
        headers=_proxy_auth_headers(settings),
        verify=verify,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        yield client


def parse_page_names(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("get-page-names: JSON deve ser objeto")
    names: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("get-page-names: chaves e valores devem ser texto")
        names[key] = value
    return names


def parse_machine_statuses(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("check-machines-status: JSON deve ser objeto")
    statuses: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise ValueError("check-machines-status: chaves devem ser texto")
        statuses[key] = value
    return statuses


def parse_proxies_payload(payload: object) -> tuple[list[dict], int]:
    if not isinstance(payload, dict):
        raise ValueError("get-proxies: JSON deve ser objeto")
    raw_proxies = payload.get("proxies") or []
    if not isinstance(raw_proxies, list):
        raise ValueError("get-proxies: proxies deve ser lista")
    proxies: list[dict] = []
    for item in raw_proxies:
        if not isinstance(item, dict):
            raise ValueError("get-proxies: item inválido")
        if "pass" not in item or "listenPort" not in item:
            continue
        proxies.append(item)
    try:
        total_pages = int(payload.get("total_pages") or 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("get-proxies: total_pages inválido") from exc
    if total_pages < 1:
        raise ValueError("get-proxies: total_pages inválido")
    return proxies, total_pages


def _fetch_page_catalog(settings: Settings) -> list[ProxyMachineSlot]:
    global _pages_cache_at, _pages_cache, _cache_at, _cache_proxies, _mappings_by_ip_cache

    now = monotonic()
    if (
        _pages_cache is not None
        and _cache_proxies is not None
        and _mappings_by_ip_cache is not None
        and now - _pages_cache_at < _CACHE_TTL_SECONDS
    ):
        return _pages_cache

    base = _proxy_api_base(settings)
    if not base:
        return []

    slots: list[ProxyMachineSlot] = []
    proxies: list[dict] = []
    mappings_by_ip: dict[str, list[PortMapping]] = {}
    public_host = resolved_vps_public_ip(settings)

    try:
        with _proxy_http_client(settings, 15.0) as client:
            names_resp = client.get(f"{base}/get-page-names")
            names_resp.raise_for_status()
            names = parse_page_names(names_resp.json())

            statuses: dict[str, object] = {}
            try:
                status_resp = client.get(f"{base}/check-machines-status")
                if status_resp.status_code == 200:
                    statuses = parse_machine_statuses(status_resp.json())
            except Exception:
                logger.debug("check-machines-status indisponível", exc_info=True)

            page = 1
            while True:
                response = client.get(
                    f"{base}/get-proxies",
                    params={"page": page, "per_page": 1000},
                )
                response.raise_for_status()
                page_proxies, total_pages = parse_proxies_payload(response.json())
                proxies.extend(page_proxies)
                internal_ip = _rdp_ip_from_proxies(page_proxies)
                if internal_ip:
                    raw_online = statuses.get(str(page))
                    online: bool | None
                    if isinstance(raw_online, bool):
                        online = raw_online
                    elif isinstance(raw_online, str):
                        online = raw_online.strip().lower() in {"1", "true", "yes", "online"}
                    else:
                        online = None
                    slots.append(
                        ProxyMachineSlot(
                            page=page,
                            name=str(names.get(str(page), "")),
                            internal_ip=internal_ip,
                            online=online,
                        )
                    )
                    if public_host:
                        page_mappings: list[PortMapping] = []
                        for item in page_proxies:
                            parsed = _parse_pass(str(item.get("pass") or ""))
                            if not parsed or parsed[0] != internal_ip:
                                continue
                            target_host, target_port = parsed
                            try:
                                public_port = int(str(item.get("listenPort") or "").strip())
                            except ValueError:
                                continue
                            page_mappings.append(
                                PortMapping(
                                    public_host=public_host,
                                    public_port=public_port,
                                    internal_host=target_host,
                                    internal_port=target_port,
                                    label=_label_for_port(target_port),
                                )
                            )
                        if page_mappings:
                            page_mappings.sort(key=lambda m: (m.internal_port, m.public_port))
                            mappings_by_ip[internal_ip] = page_mappings

                if page >= total_pages:
                    break
                page += 1

        _pages_cache_at = now
        _cache_at = now
        _pages_cache = slots
        _cache_proxies = proxies
        _mappings_by_ip_cache = mappings_by_ip
    except Exception as exc:
        logger.warning("Falha ao consultar páginas do Proxy Manager (%s): %s", base, exc)
        if _pages_cache is not None:
            return _pages_cache
        return []

    return slots


def list_empty_machine_slots(
    settings: Settings | None = None,
    *,
    used_ips: set[str] | None = None,
) -> list[ProxyMachineSlot]:
    settings = settings or get_settings()
    used = used_ips or set()
    slots = [
        slot
        for slot in _fetch_page_catalog(settings)
        if is_empty_machine_name(slot.name) and slot.internal_ip not in used
    ]
    slots.sort(key=_slot_sort_key)
    return slots


def _slot_sort_key(slot: ProxyMachineSlot) -> tuple[int, int]:
    """Ordem crescente: IP interno mais baixo primeiro, depois número da página."""
    try:
        ip_rank = int(ipaddress.IPv4Address(slot.internal_ip))
    except ipaddress.AddressValueError:
        ip_rank = 2**32
    return ip_rank, slot.page


def allocate_empty_machine_slot(
    settings: Settings,
    used_ips: set[str],
) -> ProxyMachineSlot:
    candidates = list_empty_machine_slots(settings, used_ips=used_ips)
    if not candidates:
        raise RuntimeError(
            "Nenhuma Máquina Vazia disponível no Proxy Manager. "
            "Libere um slot ou remova VPS que usem esses IPs."
        )
    candidates.sort(key=_slot_sort_key)
    return candidates[0]


def rename_proxy_page(
    page: int,
    name: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    base = _proxy_api_base(settings)
    if not base:
        raise ValueError("PORT_PROXY_API_URL não configurado")
    label = (name or "").strip()
    if not label:
        raise ValueError("Nome da máquina no Proxy Manager não pode ser vazio")

    with _proxy_http_client(settings, 10.0) as client:
        response = client.post(
            f"{base}/save-page-name",
            json={"page": page, "name": label},
        )
        response.raise_for_status()

    _invalidate_proxy_caches()
    logger.info("Proxy Manager: página %s renomeada para %s", page, label)


def find_proxy_page_for_ip(
    internal_ip: str | None,
    *,
    settings: Settings | None = None,
) -> int | None:
    ip = (internal_ip or "").strip()
    if not ip:
        return None
    settings = settings or get_settings()
    for slot in _fetch_page_catalog(settings):
        if slot.internal_ip == ip:
            return slot.page
    return None


def _fetch_all_proxies(settings: Settings) -> list[dict]:
    _fetch_page_catalog(settings)
    return _cache_proxies or []


def internal_ips_with_ports(settings: Settings | None = None) -> dict[str, set[int]]:
    """Mapa IP interno → portas configuradas no Proxy Manager."""
    settings = settings or get_settings()
    by_ip: dict[str, set[int]] = {}
    for item in _fetch_all_proxies(settings):
        parsed = _parse_pass(str(item.get("pass") or ""))
        if not parsed:
            continue
        host, port = parsed
        by_ip.setdefault(host, set()).add(port)
    return by_ip


def list_proxy_pool_ips(
    settings: Settings,
    *,
    require_rdp: bool = True,
) -> list[str]:
    """IPs do pool local que possuem portas liberadas no Proxy Manager."""
    by_ip = internal_ips_with_ports(settings)
    candidates: list[str] = []
    for ip in sorted(by_ip.keys(), key=lambda value: ipaddress.IPv4Address(value)):
        try:
            ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            continue
        start = ipaddress.IPv4Address(settings.ip_pool_start)
        end = ipaddress.IPv4Address(settings.ip_pool_end)
        target = ipaddress.IPv4Address(ip)
        if not (int(start) <= int(target) <= int(end)):
            continue
        ports = by_ip[ip]
        if require_rdp and 3389 not in ports:
            continue
        if not ports:
            continue
        candidates.append(ip)
    return candidates


def get_port_mappings_for_ip(
    internal_ip: str | None,
    *,
    settings: Settings | None = None,
) -> list[PortMapping]:
    settings = settings or get_settings()
    ip = (internal_ip or "").strip()
    if not ip or not resolved_vps_public_ip(settings):
        return []

    _fetch_page_catalog(settings)
    if _mappings_by_ip_cache is not None and ip in _mappings_by_ip_cache:
        return list(_mappings_by_ip_cache[ip])

    mappings: list[PortMapping] = []
    public_host = resolved_vps_public_ip(settings)
    for item in _fetch_all_proxies(settings):
        parsed = _parse_pass(str(item.get("pass") or ""))
        if not parsed:
            continue
        target_host, target_port = parsed
        if target_host != ip:
            continue
        try:
            public_port = int(str(item.get("listenPort") or "").strip())
        except ValueError:
            continue
        mappings.append(
            PortMapping(
                public_host=public_host,
                public_port=public_port,
                internal_host=target_host,
                internal_port=target_port,
                label=_label_for_port(target_port),
            )
        )

    mappings.sort(key=lambda m: (m.internal_port, m.public_port))
    return mappings


def get_rdp_mapping(
    internal_ip: str | None,
    *,
    settings: Settings | None = None,
) -> PortMapping | None:
    for mapping in get_port_mappings_for_ip(internal_ip, settings=settings):
        if mapping.internal_port == 3389:
            return mapping
    return None


def port_mapping_to_dict(mapping: PortMapping) -> dict:
    return {
        "public_host": mapping.public_host,
        "public_port": mapping.public_port,
        "internal_host": mapping.internal_host,
        "internal_port": mapping.internal_port,
        "connection_address": mapping.connection_address,
        "label": mapping.label,
    }
