# Priority 2 patch — plugin architecture, backtesting, PostgreSQL

Αυτό το zip χτίζεται ΠΑΝΩ στο πρώτο Priority 1 patch (χρειάζεται τα
`bot/feeds.py`, `bot/kelly.py`, `bot/daily_limit.py`, `bot/strategies/copy_trading.py`
και `bot/strategies/market_making.py` να είναι ήδη μέσα στο repo σου).

## Τι περιέχει

**Νέα αρχεία:**
```
bot/strategies/loader.py       # dynamic plugin discovery
bot/strategies/arbitrage.py    # wrapper για το υπάρχον Strategy, ώστε ο loader να το βλέπει σαν plugin
bot/backtest.py                # backtesting framework πάνω σε ιστορικά order-book snapshots
bot/ledger_pg.py                # PostgreSQL-backed ledger (ίδιο interface με bot/ledger.py::Ledger)
```

**Αντικατεστημένα αρχεία (πλήρως ενσωματωμένα):**
```
bot/main.py       # χρησιμοποιεί strategies/loader.py::load_all() αντί για χειροκίνητο registration
bot/ledger.py      # πρόσθεσε _build_ledger() factory — επιλέγει JSONL ή PostgreSQL βάσει LEDGER_BACKEND
bot/strategies/market_making.py, copy_trading.py  # πρόσθεσαν build()/STRATEGY_ENABLED_ENV
```

## 1. Plugin architecture

Κάθε αρχείο μέσα στο `bot/strategies/` γίνεται αυτόματα ανακαλυπτό αν εκθέτει:

```python
STRATEGY_ENABLED_ENV = "MY_STRATEGY_ENABLED"   # προαιρετικό — αν λείπει, φορτώνεται πάντα

def build(shared_strategy):
    return MyStrategy(...)
```

Το `bot/main.py` τώρα κάνει μόνο:
```python
from .strategies.loader import load_all
...
registry = load_all(strategy)
```

Για να προσθέσεις μια νέα στρατηγική στο μέλλον: βάλε ένα αρχείο μέσα στο
`bot/strategies/`, δώσε του `build()`, τέλος — **δεν αγγίζεις το main.py**.
Για να την αφαιρέσεις: σβήσε το αρχείο (ή βάλε `MY_STRATEGY_ENABLED=false`).

Επιβεβαιώθηκε με smoke-run: με `MM_ENABLED=false`/`COPY_TRADING_ENABLED=false`
φορτώνεται μόνο το `Strategy` (arb/directional). Με τα δύο σε `true`,
φορτώνονται και τα τρία — ίδιο resulting registry με το χειροκίνητο registration
του πρώτου patch, απλά αυτόματα.

## 2. Backtesting framework (`bot/backtest.py`)

```bash
python -m bot.backtest path/to/snapshots.jsonl
```

Format: JSONL, μία γραμμή ανά order-book μεταβολή ή resolution event:
```json
{"ts": 1735500000.0, "market": {"slug": "btc-updown-5m-...", "asset": "BTC", "up_token_id": "...", "down_token_id": "..."}, "up_bids": [...], "up_asks": [...], "down_bids": [...], "down_asks": [...], "resolved": false, "winner": null}
```
και ένα resolution event:
```json
{"ts": 1735500300.0, "market": {"slug": "btc-updown-5m-..."}, "resolved": true, "winner": "UP"}
```

Τρέχει το **πλήρες strategy stack** (arb/directional + όποια plugins είναι
ενεργά μέσω των ίδιων env vars) πάνω στα snapshots, χωρίς δίκτυο.

**⚠️ Σημαντικός περιορισμός, διάβασέ τον πριν εμπιστευτείς αριθμούς:**
Το cooldown (`bot/gates.py`) και το session drawdown kill-switch
(`bot/portfolio_gates.py`) βασίζονται σε πραγματικό `time.time()`, όχι σε
ιστορικό/injectable ρολόι. Στο backtest αυτά αντικαθίστανται από ένα
απλοποιημένο, time-independent risk μοντέλο (μόνο exposure cap + max order
size — ίδιο μαθηματικό μοντέλο, βλ. `_simple_exposure_gate` στο αρχείο). Άρα
το backtest σου δείχνει σωστά το **strategy edge**, αλλά ΟΧΙ πιστά το
πραγματικό production risk behavior (πόσα θα μπλόκαρε το cooldown/kill-switch
live). Το ανέφερα ρητά στο docstring του αρχείου — μην το προσπεράσεις.

Δοκιμάστηκε end-to-end με συνθετικό 2-γραμμών snapshot (arb pair 0.48+0.48,
UP winner) → σωστό `realized_pnl=$+2.08` (25$ σε κάθε πλευρά στο 0.96 total,
UP κερδίζει).

## 3. PostgreSQL storage (`bot/ledger_pg.py`)

```bash
pip install "psycopg[binary]>=3.1.0" psycopg_pool
```

`.env`:
```bash
LEDGER_BACKEND=postgres
DATABASE_URL=postgresql://user:pass@host:5432/polymarket_bot
```

Ίδιο public interface με το JSONL `Ledger` (`record_intent`, `record_fill`,
`record_outcome`, `win_rate`, `session_summary`) — drop-in swap, τίποτα άλλο
στον κώδικά σου δεν χρειάζεται αλλαγή. Ένας πίνακας (`ledger_entries`) με
indexes σε `kind`/`market_slug`/`ts`.

**⚠️ ΔΕΝ δοκιμάστηκε κόντρα σε πραγματικό PostgreSQL** — το sandbox εδώ δεν
έχει πρόσβαση δικτύου σε database engines (μόνο pypi/npm/github). Δοκίμασα
όμως το **fallback path**: `LEDGER_BACKEND=postgres` χωρίς `psycopg`
εγκατεστημένο ή χωρίς `DATABASE_URL` κάνει graceful fallback στο JSONL ledger
με ένα error log, ΔΕΝ κρασάρει τον bot. Πριν το εμπιστευτείς σε production:
τρέξε χειροκίνητα ένα `record_intent`/`record_fill`/`record_outcome` κύκλο
κόντρα στο δικό σου DB και έλεγξε τα rows.

Αν κάνεις restart τον bot, το `session_summary()`/`win_rate()` θα ξεκινήσουν
άδεια εκτός αν καλέσεις `pg.load_recent()` (ήδη καλείται αυτόματα στο
`_build_ledger()` factory όταν επιλέγεται το postgres backend) — φορτώνει τα
τελευταία 5000 entries από το DB στο in-memory mirror.

## Επιβεβαίωση

```
82 passed in 0.32s     # πλήρες υπάρχον test suite, με LEDGER_BACKEND default (jsonl)
82 passed in 0.43s     # ίδιο, μετά την προσθήκη ledger.py::_build_ledger()
```
plus smoke-runs για loader (enabled/disabled toggling) και backtest
(συνθετικό snapshot, σωστό pnl).

## requirements-additions.txt (ενημέρωση)

```
psycopg[binary]>=3.1.0
psycopg_pool>=3.2.0
```
Μόνο αν ενεργοποιήσεις `LEDGER_BACKEND=postgres` — χωρίς αυτό, καμία νέα
εξάρτηση δεν χρειάζεται (το `backtest.py`/`loader.py`/`arbitrage.py`
χρησιμοποιούν μόνο ό,τι έχεις ήδη).
