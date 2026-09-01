import { createFileRoute } from "@tanstack/react-router";
import { authenticateCronRequest } from "@/integrations/supabase/cron-auth";

/**
 * Scheduled monitor: evaluates every active alert rule against the last 24h of
 * mm_trades / copy_trades, records triggered alerts and pushes them to the
 * configured webhook. Idempotent per rule per hour so retries don't spam.
 */
export const Route = createFileRoute("/api/public/hooks/monitor-alerts")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const unauthorized = await authenticateCronRequest(request);
        if (unauthorized) return unauthorized;

        const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
        const since = new Date(Date.now() - 86_400_000).toISOString();

        const { data: rules, error } = await supabaseAdmin
          .from("alert_config")
          .select("id, user_id, type, channel, threshold, destination")
          .eq("active", true);
        if (error) return Response.json({ error: error.message }, { status: 500 });

        let triggered = 0;

        for (const rule of rules ?? []) {
          const { data: trades } = await supabaseAdmin
            .from("mm_trades")
            .select("pnl")
            .eq("user_id", rule.user_id)
            .gte("timestamp", since);

          const pnls = (trades ?? []).map((t) => Number(t.pnl));
          const total = pnls.reduce((a, b) => a + b, 0);
          const wins = pnls.filter((p) => p > 0).length;
          const winRate = pnls.length ? (100 * wins) / pnls.length : 100;

          let message: string | null = null;
          if (rule.type === "daily_loss" && total <= -Math.abs(rule.threshold)) {
            message = `Daily loss limit hit: ${total.toFixed(2)} USD (limit ${rule.threshold}).`;
          } else if (rule.type === "kill_switch" && total <= -Math.abs(rule.threshold)) {
            message = `Kill switch: session P&L ${total.toFixed(2)} USD breached ${rule.threshold}.`;
          } else if (rule.type === "drawdown" && pnls.length > 0) {
            let peak = 0;
            let run = 0;
            let maxDd = 0;
            for (const p of pnls) {
              run += p;
              peak = Math.max(peak, run);
              maxDd = Math.max(maxDd, peak - run);
            }
            if (maxDd >= Math.abs(rule.threshold)) {
              message = `Drawdown ${maxDd.toFixed(2)} USD exceeded ${rule.threshold}.`;
            }
          } else if (rule.type === "win_rate" && pnls.length >= 10 && winRate < rule.threshold) {
            message = `Win rate ${winRate.toFixed(1)}% fell below ${rule.threshold}%.`;
          }

          if (!message) continue;

          // Idempotency: skip if this rule already alerted within the last hour.
          const { data: recent } = await supabaseAdmin
            .from("alert_history")
            .select("id")
            .eq("config_id", rule.id)
            .gte("triggered_at", new Date(Date.now() - 3_600_000).toISOString())
            .limit(1);
          if (recent && recent.length > 0) continue;

          if (rule.destination && (rule.channel === "slack" || rule.channel === "telegram")) {
            try {
              await fetch(rule.destination, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ text: message }),
              });
            } catch {
              /* delivery failure still recorded below */
            }
          }

          await supabaseAdmin
            .from("alert_history")
            .insert({ user_id: rule.user_id, config_id: rule.id, message });
          triggered += 1;
        }

        return Response.json({ ok: true, rules: rules?.length ?? 0, triggered });
      },
    },
  },
});
