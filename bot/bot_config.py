import os
from dataclasses import dataclass, field
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()


def _parse_asset_map(raw: str) -> Dict[str, float]:
    """Parse 'BTC:150,ETH:100,SOL:50,XRP:50' into {'BTC': 150.0, ...}. Blank → {}."""
    out: Dict[str, float] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        asset, value = part.split(":", 1)
        try:
            out[asset.strip().upper()] = float(value.strip())
        except ValueError:
            continue
    return out


@dataclass
class Config:
    # Mode — live requires double opt-in (see gates.is_live_trading_allowed)
    mode: str = os.getenv("MODE", "paper").lower()  # paper | live

    # Auth
    private_key: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder_address: str = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")

    # Markets
    assets: List[str] = field(default_factory=lambda: os.getenv("ASSETS", "BTC,ETH,SOL,XRP").split(","))
    windows: List[int] = field(default_factory=lambda: [int(x) for x in os.getenv("WINDOWS", "5,15").split(",")])

    # Risk
    max_order_usd: float = float(os.getenv("MAX_ORDER_USD", "25"))
    max_market_exposure_usd: float = float(os.getenv("MAX_MARKET_EXPOSURE_USD", "150"))
    # Optional per-asset overrides, e.g. "BTC:150,ETH:100,SOL:50,XRP:50".
    # Any asset not listed falls back to max_market_exposure_usd above.
    max_market_exposure_by_asset: Dict[str, float] = field(
        default_factory=lambda: _parse_asset_map(os.getenv("MAX_MARKET_EXPOSURE_BY_ASSET", ""))
    )
    arb_threshold: float = float(os.getenv("ARB_THRESHOLD", "0.985"))
    min_directional_edge: float = float(os.getenv("MIN_DIRECTIONAL_EDGE", "0.03"))
    prefer_maker: bool = os.getenv("PREFER_MAKER", "true").lower() == "true"
    daily_loss_limit_usd: float = float(os.getenv("DAILY_LOSS_LIMIT_USD", "-200"))
    cooldown_minutes: float = float(os.getenv("COOLDOWN_MINUTES", "3"))
    # Min win-rate % from our own ledger before allowing directional (not arb)
    min_track_record_win_pct: float = float(os.getenv("MIN_TRACK_RECORD_WIN_PCT", "48"))
    min_track_record_samples: int = int(os.getenv("MIN_TRACK_RECORD_SAMPLES", "12"))

    # --- v0.5 inventory / complete-set economics ---
    # Target max average set cost (UP avg + DOWN avg); used when staggering legs
    target_set_cost: float = float(os.getenv("TARGET_SET_COST", "0.98"))
    # After a one-sided fill, work the opposite side once lag exceeds this (seconds)
    second_side_lag_sec: float = float(os.getenv("SECOND_SIDE_LAG_SEC", "15"))
    # Force second-side work if naked residual exposure exceeds this USD
    max_naked_residual_usd: float = float(os.getenv("MAX_NAKED_RESIDUAL_USD", "40"))
    # Max fraction of max_order_usd for a pure residual (directional) clip
    residual_size_factor: float = float(os.getenv("RESIDUAL_SIZE_FACTOR", "0.6"))
    # Skip books thinner than this notional on the touch (0 = disabled)
    min_book_depth_usd: float = float(os.getenv("MIN_BOOK_DEPTH_USD", "0"))

    # Network
    clob_host: str = "https://clob.polymarket.com"
    gamma_host: str = "https://gamma-api.polymarket.com"
    chain_id: int = 137
    http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "6"))
    http_retries: int = int(os.getenv("HTTP_RETRIES", "3"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # "text" (human-readable, default) or "json" (structured, one JSON object per line)
    log_format: str = os.getenv("LOG_FORMAT", "text").lower()
    # Optional Prometheus-style /metrics on the status server (needs STATUS_PORT set)
    enable_metrics: bool = os.getenv("ENABLE_METRICS", "false").lower() == "true"

    def exposure_cap_for(self, asset: str) -> float:
        """Per-asset market exposure cap, falling back to the global default."""
        return self.max_market_exposure_by_asset.get((asset or "").upper(), self.max_market_exposure_usd)

    def is_live(self) -> bool:
        """True only when double opt-in passes (checked properly in gates)."""
        from .gates import is_live_trading_allowed
        return is_live_trading_allowed().allowed


cfg = Config()