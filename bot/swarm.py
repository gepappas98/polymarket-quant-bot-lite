"""
Swarm consensus layer (GROKTOPUS-inspired architecture, non-LLM).

Maps existing quant modules to named "agents". Each produces a score in [0, 1]
and optional hard veto. A trade intent only proceeds when weighted consensus
>= threshold and no RUNE (risk) veto is active.

Agents (pipeline roles, not separate LLM calls):
  TIDAL  — market/window scan quality
  NORO   — fair-value / pricing edge
  ZEPHR  — liquidity / book depth
  OKAPI  — inventory / hedge alignment
  RUNE   — risk gates (hard veto)
  VESKA  — execution readiness
  MARIN  — settlement path available
  LUMEN  — optional soft sentiment (default neutral)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

# Default weights — RUNE is veto-only (weight 0 on score, hard block on veto)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "TIDAL": 0.10,
    "NORO": 0.25,
    "ZEPHR": 0.15,
    "OKAPI": 0.20,
    "RUNE": 0.0,   # veto only
    "VESKA": 0.15,
    "MARIN": 0.10,
    "LUMEN": 0.05,
}

AGENT_NAMES = tuple(DEFAULT_WEIGHTS.keys())


@dataclass
class AgentScore:
    name: str
    score: float  # [0, 1]
    veto: bool = False
    reason: str = ""

    def clamped(self) -> "AgentScore":
        s = max(0.0, min(1.0, float(self.score)))
        return AgentScore(self.name, s, self.veto, self.reason)


@dataclass
class ConsensusResult:
    ok: bool
    consensus: float
    threshold: float
    scores: Dict[str, AgentScore] = field(default_factory=dict)
    veto_by: List[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "consensus": round(self.consensus, 4),
            "threshold": self.threshold,
            "veto_by": list(self.veto_by),
            "detail": self.detail,
            "scores": {
                k: {"score": round(v.score, 4), "veto": v.veto, "reason": v.reason}
                for k, v in self.scores.items()
            },
        }


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, "true" if default else "false").lower() == "true"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class SwarmConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("SWARM_ENABLED", True))
    threshold: float = field(default_factory=lambda: _env_float("CONSENSUS_THRESHOLD", 0.70))
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


def consensus(
    scores: Sequence[AgentScore],
    *,
    threshold: Optional[float] = None,
    weights: Optional[Dict[str, float]] = None,
) -> ConsensusResult:
    """
    Weighted mean of non-veto agent scores. Any veto → ok=False.
    Agents missing from `scores` are treated as score=0.5 (neutral), no veto.
    """
    thr = threshold if threshold is not None else _env_float("CONSENSUS_THRESHOLD", 0.70)
    wmap = weights or DEFAULT_WEIGHTS
    by_name: Dict[str, AgentScore] = {s.name.upper(): s.clamped() for s in scores}

    veto_by = [n for n, s in by_name.items() if s.veto]
    if veto_by:
        return ConsensusResult(
            ok=False,
            consensus=0.0,
            threshold=thr,
            scores=by_name,
            veto_by=veto_by,
            detail=f"veto by {', '.join(veto_by)}",
        )

    num = 0.0
    den = 0.0
    for name, w in wmap.items():
        if w <= 0:
            continue
        s = by_name.get(name)
        score = s.score if s is not None else 0.5
        num += w * score
        den += w
    value = (num / den) if den > 0 else 0.0
    ok = value >= thr
    return ConsensusResult(
        ok=ok,
        consensus=value,
        threshold=thr,
        scores=by_name,
        veto_by=[],
        detail="pass" if ok else f"consensus {value:.3f} < {thr:.3f}",
    )


def score_market_state(
    state,
    inv=None,
    *,
    risk_veto: bool = False,
    risk_reason: str = "",
    exec_ready: bool = True,
    settle_ready: bool = True,
    sentiment: float = 0.5,
) -> List[AgentScore]:
    """
    Derive agent scores from live MarketState + optional inventory snapshot.
    Pure functions of existing data — no extra network I/O.
    """
    scores: List[AgentScore] = []

    # TIDAL — scan: active market with both books
    up_ok = state.up_ask is not None
    down_ok = state.down_ask is not None
    if up_ok and down_ok:
        scores.append(AgentScore("TIDAL", 0.9, False, "books present"))
    elif up_ok or down_ok:
        scores.append(AgentScore("TIDAL", 0.45, False, "partial book"))
    else:
        scores.append(AgentScore("TIDAL", 0.1, True, "no book"))

    # NORO — pricing: |fair - mid| edge strength
    fair = getattr(state, "fair_up_prob", None)
    up_mid = None
    try:
        up_mid = state.up_book.mid or state.up_ask
    except Exception:
        up_mid = state.up_ask
    if fair is not None and up_mid is not None:
        edge = abs(fair - up_mid)
        # 0 edge → 0.4, 5c+ → ~1.0
        noro = max(0.2, min(1.0, 0.4 + edge * 8))
        scores.append(AgentScore("NORO", noro, False, f"fair={fair:.3f} mid={up_mid:.3f}"))
    else:
        scores.append(AgentScore("NORO", 0.5, False, "no spot fair — neutral"))

    # ZEPHR — liquidity: sum of asks cheapness + optional depth
    sum_asks = state.sum_asks
    if sum_asks is None:
        scores.append(AgentScore("ZEPHR", 0.2, True, "missing asks"))
    else:
        # tighter complete-set → higher score
        z = max(0.1, min(1.0, (1.02 - sum_asks) / 0.12))
        scores.append(AgentScore("ZEPHR", z, False, f"sum_asks={sum_asks:.4f}"))

    # OKAPI — inventory: prefer reducing residual or building pairs
    okapi = 0.55
    ok_reason = "flat"
    if inv is not None:
        residual = getattr(inv, "residual_side", None)
        paired = float(getattr(inv, "paired_shares", 0) or 0)
        if residual is None and paired > 0:
            okapi = 0.85
            ok_reason = "paired inventory"
        elif residual is not None:
            okapi = 0.65
            ok_reason = f"residual={residual}"
        edge = getattr(inv, "edge_per_set", None)
        if edge is not None and edge > 0:
            okapi = min(1.0, okapi + min(0.2, edge * 2))
            ok_reason += f" set_edge={edge:.3f}"
    scores.append(AgentScore("OKAPI", okapi, False, ok_reason))

    # RUNE — risk hard veto only
    scores.append(
        AgentScore("RUNE", 1.0 if not risk_veto else 0.0, risk_veto, risk_reason or "ok")
    )

    # VESKA — execution readiness (paper always ready; live needs keys etc.)
    scores.append(
        AgentScore(
            "VESKA",
            0.9 if exec_ready else 0.2,
            not exec_ready,
            "ready" if exec_ready else "exec not ready",
        )
    )

    # MARIN — settlement path (resolver exists)
    scores.append(
        AgentScore(
            "MARIN",
            0.85 if settle_ready else 0.3,
            False,
            "resolver ok" if settle_ready else "no resolver",
        )
    )

    # LUMEN — soft sentiment default neutral
    scores.append(AgentScore("LUMEN", max(0.0, min(1.0, sentiment)), False, "sentiment"))

    return scores


def filter_intents(
    intents: list,
    state,
    inv=None,
    *,
    cfg: Optional[SwarmConfig] = None,
    risk_veto: bool = False,
    risk_reason: str = "",
) -> list:
    """
    If swarm disabled, return intents unchanged.
    Else require consensus.ok for the batch; on failure return [].
    Attaches consensus dict onto each intent via optional attribute when possible.
    """
    cfg = cfg or SwarmConfig()
    if not cfg.enabled:
        return intents
    if not intents:
        return intents

    scores = score_market_state(
        state,
        inv,
        risk_veto=risk_veto,
        risk_reason=risk_reason,
    )
    result = consensus(scores, threshold=cfg.threshold, weights=cfg.weights)
    log.info(
        f"[SWARM] {getattr(state, 'market_key', state.market.get('slug', '?'))} "
        f"consensus={result.consensus:.3f} thr={result.threshold:.2f} "
        f"ok={result.ok} {result.detail}"
    )
    if not result.ok:
        return []

    # Best-effort annotate
    for it in intents:
        try:
            it.swarm = result.as_dict()  # type: ignore[attr-defined]
        except Exception:
            pass
    return intents
