"use client";

import { useState } from "react";
import Link from "next/link";
import { LoaderCircle, Play, TimerReset, TriangleAlert } from "lucide-react";
import { createAnalysisRun } from "@/lib/uploadApi";
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
      const run = await createAnalysisRun(projectId);
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
      <section className="relative overflow-hidden border border-white/10 bg-[linear-gradient(180deg,rgba(10,10,30,0.96)_0%,rgba(7,8,20,0.96)_100%)] px-6 py-7 md:px-8 md:py-8">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -left-8 top-0 h-56 w-56 bg-[radial-gradient(circle,rgba(99,102,241,0.18),transparent_62%)]" />
          <div className="absolute bottom-0 right-0 h-48 w-48 bg-[radial-gradient(circle,rgba(20,184,166,0.12),transparent_60%)]" />
        </div>

        <div className="relative z-10 grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_360px]">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-white/42">Final Review Control</div>
            <h2 className="mt-3 max-w-4xl text-3xl font-semibold leading-tight text-white/95 md:text-[2.6rem]">
              Run the full contract review and monitor it live.
            </h2>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-white/58 md:text-[15px]">
              This screen is now just the live control room: start the run, track progress, and watch elapsed time. The completed review opens on its own dedicated report page.
            </p>

            <div className="mt-7 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void handleStartReview()}
                disabled={starting || running}
                className="inline-flex items-center gap-2 bg-white px-4 py-2.5 text-sm font-medium text-black transition-opacity disabled:opacity-50"
              >
                {(starting || running) && <LoaderCircle className="h-4 w-4 animate-spin" />}
                {!starting && !running && <Play className="h-4 w-4" />}
                {running ? "Review Running" : analysisRun?.status === "COMPLETED" ? "Run Again" : "Run Final Review"}
              </button>

              {analysisRun?.status === "COMPLETED" && (
                <Link
                  href={`/projects/${projectId}/review/report`}
                  className="inline-flex items-center gap-2 border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white/82 transition-colors hover:bg-white/[0.06]"
                >
                  Open Full Report
                </Link>
              )}
            </div>
          </div>

          <div className="grid gap-3">
            <div className="border border-white/10 bg-white/[0.04] px-5 py-4">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-white/40">
                <TimerReset className="h-3.5 w-3.5" />
                Elapsed Time
              </div>
              <div className="mt-3 text-3xl font-semibold text-white/93">{elapsed}</div>
              <div className="mt-2 text-sm text-white/50">
                {running ? "Timer is running live." : analysisRun?.completed_at ? "Final runtime for the latest review." : "Starts when you launch the review."}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Checklist Version</div>
                <div className="mt-2 text-sm text-white/86">{approvedChecklist.version}</div>
              </div>
              <div className="border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Latest Run</div>
                <div className="mt-2 text-sm text-white/86">
                  {analysisRun ? formatReviewStage(analysisRun.stage || undefined, analysisRun.status) : "Not started"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border border-white/10 bg-[rgba(8,8,26,0.88)] p-6 md:p-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Run Status</div>
            <div className="mt-3 text-2xl font-medium text-white/92">
              {analysisRun ? formatReviewStage(analysisRun.stage || undefined, analysisRun.status) : "Ready"}
            </div>
            <div className="mt-3 max-w-2xl text-sm leading-7 text-white/56">
              {analysisRun?.message ||
                "Once started, this run gathers evidence, reviews each approved check in parallel, and then synthesizes a final report."}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="border border-white/10 bg-white/[0.03] px-4 py-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Progress</div>
              <div className="mt-2 text-lg text-white/88">{analysisRun ? formatPercent(analysisRun.progress_pct) : "0%"}</div>
            </div>
            <div className="border border-white/10 bg-white/[0.03] px-4 py-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Findings Saved</div>
              <div className="mt-2 text-lg text-white/88">{findingCount}</div>
            </div>
            <div className="border border-white/10 bg-white/[0.03] px-4 py-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Started</div>
              <div className="mt-2 text-sm text-white/88">
                {analysisRun?.started_at ? new Date(analysisRun.started_at).toLocaleTimeString() : "Not started"}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 h-2 w-full overflow-hidden bg-white/10">
          <div
            className={`h-full transition-all ${analysisRun?.status === "FAILED" ? "bg-red-300" : "bg-white"}`}
            style={{ width: `${Math.max(4, analysisRun?.progress_pct || 0)}%` }}
          />
        </div>

        {analysisRun?.error_message && (
          <div className="mt-5 flex items-start gap-3 border border-red-300/20 bg-red-400/5 p-4 text-sm text-red-100/85">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <div>{analysisRun.error_message}</div>
          </div>
        )}

        {analysisRun?.status === "COMPLETED" && (
          <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border border-emerald-300/15 bg-emerald-300/5 p-4">
            <div>
              <div className="text-sm font-medium text-emerald-50/90">The review run is complete.</div>
              <div className="mt-1 text-sm text-emerald-100/70">
                Open the dedicated report page for the full outcome, evidence, and check-by-check analysis.
              </div>
            </div>
            <Link
              href={`/projects/${projectId}/review/report`}
              className="inline-flex items-center gap-2 border border-emerald-300/20 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-50 transition-colors hover:bg-emerald-300/15"
            >
              Open Full Report
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
