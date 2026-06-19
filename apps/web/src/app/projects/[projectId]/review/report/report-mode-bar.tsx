"use client";

import { Download, LoaderCircle, MessageSquareText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type ReportViewMode = "pack" | "findings";

export function ReportModeBar({
  view,
  canDownload,
  exporting,
  copilotOpen,
  onViewChange,
  onDownload,
  onToggleCopilot,
}: {
  view: ReportViewMode;
  canDownload: boolean;
  exporting: boolean;
  copilotOpen: boolean;
  onViewChange: (view: ReportViewMode) => void;
  onDownload: () => void;
  onToggleCopilot: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border/70 bg-card/90 p-3 shadow-sm lg:flex-row lg:items-center lg:justify-between">
      <Tabs
        value={view}
        onValueChange={(next) => {
          if (next === "pack" || next === "findings") onViewChange(next);
        }}
        className="min-w-0"
      >
        <TabsList variant="line" className="w-full justify-start">
          <TabsTrigger value="pack" className="px-3">
            Approval Pack
          </TabsTrigger>
          <TabsTrigger value="findings" className="px-3">
            Detailed findings
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={onDownload}
          disabled={!canDownload || exporting}
          variant="outline"
          className="h-10"
        >
          {exporting ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <Download data-icon="inline-start" />}
          Download DOCX
        </Button>
        <Button
          type="button"
          onClick={onToggleCopilot}
          variant={copilotOpen ? "secondary" : "default"}
          className="h-10"
        >
          <MessageSquareText data-icon="inline-start" />
          {copilotOpen ? "Close Copilot" : "Ask Copilot"}
        </Button>
      </div>
    </div>
  );
}
