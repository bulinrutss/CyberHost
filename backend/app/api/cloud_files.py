import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.cloud_file import CloudFile
from app.models.user import User
from app.schemas.cloud_file import (
    CloudFileResponse,
    CloudFolderCreate,
    CloudFilesLimitsResponse,
    CloudMoveRequest,
    CloudQuotaResponse,
    CloudStoragePackageResponse,
    CloudStorageOrderResponse,
    CloudStoragePurchaseRequest,
    CloudStoragePurchaseResponse,
    CloudStorageQuoteResponse,
    CloudStorageRenewQuoteRequest,
    CloudStorageRenewQuoteResponse,
    CloudStorageRenewResponse,
    CloudStorageSyncPendingResponse,
    CloudStorageSyncResponse,
    CloudStorageStatusResponse,
    CloudUploadProgressResponse,
    CloudUploadStart,
    CloudUploadStartResponse,
)
from app.services import cloud_files as svc
from app.services import cloud_storage as storage_svc
from app.services import bandwidth_limiter
from app.services.cloud_log import TAG_CLOUD, log_info
from app.services.cloud_quota import parse_storage_packages

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/upload/limits", response_model=CloudFilesLimitsResponse)
def get_upload_limits_v2():
    """Limites de upload (rota alternativa — evita conflito com DELETE /{file_id} em backends antigos)."""
    return {
        "max_upload_bytes": svc.max_upload_bytes(),
        "chunk_size_bytes": svc.chunk_size_bytes(),
    }


@router.get("/limits", response_model=CloudFilesLimitsResponse, include_in_schema=False)
def get_upload_limits(user: User = Depends(get_current_user)):
    """Limites de upload lidos do .env."""
    return {
        "max_upload_bytes": svc.max_upload_bytes(),
        "chunk_size_bytes": svc.chunk_size_bytes(),
    }


@router.get("/storage/status", response_model=CloudStorageStatusResponse)
def get_storage_status(user: User = Depends(get_current_user)):
    log_info(logger, TAG_CLOUD, "API storage/status user_id=%s", user.id)
    return svc.storage_status()


@router.post("/storage/sync-pending", response_model=CloudStorageSyncPendingResponse)
def sync_pending_storage_payments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    credited_orders, credited_gb = storage_svc.sync_all_pending_payments(db, user)
    quota = svc.quota_info(db, user)
    if credited_orders:
        log_info(
            logger,
            TAG_CLOUD,
            "API storage/sync-pending user_id=%s credited_orders=%s credited_gb=%s",
            user.id,
            credited_orders,
            credited_gb,
        )
    return CloudStorageSyncPendingResponse(
        credited_orders=credited_orders,
        credited_gb=credited_gb,
        quota_bytes=quota["quota_bytes"],
        extra_bytes=quota["extra_bytes"],
    )


@router.get("/quota", response_model=CloudQuotaResponse)
def get_quota(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    credited_orders, credited_gb = storage_svc.sync_all_pending_payments(db, user)
    if credited_orders:
        log_info(
            logger,
            TAG_CLOUD,
            "API quota auto-sync user_id=%s credited_orders=%s credited_gb=%s",
            user.id,
            credited_orders,
            credited_gb,
        )
    log_info(logger, TAG_CLOUD, "API quota user_id=%s", user.id)
    return svc.quota_info(db, user)


@router.get("/storage/packages", response_model=list[CloudStoragePackageResponse])
def list_storage_packages(user: User = Depends(get_current_user)):
    log_info(logger, TAG_CLOUD, "API storage/packages user_id=%s", user.id)
    return parse_storage_packages()


@router.get("/storage/packages/{package_slug}/quote", response_model=CloudStorageQuoteResponse)
def quote_storage_purchase(
    package_slug: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return storage_svc.quote_purchase(db, user, package_slug)


@router.post("/storage/purchase", response_model=CloudStoragePurchaseResponse)
def purchase_storage(
    payload: CloudStoragePurchaseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = storage_svc.create_purchase(db, user, payload.package_slug)
    log_info(
        logger,
        TAG_CLOUD,
        "API storage/purchase user_id=%s order_id=%s gb=%s",
        user.id,
        order.id,
        order.extra_gb,
    )
    return CloudStoragePurchaseResponse(
        order_id=order.id,
        checkout_url=order.payment_checkout_url,
        pix_br_code=order.pix_br_code,
        pix_qr_base64=order.pix_qr_base64,
        pix_expires_at=order.pix_expires_at,
        extra_gb=order.extra_gb,
        total_cents=order.total_cents,
        status=order.status.value,
    )


@router.post("/storage/renew/quote", response_model=CloudStorageRenewQuoteResponse)
def quote_storage_renewal(
    payload: CloudStorageRenewQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return storage_svc.quote_renewal(db, user, payload.months)


@router.post("/storage/renew", response_model=CloudStorageRenewResponse)
def renew_storage(
    payload: CloudStorageRenewQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = storage_svc.create_renewal(db, user, payload.months)
    log_info(
        logger,
        TAG_CLOUD,
        "API storage/renew user_id=%s order_id=%s months=%s",
        user.id,
        order.id,
        order.renewal_months,
    )
    return CloudStorageRenewResponse(
        order_id=order.id,
        checkout_url=order.payment_checkout_url,
        pix_br_code=order.pix_br_code,
        pix_qr_base64=order.pix_qr_base64,
        pix_expires_at=order.pix_expires_at,
        renewal_months=order.renewal_months or payload.months,
        total_cents=order.total_cents,
        status=order.status.value,
    )


@router.post("/storage/orders/{order_id}/sync-payment", response_model=CloudStorageSyncResponse)
def sync_storage_payment(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = storage_svc.sync_payment(db, user, order_id)
    quota = svc.quota_info(db, user)
    log_info(
        logger,
        TAG_CLOUD,
        "API storage/sync-payment user_id=%s order_id=%s status=%s extra_bytes=%s",
        user.id,
        order_id,
        order.status.value,
        quota["extra_bytes"],
    )
    return CloudStorageSyncResponse(
        order_id=order.id,
        status=order.status.value,
        extra_gb=order.extra_gb,
        quota_bytes=quota["quota_bytes"],
        extra_bytes=quota["extra_bytes"],
        pix_br_code=order.pix_br_code,
        pix_qr_base64=order.pix_qr_base64,
        pix_expires_at=order.pix_expires_at,
        total_cents=order.total_cents,
    )


@router.get("/storage/orders", response_model=list[CloudStorageOrderResponse])
def list_storage_orders(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return storage_svc.list_orders(db, user)


@router.delete("/storage/orders/{order_id}", status_code=204)
def delete_pending_storage_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    storage_svc.delete_pending_order(db, user, order_id)


@router.get("", response_model=list[CloudFileResponse])
def list_files(
    parent_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log_info(logger, TAG_CLOUD, "API list user_id=%s parent_id=%s", user.id, parent_id)
    return svc.list_files(db, user, parent_id)


@router.post("/folders", response_model=CloudFileResponse, status_code=201)
def create_folder(
    payload: CloudFolderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log_info(logger, TAG_CLOUD, "API create folder user_id=%s nome=%r", user.id, payload.name)
    return svc.create_folder(db, user, payload.name, payload.parent_id)


@router.post("/move", status_code=200)
def move_files(
    payload: CloudMoveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    moved = svc.move_nodes(db, user, payload.ids, payload.parent_id)
    log_info(
        logger,
        TAG_CLOUD,
        "API move user_id=%s itens=%s destino=%s movidos=%s",
        user.id,
        len(payload.ids),
        payload.parent_id,
        moved,
    )
    return {"moved": moved}


@router.post("/upload/start", response_model=CloudUploadStartResponse)
def start_upload(
    payload: CloudUploadStart,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record, resumed, renamed_from = svc.start_upload(
        db,
        user,
        payload.name,
        payload.parent_id,
        payload.size_bytes,
        payload.total_chunks,
        payload.mime_type,
        replace_existing=payload.replace_existing,
    )
    log_info(
        logger,
        TAG_CLOUD,
        "API upload/start user_id=%s file_id=%s retomado=%s nome=%r",
        user.id,
        record.id,
        resumed,
        record.name,
    )
    return CloudUploadStartResponse(
        file_id=record.id,
        name=record.name,
        chunk_size_bytes=svc.chunk_size_bytes(),
        resumed=resumed,
        renamed_from=renamed_from,
    )


@router.get("/progress/{file_id}", response_model=CloudUploadProgressResponse)
def upload_progress(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log_info(logger, TAG_CLOUD, "API progress user_id=%s file_id=%s", user.id, file_id)
    return svc.get_upload_progress(db, user, file_id)


@router.get("/upload/{file_id}/progress", response_model=CloudUploadProgressResponse, include_in_schema=False)
def upload_progress_legacy(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.get_upload_progress(db, user, file_id)


@router.post("/upload/{file_id}/sync-pending", status_code=204)
def sync_pending_chunks(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(CloudFile)
        .filter(CloudFile.id == file_id, CloudFile.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    pending = svc.list_pending_sync_chunks(db, user.id, file_id)
    log_info(
        logger,
        TAG_CLOUD,
        "API sync-pending user_id=%s file_id=%s pendentes=%s (sync inline)",
        user.id,
        file_id,
        len(pending),
    )
    if pending:
        failures = svc.sync_pending_parallel(file_id, user.id, pending)
        if failures:
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao processar {failures} parte(s) do arquivo — tente novamente",
            )


@router.post("/upload/{file_id}/chunk", status_code=204)
def upload_chunk(
    file_id: int,
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    written = svc.save_chunk_stream(db, user, file_id, chunk_index, chunk.file)[1]
    log_info(
        logger,
        TAG_CLOUD,
        "API upload/chunk user_id=%s file_id=%s chunk=%s bytes=%s",
        user.id,
        file_id,
        chunk_index + 1,
        written,
    )


@router.post("/upload/{file_id}/complete", response_model=CloudFileResponse)
def complete_upload(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log_info(logger, TAG_CLOUD, "API upload/complete user_id=%s file_id=%s", user.id, file_id)
    return svc.complete_upload(db, user, file_id)


@router.post("/cleanup-incomplete", status_code=200)
def cleanup_incomplete(
    parent_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    removed = svc.cleanup_incomplete_uploads(db, user, parent_id)
    log_info(logger, TAG_CLOUD, "API cleanup-incomplete user_id=%s removidos=%s", user.id, removed)
    return {"removed": removed}


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log_info(logger, TAG_CLOUD, "API download user_id=%s file_id=%s", user.id, file_id)
    result = svc.get_download(db, user, file_id)
    media_type = result.record.mime_type or "application/octet-stream"

    if bandwidth_limiter.enabled():
        return StreamingResponse(
            bandwidth_limiter.iter_file(result.path),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{result.record.name}"',
            },
        )

    return FileResponse(
        result.path,
        media_type=media_type,
        filename=result.record.name,
    )


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log_info(logger, TAG_CLOUD, "API delete user_id=%s file_id=%s", user.id, file_id)
    svc.delete_node(db, user, file_id)
