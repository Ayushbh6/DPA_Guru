"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

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
import { ApprovalPackCopilotPanel } from "./approval-pack-copilot-panel";
import { ApprovalPackView } from "./approval-pack-view";
import { ReportModeBar, type ReportViewMode } from "./report-mode-bar";

function getReportView(searchParams: URLSearchParams): ReportViewMode {
  return searchParams.get("view") === "findings" ? "findings" : "pack";
}

export default function ReviewReportPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { projectId, detail } = useProject();
  const [reportResponse, setReportResponse] = useState<AnalysisRunReportResponse | null>(null);
  const [approvalPack, setApprovalPack] = useState<ApprovalPackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);

  const analysisRun = detail?.analysis_run;
  const approvedChecklist = detail?.approved_checklist;
  const elapsed = useReviewElapsed(analysisRun?.started_at, analysisRun?.completed_at, false);
  const reportView = getReportView(searchParams);

  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
      if (!analysisRun?.analysis_run_id || analysisRun.status !== "COMPLETED") {
        if (!cancelled) {
          setReportResponse(null);
          setApprovalPack(null);
        }
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

  function handleViewChange(nextView: ReportViewMode) {
    const href =
      nextView === "findings"
        ? `/vendor-reviews/${projectId}/review/report?view=findings`
        : `/vendor-reviews/${projectId}/review/report`;
    router.push(href, { scroll: false });
  }

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
    <div className="flex min-h-0 flex-col gap-4 pb-2">
      {loading ? <ReportLoadingState /> : null}
      {error ? <ReportLoadError message={error} /> : null}

      <ReportModeBar
        view={reportView}
        canDownload={!!reportResponse?.report}
        exporting={exporting}
        copilotOpen={copilotOpen}
        onViewChange={handleViewChange}
        onDownload={() => void handleExportDocx()}
        onToggleCopilot={() => setCopilotOpen((open) => !open)}
      />

      <div className={`grid min-h-0 gap-4 ${copilotOpen ? "2xl:grid-cols-[minmax(0,1fr)_390px]" : ""}`}>
        <div className="min-w-0">
          {reportView === "pack" ? (
            approvalPack ? (
              <ApprovalPackView
                approvalPack={approvalPack}
                report={reportResponse?.report ?? null}
                findings={reportResponse?.findings ?? []}
                projectId={projectId}
              />
            ) : (
              <ReportUnavailable
                title="Approval Pack Unavailable"
                body="The detailed review report is available, but the Approval Pack narrative could not be loaded from the backend."
                cta={
                  <Button type="button" onClick={() => handleViewChange("findings")} variant="outline">
                    Open Detailed Findings
                  </Button>
                }
              />
            )
          ) : reportResponse?.report ? (
            <ReviewReportView
              report={reportResponse.report}
              findings={reportResponse.findings}
              elapsed={elapsed}
              projectId={projectId}
              documentId={detail?.document?.document_id ?? analysisRun.document_id}
              documentMimeType={detail?.document?.mime_type ?? null}
            />
          ) : null}
        </div>

        <ApprovalPackCopilotPanel
          projectId={projectId}
          open={copilotOpen}
          onOpenChange={setCopilotOpen}
        />
      </div>
    </div>
  );
}
