import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import WaterDataPlatformException, create_http_exception

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle exceptions globally.
    Catches WaterDataPlatformException and standard Exception.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except WaterDataPlatformException as exc:
            # Handle Application-specific known exceptions
            http_exc = create_http_exception(exc)
            return JSONResponse(
                status_code=http_exc.status_code,
                content={"detail": http_exc.detail},
                headers=http_exc.headers,
            )
        except Exception as exc:
            # Handle unexpected exceptions
            logger.error(f"Unhandled exception: {exc}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error", "type": "internal_error"},
            )
