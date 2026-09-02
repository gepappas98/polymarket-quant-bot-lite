from dataclasses import dataclass
from typing import Optional
from sqlalchemy import select
from app.models.strategy import StrategyConfig
from app.utils.categories import category_for_slug, CATEGORIES


@dataclass(frozen=True)
class ActiveStrategies:
    politics_only: bool = False
    sports_fade: bool = False
    crypto_focus: bool = False


def should_ignore_market(market_slug, category, active_strategies):
    category = category or category_for_slug(market_slug)
    return ((active_strategies.politics_only and category != "politics")
            or (active_strategies.sports_fade and category == "sports")
            or (active_strategies.crypto_focus and category != "crypto"))


def get_active_strategies(db, user_id=1):
    row = db.scalar(select(StrategyConfig).where(StrategyConfig.user_id == user_id))
    if row is None:
        row = StrategyConfig(user_id=user_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return ActiveStrategies(row.politics_only, row.sports_fade, row.crypto_focus)


def update_strategies(db, user_id, **flags):
    row = db.scalar(select(StrategyConfig).where(StrategyConfig.user_id == user_id))
    if row is None:
        row = StrategyConfig(user_id=user_id)
        db.add(row)
    for key in ("politics_only", "sports_fade", "crypto_focus"):
        if flags.get(key) is not None:
            setattr(row, key, flags[key])
    db.commit()
    db.refresh(row)
    return row


def strategy_names(active):
    return [name for name in ("politics_only", "sports_fade", "crypto_focus") if getattr(active, name)]
