/**
 * Sprint 1 — injectable clock so paper, live and (later) backtest replay share
 * identical execution semantics with different time sources.
 */

export interface Clock {
  now(): number;
  isoNow(): string;
}

export const systemClock: Clock = {
  now: () => Date.now(),
  isoNow: () => new Date().toISOString(),
};

/** Deterministic clock for tests and replay. */
export class ManualClock implements Clock {
  private ms: number;

  constructor(start: number | string = 0) {
    this.ms = typeof start === "string" ? new Date(start).getTime() : start;
  }

  now(): number {
    return this.ms;
  }

  isoNow(): string {
    return new Date(this.ms).toISOString();
  }

  advance(seconds: number): void {
    this.ms += seconds * 1000;
  }

  set(ms: number | string): void {
    this.ms = typeof ms === "string" ? new Date(ms).getTime() : ms;
  }
}
