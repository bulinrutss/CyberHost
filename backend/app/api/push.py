from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.host_push import HostPushMeta, HostPushSubscribe
from app.services import host_push

router = APIRouter()


@router.get("/public-key", response_model=HostPushMeta)
def push_meta(_: User = Depends(get_current_user)):
    key = host_push.push_public_key()
    return HostPushMeta(vapid_public_key=key, push_available=bool(key))


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def subscribe_push(
    payload: HostPushSubscribe,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    host_push.save_subscription(
        db, user.id, payload.endpoint, payload.keys.p256dh, payload.keys.auth
    )


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe_push(
    payload: HostPushSubscribe,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    host_push.delete_subscription(db, user.id, payload.endpoint)
