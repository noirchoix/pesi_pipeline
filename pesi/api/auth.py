from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from pesi.api.config import ApiSettings, get_settings


def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
    settings: ApiSettings = Depends(get_settings),
) -> dict[str, str]:
    """API key guard.

    Auth is optional by default for local desktop usage. Set PESI_API_KEY and
    PESI_AUTH_MODE=required for production or shared deployments.
    """
    expected = settings.api_key
    if not expected and settings.auth_mode != "required":
        return {"subject": "local-dev", "auth": "disabled"}

    supplied = x_api_key or ""
    if not supplied and authorization and authorization.lower().startswith("bearer "):
        supplied = authorization.split(" ", 1)[1].strip()

    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key. Provide X-API-Key or Bearer token.",
        )
    return {"subject": "api-key", "auth": "api-key"}


AuthContext = Annotated[dict[str, str], Depends(verify_api_key)]
