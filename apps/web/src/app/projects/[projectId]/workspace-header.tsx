"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Moon, PanelLeftOpen, PencilLine, Save, ShieldCheck, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { WorkspaceTab } from "./workspace-types";
import { formatRelativeDate, formatStatus, projectStatusStyle, statusDotColor } from "./workspace-utils";

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
    <Button
      type="button"
      onClick={toggle}
      aria-label="Toggle color theme"
      variant="ghost"
      size="icon"
      className="shrink-0 text-muted-foreground hover:text-foreground"
    >
      {dark ? <Sun data-icon="inline-start" /> : <Moon data-icon="inline-start" />}
    </Button>
  );
}

export function ProjectWorkspaceHeader({
  projectName,
  status,
  lastActivityAt,
  tabs,
  activeTab,
  renameMode,
  renameValue,
  renaming,
  onRenameValueChange,
  onStartRename,
  onCancelRename,
  onSaveRename,
  onOpenSidebar,
}: {
  projectName: string;
  status: string;
  lastActivityAt?: string | null;
  tabs: WorkspaceTab[];
  activeTab: WorkspaceTab;
  renameMode: boolean;
  renameValue: string;
  renaming: boolean;
  onRenameValueChange: (value: string) => void;
  onStartRename: () => void;
  onCancelRename: () => void;
  onSaveRename: () => void;
  onOpenSidebar: () => void;
}) {
  const router = useRouter();

  return (
    <header className="shrink-0 border-b border-border/80 bg-background/95 text-foreground backdrop-blur">
      <div className="flex min-h-16 items-center gap-3 px-4 py-3 md:px-5 lg:px-6">
        <Button
          type="button"
          onClick={onOpenSidebar}
          aria-label="Open sidebar"
          variant="ghost"
          size="icon"
          className="shrink-0 text-muted-foreground hover:text-foreground md:hidden"
        >
          <PanelLeftOpen data-icon="inline-start" />
        </Button>

        <div className="hidden size-9 shrink-0 items-center justify-center rounded-lg border border-border/70 text-primary md:flex">
          <ShieldCheck data-icon="inline-start" />
        </div>

        <div className="min-w-0 flex-1">
          {!renameMode ? (
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
              <h1 className="min-w-0 flex-1 truncate text-lg font-semibold tracking-tight text-foreground md:text-xl">
                {projectName}
              </h1>
              <Button
                type="button"
                onClick={onStartRename}
                aria-label="Rename review"
                variant="ghost"
                size="icon-xs"
                className="text-muted-foreground hover:text-foreground"
              >
                <PencilLine data-icon="inline-start" />
              </Button>
              <span
                className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em]"
                style={projectStatusStyle(status)}
              >
                <span
                  className="inline-block size-1.5 rounded-full"
                  style={{ background: statusDotColor(status) }}
                />
                {formatStatus(status)}
              </span>
              <span className="text-xs text-muted-foreground">
                {lastActivityAt ? formatRelativeDate(lastActivityAt) : "Just now"}
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input
                autoFocus
                value={renameValue}
                onChange={(event) => onRenameValueChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") onSaveRename();
                  if (event.key === "Escape") onCancelRename();
                }}
                className="h-10 w-full rounded-lg bg-background text-sm sm:max-w-xl"
              />
              <div className="flex gap-2">
                <Button
                  type="button"
                  onClick={onSaveRename}
                  disabled={renaming || !renameValue.trim()}
                  className="h-10 px-3"
                >
                  <Save data-icon="inline-start" />
                  Save
                </Button>
                <Button
                  type="button"
                  onClick={onCancelRename}
                  variant="outline"
                  className="h-10 px-3"
                >
                  <X data-icon="inline-start" />
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>

        <ThemeToggle />
      </div>

      <div className="border-t border-border/70 px-4 md:px-5 lg:px-6">
        <div className="py-2 md:hidden">
          <Select
            items={tabs.map((tab) => ({ value: tab.href, label: tab.name }))}
            value={activeTab.href}
            onValueChange={(href) => {
              if (typeof href === "string") router.push(href);
            }}
          >
            <SelectTrigger className="h-10 w-full rounded-lg bg-muted/40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="start">
              <SelectGroup>
                {tabs.map((tab, index) => (
                  <SelectItem key={tab.href} value={tab.href}>
                    <span className="mr-2 inline-flex size-5 items-center justify-center rounded-md bg-muted text-[10px] font-semibold text-muted-foreground">
                      {index + 1}
                    </span>
                    {tab.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        <nav className="hidden min-w-0 items-center gap-1 overflow-x-auto md:flex" aria-label="Project steps">
          {tabs.map((tab, index) => {
            const isActive = tab.href === activeTab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={isActive ? "page" : undefined}
                className={`flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-sm font-medium transition-colors ${
                  isActive
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                }`}
              >
                <span
                  className={`inline-flex size-5 items-center justify-center rounded-md text-[10px] font-semibold ${
                    isActive ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                  }`}
                  aria-hidden="true"
                >
                  {index + 1}
                </span>
                <span>{tab.name}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
