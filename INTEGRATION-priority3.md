# Priority 3 patch — ML ensemble, cross-platform arbitrage, monitoring

Χτίζεται πάνω στα Priority 1 + Priority 2 patches (χρειάζεται τα strategies/loader.py,
bot/kelly.py, bot/backtest.py κ.λπ. ήδη μέσα στο repo σου).

## Τι περιέχει

**Νέα αρχεία:**
```
bot/ml_model.py                          # XGBoost probability model, training από backtest snapshots
bot/strategies/ml_directional.py         # χρησιμοποιεί το ML model + Kelly sizing
bot/venues/__init__.py
bot/venues/kalshi_client.py              # Kalshi REST client, RSA-PSS request signing
bot/strategies/cross_platform_arbitrage.py
bot/metrics.py                           # Prometheus /metrics exporter
deploy/docker-compose.monitoring.yml
deploy/prometheus.yml
deploy/grafana-datasource.yml
deploy/grafana-dashboard-provider.yml
deploy/grafana-dashboard.json
requirements-additions-priority3.txt
```

**Αντικατεστημένα αρχεία (ήδη ενσωματωμένα):**
```
bot/executor.py   # metrics.record_intent/record_blocked/record_fill/set_kill_switch_active
bot/resolver.py    # metrics.record_outcome/set_daily_pnl
bot/main.py         # metrics.start_metrics_server()
```

Όλα OFF by default: `ML_STRATEGY_ENABLED=false`, `KALSHI_ARB_ENABLED=false`.
Το `bot/metrics.py` ξεκινάει πάντα (αν το `prometheus_client` είναι
εγκατεστημένο) αλλά δεν επηρεάζει καθόλου το trading path — απλά εκθέτει
αριθμούς σε ένα HTTP endpoint.

## 1. XGBoost ensemble (`bot/ml_model.py`)

```bash
pip install xgboost
```

Training pipeline (batch, εκτός του live loop):
```python
from bot.backtest import load_snapshots
from bot.ml_model import build_training_set, ProbabilityModel

snapshots = load_snapshots("data/historical_snapshots.jsonl")
X, y = build_training_set(snapshots)
model = ProbabilityModel()
model.train(X, y)
model.save()  # -> data/ml_model.json (ML_MODEL_PATH)
```

Μετά, `ML_STRATEGY_ENABLED=true` στο `.env` κάνει το
`bot/strategies/ml_directional.py` να φορτώσει το saved model και να παράγει
directional intents με Kelly sizing όποτε η confidence ξεπερνά
`ML_MIN_CONFIDENCE_EDGE` (default 0.08).

**Δοκιμάστηκε πλήρως end-to-end** με 300 συνθετικά resolved markets (imbalance
→ outcome με τεχνητό sigmoid pattern + θόρυβο): training, save, load,
inference όλα δούλεψαν, και το μοντέλο έμαθε σωστά το pattern (P(UP)=0.84 σε
ισχυρά UP-imbalanced book). **ΔΕΝ έχω πραγματικά ιστορικά δεδομένα Polymarket
markets** — η ΠΟΙΟΤΗΤΑ ενός πραγματικού μοντέλου εξαρτάται 100% από το πόσα
πραγματικά resolved markets θα του δώσεις. Με λίγα δείγματα (<200), μην
περιμένεις να ξεπεράσει το heuristic.

## 2. Cross-platform arbitrage — Polymarket ↔ Kalshi (πειραματικό, ΜΗΝ το θεωρήσεις risk-free)

**Σημαντικός περιορισμός, διάβασέ τον πριν ενεργοποιήσεις:**
Αυτό το module ανιχνεύει price gap ανάμεσα σε Polymarket UP/DOWN και Kalshi
YES/NO, αλλά **εκτελεί ΜΟΝΟ το Polymarket σκέλος**. Δεν υπάρχει (ακόμα)
Kalshi order-execution client — θα χρειαστεί ξεχωριστό, μεγαλύτερο patch
(auth, order placement, fills, δικό του ledger/reconciliation). Μέχρι τότε,
αυτό είναι ένα **κατευθυντικό σήμα ενισχυμένο με εξωτερική τιμή**, ΟΧΙ
πραγματικό hedged arbitrage — έχει directional risk στο Polymarket leg. Το
`reason` κάθε intent το δηλώνει ρητά ("DIRECTIONAL, not hedged") ώστε να
ξεχωρίζει καθαρά στο ledger σου.

Setup:
```bash
pip install cryptography
```
```bash
KALSHI_ARB_ENABLED=true
KALSHI_API_KEY_ID=<το API key id σου από Kalshi>
KALSHI_PRIVATE_KEY_PATH=/path/to/kalshi_private_key.pem
KALSHI_MARKET_MAP={"btc-updown-5m-...": "KXBTC-..."}   # ή path σε JSON αρχείο
KALSHI_ARB_MIN_GAP=0.04
```

Το Kalshi orderbook endpoint **απαιτεί signed request ακόμα και για
read-only πρόσβαση** (RSA-PSS + SHA256 πάνω σε timestamp+method+path) —
επιβεβαιωμένο από τα επίσημα docs. Το `bot/venues/kalshi_client.py`
υλοποιεί αυτό το signing.

**Δοκιμάστηκε:** το request signing επιβεβαιώθηκε κρυπτογραφικά σωστό (η
υπογραφή περνάει επαλήθευση με το αντίστοιχο public key, με ένα self-generated
test RSA key pair), plus graceful χειρισμός όταν λείπουν credentials (επιστρέφει
`None`, δεν κάνει raise στο evaluate loop). **ΔΕΝ δοκιμάστηκε κόντρα σε
πραγματικό Kalshi account/API** — το sandbox εδώ δεν έχει δικό σου API key.
Δοκίμασε πρώτα με το Kalshi demo environment
(`KALSHI_API_HOST=https://demo-api.kalshi.co/trade-api/v2`) πριν βάλεις
πραγματικό key.

## 3. Prometheus/Grafana (`bot/metrics.py` + `deploy/`)

```bash
pip install prometheus-client
```

```bash
docker compose -f deploy/docker-compose.monitoring.yml up -d
```

Prometheus: http://localhost:9090, Grafana: http://localhost:3000
(admin/admin — άλλαξέ το). Το dashboard (`deploy/grafana-dashboard.json`)
φορτώνεται αυτόματα με 6 panels: daily PnL, kill-switch status, intents/min
by side, blocked intents/min by reason, fill USD notional/hour, outcomes by
winner.

Ο bot εκθέτει `/metrics` στο port `PROMETHEUS_PORT` (default 9108) — **στο
host, όχι μέσα στο docker-compose** (ο bot συνεχίζει να τρέχει όπως πάντα,
`python -m bot.main`). Το Prometheus container σκανάρει
`host.docker.internal:9108`.

**Δοκιμάστηκε πλήρως end-to-end**: πραγματικό HTTP server, πραγματικό
`/metrics` scrape, όλα τα counters/gauges (`bot_intents_total`,
`bot_intents_blocked_total`, `bot_fills_total`, `bot_fill_usd_total`,
`bot_outcomes_total`, `bot_daily_pnl_usd`, `bot_kill_switch_active`) σωστά
ενημερωμένα. **ΔΕΝ δοκιμάστηκε** το ίδιο το docker-compose stack (Prometheus
+ Grafana containers) — μόνο η JSON/YAML σύνταξη επικυρώθηκε, όχι πραγματικό
`docker compose up` (χωρίς docker daemon σε αυτό το sandbox).

## Pitfalls (πρόσθετα σε αυτά των προηγούμενων patches)

- **Cardinality**: `metrics.record_blocked(reason_kind)` παίρνει σκόπιμα
  ΜΙΚΡΟ, low-cardinality label ("daily_kill", "drawdown", "pair_lock",
  "gate") — ΠΟΤΕ μην περάσεις το πλήρες free-text reason string εκεί, θα
  εκραγεί το cardinality του Prometheus.
- **ML model drift**: αν αλλάξεις τη λίστα `FEATURE_NAMES` στο
  `bot/ml_model.py`, ΠΡΕΠΕΙ να ξανα-εκπαιδεύσεις — ένα saved μοντέλο με
  διαφορετικό feature σχήμα θα κάνει silent-wrong predictions, όχι crash.
- **Kalshi rate limits/auth expiry**: tokens λήγουν κάθε 30 λεπτά per τα
  docs — το τρέχον client κάνει νέο signing σε κάθε request (όχι session
  token), οπότε δεν έχει θέμα expiry, αλλά έλεγξε τα δικά σου rate limits
  αν έχεις πολλά tracked markets.
- **Grafana admin password**: το `docker-compose.monitoring.yml` έχει
  hardcoded `admin/admin` — άλλαξέ το πριν εκθέσεις το Grafana port οπουδήποτε
  εκτός localhost.
