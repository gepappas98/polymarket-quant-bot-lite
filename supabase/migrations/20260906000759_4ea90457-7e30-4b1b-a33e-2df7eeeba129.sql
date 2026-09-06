CREATE TABLE public.orders (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  client_order_id text NOT NULL,
  venue_order_id text,
  venue text NOT NULL DEFAULT 'paper',
  mode text NOT NULL DEFAULT 'paper',
  market text NOT NULL,
  side text NOT NULL,
  order_type text NOT NULL DEFAULT 'MARKET',
  price numeric NOT NULL,
  size_shares numeric NOT NULL,
  filled_shares numeric NOT NULL DEFAULT 0,
  avg_fill_price numeric NOT NULL DEFAULT 0,
  fees_paid numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'PENDING',
  reason text,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, client_order_id)
);

CREATE TABLE public.order_fills (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  order_id uuid NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
  fill_id text NOT NULL,
  price numeric NOT NULL,
  shares numeric NOT NULL,
  fee numeric NOT NULL DEFAULT 0,
  filled_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (order_id, fill_id)
);

CREATE INDEX orders_user_created_idx ON public.orders (user_id, created_at DESC);
CREATE INDEX orders_user_status_idx ON public.orders (user_id, status);
CREATE INDEX order_fills_order_idx ON public.order_fills (order_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.orders TO authenticated;
GRANT ALL ON public.orders TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.order_fills TO authenticated;
GRANT ALL ON public.order_fills TO service_role;

ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_fills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own orders" ON public.orders FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own order fills" ON public.order_fills FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();