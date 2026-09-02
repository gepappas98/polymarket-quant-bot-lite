from fastapi import Depends
from app.api.routes import api_router
from app.core.database import get_db
from app.schemas.v04_schemas import StrategyFlags, StrategyUpdateRequest
from app.services.strategy_service import get_active_strategies, strategy_names, update_strategies
from app.api.deps import require_api_token


def _result(row):
    active = get_active_strategies_from_row(row)
    return {"politics_only": active.politics_only, "sports_fade": active.sports_fade, "crypto_focus": active.crypto_focus, "active": strategy_names(active), "categories": [x for x, enabled in (("politics", active.politics_only), ("sports", active.sports_fade), ("crypto", active.crypto_focus)) if enabled]}


def _categories(active):
    return [x for x, flag in (("politics", "politics_only"), ("sports", "sports_fade"), ("crypto", "crypto_focus")) if getattr(active, flag)]


def get_active_strategies_from_row(row):
    from app.services.strategy_service import ActiveStrategies
    return ActiveStrategies(row.politics_only, row.sports_fade, row.crypto_focus)


@api_router.get("/strategies")
def strategies(db=Depends(get_db)):
    active = get_active_strategies(db)
    flags = active.__dict__
    return {**flags, "flags": flags, "active": strategy_names(active), "categories": _categories(active)}


@api_router.post("/strategies/update")
def update(request: StrategyUpdateRequest, db=Depends(get_db), _token=Depends(require_api_token)):
    row = update_strategies(db, 1, **request.model_dump(exclude_unset=True))
    active = get_active_strategies_from_row(row)
    return {**active.__dict__, "flags": active.__dict__, "active": strategy_names(active), "categories": _categories(active)}
