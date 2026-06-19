"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { login } from "@/lib/uploadApi";
import { useAuth } from "@/components/AuthProvider";

export default function LoginForm({ nextPath }: { nextPath: string }) {
  const router = useRouter();
  const { applyAuthenticatedUser } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const currentUser = await login(username, password);
      applyAuthenticatedUser(currentUser);
      router.push(nextPath || "/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-md rounded-xl border-border bg-card py-0 text-card-foreground shadow-sm">
      <CardHeader className="px-7 pt-8">
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-background text-primary">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <div className="text-[11px] uppercase tracking-[0.28em] text-primary">
          Private Alpha
        </div>
        <CardTitle className="mt-2 text-3xl">Log in to Checker</CardTitle>
        <CardDescription className="leading-6">
          Use the tester credentials you were given to access the Vendor Review workspace.
        </CardDescription>
      </CardHeader>
      <CardContent className="px-7 pb-8">
        <form onSubmit={handleSubmit} suppressHydrationWarning className="grid gap-5">
          <label className="grid gap-2 text-sm">
            <span className="text-muted-foreground">Username</span>
            <Input
              suppressHydrationWarning
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              className="h-12 rounded-lg bg-background px-4"
            />
          </label>

          <label className="grid gap-2 text-sm">
            <span className="text-muted-foreground">Password</span>
            <Input
              suppressHydrationWarning
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              className="h-12 rounded-lg bg-background px-4"
            />
          </label>

          {error ? (
            <Alert variant="destructive" className="border-destructive/30 bg-[var(--danger-bg)]">
              <AlertDescription className="text-[var(--danger)]">{error}</AlertDescription>
            </Alert>
          ) : null}

          <Button type="submit" disabled={submitting || !username.trim() || !password} className="h-12 rounded-lg">
            {submitting ? <LoaderCircle data-icon="inline-start" className="h-4 w-4 animate-spin" /> : null}
            {submitting ? "Signing in..." : "Log in"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
