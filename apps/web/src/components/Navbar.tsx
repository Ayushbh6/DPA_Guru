"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/button";

function getInitialDarkMode() {
  if (typeof window === "undefined") return true;
  const stored = window.localStorage.getItem("theme");
  return stored ? stored === "dark" : true;
}

function formatDisplayName(username: string) {
  if (!username) return "";
  return username.charAt(0).toUpperCase() + username.slice(1).toLowerCase();
}

function ThemeToggle() {
  const [dark, setDark] = useState(getInitialDarkMode);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  }, [dark]);

  function toggle() {
    const next = !dark;
    setDark(next);
    const theme = next ? "dark" : "light";
    localStorage.setItem("theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
  }

  return (
    <Button
      type="button"
      onClick={toggle}
      aria-label="Toggle color theme"
      variant="ghost"
      size="icon"
      className="h-9 w-9 rounded-2xl text-muted-foreground hover:text-foreground"
    >
      {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </Button>
  );
}

export default function Navbar() {
  const pathname = usePathname();
  const { user, logoutUser } = useAuth();

  if (pathname.startsWith("/projects") || pathname.startsWith("/vendor-reviews")) {
    return null;
  }

  return (
    <nav
      className="fixed left-0 top-0 z-50 w-full"
      style={{
        background: 'color-mix(in srgb, var(--bg) 96%, var(--bg-1))',
        borderBottom: '1px solid var(--line)',
      }}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 md:px-6">
        <Link
          href="/"
          className="group flex items-center gap-3"
          style={{ color: 'var(--text)' }}
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-2xl border" style={{ borderColor: "var(--line)", background: "var(--bg-1)" }}>
            <Shield className="h-4 w-4 transition-transform duration-300 group-hover:scale-110" style={{ color: 'var(--accent)' }} />
          </span>
          <span className="text-sm font-semibold tracking-[-0.02em]">
            Checker
          </span>
        </Link>
        <div className="flex items-center gap-2">
          {user ? (
            <>
              <div className="hidden text-sm sm:block" style={{ color: "var(--text-2)" }}>
                Hi, <span style={{ color: "var(--text)" }}>{formatDisplayName(user.username)}</span>
              </div>
              <Button
                type="button"
                onClick={() => void logoutUser()}
                variant="ghost"
                size="sm"
                className="rounded-2xl text-muted-foreground hover:text-foreground"
              >
                Log out
              </Button>
            </>
          ) : (
            <Button render={<Link href="/login" />} variant="outline" size="sm" className="rounded-2xl">
              Log in
            </Button>
          )}
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
