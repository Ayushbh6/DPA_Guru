"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

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
    <form
      onSubmit={handleSubmit}
      suppressHydrationWarning
      className="w-full max-w-md p-8"
      style={{ background: "var(--bg-1)", border: "1px solid var(--line)" }}
    >
      <div className="mb-8">
        <div className="mb-2 text-xs uppercase tracking-[0.3em]" style={{ color: "var(--accent)" }}>
          Private Alpha
        </div>
        <h1 className="text-3xl font-semibold">Log in to Merlin AI</h1>
        <p className="mt-3 text-sm" style={{ color: "var(--text-2)" }}>
          Use the tester credentials you were given to access the DPA review workspace.
        </p>
      </div>

      <label className="mb-5 block text-sm">
        <span className="mb-2 block" style={{ color: "var(--text-2)" }}>
          Username
        </span>
        <input
          suppressHydrationWarning
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          className="w-full px-4 py-3 outline-none"
          style={{ background: "var(--bg-2)", border: "1px solid var(--line)" }}
        />
      </label>

      <label className="mb-6 block text-sm">
        <span className="mb-2 block" style={{ color: "var(--text-2)" }}>
          Password
        </span>
        <input
          suppressHydrationWarning
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          className="w-full px-4 py-3 outline-none"
          style={{ background: "var(--bg-2)", border: "1px solid var(--line)" }}
        />
      </label>

      {error ? (
        <div className="mb-4 text-sm" style={{ color: "var(--status-noncompliant)" }}>
          {error}
        </div>
      ) : null}

      <button
        type="submit"
        disabled={submitting || !username.trim() || !password}
        className="w-full px-4 py-3 text-sm font-medium disabled:opacity-50"
        style={{ background: "var(--invert)", color: "var(--invert-fg)" }}
      >
        {submitting ? "Signing in..." : "Log in"}
      </button>
    </form>
  );
}
