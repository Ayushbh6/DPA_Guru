"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return true;
    const stored = localStorage.getItem("theme");
    return stored ? stored === "dark" : true;
  });

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
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle color theme"
      className="flex items-center justify-center w-8 h-8 transition-colors"
      style={{ color: 'var(--text-3)' }}
      onMouseEnter={e => (e.currentTarget.style.color = 'var(--text)')}
      onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
    >
      {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </button>
  );
}

export default function Navbar() {
  const pathname = usePathname();

  if (pathname.startsWith("/projects")) {
    return null;
  }

  return (
    <nav
      className="fixed top-0 left-0 w-full z-50 backdrop-blur-xl"
      style={{
        background: 'color-mix(in srgb, var(--bg) 85%, transparent)',
        borderBottom: '1px solid var(--line)',
      }}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link
          href="/"
          className="flex items-center gap-3 group"
          style={{ color: 'var(--text)' }}
        >
          <Shield
            className="w-5 h-5 transition-transform duration-300 group-hover:scale-110"
            style={{ color: 'var(--accent)' }}
          />
          <span className="text-[15px] font-medium tracking-wide">
            Merlin AI
          </span>
        </Link>
        <ThemeToggle />
      </div>
    </nav>
  );
}
