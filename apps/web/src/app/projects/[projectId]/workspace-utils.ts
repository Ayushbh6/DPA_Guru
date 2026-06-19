import type { CSSProperties } from "react";

export function projectStatusStyle(status: string): CSSProperties {
  if (status === "REVIEW_COMPLETE" || status === "COMPLETED") {
    return {
      color: "var(--status-compliant)",
      background: "var(--status-compliant-bg)",
      borderColor: "color-mix(in srgb, var(--status-compliant) 34%, transparent)",
    };
  }
  if (status === "CHECKLIST_APPROVED") {
    return {
      color: "var(--status-partial)",
      background: "var(--status-partial-bg)",
      borderColor: "color-mix(in srgb, var(--status-partial) 34%, transparent)",
    };
  }
  if (status.includes("FAIL")) {
    return {
      color: "var(--status-noncompliant)",
      background: "var(--status-noncompliant-bg)",
      borderColor: "color-mix(in srgb, var(--status-noncompliant) 34%, transparent)",
    };
  }
  return {
    color: "var(--text-2)",
    background: "var(--bg-2)",
    borderColor: "var(--line)",
  };
}

export function statusDotColor(status: string): string {
  if (status === "REVIEW_COMPLETE" || status === "COMPLETED") return "var(--status-compliant)";
  if (status === "CHECKLIST_APPROVED") return "var(--status-partial)";
  if (status.includes("FAIL")) return "var(--status-noncompliant)";
  return "var(--text-3)";
}

export function formatStatus(status: string) {
  return status.replaceAll("_", " ");
}

export function formatRelativeDate(value: string) {
  const date = new Date(value);
  const diffHours = Math.round((Date.now() - date.getTime()) / (1000 * 60 * 60));
  if (diffHours < 1) return "Just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
