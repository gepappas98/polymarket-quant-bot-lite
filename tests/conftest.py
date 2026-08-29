import os

# Force safe defaults before any bot module is imported, so tests never
# accidentally pick up a real .env with live credentials.
os.environ.setdefault("MODE", "paper")
os.environ.pop("LIVE_TRADING_CONFIRM", None)
os.environ.pop("POLYMARKET_PRIVATE_KEY", None)
