"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, LoaderCircle, Sparkles, WandSparkles, X } from "lucide-react";
import { motion } from "framer-motion";
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
      <div className="border p-8" style={{ borderColor: "var(--line)", background: "var(--bg-1)" }}>
        <h2 className="text-xl" style={{ color: "var(--text)" }}>Documents Not Ready</h2>
        <p className="mt-2" style={{ color: "var(--text-2)" }}>
          Upload one primary Main DPA and wait for every active document to finish parsing before generating criteria.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 pb-6">
      <section className="border p-4 md:p-7" style={{ background: "var(--bg-1)", borderColor: "var(--line)" }}>
        <div className="flex items-center gap-3">
          <Sparkles className="h-5 w-5" style={{ color: "var(--text-2)" }} />
          <div>
            <div className="text-sm font-medium md:text-base" style={{ color: "var(--text)" }}>Standard Vendor DPA Criteria</div>
            <div className="text-xs md:text-sm" style={{ color: "var(--text-3)" }}>
              Checker applies the default vendor DPA profile and all active knowledge-base sources automatically.
            </div>
          </div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="border p-4" style={{ borderColor: "var(--line)", background: "var(--bg-2)" }}>
            <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>Active Documents</div>
            <div className="mt-2 text-xl font-semibold" style={{ color: "var(--text)" }}>{activeDocuments.length}</div>
          </div>
          <div className="border p-4" style={{ borderColor: "var(--line)", background: "var(--bg-2)" }}>
            <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>Primary DPA</div>
            <div className="mt-2 truncate text-sm" style={{ color: "var(--text)" }}>{document.filename}</div>
          </div>
          <div className="border p-4" style={{ borderColor: "var(--line)", background: "var(--bg-2)" }}>
            <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>Profile</div>
            <div className="mt-2 text-sm" style={{ color: "var(--text)" }}>Standard Vendor DPA</div>
          </div>
        </div>
      </section>

      <section className="border p-4 md:p-7" style={{ background: "var(--bg-1)", borderColor: "var(--line)" }}>
        <div className="mb-4 flex items-center gap-3">
          <WandSparkles className="h-5 w-5" style={{ color: "var(--text-2)" }} />
          <div>
            <div className="text-sm font-medium md:text-base" style={{ color: "var(--text)" }}>Optional Criteria Instructions</div>
            <div className="text-xs md:text-sm" style={{ color: "var(--text-3)" }}>Strong preference only. Checker will not invent unsupported obligations.</div>
          </div>
        </div>
        <textarea
          value={effectiveInstruction}
          onChange={(event) => setInstructionOverride(event.target.value)}
          placeholder='Example: "Emphasize subprocessors, audit rights, and breach notice language."'
          className="min-h-[140px] w-full resize-y border px-4 py-3 text-sm outline-none"
          style={{ borderColor: "var(--line)", background: "var(--bg-2)", color: "var(--text)" }}
        />
      </section>

      {checklistDraft && (
        <section className="border p-4 md:p-7" style={{ background: "var(--bg-1)", borderColor: "var(--line)" }}>
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>Criteria Generation</div>
              <div className="mt-2 flex items-center gap-3">
                {checklistDraft.status === "COMPLETED" ? (
                  <Sparkles className="h-5 w-5 text-emerald-300" />
                ) : checklistDraft.status === "FAILED" ? (
                  <X className="h-5 w-5 text-red-300" />
                ) : (
                  <LoaderCircle className="h-5 w-5 animate-spin" style={{ color: "var(--text-2)" }} />
                )}
                <h2 className="text-xl" style={{ color: "var(--text)" }}>{formatChecklistStage(checklistDraft.stage)}</h2>
              </div>
              <p className="mt-3 max-w-3xl text-sm" style={{ color: "var(--text-3)" }}>{checklistDraft.message || "Preparing your criteria."}</p>
              {formatChecklistMeta(checklistDraft.meta) && (
                <p className="mt-2 max-w-3xl text-xs uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>
                  {formatChecklistMeta(checklistDraft.meta)}
                </p>
              )}
            </div>
          </div>

          <div className="mt-6 border p-4" style={{ borderColor: "var(--line)", background: "var(--bg-2)" }}>
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
              <span>Progress</span>
              <span>{Math.max(0, Math.min(100, checklistDraft.progress_pct || 0))}%</span>
            </div>
            <div className="mt-3 h-[6px] overflow-hidden" style={{ background: "var(--line)" }}>
              <motion.div
                initial={false}
                animate={{ width: `${Math.max(2, Math.min(100, checklistDraft.progress_pct || 0))}%` }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="h-full"
                style={{ background: "var(--accent)" }}
              />
            </div>
          </div>
        </section>
      )}

      <div className="-mx-4 mt-4 border-t px-4 py-4 md:sticky md:bottom-0 md:z-20 md:-mx-8 md:px-8 md:py-5 md:backdrop-blur-xl" style={{ borderColor: "var(--line)", background: "color-mix(in srgb, var(--bg) 96%, transparent)" }}>
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3 text-sm">
            <FileText className="h-4 w-4" style={{ color: "var(--text-3)" }} />
            <span style={{ color: "var(--text-2)" }}>Active parsed documents and the default criteria profile will be used.</span>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            {isGenerating && checklistDraft?.checklist_draft_id && (
              <button
                type="button"
                onClick={() => void handleStopCriteria()}
                disabled={isStopping}
                className="border px-4 py-2 text-sm transition-colors"
                style={{ borderColor: "var(--line)", color: "var(--text-2)" }}
              >
                {isStopping ? "Stopping Run" : "Stop Run"}
              </button>
            )}
            {checklistDraft?.status === "COMPLETED" && (
              <button
                type="button"
                onClick={() => router.push(`/vendor-reviews/${projectId}/checklist/result`)}
                className="border px-4 py-2 text-sm transition-colors"
                style={{ borderColor: "var(--line)", color: "var(--text-2)" }}
              >
                View Criteria
              </button>
            )}
            <button
              type="button"
              disabled={!!isGenerating || !document?.document_id}
              onClick={() => void handleGenerateCriteria()}
              className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium disabled:opacity-60"
              style={{ background: "var(--invert)", color: "var(--invert-fg)" }}
            >
              {isGenerating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {isGenerating ? "Generating Criteria" : checklistDraft ? "Regenerate Criteria" : "Generate Criteria"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
