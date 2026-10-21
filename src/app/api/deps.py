from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AppError
from app.core.security import decode_token_or_raise

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if not credentials:
        raise AppError("TOKEN_INVALID", "Missing token", 401)
    payload = decode_token_or_raise(credentials.credentials, "access")
    return {"id": int(payload["sub"]), "role": payload.get("role")}


def require_roles(*roles: str):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise AppError("ACCESS_DENIED", "Insufficient rights", 403)
        return user

    return checker