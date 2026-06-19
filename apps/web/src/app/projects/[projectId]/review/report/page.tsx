"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Download, LoaderCircle } from "lucide-react";
import { CheckerPanel, CheckerSurface, MetricTile, SectionHeader } from "@/components/checker-ui";
import { Button } from "@/components/ui/button";
import { downloadFinalReportDocx } from "@/lib/docxExport";
import { getAnalysisReport, getApprovalPack, type AnalysisRunReportResponse, type ApprovalPackResponse } from "@/lib/uploadApi";
import { useProject } from "../../ProjectProvider";
import {
  ReportLoadError,
  ReportLoadingState,
  ReportUnavailable,
  ReviewReportView,
  useReviewElapsed,
} from "../review-ui";
import { ApprovalPackCopilot } from "./ApprovalPackCopilot";

function PackList({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <CheckerPanel className="p-4">
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{title}</div>
      <div className="mt-4 grid gap-3">
        {rows.length ? rows.slice(0, 5).map((row, index) => (
          <div key={`${String(row.check_id || index)}-${index}`} className="rounded-lg border border-border bg-background p-3">
            <div className="text-sm font-medium">{String(row.title || row.check_id || "Finding")}</div>
            <div className="mt-1 text-xs uppercase tracking-[0.12em] text-muted-foreground">
              {String(row.risk || "UNKNOWN")} · {String(row.status || "UNKNOWN")}
            </div>
            {typeof row.rationale === "string" && (
              <div className="mt-2 text-sm leading-6 text-muted-foreground">{row.rationale}</div>
            )}
          </div>
        )) : (
          <div className="text-sm text-muted-foreground">No rows.</div>
        )}
      </div>
    </CheckerPanel>
  );
}

function PackQuestions({ rows }: { rows: string[] }) {
  return (
    <CheckerPanel className="p-4">
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Vendor Questions</div>
      <ol className="mt-4 grid list-decimal gap-2 pl-5 text-sm leading-6 text-muted-foreground">
        {rows.length ? rows.slice(0, 8).map((question, index) => <li key={`${question}-${index}`}>{question}</li>) : <li>No vendor questions generated.</li>}
      </ol>
    </CheckerPanel>
  );
}

export default function ReviewReportPage() {
  const { projectId, detail } = useProject();
  const [reportResponse, setReportResponse] = useState<AnalysisRunReportResponse | null>(null);
  const [approvalPack, setApprovalPack] = useState<ApprovalPackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

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
        const [response, packResponse] = await Promise.all([
          getAnalysisReport(analysisRun.analysis_run_id),
          getApprovalPack(analysisRun.analysis_run_id).catch(() => null),
        ]);
        if (!cancelled) {
          setReportResponse(response);
          setApprovalPack(packResponse);
        }
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

  async function handleExportDocx() {
    if (!reportResponse?.report) return;
    setExporting(true);
    try {
      await downloadFinalReportDocx({
        projectName: `${detail?.project.vendor_name || detail?.project.name || "Vendor Review"} Approval Pack`,
        elapsed,
        report: reportResponse.report,
        findings: reportResponse.findings,
      });
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Failed to export final report.");
    } finally {
      setExporting(false);
    }
  }

  if (!approvedChecklist) {
    return (
      <ReportUnavailable
        title="No Approved Checklist"
        body="The Approval Pack becomes available only after criteria have been approved and a review run has completed."
        cta={
          <Button render={<Link href={`/vendor-reviews/${projectId}/checklist/result`} />} variant="outline" className="rounded-lg">
            Go to Approved Criteria
          </Button>
        }
      />
    );
  }

  if (!analysisRun) {
    return (
      <ReportUnavailable
        title="No Review Run Yet"
        body="Start a review first. This page is reserved for the completed Approval Pack."
        cta={
          <Button render={<Link href={`/vendor-reviews/${projectId}/review`} />} variant="outline" className="rounded-lg">
            Open Review Control
          </Button>
        }
      />
    );
  }

  if (analysisRun.status !== "COMPLETED") {
    return (
      <ReportUnavailable
        title="Review Still Running"
        body="The Approval Pack is generated only after the review run finishes. Keep watching the live run on the control page."
        cta={
          <Button render={<Link href={`/vendor-reviews/${projectId}/review`} />} variant="outline" className="rounded-lg">
            Back to Review Control
          </Button>
        }
      />
    );
  }

  return (
    <div className="grid gap-5 pb-6">
      {loading && <ReportLoadingState />}
      {error && <ReportLoadError message={error} />}
      {reportResponse?.report && (
        <div className="flex justify-end">
          <Button
            type="button"
            onClick={() => void handleExportDocx()}
            disabled={exporting}
            variant="outline"
            className="rounded-lg"
          >
            {exporting ? <LoaderCircle data-icon="inline-start" className="h-4 w-4 animate-spin" /> : <Download data-icon="inline-start" className="h-4 w-4" />}
            Download Approval Pack DOCX
          </Button>
        </div>
      )}
      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="grid min-w-0 gap-5">
          {approvalPack && (
            <CheckerSurface className="p-5 md:p-7">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <SectionHeader
                  label="Approval Pack"
                  title={<span className="capitalize">{String(approvalPack.recommendation).replaceAll("_", " ")}</span>}
                  description={approvalPack.recommendation_summary}
                />
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <MetricTile label="Confidence" value={`${Math.round(approvalPack.confidence * 100)}%`} tone="accent" />
                  <MetricTile label="Review Required" value={approvalPack.review_required ? "Yes" : "No"} tone={approvalPack.review_required ? "warning" : "success"} />
                </div>
              </div>
              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                {Array.isArray((approvalPack.pack as Record<string, unknown>).top_risks) && (
                  <PackList title="Top Risks" rows={(approvalPack.pack as { top_risks: Array<Record<string, unknown>> }).top_risks} />
                )}
                {Array.isArray((approvalPack.pack as Record<string, unknown>).vendor_questions) && (
                  <PackQuestions rows={(approvalPack.pack as { vendor_questions: string[] }).vendor_questions} />
                )}
              </div>
              {typeof (approvalPack.pack as Record<string, unknown>).internal_memo === "string" && (
                <CheckerPanel className="mt-4 bg-background p-4 text-sm leading-7 text-muted-foreground">
                  {(approvalPack.pack as { internal_memo: string }).internal_memo}
                </CheckerPanel>
              )}
            </CheckerSurface>
          )}
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
        <ApprovalPackCopilot projectId={projectId} />
      </div>
    </div>
  );
}
