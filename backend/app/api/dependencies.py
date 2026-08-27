from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session

SessionDependency = Annotated[Session, Depends(get_session)]


def require_internal_api_key(
    provided: Annotated[str | None, Header(alias="X-Chaska-Internal-Key")] = None,
) -> None:
    expected = get_settings().internal_api_key
    if expected and provided != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API credentials")


PrivateAPIDependency = Annotated[None, Depends(require_internal_api_key)]
