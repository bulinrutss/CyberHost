"""Endpoint admin para liberar pedidos a partir de Pix DevMode colado."""

from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from app.services.pixdev import MAX_TEXT, release_text

router = APIRouter()


class PixDevRequest(BaseModel):
    text: str = Field(min_length=8, max_length=MAX_TEXT)


class PixDevItem(BaseModel):
    charge_id: str
    ok: bool
    action: str
    detail: str
    kind: str | None = None
    order_id: int | None = None
    order_status: str | None = None
    simulated: bool = False


class PixDevResponse(BaseModel):
    results: list[PixDevItem]
    released: int
    skipped: int
    failed: int


@router.post("/pixdev", response_model=PixDevResponse)
def pixdev_release(
    payload: PixDevRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del admin
    results = release_text(db, payload.text, background_tasks)
    return PixDevResponse(
        results=[PixDevItem(**asdict(item)) for item in results],
        released=sum(1 for item in results if item.action == "released"),
        skipped=sum(1 for item in results if item.action == "already"),
        failed=sum(1 for item in results if item.action == "failed"),
    )
