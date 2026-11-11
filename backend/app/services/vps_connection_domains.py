"""Domínios personalizados por porta pública da VPS."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.vps import VpsInstance
from app.models.vps_connection import VpsConnectionDomain
from app.models.web_site import WebSite
from app.services.port_proxy import get_port_mappings_for_ip
from app.services.vps_connection_ssl import configure_domain, has_certificate
from app.services.vps_nginx import remove_snippet, supports_http_proxy
from app.services.web_domain import domain_in_use, normalize_domain


def list_for_instance(db: Session, instance: VpsInstance) -> list[VpsConnectionDomain]:
    return (
        db.query(VpsConnectionDomain)
        .filter(VpsConnectionDomain.vps_instance_id == instance.id)
        .order_by(VpsConnectionDomain.public_port.asc(), VpsConnectionDomain.id.asc())
        .all()
    )


def _domain_taken(
    db: Session,
    domain: str,
    *,
    ignore_id: int | None = None,
) -> bool:
    return domain_in_use(db, domain, ignore_vps_connection_id=ignore_id)


def _resolve_mapping(instance: VpsInstance, public_port: int):
    for mapping in get_port_mappings_for_ip(instance.ip_address):
        if mapping.public_port == public_port:
            return mapping
    raise HTTPException(
        status_code=400,
        detail="Porta pública inválida para esta VPS. Escolha uma porta listada em Conexões.",
    )


def upsert_connection_domain(
    db: Session,
    instance: VpsInstance,
    user: User,
    *,
    domain_raw: str,
    public_port: int,
) -> VpsConnectionDomain:
    domain = normalize_domain(domain_raw)
    if _domain_taken(db, domain):
        raise HTTPException(status_code=400, detail="Este domínio já está em uso")
    mapping = _resolve_mapping(instance, int(public_port))
    existing = (
        db.query(VpsConnectionDomain)
        .filter(
            VpsConnectionDomain.vps_instance_id == instance.id,
            VpsConnectionDomain.public_port == mapping.public_port,
        )
        .first()
    )
    if existing and existing.domain != domain:
        old_domain = existing.domain
        existing.domain = domain
        existing.internal_port = mapping.internal_port
        db.commit()
        db.refresh(existing)
        try:
            configure_domain(existing)
        except Exception as exc:
            existing.domain = old_domain
            db.commit()
            raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
        return existing

    if existing:
        return existing

    conn = VpsConnectionDomain(
        vps_instance_id=instance.id,
        user_id=user.id,
        domain=domain,
        public_port=mapping.public_port,
        internal_port=mapping.internal_port,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    try:
        configure_domain(conn)
    except Exception as exc:
        db.delete(conn)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)[:300]) from exc
    return conn


def remove_connection_domain(db: Session, instance: VpsInstance, connection_id: int) -> None:
    conn = (
        db.query(VpsConnectionDomain)
        .filter(
            VpsConnectionDomain.id == connection_id,
            VpsConnectionDomain.vps_instance_id == instance.id,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Domínio não encontrado")
    remove_snippet(conn)
    db.delete(conn)
    db.commit()
    try:
        from app.services.web_nginx import reload_nginx

        reload_nginx()
    except Exception:
        pass


def connection_to_dict(conn: VpsConnectionDomain) -> dict:
    return {
        "id": conn.id,
        "domain": conn.domain,
        "public_port": conn.public_port,
        "internal_port": conn.internal_port,
        "http_proxy": supports_http_proxy(conn.internal_port),
        "ssl_active": bool(conn.domain and has_certificate(conn)),
        "created_at": conn.created_at,
    }
