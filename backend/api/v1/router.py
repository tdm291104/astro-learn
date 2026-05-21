"""Aggregates every v1 route module under one APIRouter."""

from __future__ import annotations

from fastapi import APIRouter

from api.v1.routes import (
    admin_routes,
    agent_routes,
    astronomy_routes,
    notebook_routes,
    session_routes,
    shared_routes,
    user_routes,
)

api_v1_router = APIRouter()
api_v1_router.include_router(user_routes.router)
api_v1_router.include_router(session_routes.router)
api_v1_router.include_router(notebook_routes.router)
api_v1_router.include_router(astronomy_routes.router)
api_v1_router.include_router(agent_routes.router)
api_v1_router.include_router(shared_routes.router)
api_v1_router.include_router(admin_routes.router)
