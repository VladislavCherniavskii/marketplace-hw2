from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_roles
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.models import (
    DiscountType,
    OperationType,
    Order,
    OrderItem,
    OrderStatus as DBOrderStatus,
    Product,
    ProductStatus as DBProductStatus,
    PromoCode,
    UserOperation,
)
from app.db.session import get_db
from app.generated.models import (
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate,
    OrderUpdate,
)

router = APIRouter()

VALID_TRANSITIONS = {
    "CREATED": ["PAYMENT_PENDING"],
    "PAYMENT_PENDING": ["PAID"],
    "PAID": ["SHIPPED"],
    "SHIPPED": ["COMPLETED"],
}


async def _last_operation(db, user_id, op_type):
    return await db.scalar(
        select(UserOperation)
        .where(
            UserOperation.user_id == user_id,
            UserOperation.operation_type == op_type,
        )
        .order_by(UserOperation.created_at.desc())
        .limit(1)
    )


async def _reserve_items(db, items):
    order_items = []
    total = Decimal("0")
    for item in items:
        product = await db.get(Product, item.product_id, with_for_update=True)
        if not product:
            raise AppError("PRODUCT_NOT_FOUND", f"Product {item.product_id} not found", 404)
        if product.status != DBProductStatus.ACTIVE:
            raise AppError("PRODUCT_INACTIVE", f"Product {item.product_id} is not active", 409)
        if product.stock < item.quantity:
            raise AppError(
                "INSUFFICIENT_STOCK",
                "Not enough stock",
                409,
                {"product_id": product.id, "requested": item.quantity, "available": product.stock},
            )
        product.stock -= item.quantity
        order_items.append(
            OrderItem(
                product_id=product.id,
                quantity=item.quantity,
                price_at_order=product.price,
            )
        )
        total += product.price * item.quantity
    return order_items, total


async def _apply_promo(db, total: Decimal, promo_code: str | None):
    if not promo_code:
        return Decimal("0"), None
    promo = await db.scalar(select(PromoCode).where(PromoCode.code == promo_code))
    now = datetime.now(timezone.utc)
    if (
        not promo
        or not promo.active
        or promo.current_uses >= promo.max_uses
        or not (promo.valid_from <= now <= promo.valid_until)
    ):
        raise AppError("PROMO_CODE_INVALID", "Promo code invalid", 422)
    if total < promo.min_order_amount:
        raise AppError("PROMO_CODE_MIN_AMOUNT", "Order below minimum for promo", 422)
    if promo.discount_type == DiscountType.PERCENTAGE:
        discount = total * promo.discount_value / Decimal("100")
        if discount > total * Decimal("0.7"):
            discount = total * Decimal("0.7")
    else:
        discount = min(promo.discount_value, total)
    promo.current_uses += 1
    return discount, promo


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("USER", "ADMIN")),
):
    last = await _last_operation(db, user["id"], OperationType.CREATE_ORDER)
    if last and (datetime.now(timezone.utc) - last.created_at) < timedelta(
        minutes=settings.ORDER_CREATE_LIMIT_MINUTES
    ):
        raise AppError("ORDER_LIMIT_EXCEEDED", "Too many orders", 429)

    active = await db.scalar(
        select(Order)
        .where(
            Order.user_id == user["id"],
            Order.status.in_([DBOrderStatus.CREATED, DBOrderStatus.PAYMENT_PENDING]),
        )
        .limit(1)
    )
    if active:
        raise AppError("ORDER_HAS_ACTIVE", "You already have an active order", 409)

    order_items, total = await _reserve_items(db, data.items)
    discount, promo = await _apply_promo(db, total, data.promo_code)
    total -= discount

    order = Order(
        user_id=user["id"],
        status=DBOrderStatus.CREATED,
        promo_code_id=promo.id if promo else None,
        total_amount=total,
        discount_amount=discount,
        items=order_items,
    )
    db.add(order)
    db.add(UserOperation(user_id=user["id"], operation_type=OperationType.CREATE_ORDER))
    await db.commit()
    await db.refresh(order, attribute_names=["items"])
    return OrderResponse.model_validate(order, from_attributes=True)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("USER", "ADMIN")),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise AppError("ORDER_NOT_FOUND", "Order not found", 404)
    if user["role"] != "ADMIN" and order.user_id != user["id"]:
        raise AppError("ORDER_OWNERSHIP_VIOLATION", "Not your order", 403)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.put("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: int,
    data: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("USER", "ADMIN")),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise AppError("ORDER_NOT_FOUND", "Order not found", 404)
    if user["role"] != "ADMIN" and order.user_id != user["id"]:
        raise AppError("ORDER_OWNERSHIP_VIOLATION", "Not your order", 403)
    if order.status != DBOrderStatus.CREATED:
        raise AppError("INVALID_STATE_TRANSITION", "Only CREATED orders can be updated", 409)

    last = await _last_operation(db, user["id"], OperationType.UPDATE_ORDER)
    if last and (datetime.now(timezone.utc) - last.created_at) < timedelta(
        minutes=settings.ORDER_UPDATE_LIMIT_MINUTES
    ):
        raise AppError("ORDER_LIMIT_EXCEEDED", "Too many updates", 429)

    for old_item in order.items:
        product = await db.get(Product, old_item.product_id, with_for_update=True)
        if product:
            product.stock += old_item.quantity

    order.items.clear()
    await db.flush()

    new_items, total = await _reserve_items(db, data.items)
    order.items = new_items

    if order.promo_code_id:
        promo = await db.get(PromoCode, order.promo_code_id)
        if promo:
            promo.current_uses -= 1
            try:
                discount, _ = await _apply_promo(db, total, promo.code)
                total -= discount
                order.discount_amount = discount
            except AppError as e:
                if e.error_code == "PROMO_CODE_MIN_AMOUNT":
                    order.promo_code_id = None
                    order.discount_amount = Decimal("0")
                else:
                    raise
    else:
        order.discount_amount = Decimal("0")

    order.total_amount = total
    db.add(UserOperation(user_id=user["id"], operation_type=OperationType.UPDATE_ORDER))
    await db.commit()
    await db.refresh(order, attribute_names=["items"])
    return OrderResponse.model_validate(order, from_attributes=True)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("USER", "ADMIN")),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise AppError("ORDER_NOT_FOUND", "Order not found", 404)
    if user["role"] != "ADMIN" and order.user_id != user["id"]:
        raise AppError("ORDER_OWNERSHIP_VIOLATION", "Not your order", 403)
    if order.status not in (DBOrderStatus.CREATED, DBOrderStatus.PAYMENT_PENDING):
        raise AppError("INVALID_STATE_TRANSITION", "Cannot cancel in current status", 409)

    for item in order.items:
        product = await db.get(Product, item.product_id, with_for_update=True)
        if product:
            product.stock += item.quantity

    if order.promo_code_id:
        promo = await db.get(PromoCode, order.promo_code_id)
        if promo and promo.current_uses > 0:
            promo.current_uses -= 1

    order.status = DBOrderStatus.CANCELED
    await db.commit()
    await db.refresh(order, attribute_names=["items"])
    return OrderResponse.model_validate(order, from_attributes=True)


@router.put("/{order_id}/status", response_model=OrderResponse)
async def change_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("ADMIN")),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise AppError("ORDER_NOT_FOUND", "Order not found", 404)

    current = order.status.value
    target = data.status.value
    allowed = VALID_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise AppError(
            "INVALID_STATE_TRANSITION",
            f"Cannot transition from {current} to {target}. Allowed: {allowed}",
            409,
        )

    order.status = DBOrderStatus(target)
    await db.commit()
    await db.refresh(order, attribute_names=["items"])
    return OrderResponse.model_validate(order, from_attributes=True)