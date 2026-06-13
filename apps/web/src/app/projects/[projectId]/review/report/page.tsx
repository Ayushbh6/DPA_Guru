"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Download, LoaderCircle } from "lucide-react";
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

function PackList({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
      <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-3)' }}>{title}</div>
      <div className="mt-3 grid gap-3">
        {rows.length ? rows.slice(0, 5).map((row, index) => (
          <div key={`${String(row.check_id || index)}-${index}`} className="border p-3" style={{ borderColor: 'var(--line)', background: 'var(--bg)' }}>
            <div className="text-sm font-medium" style={{ color: 'var(--text)' }}>{String(row.title || row.check_id || "Finding")}</div>
            <div className="mt-1 text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--text-3)' }}>
              {String(row.risk || "UNKNOWN")} · {String(row.status || "UNKNOWN")}
            </div>
            {typeof row.rationale === "string" && (
              <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-2)' }}>{row.rationale}</div>
            )}
          </div>
        )) : (
          <div className="text-sm" style={{ color: 'var(--text-3)' }}>No rows.</div>
        )}
      </div>
    </div>
  );
}

function PackQuestions({ rows }: { rows: string[] }) {
  return (
    <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
      <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-3)' }}>Vendor Questions</div>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6" style={{ color: 'var(--text-2)' }}>
        {rows.length ? rows.slice(0, 8).map((question, index) => <li key={`${question}-${index}`}>{question}</li>) : <li>No vendor questions generated.</li>}
      </ol>
    </div>
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
          <Link
            href={`/vendor-reviews/${projectId}/checklist/result`}
            className="inline-flex items-center gap-2 border px-4 py-2.5 text-sm transition-colors"
            style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
          >
            Go to Approved Criteria
          </Link>
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
          <Link
            href={`/vendor-reviews/${projectId}/review`}
            className="inline-flex items-center gap-2 border px-4 py-2.5 text-sm transition-colors"
            style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
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
        body="The Approval Pack is generated only after the review run finishes. Keep watching the live run on the control page."
        cta={
          <Link
            href={`/vendor-reviews/${projectId}/review`}
            className="inline-flex items-center gap-2 border px-4 py-2.5 text-sm transition-colors"
            style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
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
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => void handleExportDocx()}
            disabled={exporting}
            className="inline-flex items-center gap-2 border px-4 py-2.5 text-sm transition-colors disabled:opacity-50"
            style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
          >
            {exporting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Download Approval Pack DOCX
          </button>
        </div>
      )}
      {approvalPack && (
        <section className="border p-5 md:p-7" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)' }}>
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Approval Pack</div>
              <h2 className="mt-3 text-2xl font-semibold capitalize" style={{ color: 'var(--text)' }}>
                {String(approvalPack.recommendation).replaceAll("_", " ")}
              </h2>
              <p className="mt-3 max-w-3xl text-sm leading-7" style={{ color: 'var(--text-2)' }}>
                {approvalPack.recommendation_summary}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-3)' }}>Confidence</div>
                <div className="mt-2 text-lg" style={{ color: 'var(--text)' }}>{Math.round(approvalPack.confidence * 100)}%</div>
              </div>
              <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-3)' }}>Review Required</div>
                <div className="mt-2 text-lg" style={{ color: 'var(--text)' }}>{approvalPack.review_required ? "Yes" : "No"}</div>
              </div>
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
            <div className="mt-4 border p-4 text-sm leading-7" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}>
              {(approvalPack.pack as { internal_memo: string }).internal_memo}
            </div>
          )}
        </section>
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
  );
}
