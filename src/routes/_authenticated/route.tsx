import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  beforeLoad: async () => {
    const { data, error } = await supabase.auth.getUser();
    if (error || !data.user) throw redirect({ to: "/auth" });
    return { user: data.user };
  },
  component: () => <Outlet />,
  errorComponent: ({ error }) => (
    <main className="mx-auto max-w-xl px-4 py-16 text-center">
      <h1 className="text-lg font-bold">This area is temporarily unavailable</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {error instanceof Error ? error.message : "Please try again in a moment."}
      </p>
      <a href="/" className="tape mt-6 inline-block rounded border border-border px-3 py-1 text-xs uppercase">
        back to monitor
      </a>
    </main>
  ),
});
