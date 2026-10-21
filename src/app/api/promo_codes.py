from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.models import DiscountType, PromoCode
from app.db.session import get_db
from app.generated.models import PromoCodeCreate, PromoCodeResponse

router = APIRouter()


@router.post("", response_model=PromoCodeResponse, status_code=201)
async def create_promo_code(
    data: PromoCodeCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles("SELLER", "ADMIN")),
):
    promo = PromoCode(
        code=data.code,
        discount_type=DiscountType(data.discount_type.value),
        discount_value=data.discount_value,
        min_order_amount=data.min_order_amount,
        max_uses=data.max_uses,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return PromoCodeResponse.model_validate(promo, from_attributes=True)
