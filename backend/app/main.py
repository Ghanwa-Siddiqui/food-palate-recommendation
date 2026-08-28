import secrets

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import (
    deals,
    dishes,
    partner_dishes,
    partner_restaurants,
    ranking,
    restaurants,
    reviews,
    users,
)
from app.core.config import get_settings, validate_production_settings
from app.services.data_core.catalog import (
    EmbeddingUnavailableError,
    InvalidRequestError,
    NotFoundError,
)


def create_app() -> FastAPI:
    settings = get_settings()
    validate_production_settings(settings)
    application = FastAPI(title=settings.app_name, version="1.0.0")

    if settings.app_env.lower() == "production":

        @application.middleware("http")
        async def require_internal_key(request: Request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            provided = request.headers.get("X-Chaska-Internal-Key", "")
            if not secrets.compare_digest(provided, settings.internal_api_key or ""):
                return JSONResponse(
                    status_code=401,
                    content={"error": {"code": "unauthorized", "message": "Unauthorized"}},
                )
            return await call_next(request)

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(NotFoundError)
    async def not_found_handler(
        _request: Request,
        error: NotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "not_found",
                    "message": str(error),
                }
            },
        )

    @application.exception_handler(InvalidRequestError)
    async def invalid_request_handler(
        _request: Request,
        error: InvalidRequestError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": str(error),
                }
            },
        )

    @application.exception_handler(EmbeddingUnavailableError)
    async def embedding_unavailable_handler(
        _request: Request,
        error: EmbeddingUnavailableError,
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
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": jsonable_encoder(error.errors()),
                }
            },
        )

    application.include_router(restaurants.router)
    application.include_router(dishes.router)
    application.include_router(deals.router)
    application.include_router(ranking.router)
    application.include_router(users.router)
    application.include_router(reviews.router)
    application.include_router(partner_restaurants.router)
    application.include_router(partner_dishes.router)

    return application


app = create_app()
