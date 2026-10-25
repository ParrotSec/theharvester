import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

API_KEY_ENV_VAR = 'THEHARVESTER_API_KEY'


def get_api_key(x_api_key: Annotated[str | None, Header(alias='X-API-Key')] = None) -> str:
    """Validate the API key used by protected API routes."""
    configured_api_key = os.getenv(API_KEY_ENV_VAR)
    if not configured_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'{API_KEY_ENV_VAR} is not configured',
        )

    if x_api_key is None or not secrets.compare_digest(x_api_key, configured_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid API key',
        )

    return x_api_key
