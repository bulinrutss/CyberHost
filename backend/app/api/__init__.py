from fastapi import APIRouter

from app.api import (
    admin,
    analytics,
    auth,
    cloud_files,
    finance,
    finance_auth,
    game_orders,
    game_servers,
    orders,
    payments,
    push,
    support,
    vps,
    vmware_admin,
    web_orders,
    web_sites,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(cloud_files.router, prefix="/files", tags=["files"])
api_router.include_router(vps.router, prefix="/vps", tags=["vps"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(game_servers.router, prefix="/game-servers", tags=["game-servers"])
api_router.include_router(game_orders.router, prefix="/game-orders", tags=["game-orders"])
api_router.include_router(web_sites.router, prefix="/web-sites", tags=["web-sites"])
api_router.include_router(web_orders.router, prefix="/web-orders", tags=["web-orders"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(support.router, prefix="/support", tags=["support"])
api_router.include_router(finance_auth.router, prefix="/finance/auth", tags=["finance-auth"])
api_router.include_router(finance.router, prefix="/finance", tags=["finance"])
api_router.include_router(push.router, prefix="/push", tags=["push"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(vmware_admin.router, prefix="/vmware", tags=["vmware"])
