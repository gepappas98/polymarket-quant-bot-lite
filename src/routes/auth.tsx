import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { lovable } from "@/integrations/lovable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/auth")({
  head: () => ({
    meta: [
      { title: "Sign in — Polymarket Quant Bot desk" },
      {
        name: "description",
        content:
          "Sign in to the Polymarket Quant Bot trading desk: market-making, copy-trading, Kelly sizing, cooldowns, backtests and alerts.",
      },
      { property: "og:title", content: "Sign in — Polymarket Quant Bot desk" },
      {
        property: "og:description",
        content: "Access your private trading desk: market-making, copy-trading, backtests, alerts.",
      },
    ],
  }),
  component: AuthPage,
});

function friendlyError(message: string) {
  const m = message.toLowerCase();
  if (m.includes("invalid login credentials"))
    return "Email or password is wrong. If this is your first time here, use “Create one” below.";
  if (m.includes("email not confirmed"))
    return "Confirm your email first — open the link we sent you, then sign in.";
  if (m.includes("weak") || m.includes("pwned"))
    return "That password appears in known leaks. Pick a longer, unique one.";
  if (m.includes("already registered") || m.includes("already been registered"))
    return "That email already has an account. Sign in instead.";
  if (m.includes("at least") || m.includes("6 characters"))
    return "Password must be at least 6 characters.";
  if (m.includes("failed to fetch") || m.includes("network"))
    return "Could not reach the sign-in service. Check your connection and try again.";
  return message;
}

function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "signup") {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/auth` },
        });
        if (signUpError) throw signUpError;
        if (data.session) {
          navigate({ to: "/desk" });
          return;
        }
        setMode("signin");
        setNotice(`Account created. Open the confirmation link we sent to ${email}, then sign in.`);
        toast.success("Check your inbox to confirm your email.");
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        if (signInError) throw signInError;
        navigate({ to: "/desk" });
      }
    } catch (err) {
      const message = friendlyError(err instanceof Error ? err.message : "Authentication failed");
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  async function resendConfirmation() {
    if (!email) {
      setError("Enter your email first.");
      return;
    }
    setBusy(true);
    try {
      const { error: resendError } = await supabase.auth.resend({
        type: "signup",
        email,
        options: { emailRedirectTo: `${window.location.origin}/auth` },
      });
      if (resendError) throw resendError;
      setNotice(`Confirmation link sent again to ${email}.`);
    } catch (err) {
      setError(friendlyError(err instanceof Error ? err.message : "Could not resend the email"));
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    setBusy(true);
    setError(null);
    try {
      const result = await lovable.auth.signInWithOAuth("google", {
        redirect_uri: `${window.location.origin}/auth/callback`,
      });
      if (result.error) throw result.error;
      if (!result.redirected) {
        navigate({ to: "/desk" });
      }
    } catch (err) {
      const message = friendlyError(err instanceof Error ? err.message : "Google sign-in failed");
      setError(message);
      toast.error(message);
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="panel w-full max-w-sm px-5 py-6">
        <h1 className="text-lg font-bold tracking-tight">Trading desk access</h1>
        <p className="tape mt-1 text-[11px] text-muted-foreground">
          Your strategies, trades and alerts stay private to your account.
        </p>

        {notice ? (
          <p className="mt-4 rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-[11px] text-foreground">
            {notice}
          </p>
        ) : null}
        {error ? (
          <p
            role="alert"
            className="mt-4 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-[11px] text-foreground"
          >
            {error}
          </p>
        ) : null}

        <form onSubmit={submit} className="mt-5 space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
            {mode === "signup" ? (
              <p className="tape text-[10px] text-muted-foreground">
                8+ characters, not a password you use elsewhere.
              </p>
            ) : null}
          </div>
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
          </Button>
        </form>

        <Button variant="outline" className="mt-3 w-full" onClick={google} disabled={busy}>
          Continue with Google
        </Button>

        <button
          type="button"
          className="tape mt-4 w-full text-[11px] text-muted-foreground underline"
          onClick={() => {
            setError(null);
            setNotice(null);
            setMode(mode === "signin" ? "signup" : "signin");
          }}
        >
          {mode === "signin" ? "No account? Create one" : "Already have an account? Sign in"}
        </button>

        {mode === "signin" ? (
          <button
            type="button"
            className="tape mt-2 w-full text-[11px] text-muted-foreground underline"
            onClick={resendConfirmation}
            disabled={busy}
          >
            Resend confirmation email
          </button>
        ) : null}
      </div>
    </main>
  );
}
