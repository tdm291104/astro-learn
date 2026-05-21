"""Domain exception hierarchy and FastAPI exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_logger = logging.getLogger(__name__)


class AstroLearnError(Exception):
    """Root of the application exception hierarchy."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}


class NotFoundError(AstroLearnError):
    """Resource does not exist."""
    status_code = 404
    code = "not_found"


class ValidationError(AstroLearnError):
    """Request payload failed domain validation beyond Pydantic schema."""
    status_code = 422
    code = "validation_error"


class ConflictError(AstroLearnError):
    """Operation conflicts with current resource state."""
    status_code = 409
    code = "conflict"


class AuthenticationError(AstroLearnError):
    """Caller is not authenticated."""
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(AstroLearnError):
    """Caller is authenticated but not allowed."""
    status_code = 403
    code = "forbidden"


class AgentError(AstroLearnError):
    """Generic agent failure."""
    status_code = 500
    code = "agent_error"


class AgentNotFoundError(AgentError):
    """Requested agent name is not registered in AgentRegistry."""
    status_code = 404
    code = "agent_not_found"


class WorkflowError(AstroLearnError):
    """Workflow engine failure (step error, invalid transition, etc.)."""
    status_code = 500
    code = "workflow_error"


class ToolError(AstroLearnError):
    """Generic tool failure."""
    status_code = 502
    code = "tool_error"


class ExternalServiceError(AstroLearnError):
    """Upstream third-party service failed (NASA, Simbad, etc.)."""
    status_code = 502
    code = "external_service_error"


class LLMError(AstroLearnError):
    """LiteLLM call failed (timeout, rate limit, provider error)."""
    status_code = 503
    code = "llm_error"


async def astrolearn_exception_handler(
    request: Request,
    exc: AstroLearnError,
) -> JSONResponse:
    """Convert any AstroLearnError into a JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Normalize FastAPI's 422 validation errors into the standard envelope."""
    # jsonable_encoder handles non-JSON values (bytes, exceptions) in input.
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
            }
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all; never echoes original message (may contain internal details)."""
    _logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred",
                "details": {},
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register the domain + validation + catch-all exception handlers."""
    # Base AstroLearnError covers whole hierarchy via isinstance.
    app.add_exception_handler(AstroLearnError, astrolearn_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
