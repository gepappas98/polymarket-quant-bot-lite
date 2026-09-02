import math
from dataclasses import dataclass
from statistics import mean, pvariance
from typing import Optional

from app.ledger.reader import fills, recent_category_pnls
from bot.config import cfg


@dataclass
class SizingResult:
    suggested_amount: float
    f_value: float
    raw_kelly: float
    variance_used: Optional[float]
    capped_by: Optional[str]


def rolling_variance(category: str, n: int = 20) -> Optional[float]:
    values = recent_category_pnls(category, n)
    return pvariance(values) if len(values) >= 2 else None


def calculate_kelly_size(confidence, odds, category, balance, k_value, max_pct, variance=None):
    p = max(0.0, min(float(confidence), 1.0))
    b = float(odds) - 1.0
    if b <= 0:
        return SizingResult(0.0, 0.0, 0.0, variance, None)
    raw = max(0.0, min((b * p - (1 - p)) / b, 1.0))
    f = raw * float(k_value)
    capped = None
    var = variance if variance is not None else rolling_variance(category)
    if var is not None and var > 0:
        recent = fills(category)[-20:]
        stakes = [float(row.get("size_usd") or 0) for row in recent]
        mean_stake = mean(stakes) if stakes else float(balance) * float(max_pct)
        cv = math.sqrt(var) / max(mean_stake, 1e-9)
        f_var = f / (1.0 + cv)
        if f_var < f:
            capped = "variance"
            f = f_var
    if f > float(max_pct):
        f = float(max_pct)
        capped = "max_pct"
    amount = f * float(balance)
    if amount > cfg.max_order_usd:
        amount = cfg.max_order_usd
        capped = "max_order_usd"
    return SizingResult(round(amount, 2), round(f * 100, 4), raw, var, capped)


def odds_from_price(price):
    return 1.0 / max(0.01, min(float(price), 0.99))
