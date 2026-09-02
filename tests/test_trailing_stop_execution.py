from app.core import database
from app.models.trade import Trade
from app.services.trading_service import process_price_update
from bot.executor import Fill
from bot.strategy import Intent, Side


class FakeExecutor:
    def __init__(self):
        self.intents = []

    def execute(self, intents):
        self.intents.extend(intents)
        intent = intents[0]
        shares = intent.size_usd / intent.price
        return [Fill(intent, shares, intent.price, intent.size_usd, 1.0, "paper-close", True)]


def test_price_update_holds_and_persists_price():
    with database.SessionLocal() as db:
        trade = Trade(market_slug="btc-up-or-down", token_id="up-token", category="crypto", side="UP", entry_price=.5, size_usd=10)
        db.add(trade)
        db.commit()
        db.refresh(trade)

        result = process_price_update(trade.id, .49, db=db, executor=FakeExecutor())
        db.refresh(trade)

        assert result.status == "held"
        assert trade.status == "open"
        assert trade.current_price == .49


def test_price_update_executes_trailing_stop_close():
    executor = FakeExecutor()
    with database.SessionLocal() as db:
        trade = Trade(market_slug="btc-up-or-down", token_id="up-token", category="crypto", side="UP", entry_price=.5, size_usd=10)
        db.add(trade)
        db.commit()
        db.refresh(trade)

        result = process_price_update(trade.id, .47, db=db, executor=executor)
        db.refresh(trade)

        assert result.status == "closed"
        assert result.pnl_usd == -0.6
        assert trade.status == "closed"
        assert trade.pnl_usd == -0.6
        assert len(executor.intents) == 1
        assert executor.intents[0].action == "SELL"
        assert executor.intents[0].token_id == "up-token"
