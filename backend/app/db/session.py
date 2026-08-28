from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    # pool_pre_ping issues a SELECT 1 before every checkout. Against the
    # Supabase pooler that is a ~300ms network round trip added to every
    # request. pool_recycle retires connections on age instead, which costs
    # nothing per request and still avoids handing out a stale socket.
    options: dict[str, object] = {"pool_recycle": 900}
    if not settings.database_url.startswith("sqlite"):
        options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        if settings.database_url.startswith("postgresql+psycopg"):
            options["connect_args"] = {"prepare_threshold": None}
    return create_engine(settings.database_url, **options)


def get_session() -> Generator[Session, None, None]:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        yield session
