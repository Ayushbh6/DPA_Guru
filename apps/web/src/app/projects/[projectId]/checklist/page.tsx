"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, LoaderCircle, Sparkles, WandSparkles, X } from "lucide-react";
import { Button, CheckerPanel, CheckerSurface, MetricTile, SectionHeader, StatusBadge } from "@/components/checker-ui";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { cancelChecklistDraft, createVendorCriteriaDraft } from "@/lib/uploadApi";
import { useProject } from "../ProjectProvider";

const CHECKLIST_STAGE_LABELS: Record<string, string> = {
  QUEUED: "Starting Criteria",
  RETRIEVING_KB: "Preparing References",
  EXPANDING_SOURCE_CONTEXT: "Gathering Supporting Information",
  INSPECTING_DPA: "Reviewing Active Documents",
  DRAFTING_CHECKLIST: "Drafting Criteria",
  GROUPING_CATEGORIES: "Grouping By Category",
  EMBEDDING_CHECKS: "Embedding Draft Checks",
  FORMING_SEMANTIC_GROUPS: "Forming Semantic Groups",
  VERIFYING_OVERLAPS: "Verifying Overlaps",
  RESOLVING_GROUPS: "Resolving Semantic Groups",
  MERGING_GROUPS: "Merging Groups",
  FINALIZING_OUTPUT: "Finalizing Synthesis",
  VALIDATING_OUTPUT: "Finalizing Criteria",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

function formatChecklistStage(stage: string | undefined) {
  if (!stage) return "Starting Criteria";
  return CHECKLIST_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

function formatChecklistMeta(meta: Record<string, unknown> | null | undefined) {
  if (!meta) return null;
  const groupsCompleted = typeof meta.semantic_groups_resolved === "number"
    ? meta.semantic_groups_resolved
    : typeof meta.merge_groups_completed === "number"
      ? meta.merge_groups_completed
      : null;
  const groupsTotal = typeof meta.semantic_groups_total === "number"
    ? meta.semantic_groups_total
    : typeof meta.merge_groups_total === "number"
      ? meta.merge_groups_total
      : null;
  if (groupsCompleted != null && groupsTotal != null && groupsTotal > 0) {
    return `Groups ${groupsCompleted}/${groupsTotal}`;
  }
  return null;
}

export default function SetupChecklistPage() {
  const router = useRouter();
  const { projectId, detail, setWorkspaceError, setDetail, connectChecklistSocket } = useProject();
  const [instructionOverride, setInstructionOverride] = useState<string | null>(null);
  const [isStopping, setIsStopping] = useState(false);

  const document = detail?.document;
  const checklistDraft = detail?.checklist_draft;
  const activeDocuments = detail?.documents?.filter((item) => item.lifecycle_status === "active") || [];
  const parseReady = !!document?.document_id && activeDocuments.length > 0 && activeDocuments.every((item) => item.parse_status === "COMPLETED");
  const isGenerating = checklistDraft && !["COMPLETED", "FAILED"].includes(checklistDraft.status);
  const effectiveInstruction = instructionOverride ?? checklistDraft?.user_instruction ?? "";

  async function handleGenerateCriteria() {
    if (!projectId || !document?.document_id) return;
    setWorkspaceError(null);
    try {
      const res = await createVendorCriteriaDraft(projectId, effectiveInstruction.trim() || null);
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              checklist_draft: {
                checklist_draft_id: res.checklist_draft_id,
                document_id: res.document_id,
                project_id: res.project_id,
                vendor_review_id: res.vendor_review_id,
                input_document_ids: res.input_document_ids,
                status: "QUEUED",
                stage: "QUEUED",
                progress_pct: 5,
                message: "Starting criteria generation.",
                selected_source_ids: [],
                user_instruction: effectiveInstruction.trim() || null,
              },
            }
          : prev,
      );
      connectChecklistSocket(res.checklist_draft_id);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to start criteria generation.");
    }
  }

  async function handleStopCriteria() {
    if (!checklistDraft?.checklist_draft_id || !isGenerating) return;
    setWorkspaceError(null);
    setIsStopping(true);
    try {
      const snapshot = await cancelChecklistDraft(checklistDraft.checklist_draft_id);
      setDetail((prev) => (prev ? { ...prev, checklist_draft: snapshot } : prev));
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to stop this criteria run.");
    } finally {
      setIsStopping(false);
    }
  }

  if (!parseReady) {
    return (
      <CheckerSurface className="p-6 md:p-8">
        <SectionHeader
          label="Criteria"
          title="Documents not ready"
          description="Upload one primary Main DPA and wait for every active document to finish parsing before generating criteria."
        />
      </CheckerSurface>
    );
  }

  return (
    <div className="grid gap-6 pb-6">
      <CheckerSurface className="p-4 md:p-7">
        <SectionHeader
          label="Criteria"
          title={
            <span className="inline-flex items-center gap-3">
              <Sparkles className="h-5 w-5 text-muted-foreground" />
              Standard Vendor DPA Criteria
            </span>
          }
          description="Checker applies the default vendor DPA profile and all active knowledge-base sources automatically."
        />
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <MetricTile label="Active Documents" value={activeDocuments.length} tone="accent" />
          <MetricTile label="Primary DPA" value={<span className="block truncate text-sm">{document.filename}</span>} />
          <MetricTile label="Profile" value="Standard Vendor DPA" />
        </div>
      </CheckerSurface>

      <CheckerSurface className="p-4 md:p-7">
        <SectionHeader
          title={
            <span className="inline-flex items-center gap-3">
              <WandSparkles className="h-5 w-5 text-muted-foreground" />
              Optional Criteria Instructions
            </span>
          }
          description="Strong preference only. Checker will not invent unsupported obligations."
        />
        <Textarea
          value={effectiveInstruction}
          onChange={(event) => setInstructionOverride(event.target.value)}
          placeholder='Example: "Emphasize subprocessors, audit rights, and breach notice language."'
          className="mt-5 min-h-[140px] resize-y rounded-lg bg-background px-4 py-3 text-sm"
        />
      </CheckerSurface>

      {checklistDraft && (
        <CheckerSurface className="p-4 md:p-7">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Criteria Generation</div>
              <div className="mt-2 flex items-center gap-3">
                {checklistDraft.status === "COMPLETED" ? (
                  <Sparkles className="h-5 w-5 text-[var(--success)]" />
                ) : checklistDraft.status === "FAILED" ? (
                  <X className="h-5 w-5 text-[var(--danger)]" />
                ) : (
                  <LoaderCircle className="h-5 w-5 animate-spin text-muted-foreground" />
                )}
                <h2 className="text-xl font-semibold text-foreground">{formatChecklistStage(checklistDraft.stage)}</h2>
                <StatusBadge
                  tone={
                    checklistDraft.status === "COMPLETED"
                      ? "success"
                      : checklistDraft.status === "FAILED"
                        ? "danger"
                        : "accent"
                  }
                >
                  {checklistDraft.status}
                </StatusBadge>
              </div>
              <p className="mt-3 max-w-3xl text-sm text-muted-foreground">{checklistDraft.message || "Preparing your criteria."}</p>
              {formatChecklistMeta(checklistDraft.meta) && (
                <p className="mt-2 max-w-3xl text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  {formatChecklistMeta(checklistDraft.meta)}
                </p>
              )}
            </div>
          </div>

          <CheckerPanel className="mt-6 p-4">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              <span>Progress</span>
              <span>{Math.max(0, Math.min(100, checklistDraft.progress_pct || 0))}%</span>
            </div>
            <Progress className="mt-3" value={Math.max(0, Math.min(100, checklistDraft.progress_pct || 0))}>
              <ProgressTrack>
                <ProgressIndicator />
              </ProgressTrack>
            </Progress>
          </CheckerPanel>
        </CheckerSurface>
      )}

      <div className="-mx-4 mt-4 border-t border-border bg-background/95 px-4 py-4 backdrop-blur md:sticky md:bottom-0 md:z-20 md:-mx-8 md:px-8 md:py-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3 text-sm">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Active parsed documents and the default criteria profile will be used.</span>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            {isGenerating && checklistDraft?.checklist_draft_id && (
              <Button
                type="button"
                onClick={() => void handleStopCriteria()}
                disabled={isStopping}
                variant="outline"
                size="lg"
                className="h-10 px-4"
              >
                {isStopping ? "Stopping Run" : "Stop Run"}
              </Button>
            )}
            {checklistDraft?.status === "COMPLETED" && (
              <Button
                type="button"
                onClick={() => router.push(`/vendor-reviews/${projectId}/checklist/result`)}
                variant="outline"
                size="lg"
                className="h-10 px-4"
              >
                View Criteria
              </Button>
            )}
            <Button
              type="button"
              disabled={!!isGenerating || !document?.document_id}
              onClick={() => void handleGenerateCriteria()}
              size="lg"
              className="h-10 px-5"
            >
              {isGenerating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {isGenerating ? "Generating Criteria" : checklistDraft ? "Regenerate Criteria" : "Generate Criteria"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
