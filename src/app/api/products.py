from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppError
from app.db.models import Product, ProductStatus as DBProductStatus
from app.db.session import get_db
from app.generated.models import (
    ProductCreate,
    ProductPage,
    ProductResponse,
    ProductStatus,
    ProductUpdate,
)

router = APIRouter()


@router.get("", response_model=ProductPage)
async def list_products(
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    status: ProductStatus | None = None,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    query = select(Product)
    if status:
        query = query.where(Product.status == DBProductStatus(status.value))
    if category:
        query = query.where(Product.category == category)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.execute(query.offset(page * size).limit(size))
    ).scalars().all()

    return ProductPage(
        items=[
            ProductResponse.model_validate(p, from_attributes=True) for p in rows
        ],
        totalElements=total or 0,
        page=page,
        size=size,
    )


@router.post("", response_model=ProductResponse, status_code=201)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("SELLER", "ADMIN")),
):
    product = Product(
        name=data.name,
        description=data.description,
        price=data.price,
        stock=data.stock,
        category=data.category,
        status=DBProductStatus(data.status.value) if data.status else DBProductStatus.ACTIVE,
        seller_id=user["id"] if user["role"] == "SELLER" else None,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return ProductResponse.model_validate(product, from_attributes=True)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    product = await db.get(Product, product_id)
    if not product:
        raise AppError("PRODUCT_NOT_FOUND", "Product not found", 404)
    return ProductResponse.model_validate(product, from_attributes=True)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("SELLER", "ADMIN")),
):
    product = await db.get(Product, product_id)
    if not product:
        raise AppError("PRODUCT_NOT_FOUND", "Product not found", 404)
    if user["role"] == "SELLER" and product.seller_id != user["id"]:
        raise AppError("ACCESS_DENIED", "Not your product", 403)

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "status" and value is not None:
            value = DBProductStatus(value.value if hasattr(value, "value") else value)
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return ProductResponse.model_validate(product, from_attributes=True)


@router.delete("/{product_id}", status_code=204)
async def archive_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("SELLER", "ADMIN")),
):
    product = await db.get(Product, product_id)
    if not product:
        raise AppError("PRODUCT_NOT_FOUND", "Product not found", 404)
    if user["role"] == "SELLER" and product.seller_id != user["id"]:
        raise AppError("ACCESS_DENIED", "Not your product", 403)
    product.status = DBProductStatus.ARCHIVED
    await db.commit()
