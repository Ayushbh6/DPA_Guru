"use client";

import { useState } from "react";
import Link from "next/link";
import { LoaderCircle, Play, TimerReset, TriangleAlert } from "lucide-react";
import { Button, CheckerPanel, CheckerSurface, MetricTile, SectionHeader, StatusBadge } from "@/components/checker-ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { createVendorReviewRun } from "@/lib/uploadApi";
import { useProject } from "../ProjectProvider";
import { formatPercent, formatReviewStage, ReportUnavailable, useReviewElapsed } from "./review-ui";

function isRunActive(status?: string | null) {
  return !!status && !["COMPLETED", "FAILED"].includes(status);
}

export default function ReviewPage() {
  const { projectId, detail, refreshProject, setWorkspaceError, connectAnalysisSocket } = useProject();
  const [starting, setStarting] = useState(false);

  const approvedChecklist = detail?.approved_checklist;
  const analysisRun = detail?.analysis_run;
  const findingCount = analysisRun && "finding_count" in analysisRun ? Number(analysisRun.finding_count || 0) : 0;
  const running = isRunActive(analysisRun?.status);
  const elapsed = useReviewElapsed(analysisRun?.started_at, analysisRun?.completed_at, running);

  async function handleStartReview() {
    if (!projectId) return;
    setStarting(true);
    try {
      const run = await createVendorReviewRun(projectId);
      connectAnalysisSocket(run.analysis_run_id);
      await refreshProject(false);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to start final review.");
    } finally {
      setStarting(false);
    }
  }

  if (!approvedChecklist) {
    return (
      <ReportUnavailable
        title="Approved Checklist Required"
        body="Approve the checklist first. Final review always runs against the latest approved checklist version, not the raw draft."
      />
    );
  }

  return (
    <div className="grid gap-6 pb-6">
      <CheckerSurface className="relative overflow-hidden p-5 md:p-7">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_360px]">
          <div>
            <SectionHeader
              label="Approval Pack Control"
              title="Run the full Vendor Review and monitor it live."
              description="Checker reviews all active parsed documents against the approved criteria, then assembles a deterministic Approval Pack from the saved findings."
            />

            <div className="mt-7 flex flex-wrap gap-3">
              <Button
                type="button"
                onClick={() => void handleStartReview()}
                disabled={starting || running}
                size="lg"
                className="h-10 px-4"
              >
                {(starting || running) && <LoaderCircle className="h-4 w-4 animate-spin" />}
                {!starting && !running && <Play className="h-4 w-4" />}
                {running ? "Review Running" : analysisRun?.status === "COMPLETED" ? "Run Again" : "Run Review"}
              </Button>

              {analysisRun?.status === "COMPLETED" && (
                <Button render={<Link href={`/vendor-reviews/${projectId}/review/report`} />} variant="outline" size="lg" className="h-10 px-4">
                  Open Approval Pack
                </Button>
              )}
            </div>
          </div>

          <div className="grid gap-3">
            <CheckerPanel className="px-5 py-4">
              <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                <TimerReset className="h-3.5 w-3.5" />
                Elapsed Time
              </div>
              <div className="mt-3 text-3xl font-semibold text-foreground">{elapsed}</div>
              <div className="mt-2 text-sm text-muted-foreground">
                {running ? "Timer is running live." : analysisRun?.completed_at ? "Final runtime for the latest review." : "Starts when you launch the review."}
              </div>
            </CheckerPanel>
            <div className="grid grid-cols-2 gap-3">
              <MetricTile label="Checklist Version" value={approvedChecklist.version} />
              <MetricTile label="Latest Run" value={analysisRun ? formatReviewStage(analysisRun.stage || undefined, analysisRun.status) : "Not started"} />
            </div>
          </div>
        </div>
      </CheckerSurface>

      <CheckerSurface className="p-5 md:p-7">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Run Status</div>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-2xl font-medium text-foreground">
              {analysisRun ? formatReviewStage(analysisRun.stage || undefined, analysisRun.status) : "Ready"}
              {analysisRun?.status ? (
                <StatusBadge tone={analysisRun.status === "COMPLETED" ? "success" : analysisRun.status === "FAILED" ? "danger" : "accent"}>
                  {analysisRun.status}
                </StatusBadge>
              ) : null}
            </div>
            <div className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground">
              {analysisRun?.message ||
                "Once started, this run gathers evidence, reviews each approved check in parallel, and then synthesizes a final report."}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <MetricTile label="Progress" value={analysisRun ? formatPercent(analysisRun.progress_pct) : "0%"} tone="accent" />
            <MetricTile label="Findings Saved" value={findingCount} />
            <MetricTile
              label="Started"
              value={analysisRun?.started_at ? new Date(analysisRun.started_at).toLocaleTimeString() : "Not started"}
            />
          </div>
        </div>

        <Progress className="mt-6" value={Math.max(0, Math.min(100, analysisRun?.progress_pct || 0))} />

        {analysisRun?.error_message && (
          <Alert variant="destructive" className="mt-5 border-[var(--danger)] bg-[var(--danger-bg)] text-[var(--danger)]">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <AlertDescription className="text-[var(--danger)]">{analysisRun.error_message}</AlertDescription>
          </Alert>
        )}

        {analysisRun?.status === "COMPLETED" && (
          <CheckerPanel className="mt-6 flex flex-wrap items-center justify-between gap-4 border-[var(--success)] bg-[var(--success-bg)] p-4">
            <div>
              <div className="text-sm font-medium text-[var(--success)]">The review run is complete.</div>
              <div className="mt-1 text-sm text-[var(--success)] opacity-80">
                Open the Approval Pack for recommendation, risks, questions, memo, and evidence.
              </div>
            </div>
            <Button render={<Link href={`/vendor-reviews/${projectId}/review/report`} />} variant="outline">
              Open Approval Pack
            </Button>
          </CheckerPanel>
        )}
      </CheckerSurface>
    </div>
  );
}
