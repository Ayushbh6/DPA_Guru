"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getAnalysisReport, type AnalysisRunReportResponse } from "@/lib/uploadApi";
import { useProject } from "../../ProjectProvider";
import {
  ReportLoadError,
  ReportLoadingState,
  ReportUnavailable,
  ReviewReportView,
  useReviewElapsed,
} from "../review-ui";

export default function ReviewReportPage() {
  const { projectId, detail } = useProject();
  const [reportResponse, setReportResponse] = useState<AnalysisRunReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analysisRun = detail?.analysis_run;
  const approvedChecklist = detail?.approved_checklist;
  const elapsed = useReviewElapsed(analysisRun?.started_at, analysisRun?.completed_at, false);

  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
      if (!analysisRun?.analysis_run_id || analysisRun.status !== "COMPLETED") {
        if (!cancelled) setReportResponse(null);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const response = await getAnalysisReport(analysisRun.analysis_run_id);
        if (!cancelled) setReportResponse(response);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load the full review report.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadReport();
    return () => {
      cancelled = true;
    };
  }, [analysisRun?.analysis_run_id, analysisRun?.status]);

  if (!approvedChecklist) {
    return (
      <ReportUnavailable
        title="No Approved Checklist"
        body="The review report becomes available only after the checklist has been approved and a review run has completed."
        cta={
          <Link
            href={`/projects/${projectId}/checklist/result`}
            className="inline-flex items-center gap-2 border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white/82 transition-colors hover:bg-white/[0.06]"
          >
            Go to Checklist Result
          </Link>
        }
      />
    );
  }

  if (!analysisRun) {
    return (
      <ReportUnavailable
        title="No Review Run Yet"
        body="Start a final review first. This report page is reserved for the completed review output."
        cta={
          <Link
            href={`/projects/${projectId}/review`}
            className="inline-flex items-center gap-2 border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white/82 transition-colors hover:bg-white/[0.06]"
          >
            Open Review Control
          </Link>
        }
      />
    );
  }

  if (analysisRun.status !== "COMPLETED") {
    return (
      <ReportUnavailable
        title="Review Still Running"
        body="The full report is generated only after the review run finishes. Keep watching the live run on the control page."
        cta={
          <Link
            href={`/projects/${projectId}/review`}
            className="inline-flex items-center gap-2 border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white/82 transition-colors hover:bg-white/[0.06]"
          >
            Back to Review Control
          </Link>
        }
      />
    );
  }

  return (
    <div className="grid gap-5 pb-6">
      {loading && <ReportLoadingState />}
      {error && <ReportLoadError message={error} />}
      {reportResponse?.report && (
        <ReviewReportView
          report={reportResponse.report}
          findings={reportResponse.findings}
          elapsed={elapsed}
          projectId={projectId}
          documentId={detail?.document?.document_id ?? analysisRun.document_id}
          documentMimeType={detail?.document?.mime_type ?? null}
        />
      )}
    </div>
  );
}
