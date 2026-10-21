from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        http_status: int,
        details: dict | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        self.details = details or {}


def error_response(
    error_code: str,
    message: str,
    http_status: int,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={
            "error_code": error_code,
            "message": message,
            "details": details or {},
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.error_code, exc.message, exc.http_status, exc.details)


async def validation_error_handler(request: Request, exc) -> JSONResponse:
    details = []
    for err in exc.errors():
        details.append(
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "issue": err["msg"],
            }
        )
    return error_response(
        "VALIDATION_ERROR",
        "Validation failed",
        400,
        {"fields": details},
    )
