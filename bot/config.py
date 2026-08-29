import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Mode — live requires double opt-in (see gates.is_live_trading_allowed)
    mode: str = os.getenv("MODE", "paper").lower()  # paper | live

    # Auth
    private_key: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder_address: str = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")

    # Markets
    assets: List[str] = field(default_factory=lambda: os.getenv("ASSETS", "BTC").split(","))
    windows: List[int] = field(default_factory=lambda: [int(x) for x in os.getenv("WINDOWS", "5,15").split(",")])

    # Risk
    max_order_usd: float = float(os.getenv("MAX_ORDER_USD", "25"))
    max_market_exposure_usd: float = float(os.getenv("MAX_MARKET_EXPOSURE_USD", "150"))
    arb_threshold: float = float(os.getenv("ARB_THRESHOLD", "0.985"))
    min_directional_edge: float = float(os.getenv("MIN_DIRECTIONAL_EDGE", "0.03"))
    prefer_maker: bool = os.getenv("PREFER_MAKER", "true").lower() == "true"
    daily_loss_limit_usd: float = float(os.getenv("DAILY_LOSS_LIMIT_USD", "-200"))
    cooldown_minutes: float = float(os.getenv("COOLDOWN_MINUTES", "3"))
    # Min win-rate % from our own ledger before allowing directional (not arb)
    min_track_record_win_pct: float = float(os.getenv("MIN_TRACK_RECORD_WIN_PCT", "48"))
    min_track_record_samples: int = int(os.getenv("MIN_TRACK_RECORD_SAMPLES", "12"))

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

    def is_live(self) -> bool:
        """True only when double opt-in passes (checked properly in gates)."""
        from .gates import is_live_trading_allowed
        return is_live_trading_allowed().allowed


cfg = Config()