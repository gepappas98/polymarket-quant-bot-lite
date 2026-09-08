CREATE TABLE IF NOT EXISTS public.copy_activity_events (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  wallet TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source = 'polymarket_data_api'),
  source_activity_id TEXT NOT NULL,
  transaction_hash TEXT,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  market TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
  price NUMERIC,
  quantity NUMERIC,
  usdc_size NUMERIC,
  event_timestamp TIMESTAMPTZ NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  raw_payload JSONB,
  UNIQUE (user_id, wallet, source, source_activity_id)
);

ALTER TABLE public.copy_activity_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own copy activity events" ON public.copy_activity_events
  FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS copy_activity_events_wallet_time_idx
  ON public.copy_activity_events (user_id, wallet, event_timestamp DESC);
