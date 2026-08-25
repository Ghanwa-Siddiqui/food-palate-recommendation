from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import deals, dishes, restaurants
from app.core.config import get_settings
from app.services.data_core.catalog import (
    EmbeddingUnavailableError,
    InvalidRequestError,
    NotFoundError,
)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="1.0.0")

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": str(error)}},
        )

    @application.exception_handler(InvalidRequestError)
    async def invalid_request_handler(
        _request: Request, error: InvalidRequestError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": str(error)}},
        )

    @application.exception_handler(EmbeddingUnavailableError)
    async def embedding_unavailable_handler(
        _request: Request, error: EmbeddingUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "embedding_unavailable",
                    "message": str(error),
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": error.errors(),
                }
            },
        )

    application.include_router(restaurants.router)
    application.include_router(dishes.router)
    application.include_router(deals.router)
    return application


app = create_app()
