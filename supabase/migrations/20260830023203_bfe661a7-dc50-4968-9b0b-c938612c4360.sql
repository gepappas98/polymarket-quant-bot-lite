CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$
LANGUAGE plpgsql SET search_path = public;

-- mm_trades
CREATE TABLE public.mm_trades (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  market TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
  price NUMERIC NOT NULL,
  size NUMERIC NOT NULL,
  pnl NUMERIC NOT NULL DEFAULT 0,
  strategy TEXT,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.mm_trades TO authenticated;
GRANT ALL ON public.mm_trades TO service_role;
ALTER TABLE public.mm_trades ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own mm_trades" ON public.mm_trades FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER mm_trades_updated_at BEFORE UPDATE ON public.mm_trades
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE INDEX mm_trades_user_market_idx ON public.mm_trades (user_id, market, timestamp DESC);

-- copy_watchlist
CREATE TABLE public.copy_watchlist (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  wallet_address TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, wallet_address)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.copy_watchlist TO authenticated;
GRANT ALL ON public.copy_watchlist TO service_role;
ALTER TABLE public.copy_watchlist ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own copy_watchlist" ON public.copy_watchlist FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER copy_watchlist_updated_at BEFORE UPDATE ON public.copy_watchlist
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- copy_trades
CREATE TABLE public.copy_trades (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  wallet TEXT NOT NULL,
  market TEXT NOT NULL,
  side TEXT NOT NULL,
  size NUMERIC NOT NULL,
  price NUMERIC,
  pnl NUMERIC NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','mirrored','skipped','closed')),
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.copy_trades TO authenticated;
GRANT ALL ON public.copy_trades TO service_role;
ALTER TABLE public.copy_trades ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own copy_trades" ON public.copy_trades FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER copy_trades_updated_at BEFORE UPDATE ON public.copy_trades
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE INDEX copy_trades_user_idx ON public.copy_trades (user_id, timestamp DESC);

-- cooldown_state
CREATE TABLE public.cooldown_state (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  market TEXT NOT NULL,
  last_trade_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  cooldown_seconds INTEGER NOT NULL DEFAULT 300,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, market)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cooldown_state TO authenticated;
GRANT ALL ON public.cooldown_state TO service_role;
ALTER TABLE public.cooldown_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own cooldown_state" ON public.cooldown_state FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER cooldown_state_updated_at BEFORE UPDATE ON public.cooldown_state
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- strategy_config
CREATE TABLE public.strategy_config (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  name TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT false,
  parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, name)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.strategy_config TO authenticated;
GRANT ALL ON public.strategy_config TO service_role;
ALTER TABLE public.strategy_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own strategy_config" ON public.strategy_config FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER strategy_config_updated_at BEFORE UPDATE ON public.strategy_config
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- backtest_results
CREATE TABLE public.backtest_results (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  strategy TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  pnl NUMERIC NOT NULL DEFAULT 0,
  win_rate NUMERIC NOT NULL DEFAULT 0,
  trades INTEGER NOT NULL DEFAULT 0,
  equity_curve JSONB NOT NULL DEFAULT '[]'::jsonb,
  parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.backtest_results TO authenticated;
GRANT ALL ON public.backtest_results TO service_role;
ALTER TABLE public.backtest_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own backtest_results" ON public.backtest_results FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER backtest_results_updated_at BEFORE UPDATE ON public.backtest_results
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- alert_config
CREATE TABLE public.alert_config (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('kill_switch','daily_loss','drawdown','win_rate')),
  channel TEXT NOT NULL CHECK (channel IN ('slack','telegram','email')),
  destination TEXT,
  threshold NUMERIC NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.alert_config TO authenticated;
GRANT ALL ON public.alert_config TO service_role;
ALTER TABLE public.alert_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own alert_config" ON public.alert_config FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER alert_config_updated_at BEFORE UPDATE ON public.alert_config
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- alert_history
CREATE TABLE public.alert_history (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  config_id UUID REFERENCES public.alert_config(id) ON DELETE SET NULL,
  message TEXT NOT NULL DEFAULT '',
  triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.alert_history TO authenticated;
GRANT ALL ON public.alert_history TO service_role;
ALTER TABLE public.alert_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own alert_history" ON public.alert_history FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER alert_history_updated_at BEFORE UPDATE ON public.alert_history
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- historical_winrate
CREATE TABLE public.historical_winrate (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users ON DELETE CASCADE,
  strategy TEXT NOT NULL,
  wins INTEGER NOT NULL DEFAULT 0,
  losses INTEGER NOT NULL DEFAULT 0,
  avg_pnl NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, strategy)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.historical_winrate TO authenticated;
GRANT ALL ON public.historical_winrate TO service_role;
ALTER TABLE public.historical_winrate ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own historical_winrate" ON public.historical_winrate FOR ALL TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE TRIGGER historical_winrate_updated_at BEFORE UPDATE ON public.historical_winrate
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- historical_candles (shared cache, server-written)
CREATE TABLE public.historical_candles (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  asset TEXT NOT NULL,
  interval TEXT NOT NULL,
  bucket_time TIMESTAMPTZ NOT NULL,
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (asset, interval, bucket_time)
);
GRANT SELECT ON public.historical_candles TO authenticated;
GRANT ALL ON public.historical_candles TO service_role;
ALTER TABLE public.historical_candles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "read candles" ON public.historical_candles FOR SELECT TO authenticated USING (true);

ALTER PUBLICATION supabase_realtime ADD TABLE public.mm_trades;
ALTER PUBLICATION supabase_realtime ADD TABLE public.cooldown_state;
ALTER PUBLICATION supabase_realtime ADD TABLE public.alert_history;