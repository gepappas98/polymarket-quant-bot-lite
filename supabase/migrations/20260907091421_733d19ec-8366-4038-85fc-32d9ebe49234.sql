CREATE TABLE public.paper_orders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  client_order_id text NOT NULL,
  market text NOT NULL,
  side text NOT NULL,
  action text NOT NULL,
  order_type text NOT NULL DEFAULT 'MARKET',
  requested_shares numeric NOT NULL DEFAULT 0,
  filled_shares numeric NOT NULL DEFAULT 0,
  remaining_shares numeric NOT NULL DEFAULT 0,
  avg_fill_price numeric NOT NULL DEFAULT 0,
  fees numeric NOT NULL DEFAULT 0,
  slippage numeric NOT NULL DEFAULT 0,
  state text NOT NULL DEFAULT 'NEW',
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, client_order_id)
);

CREATE TABLE public.paper_order_fills (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  order_id uuid NOT NULL REFERENCES public.paper_orders(id) ON DELETE CASCADE,
  price numeric NOT NULL,
  shares numeric NOT NULL,
  fee numeric NOT NULL DEFAULT 0,
  filled_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_paper_orders_user ON public.paper_orders (user_id, created_at DESC);
CREATE INDEX idx_paper_order_fills_order ON public.paper_order_fills (order_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.paper_orders TO authenticated;
GRANT ALL ON public.paper_orders TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.paper_order_fills TO authenticated;
GRANT ALL ON public.paper_order_fills TO service_role;

ALTER TABLE public.paper_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_order_fills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own paper orders" ON public.paper_orders FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own paper order fills" ON public.paper_order_fills FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE TRIGGER paper_orders_updated_at BEFORE UPDATE ON public.paper_orders FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.paper_trades ADD COLUMN IF NOT EXISTS client_order_id text;
ALTER TABLE public.paper_trades ADD COLUMN IF NOT EXISTS execution_mode text NOT NULL DEFAULT 'paper';