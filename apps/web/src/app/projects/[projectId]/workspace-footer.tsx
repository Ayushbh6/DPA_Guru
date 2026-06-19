"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, FileText, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { WorkspaceTab } from "./workspace-types";

function getReportView(searchParams: URLSearchParams) {
  return searchParams.get("view") === "findings" ? "findings" : "pack";
}

export function ProjectWorkspaceFooter({
  tabs,
  activeTab,
  pathname,
  projectId,
}: {
  tabs: WorkspaceTab[];
  activeTab: WorkspaceTab;
  pathname: string;
  projectId: string;
}) {
  const searchParams = useSearchParams();
  const activeIndex = Math.max(0, tabs.findIndex((tab) => tab.href === activeTab.href));
  const previousTab = activeIndex > 0 ? tabs[activeIndex - 1] : null;
  const nextTab = activeIndex < tabs.length - 1 ? tabs[activeIndex + 1] : null;
  const isReportRoute = pathname.endsWith("/review/report");
  const reportView = getReportView(searchParams);

  if (isReportRoute) {
    const nextViewHref =
      reportView === "findings"
        ? `/vendor-reviews/${projectId}/review/report`
        : `/vendor-reviews/${projectId}/review/report?view=findings`;

    return (
      <footer className="shrink-0 border-t border-border/80 bg-background/95 px-4 py-3 backdrop-blur md:px-5 lg:px-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Approval Pack
            </div>
            <div className="mt-1 truncate text-sm text-foreground">
              {reportView === "findings" ? "Detailed evidence view" : "Business recommendation view"}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button render={<Link href={`/vendor-reviews/${projectId}/review`} />} variant="outline" className="h-10">
              <ArrowLeft data-icon="inline-start" />
              Review control
            </Button>
            <Button render={<Link href={nextViewHref} />} variant="secondary" className="h-10">
              {reportView === "findings" ? <FileText data-icon="inline-start" /> : <ListChecks data-icon="inline-start" />}
              {reportView === "findings" ? "Approval Pack" : "Detailed findings"}
            </Button>
          </div>
        </div>
      </footer>
    );
  }

  return (
    <footer className="shrink-0 border-t border-border/80 bg-background/95 px-4 py-3 backdrop-blur md:px-5 lg:px-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
            Step {activeIndex + 1} of {tabs.length}
          </div>
          <div className="mt-1 truncate text-sm text-foreground">{activeTab.name}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {previousTab ? (
            <Button render={<Link href={previousTab.href} />} variant="outline" className="h-10">
              <ArrowLeft data-icon="inline-start" />
              {previousTab.shortName}
            </Button>
          ) : null}
          {nextTab ? (
            <Button render={<Link href={nextTab.href} />} className="h-10">
              {nextTab.shortName}
              <ArrowRight data-icon="inline-end" />
            </Button>
          ) : null}
        </div>
      </div>
    </footer>
  );
}
