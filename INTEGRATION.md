# Πλήρες patch — Priority 1 (market-making, copy-trading, Kelly, daily kill switch)

## Τι περιέχει το zip

**Νέα αρχεία** (αντιγράψτε ως έχουν):
```
bot/feeds.py                      # έλειπε από το upload σου — δημιουργήθηκε από το interface
bot/ledger.py                     # έλειπε από το upload σου — δημιουργήθηκε από το interface
bot/kelly.py                      # Kelly Criterion sizing
bot/daily_limit.py                # daily kill switch, persisted σε δίσκο
bot/strategies/__init__.py
bot/strategies/base.py            # StrategyRegistry
bot/strategies/market_making.py
bot/strategies/copy_trading.py
```

**Αντικατεστημένα αρχεία** (ήδη πλήρως ενσωματωμένα — απλά αντικατέστησε τα
υπάρχοντα με αυτά, δεν χρειάζεται χειροκίνητο diff):
```
bot/main.py        # registry.evaluate_all() αντί για strategy.evaluate()
bot/executor.py     # daily kill switch δίπλα στο max_drawdown_gate
bot/resolver.py     # record_pnl() στο σημείο settlement
```

**Άλλο**:
```
env.example                  # νέα env vars — merge τα μέσα στο δικό σου .env.example
requirements-additions.txt   # σχόλια/οδηγίες, καμία νέα εξάρτηση απαιτείται για Priority 1
```

## Πώς επιβεβαιώθηκε

Δεν είχα πρόσβαση στα πραγματικά `bot/feeds.py` / `bot/ledger.py` (δεν ήταν
στο zip που ανέβασες), οπότε τα ανακατασκεύασα ΑΠΟ ΤΟ INTERFACE που ήδη
χρησιμοποιεί ο υπόλοιπος κώδικάς σου: το `tests/test_strategy.py` έχει ένα
`FakeBook`/`FakeState` σχεδιασμένο ρητά ως stand-in για αυτές τις δύο κλάσεις
— έγραψα το πραγματικό `OrderBook`/`MarketState` ώστε να ταιριάζουν 1:1 σε
αυτό το interface (`best_bid`, `best_ask`, `mid`, `.market`, `.up_ask`,
`.down_ask`, `.sum_asks`, `.arb_available`). Το ίδιο για `LedgerEntry`/`Ledger`
— το schema βγήκε από τα πραγματικά `LedgerEntry(...)` constructor calls μέσα
στα tests σου και στο `resolver.py`/`status_server.py`.

Έτρεξα το **πλήρες υπάρχον test suite σου** πάνω στο patched repo:

```
tests/test_config.py .........
tests/test_gates.py ...................
tests/test_logging_setup.py .....
tests/test_market_finder.py ....................
tests/test_portfolio_gates.py .............
tests/test_strategy.py ................
82 passed in 0.17s
```

και έκανα smoke-run `python -m bot.main` σε paper mode — ξεκινάει καθαρά,
κάνει register τα 3 strategy modules (`Strategy`, `market_making`,
`copy_trading`) και βγαίνει graceful όταν δεν βρίσκει markets (αναμενόμενο
χωρίς πρόσβαση δικτύου στο sandbox — σε πραγματικό deploy θα βρει markets
κανονικά μέσω Gamma).

## Ένα σημείο προσοχής

Το `bot/feeds.py::PriceFeed` (ccxt/Binance spot price) είναι **hook point**
για το ROADMAP item "window open-price delta" — η υπάρχουσα directional
λογική στο `bot/strategy.py` ΔΕΝ το καταναλώνει σήμερα (συνεχίζει να
χρησιμοποιεί μόνο book imbalance, όπως ήδη έκανε). Αν το πραγματικό σου
`feeds.py` (αυτό που λείπει) είχε ήδη διαφορετική λογική εκεί, ή extra
methods/attributes που κάτι άλλο περιμένει (π.χ. WebSocket subscription, κάτι
που η dashboard χρειάζεται) — στείλε μου το πραγματικό αρχείο και σου δίνω
merge patch αντί για πλήρη αντικατάσταση.

## Νέα env vars (ήδη στο env.example του zip)

```bash
# Market making
MM_ENABLED=false
MM_HALF_SPREAD=0.02
MM_MAX_SKEW_INVENTORY_USD=60
MM_SKEW_STRENGTH=0.05
MM_QUOTE_SIZE_USD=10
MM_REQUOTE_INTERVAL_SEC=6

# Copy trading
COPY_TRADING_ENABLED=false
COPY_TRADING_WALLETS=
COPY_TRADING_SIZE_MULTIPLIER=0.1
COPY_TRADING_MIN_TRADE_USD=20
COPY_TRADING_POLL_INTERVAL_SEC=15
COPY_TRADING_MAX_TRADE_AGE_SEC=120
POLYMARKET_DATA_API_HOST=https://data-api.polymarket.com

# Daily kill switch persistence
DAILY_LIMIT_STATE_PATH=data/daily_pnl.json

# (προαιρετικά, ήδη υποστηρίζεται από τον νέο ledger.py)
# LEDGER_PATH=data/trades.jsonl
```

Όλα τα νέα trading features (market-making, copy-trading) είναι **off by
default** — το merge αυτού του patch δεν αλλάζει καμία τρέχουσα συμπεριφορά
μέχρι να τα ενεργοποιήσεις ρητά.

## Βήματα εγκατάστασης

1. Αντίγραψε τα "νέα αρχεία" παραπάνω μέσα στο repo σου (νέα paths).
2. Αντικατέστησε τα `bot/main.py`, `bot/executor.py`, `bot/resolver.py` με τις
   εκδόσεις του zip.
3. Merge το `env.example` μέσα στο δικό σου `.env.example` (και στο τοπικό σου
   `.env`, αν θες να δοκιμάσεις market-making/copy-trading).
4. `pytest -q` — πρέπει να δεις τα ίδια 82 passed (ή περισσότερα αν προσθέσεις
   tests για τα νέα modules).
5. `python -m bot.main` σε `MODE=paper` πρώτα, όπως πάντα.

## Pitfalls (αμετάβλητα από την πρώτη απάντηση)

- **Rate limits (Gamma/Data API)**: το `copy_trading.py` προσθέτει ένα request
  ανά tracked wallet κάθε `COPY_TRADING_POLL_INTERVAL_SEC` (default 15s). Με
  πολλά wallets, μεγάλωσε το interval ή πρόσθεσε backoff σε 429.
- **CLOB v2 client changes**: το `py_clob_client_v2` import παραμένει lazy
  μέσα στο `LiveExecutor._init_client()` — αν αλλάξουν signatures σε live,
  θα σπάσει μόνο εκεί, όχι στο paper mode.
- **Polygon gas**: τα trades στο CLOB είναι off-chain (μόνο settlement/redeem
  on-chain) — gas μόνο θέμα στο auto-redeem step του ROADMAP, όχι ανά trade.
- **Market-making adverse selection**: το `market_making.py` παράγει intents
  που εκτελούνται immediate (ίδιο execution model με την υπόλοιπη βάση κώδικα,
  όχι πραγματικό resting order book) — βλ. σχόλιο στην κορυφή του αρχείου.
- **Copy-trading schema drift**: το `/activity` endpoint schema του
  Data API δεν είναι εγγυημένα σταθερό — δοκίμασε με πραγματικό response πριν
  live (βλ. σχόλιο στην κορυφή του `copy_trading.py`).
- **Kelly σε heuristic edge**: `fraction_of_kelly=0.5` default — μην ανεβάσεις
  χωρίς πραγματικό backtest calibration.
- **bot/feeds.py PriceFeed**: αναδημιουργήθηκε χωρίς το πρωτότυπο — βλ. σημείο
  προσοχής παραπάνω.
