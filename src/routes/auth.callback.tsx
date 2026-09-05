import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/auth/callback")({
  ssr: false,
  component: AuthCallbackPage,
});

function AuthCallbackPage() {
  const navigate = useNavigate();
  const [message, setMessage] = useState("Completing Google sign-in…");

  useEffect(() => {
    let cancelled = false;

    async function completeSignIn() {
      const params = new URLSearchParams(window.location.search);
      const errorDescription = params.get("error_description") || params.get("error");
      const code = params.get("code");

      if (errorDescription) {
        if (!cancelled) {
          setMessage("Google sign-in was canceled or denied.");
          toast.error("Google sign-in was canceled or denied.");
        }
        return;
      }

      if (!code) {
        if (!cancelled) {
          setMessage("This sign-in link is missing its authorization code.");
          toast.error("Google sign-in could not be completed.");
        }
        return;
      }

      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (cancelled) return;

      if (error) {
        setMessage("Google sign-in could not be completed.");
        toast.error("Google sign-in could not be completed.");
        return;
      }

      await navigate({ to: "/desk", replace: true });
    }

    void completeSignIn();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="panel w-full max-w-sm px-5 py-6 text-center">
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
    </main>
  );
}
