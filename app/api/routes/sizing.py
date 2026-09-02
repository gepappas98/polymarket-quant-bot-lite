from fastapi import Depends
from app.api.routes import api_router
from app.core.database import get_db
from app.schemas.v04_schemas import KellySizingRequest, KellySizingResponse
from app.services.risk_service import get_or_create_risk_config
from app.services.sizing_service import calculate_kelly_size, odds_from_price


@api_router.post("/sizing/calculate", response_model=KellySizingResponse)
def calculate(request: KellySizingRequest, db=Depends(get_db)):
    config = get_or_create_risk_config(db)
    odds = request.odds or (odds_from_price(request.price) if request.price is not None else 1 / max(request.confidence, 0.01))
    result = calculate_kelly_size(request.confidence, odds, request.category, request.balance, request.k_value if request.k_value is not None else config.k_value, request.max_position_pct if request.max_position_pct is not None else config.max_position_pct)
    return {"suggested_size": result.suggested_amount, "suggested_amount": result.suggested_amount, "f_value": result.f_value, "raw_kelly": result.raw_kelly, "variance_used": result.variance_used, "capped_by": result.capped_by, "category": request.category}
