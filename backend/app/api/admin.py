"""Painel administrativo — usuários e VPS de todos os clientes."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_admin, hash_password
from app.database import get_db
from app.models.user import User
from app.models.vps import VpsInstance
from app.schemas.auth import AdminUserCreate, AdminUserUpdate, UserResponse
from app.schemas.cloud_file import CloudFileResponse
from app.schemas.coupon import CouponCreate, CouponResponse, CouponUpdate
from app.models.coupon import DiscountCoupon
from app.services.coupons import normalize_coupon_code
from app.schemas.vps import (
    ChangeIpRequest,
    ChangePasswordRequest,
    OrderResponse,
    VpsActionResponse,
    VpsInstanceAdminDetailResponse,
    VpsInstanceAdminResponse,
    WindowsCredentials,
)
from app.schemas.admin_management import (
    AdminAccountDeleteRequest,
    AdminAccountDeleteResponse,
    AdminAccountDeletionPreview,
    AdminCloudBillingUpdateRequest,
    AdminCloudQuotaAdjustRequest,
    AdminCloudQuotaAdjustResponse,
    AdminCreateVpsRequest,
    AdminUserDetailResponse,
    AdminVpsBillingUpdateRequest,
    AdminVpsUpdateRequest,
    AdminVpsUpdateResponse,
)
from app.schemas.admin_stats import AdminStatsResponse
from app.schemas.analytics import AdminAnalyticsResponse
from app.services import admin_stats as admin_stats_svc
from app.services import analytics as analytics_svc
from app.api import admin_import
from app.api import admin_pixdev
from app.api import admin_support
from app.api import admin_host
from app.api import admin_nginx_proxy
from app.api import admin_web_sites
from app.services import admin_mfa
from app.services import admin_management as admin_mgmt
from app.services.auth_step_up import require_step_up
from app.services import bandwidth_limiter
from app.services import cloud_files as cloud_files_svc
from app.services import vps_actions

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(admin_import.router, prefix="/import", tags=["admin-import"])
router.include_router(admin_pixdev.router, tags=["admin-pixdev"])
router.include_router(admin_host.router, prefix="/host", tags=["admin-host"])
router.include_router(admin_support.router, prefix="/support", tags=["admin-support"])
router.include_router(admin_web_sites.router, tags=["admin-web-sites"])
router.include_router(admin_nginx_proxy.router, tags=["admin-nginx-proxy"])


@router.get("/coupons", response_model=list[CouponResponse])
def list_coupons(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return (
        db.query(DiscountCoupon)
        .order_by(DiscountCoupon.created_at.desc())
        .all()
    )


@router.post("/coupons", response_model=CouponResponse, status_code=status.HTTP_201_CREATED)
def create_coupon(
    payload: CouponCreate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    code = normalize_coupon_code(payload.code)
    if db.query(DiscountCoupon).filter(DiscountCoupon.code == code).first():
        raise HTTPException(status_code=400, detail="Código de cupom já existe")

    coupon = DiscountCoupon(
        code=code,
        description=payload.description,
        discount_percent=payload.discount_percent,
        discount_cents=payload.discount_cents,
        max_uses=payload.max_uses,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        is_active=payload.is_active,
    )
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return coupon


@router.patch("/coupons/{coupon_id}", response_model=CouponResponse)
def update_coupon(
    coupon_id: int,
    payload: CouponUpdate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    coupon = db.get(DiscountCoupon, coupon_id)
    if not coupon:
        raise HTTPException(status_code=404, detail="Cupom não encontrado")

    data = payload.model_dump(exclude_unset=True)
    if "discount_percent" in data or "discount_cents" in data:
        percent = data.get("discount_percent", coupon.discount_percent)
        cents = data.get("discount_cents", coupon.discount_cents)
        if bool(percent) == bool(cents):
            raise HTTPException(
                status_code=400,
                detail="Informe desconto em percentual OU valor fixo, não ambos",
            )

    for key, value in data.items():
        setattr(coupon, key, value)

    db.commit()
    db.refresh(coupon)
    return coupon


@router.delete("/coupons/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coupon(
    coupon_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    coupon = db.get(DiscountCoupon, coupon_id)
    if not coupon:
        raise HTTPException(status_code=404, detail="Cupom não encontrado")
    coupon.is_active = False
    db.commit()


@router.get("/stats", response_model=AdminStatsResponse)
def admin_stats(
    days: int = Query(default=30, ge=7, le=90),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    window = days if days in admin_stats_svc.ALLOWED_DAYS else 30
    return admin_stats_svc.collect_admin_stats(db, window)


@router.get("/analytics", response_model=AdminAnalyticsResponse)
def admin_analytics(
    days: int = Query(default=30, ge=7, le=90),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    window = days if days in analytics_svc.ALLOWED_DAYS else 30
    return analytics_svc.collect_analytics(db, window)


@router.delete("/orders/{kind}/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_order(
    kind: str,
    order_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    admin_mgmt.delete_admin_order(db, kind, order_id)


@router.get("/users", response_model=list[UserResponse])
def list_users(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_mgmt.create_panel_user(
        db,
        phone=payload.phone,
        email=str(payload.email),
        name=payload.name,
        password=payload.password,
        is_admin=payload.is_admin,
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Você não pode desativar sua própria conta")
    if user.id == admin.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail="Você não pode remover seu próprio acesso admin")

    if payload.name is not None:
        user.name = payload.name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
        if payload.is_admin is False:
            admin_mfa.clear_mfa(user)
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
    if payload.reset_mfa:
        admin_mfa.clear_mfa(user)

    db.commit()
    db.refresh(user)
    return user


@router.post("/vps", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def admin_create_vps(
    payload: AdminCreateVpsRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    order = admin_mgmt.create_courtesy_vps_order(
        db,
        user_id=payload.user_id,
        hostname=payload.hostname,
        os_template=payload.os_template,
        plan_id=payload.plan_id,
        preset_id=payload.preset_id,
        vcpu=payload.vcpu,
        ram_mb=payload.ram_mb,
        disk_gb=payload.disk_gb,
    )
    db.commit()
    db.refresh(order)
    from app.api.orders import _enqueue_order_fulfillment

    _enqueue_order_fulfillment(background_tasks, order)
    return order


@router.get("/instances", response_model=list[VpsInstanceAdminResponse])
def list_all_instances(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(VpsInstance, User)
        .join(User, VpsInstance.user_id == User.id)
        .order_by(VpsInstance.created_at.desc())
        .all()
    )
    return [
        VpsInstanceAdminResponse(
            id=inst.id,
            vm_name=inst.vm_name,
            vcpu=inst.vcpu,
            ram_mb=inst.ram_mb,
            ip_address=inst.ip_address,
            status=inst.status,
            esxi_host=inst.esxi_host,
            error_message=inst.error_message,
            created_at=inst.created_at,
            user_id=user.id,
            user_phone=user.phone,
            user_name=user.name,
        )
        for inst, user in rows
    ]


@router.get("/instances/{instance_id}", response_model=VpsInstanceAdminDetailResponse)
def get_admin_instance(
    instance_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    owner = db.get(User, instance.user_id)
    detail = vps_actions.build_instance_detail(instance, db=db, include_secrets=False)
    return {
        **detail,
        "user_id": owner.id if owner else instance.user_id,
        "user_phone": owner.phone if owner else "",
        "user_name": owner.name if owner else "",
        "custom_monthly_cents": instance.custom_monthly_cents,
    }


@router.get(
    "/instances/{instance_id}/credentials",
    response_model=WindowsCredentials,
)
def admin_get_instance_credentials(
    instance_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    creds = vps_actions.get_windows_credentials(instance, include_secrets=True)
    if not creds or not creds.get("password"):
        raise HTTPException(status_code=404, detail="Credenciais não disponíveis")
    return creds


def _action_response(instance: VpsInstance, message: str) -> VpsActionResponse:
    return VpsActionResponse(success=True, message=message, instance=instance)


@router.post("/instances/{instance_id}/power-on", response_model=VpsActionResponse)
def admin_power_on(
    instance_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    message = vps_actions.power_on_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.post("/instances/{instance_id}/power-off", response_model=VpsActionResponse)
def admin_power_off(
    instance_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    message = vps_actions.power_off_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.post("/instances/{instance_id}/reset", response_model=VpsActionResponse)
def admin_reset(
    instance_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    message = vps_actions.reset_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.post("/instances/{instance_id}/change-ip", response_model=VpsActionResponse)
def admin_change_ip(
    instance_id: int,
    payload: ChangeIpRequest,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    message = vps_actions.change_instance_ip(db, instance, payload.ip_address)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.post("/instances/{instance_id}/change-password", response_model=VpsActionResponse)
def admin_change_password(
    instance_id: int,
    payload: ChangePasswordRequest,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    message = vps_actions.change_instance_password(
        instance, payload.username, payload.new_password
    )
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.delete("/instances/{instance_id}/error", status_code=status.HTTP_204_NO_CONTENT)
def admin_clear_instance_error(
    instance_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    admin_mgmt.clear_machine_error_event(db, instance_id)


@router.delete("/instances/{instance_id}", response_model=VpsActionResponse)
def admin_destroy(
    instance_id: int,
    _: User = Depends(get_current_admin),
    __: User = Depends(require_step_up),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    message = vps_actions.destroy_instance(instance)
    db.commit()
    db.refresh(instance)
    return _action_response(instance, message)


@router.get("/users/{user_id}/detail", response_model=AdminUserDetailResponse)
def get_user_detail(
    user_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_mgmt.get_user_detail(db, user_id)


@router.get("/users/{user_id}/deletion-preview", response_model=AdminAccountDeletionPreview)
def admin_user_deletion_preview(
    user_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_mgmt.collect_deletion_preview(db, user_id)


@router.delete("/users/{user_id}", response_model=AdminAccountDeleteResponse)
def admin_delete_user(
    user_id: int,
    payload: AdminAccountDeleteRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_mgmt.delete_user_account(db, admin, user_id, payload.confirm_phone)


@router.get("/users/{user_id}/files", response_model=list[CloudFileResponse])
def admin_list_user_files(
    user_id: int,
    parent_id: int | None = None,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    logger.info(
        "Admin %s listou CyberCloud user_id=%s parent_id=%s",
        admin.id,
        user_id,
        parent_id,
    )
    return cloud_files_svc.list_files(db, user, parent_id)


@router.get("/users/{user_id}/files/{file_id}/download")
def admin_download_user_file(
    user_id: int,
    file_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    logger.info(
        "Admin %s baixou CyberCloud user_id=%s file_id=%s",
        admin.id,
        user_id,
        file_id,
    )
    result = cloud_files_svc.get_download(db, user, file_id)
    media_type = result.record.mime_type or "application/octet-stream"
    filename = admin_mgmt._safe_attachment_name(result.record.name)
    if bandwidth_limiter.enabled():
        return StreamingResponse(
            bandwidth_limiter.iter_file(result.path),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    return FileResponse(
        result.path,
        media_type=media_type,
        filename=filename,
    )


@router.post("/users/{user_id}/cloud-quota", response_model=AdminCloudQuotaAdjustResponse)
def adjust_user_cloud_quota(
    user_id: int,
    payload: AdminCloudQuotaAdjustRequest,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return admin_mgmt.adjust_cloud_quota(
        db, user, payload.extra_gb, payload.charge_mode, note=payload.note
    )


@router.patch("/instances/{instance_id}/resources", response_model=AdminVpsUpdateResponse)
def admin_update_vps_resources(
    instance_id: int,
    payload: AdminVpsUpdateRequest,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    return admin_mgmt.update_vps_admin(
        db,
        instance,
        target_vcpu=payload.target_vcpu,
        target_ram_mb=payload.target_ram_mb,
        target_disk_gb=payload.target_disk_gb,
        charge_mode=payload.charge_mode,
        apply_vmware=payload.apply_vmware,
        paid_until=payload.paid_until,
        clear_suspension=payload.clear_suspension,
    )


@router.patch("/instances/{instance_id}/billing")
def admin_update_vps_billing(
    instance_id: int,
    payload: AdminVpsBillingUpdateRequest,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    instance = vps_actions.resolve_instance(db, instance_id, admin=True)
    return admin_mgmt.update_vps_billing(
        db,
        instance,
        paid_until=payload.paid_until,
        clear_suspension=payload.clear_suspension,
        clear_pending_charge=payload.clear_pending_charge,
        custom_monthly_cents=payload.custom_monthly_cents,
        _clear_custom_monthly=payload.clear_custom_monthly_cents,
    )


@router.patch("/users/{user_id}/cloud-billing")
def admin_update_cloud_billing(
    user_id: int,
    payload: AdminCloudBillingUpdateRequest,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return admin_mgmt.update_cloud_billing(
        db,
        user,
        paid_until=payload.paid_until,
        cloud_contracted_gb=payload.cloud_contracted_gb,
        cloud_monthly_cents=payload.cloud_monthly_cents,
        clear_suspension=payload.clear_suspension,
        clear_pending_charge=payload.clear_pending_charge,
    )
