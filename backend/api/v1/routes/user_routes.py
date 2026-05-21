"""User routes — register, login, current profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from core.dependencies import (
    CurrentUserDep,
    TokenUsageServiceDep,
    UserServiceDep,
    UserStatsServiceDep,
)
from schemas.stats_schema import UserStatsResponse
from schemas.token_usage_schema import CostBreakdownResponse, TokenUsageSummary
from schemas.user_schema import (
    PasswordChangeRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: UserRegisterRequest,
    service: UserServiceDep,
) -> UserResponse:
    """Create a new account. Returns the public profile (no token)."""
    return await service.register(request)


@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: UserServiceDep,
) -> TokenResponse:
    """OAuth2 password flow — returns a bearer token."""
    return await service.authenticate(email=form.username, password=form.password)


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUserDep) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    request: UserUpdateRequest,
    current_user: CurrentUserDep,
    service: UserServiceDep,
) -> UserResponse:
    """Patch editable profile fields (currently just full_name)."""
    return await service.update_profile(current_user.id, request)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
    request: PasswordChangeRequest,
    current_user: CurrentUserDep,
    service: UserServiceDep,
) -> None:
    """Verify current password and replace it with a new one."""
    await service.change_password(current_user.id, request)


@router.get("/me/stats", response_model=UserStatsResponse)
async def me_stats(
    current_user: CurrentUserDep,
    service: UserStatsServiceDep,
) -> UserStatsResponse:
    """Counts powering the dashboard's stat cards in a single round-trip."""
    return await service.summary(current_user.id)


@router.get("/me/token-usage", response_model=TokenUsageSummary)
async def me_token_usage(
    current_user: CurrentUserDep,
    service: TokenUsageServiceDep,
    days: int = 30,
) -> TokenUsageSummary:
    """Monthly total + daily breakdown for the dashboard chart."""
    return await service.summary(current_user.id, days=days)


@router.get("/me/cost-breakdown", response_model=CostBreakdownResponse)
async def me_cost_breakdown(
    current_user: CurrentUserDep,
    service: TokenUsageServiceDep,
    days: int = 30,
) -> CostBreakdownResponse:
    """Per-model token usage + estimated USD cost for the caller."""
    return await service.cost_breakdown(current_user.id, days=days)
