"""Aggregates the v1 routers."""

from fastapi import APIRouter

from app.api.v1 import cluster

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(cluster.router)
