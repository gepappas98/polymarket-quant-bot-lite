CREATE TABLE public.paper_account (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE UNIQUE,
  starting_bankroll NUMERIC NOT NULL DEFAULT 10000,
  cash NUMERIC NOT NULL DEFAULT 10000,
  realized_pnl NUMERIC NOT NULL DEFAULT 0,
  daily_loss_limit NUMERIC NOT NULL DEFAULT 500,
  max_position_pct NUMERIC NOT NULL DEFAULT 10,
  cooldown_seconds INTEGER NOT NULL DEFAULT 60,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.paper_positions (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  market TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('UP','DOWN')),
  shares NUMERIC NOT NULL,
  avg_price NUMERIC NOT NULL,
  cost_usd NUMERIC NOT NULL,
  opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, market, side)
);

CREATE TABLE public.paper_trades (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  market TEXT NOT NULL,
  side TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('BUY','SELL')),
  price NUMERIC NOT NULL,
  shares NUMERIC NOT NULL,
  size_usd NUMERIC NOT NULL,
  realized_pnl NUMERIC NOT NULL DEFAULT 0,
  cash_after NUMERIC NOT NULL DEFAULT 0,
  reason TEXT,
  gates JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX paper_trades_user_created_idx ON public.paper_trades (user_id, created_at DESC);
CREATE INDEX paper_positions_user_idx ON public.paper_positions (user_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.paper_account TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.paper_positions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.paper_trades TO authenticated;
GRANT ALL ON public.paper_account TO service_role;
GRANT ALL ON public.paper_positions TO service_role;
GRANT ALL ON public.paper_trades TO service_role;

ALTER TABLE public.paper_account ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_trades ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own paper account" ON public.paper_account FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own paper positions" ON public.paper_positions FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own paper trades" ON public.paper_trades FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);