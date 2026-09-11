"""Aggregates the v1 routers."""

from fastapi import APIRouter

from app.api.v1 import actions, cluster, database, events, inventory, resources

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(cluster.router)
api_router.include_router(inventory.router)
api_router.include_router(resources.router)
api_router.include_router(events.router)
api_router.include_router(actions.router)
api_router.include_router(database.router)
