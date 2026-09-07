ALTER TABLE public.paper_trades
  ADD COLUMN IF NOT EXISTS client_order_id text,
  ADD COLUMN IF NOT EXISTS execution_mode text NOT NULL DEFAULT 'paper';

CREATE UNIQUE INDEX IF NOT EXISTS paper_orders_user_client_order_id_uidx
  ON public.paper_orders (user_id, client_order_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.paper_trades TO authenticated;
GRANT ALL ON public.paper_trades TO service_role;

ALTER TABLE public.paper_trades ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'paper_trades'
      AND policyname = 'own paper trades'
  ) THEN
    CREATE POLICY "own paper trades" ON public.paper_trades
      FOR ALL TO authenticated
      USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;
