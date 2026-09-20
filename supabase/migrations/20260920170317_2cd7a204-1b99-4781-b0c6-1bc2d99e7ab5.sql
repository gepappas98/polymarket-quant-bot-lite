ALTER TABLE public.paper_trades
  ADD COLUMN IF NOT EXISTS conviction numeric,
  ADD COLUMN IF NOT EXISTS worker_mirrored boolean,
  ADD COLUMN IF NOT EXISTS worker_reason text;