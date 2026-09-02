from datetime import datetime
from fastapi import Depends, HTTPException
from app.api.routes import api_router
from app.core.database import get_db
from app.ledger.reader import trade_history
from app.schemas.v04_schemas import CloseTradeResponse, PlaceOrderRequest, PlaceOrderResponse, PriceUpdateRequest, TradeHistoryItem
from app.services.trading_service import place_order, process_price_update
from app.api.deps import require_api_token


def _timestamp(value):
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


@api_router.get("/trades/history", response_model=list[TradeHistoryItem])
def history(category=None, start=None, end=None, status=None, limit=200):
    return trade_history(category, _timestamp(start), _timestamp(end), status, min(int(limit), 1000))


@api_router.post("/trades/place", response_model=PlaceOrderResponse)
def place(request: PlaceOrderRequest, db=Depends(get_db), _token=Depends(require_api_token)):
    try:
        return place_order(**request.model_dump(), db=db)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@api_router.post("/trades/price", response_model=CloseTradeResponse)
def price_update(request: PriceUpdateRequest, db=Depends(get_db), _token=Depends(require_api_token)):
    try:
        return process_price_update(request.trade_id, request.current_price, db=db)
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 422, str(exc))
