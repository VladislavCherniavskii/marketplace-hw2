from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api import auth, orders, products, promo_codes
from app.core.exceptions import (
    AppError,
    app_error_handler,
    validation_error_handler,
)
from app.middleware.logging import RequestLoggingMiddleware

app = FastAPI(title="Marketplace API", version="1.0.0")

app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])
app.include_router(promo_codes.router, prefix="/promo-codes", tags=["Promo Codes"])
