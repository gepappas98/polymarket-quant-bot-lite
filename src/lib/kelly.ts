/**
 * Kelly Criterion sizing for binary outcome tokens priced in [0,1].
 *
 * b = (1 - price) / price          (net odds)
 * f* = (b * winProb - (1 - winProb)) / b
 *
 * Fractional Kelly (half by default) because winProb comes from heuristics,
 * not a calibrated model. The result is always clamped by maxOrderUsd, so
 * Kelly can only make sizing more conservative, never more aggressive.
 */
export function kellyFraction(winProb: number, price: number): number {
  const p = Math.min(Math.max(winProb, 0), 1);
  const px = Math.min(Math.max(price, 0.01), 0.99);
  const b = (1 - px) / px;
  if (b <= 0) return 0;
  return Math.max(0, Math.min((b * p - (1 - p)) / b, 1));
}

export interface KellyInput {
  winProb: number;
  price: number;
  bankrollUsd: number;
  fractionOfKelly?: number;
  maxOrderUsd?: number;
}

export function kellySizeUsd({
  winProb,
  price,
  bankrollUsd,
  fractionOfKelly = 0.5,
  maxOrderUsd = Number.POSITIVE_INFINITY,
}: KellyInput): number {
  const frac = Math.min(Math.max(fractionOfKelly, 0), 1);
  const size = kellyFraction(winProb, price) * frac * Math.max(bankrollUsd, 0);
  return Math.round(Math.min(size, maxOrderUsd) * 100) / 100;
}

/** Convert a strategy "edge" (fair value - price) into a win probability. */
export function winProbFromEdge(edge: number, price: number): number {
  return Math.min(Math.max(price + edge, 0), 1);
}

/** Historical win rate → win probability, Laplace-smoothed for small samples. */
export function winRateFromRecord(wins: number, losses: number): number {
  return (wins + 1) / (wins + losses + 2);
}
