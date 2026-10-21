import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

from app.core.security import decode_token

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(message)s")

SENSITIVE_FIELDS = {"password", "password_hash", "token", "refresh_token", "access_token"}


def _mask_sensitive(data):
    if isinstance(data, dict):
        return {
            k: ("***" if k.lower() in SENSITIVE_FIELDS else _mask_sensitive(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_sensitive(item) for item in data]
    return data


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.time()

        body = b""
        if request.method in ("POST", "PUT", "DELETE"):
            body = await request.body()

        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)

        user_id = None
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            payload = decode_token(auth.split(" ", 1)[1])
            if payload.get("sub"):
                user_id = int(payload["sub"])

        log = {
            "request_id": request_id,
            "method": request.method,
            "endpoint": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if body:
            try:
                log["request_body"] = _mask_sensitive(json.loads(body))
            except Exception:
                log["request_body"] = body.decode(errors="ignore")

        logger.info(json.dumps(log, ensure_ascii=False))
        response.headers["X-Request-Id"] = request_id
        return response
