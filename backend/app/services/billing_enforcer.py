"""Desliga VPS, sites e suspende CyberCloud após o fim da carência de pagamento."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.user import User
from app.models.vps import VpsInstance, VpsStatus
from app.models.web_site import WebSite, WebSiteStatus
from app.services.billing import GRACE_DAYS
from app.services.vmware.client import esxi_session
from app.services.vmware.configure import power_off

logger = logging.getLogger(__name__)


def enforce_billing_suspensions() -> int:
    """Desliga VMs com mensalidade vencida há mais de GRACE_DAYS dias."""
    db = SessionLocal()
    suspended_count = 0
    try:
        now = datetime.utcnow()

        instances = (
            db.query(VpsInstance)
            .filter(
                VpsInstance.status.in_([VpsStatus.RUNNING, VpsStatus.STOPPED]),
                VpsInstance.paid_until.isnot(None),
                VpsInstance.suspended_for_billing.is_(False),
            )
            .all()
        )

        for instance in instances:
            grace_end = instance.paid_until + timedelta(days=GRACE_DAYS)
            if now <= grace_end:
                continue
            try:
                with esxi_session() as client:
                    vm = client.find_vm_by_name(instance.vm_name)
                    if vm:
                        power_off(client, vm)
                instance.suspended_for_billing = True
                instance.status = VpsStatus.STOPPED
                suspended_count += 1
                logger.info(
                    "VPS %s suspensa por inadimplência (venceu em %s)",
                    instance.vm_name,
                    instance.paid_until,
                )
            except Exception:
                logger.exception("Falha ao suspender VPS %s", instance.vm_name)

        cloud_users = (
            db.query(User)
            .filter(
                User.cloud_contracted_gb > 0,
                User.cloud_paid_until.isnot(None),
                User.cloud_suspended_for_billing.is_(False),
            )
            .all()
        )
        for user in cloud_users:
            grace_end = user.cloud_paid_until + timedelta(days=GRACE_DAYS)
            if now <= grace_end:
                continue
            user.cloud_suspended_for_billing = True
            suspended_count += 1
            logger.info(
                "CyberCloud user_id=%s suspenso por inadimplência (venceu em %s)",
                user.id,
                user.cloud_paid_until,
            )

        from app.services import web_process

        sites = (
            db.query(WebSite)
            .filter(
                WebSite.status != WebSiteStatus.DELETED,
                WebSite.paid_until.isnot(None),
                WebSite.suspended_for_billing.is_(False),
            )
            .all()
        )
        for site in sites:
            grace_end = site.paid_until + timedelta(days=GRACE_DAYS)
            if now <= grace_end:
                continue
            try:
                web_process.stop_site(site)
                site.suspended_for_billing = True
                site.status = WebSiteStatus.STOPPED
                suspended_count += 1
                logger.info(
                    "Site %s suspenso por inadimplência (venceu em %s)",
                    site.domain,
                    site.paid_until,
                )
            except Exception:
                logger.exception("Falha ao suspender site %s", site.domain)

        if suspended_count:
            db.commit()
    finally:
        db.close()

    return suspended_count


async def billing_enforcer_loop(interval_seconds: int = 3600) -> None:
    while True:
        try:
            count = await asyncio.to_thread(enforce_billing_suspensions)
            if count:
                logger.info("Billing enforcer: %s recurso(s) suspenso(s)", count)
            from app.services.billing_reminders import send_due_reminders

            sent = await asyncio.to_thread(send_due_reminders)
            if sent:
                logger.info("Billing reminders: %s e-mail(s) enviado(s)", sent)
        except Exception:
            logger.exception("Erro no billing enforcer")
        await asyncio.sleep(interval_seconds)
