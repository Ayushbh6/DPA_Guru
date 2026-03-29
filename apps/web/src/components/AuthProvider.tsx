"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { ApiError, getCurrentUser, logout, type AuthUserResponse } from "@/lib/uploadApi";


type AuthContextValue = {
  user: AuthUserResponse | null;
  loading: boolean;
  refreshUser: () => Promise<void>;
  logoutUser: () => Promise<void>;
  applyAuthenticatedUser: (user: AuthUserResponse | null) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function isProtectedPath(pathname: string) {
  return pathname.startsWith("/projects") || pathname.startsWith("/analysis");
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const refreshRequestIdRef = useRef(0);

  const applyAuthenticatedUser = useCallback((nextUser: AuthUserResponse | null) => {
    refreshRequestIdRef.current += 1;
    setUser(nextUser);
    setAuthError(null);
    setLoading(false);
  }, []);

  const refreshUser = useCallback(async () => {
    const requestId = refreshRequestIdRef.current + 1;
    refreshRequestIdRef.current = requestId;
    try {
      const currentUser = await getCurrentUser();
      if (refreshRequestIdRef.current !== requestId) return;
      setUser(currentUser);
      setAuthError(null);
    } catch (error) {
      if (refreshRequestIdRef.current !== requestId) return;
      if (error instanceof ApiError && error.status === 401) {
        setUser(null);
        setAuthError(null);
        if (isProtectedPath(pathname)) {
          const next = `${pathname}${window.location.search}`;
          router.replace(`/login?next=${encodeURIComponent(next)}`);
        }
        return;
      }
      setUser(null);
      setAuthError(error instanceof Error ? error.message : "Unable to verify access right now.");
      return;
    } finally {
      if (refreshRequestIdRef.current !== requestId) return;
      setLoading(false);
    }
  }, [pathname, router]);

  useEffect(() => {
    setLoading(true);
    void refreshUser();
  }, [pathname, refreshUser]);

  async function logoutUser() {
    await logout();
    applyAuthenticatedUser(null);
    router.push("/login");
  }

  if (loading && isProtectedPath(pathname)) {
    return (
      <main
        className="flex min-h-screen items-center justify-center px-6"
        style={{ background: "var(--bg)", color: "var(--text)" }}
      >
        <div className="text-sm" style={{ color: "var(--text-2)" }}>
          Checking access…
        </div>
      </main>
    );
  }

  if (authError && isProtectedPath(pathname)) {
    return (
      <main
        className="flex min-h-screen items-center justify-center px-6"
        style={{ background: "var(--bg)", color: "var(--text)" }}
      >
        <div className="max-w-md text-center">
          <div className="mb-2 text-sm font-medium">Unable to verify access</div>
          <div className="text-sm" style={{ color: "var(--text-2)" }}>
            {authError}
          </div>
        </div>
      </main>
    );
  }

  return (
    <AuthContext.Provider value={{ user, loading, refreshUser, logoutUser, applyAuthenticatedUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
