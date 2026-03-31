"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ExternalLink, LoaderCircle, ShieldCheck, Sparkles, WandSparkles, X, FileText } from "lucide-react";
import { motion } from "framer-motion";
import { cancelChecklistDraft, createChecklistDraft } from "@/lib/uploadApi";
import { useProject } from "../ProjectProvider";

const CHECKLIST_STAGE_LABELS: Record<string, string> = {
  QUEUED: "Starting Checklist",
  RETRIEVING_KB: "Preparing References",
  EXPANDING_SOURCE_CONTEXT: "Gathering Supporting Information",
  INSPECTING_DPA: "Reviewing Your Document",
  DRAFTING_CHECKLIST: "Drafting Your Checklist",
  GROUPING_CATEGORIES: "Grouping By Category",
  EMBEDDING_CHECKS: "Embedding Draft Checks",
  FORMING_SEMANTIC_GROUPS: "Forming Semantic Groups",
  VERIFYING_OVERLAPS: "Verifying Overlaps",
  RESOLVING_GROUPS: "Resolving Semantic Groups",
  MERGING_GROUPS: "Merging Groups",
  FINALIZING_OUTPUT: "Finalizing Synthesis",
  VALIDATING_OUTPUT: "Finalizing Checklist",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

function formatChecklistStage(stage: string | undefined) {
  if (!stage) return "Starting Checklist";
  return CHECKLIST_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

function formatChecklistMeta(meta: Record<string, unknown> | null | undefined) {
  if (!meta) return null;
  const parts: string[] = [];
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
  const exactDuplicatesRemoved = typeof meta.exact_duplicates_removed === "number" ? meta.exact_duplicates_removed : null;
  if (groupsCompleted != null && groupsTotal != null && groupsTotal > 0) {
    parts.push(`Groups ${groupsCompleted}/${groupsTotal}`);
  }
  if (exactDuplicatesRemoved != null && exactDuplicatesRemoved > 0) {
    parts.push(`Exact duplicates removed ${exactDuplicatesRemoved}`);
  }
  if (meta.fallback_used === true) {
    parts.push("Legacy fallback used");
  }
  return parts.length ? parts.join(" • ") : null;
}

export default function SetupChecklistPage() {
  const router = useRouter();
  const {
    projectId,
    detail,
    sources,
    setWorkspaceError,
    setDetail,
    connectChecklistSocket,
  } = useProject();

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [instructionOverride, setInstructionOverride] = useState<string | null>(null);
  const [isStopping, setIsStopping] = useState(false);

  const document = detail?.document;
  const checklistDraft = detail?.checklist_draft;

  const parseReady = document?.parse_status === "COMPLETED";
  const isGenerating = checklistDraft && !["COMPLETED", "FAILED"].includes(checklistDraft.status);

  const persistedSelectedSourceIds = checklistDraft?.result?.meta.selected_source_ids?.length
    ? checklistDraft.result.meta.selected_source_ids
    : checklistDraft?.selected_source_ids?.length
      ? checklistDraft.selected_source_ids
    : sources.map((src) => src.source_id);
  const defaultSelected = Object.fromEntries(
    sources.map((src) => [src.source_id, persistedSelectedSourceIds.includes(src.source_id)]),
  );

  const effectiveSelected = Object.keys(selected).length
    ? Object.fromEntries(sources.map((src) => [src.source_id, Boolean(selected[src.source_id])]))
    : defaultSelected;
  const effectiveInstruction = instructionOverride ?? checklistDraft?.user_instruction ?? "";

  const selectedIds = sources.filter((src) => effectiveSelected[src.source_id]).map((src) => src.source_id);

  async function handleGenerateChecklist() {
    if (!document?.document_id) return;
    if (!selectedIds.length) {
      setWorkspaceError("Select at least one reference source to continue.");
      return;
    }
    setWorkspaceError(null);
    try {
      const res = await createChecklistDraft({
        document_id: document.document_id,
        selected_source_ids: selectedIds,
        user_instruction: effectiveInstruction.trim() || null,
      });
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              checklist_draft: {
                checklist_draft_id: res.checklist_draft_id,
                document_id: res.document_id,
                project_id: res.project_id,
                status: "QUEUED",
                stage: "QUEUED",
                progress_pct: 5,
                message: "Starting checklist generation.",
                selected_source_ids: selectedIds,
                user_instruction: effectiveInstruction.trim() || null,
              },
            }
          : prev,
      );
      connectChecklistSocket(res.checklist_draft_id);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to start checklist generation.");
    }
  }

  async function handlePauseChecklist() {
    if (!checklistDraft?.checklist_draft_id || !isGenerating) return;
    setWorkspaceError(null);
    setIsStopping(true);
    try {
      const snapshot = await cancelChecklistDraft(checklistDraft.checklist_draft_id);
      setDetail((prev) => (prev ? { ...prev, checklist_draft: snapshot } : prev));
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to stop this checklist run.");
    } finally {
      setIsStopping(false);
    }
  }

  if (!parseReady) {
    return (
      <div className="border p-8" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)' }}>
        <h2 className="text-xl" style={{ color: 'var(--text)' }}>Document Not Ready</h2>
        <p className="mt-2" style={{ color: 'var(--text-2)' }}>Please upload a document and wait for parsing to complete before setting up the checklist.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 pb-6">
      <section className="border p-4 md:p-7" style={{ background: 'var(--bg-1)', borderColor: 'var(--line)' }}>
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-5 h-5" style={{ color: 'var(--text-2)' }} />
            <div>
              <div className="text-sm md:text-base font-medium" style={{ color: 'var(--text)' }}>Regulatory Reference Corpus</div>
              <div className="text-xs md:text-sm" style={{ color: 'var(--text-3)' }}>Only the selected sources may define the legal obligations in the checklist.</div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSelected(Object.fromEntries(sources.map((s) => [s.source_id, true])))}
            className="text-xs uppercase tracking-[0.16em] border px-3 py-2 transition-colors"
            style={{ borderColor: 'var(--line)', color: 'var(--text-2)' }}
          >
            Select All
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sources.map((src) => {
            const checked = Boolean(effectiveSelected[src.source_id]);
            return (
              <button
                type="button"
                key={src.source_id}
                onClick={() =>
                  setSelected((prev) => {
                    const base = Object.keys(prev).length ? effectiveSelected : defaultSelected;
                    return { ...base, [src.source_id]: !base[src.source_id] };
                  })
                }
                className="relative text-left border p-4 transition-all duration-200 group"
                style={{
                  borderColor: checked ? 'color-mix(in srgb, var(--accent) 35%, transparent)' : 'var(--line)',
                  background: checked ? 'color-mix(in srgb, var(--accent) 6%, transparent)' : 'var(--bg-2)',
                  boxShadow: checked ? 'inset 0 0 0 1px color-mix(in srgb, var(--accent) 12%, transparent)' : 'none',
                }}
              >
                <div className="absolute inset-x-0 top-0 h-px" style={{ background: checked ? 'var(--accent)' : 'transparent', opacity: checked ? 0.4 : 0 }} />
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-5 h-5 border flex items-center justify-center"
                      style={{
                        borderColor: checked ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--line-2)',
                        background: checked ? 'color-mix(in srgb, var(--accent) 22%, transparent)' : 'transparent',
                      }}
                    >
                      {checked && <Check className="w-3.5 h-3.5" style={{ color: 'var(--text)' }} />}
                    </div>
                    <span className="text-[11px] font-medium uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>{src.authority}</span>
                  </div>
                  <span className="text-[11px] font-medium uppercase tracking-[0.16em] border px-2 py-1" style={{ borderColor: 'var(--line)', color: 'var(--text-3)' }}>
                    {src.kind}
                  </span>
                </div>
                <div className="mt-3 min-h-[68px] leading-snug" style={{ color: 'var(--text)' }}>{src.title}</div>
                <div className="mt-4 flex items-center justify-between gap-3">
                  <div className="truncate text-xs" style={{ color: 'var(--text-3)' }}>{src.source_id}</div>
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex items-center gap-1 text-xs transition-colors" style={{ color: 'var(--text-2)' }}
                  >
                    Open <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <section className="border p-4 md:p-7" style={{ background: 'var(--bg-1)', borderColor: 'var(--line)' }}>
        <div className="flex items-center gap-3 mb-4">
          <WandSparkles className="w-5 h-5" style={{ color: 'var(--text-2)' }} />
          <div>
            <div className="text-sm md:text-base font-medium" style={{ color: 'var(--text)' }}>Optional Checklist Instructions</div>
            <div className="text-xs md:text-sm" style={{ color: 'var(--text-3)' }}>Strong preference only. The agent will not invent unsupported legal obligations.</div>
          </div>
        </div>
        <textarea
          value={effectiveInstruction}
          onChange={(event) => setInstructionOverride(event.target.value)}
          placeholder='Example: "Emphasize subprocessors, audit rights, and breach notice language. If Article 28 obligations appear fragmented, still keep them separate in the checklist."'
          className="w-full min-h-[140px] border px-4 py-3 text-sm outline-none resize-y"
          style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text)' }}
        />
      </section>

      {checklistDraft && (
        <section className="border p-4 md:p-7" style={{ background: 'var(--bg-1)', borderColor: 'var(--line)' }}>
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Checklist Generation</div>
              <div className="mt-2 flex items-center gap-3">
                {checklistDraft.status === "COMPLETED" ? (
                  <Sparkles className="w-5 h-5 text-emerald-300" />
                ) : checklistDraft.status === "FAILED" ? (
                  <X className="w-5 h-5 text-red-300" />
                ) : (
                  <LoaderCircle className="w-5 h-5 animate-spin" style={{ color: 'var(--text-2)' }} />
                )}
                <h2 className="text-xl" style={{ color: 'var(--text)' }}>{formatChecklistStage(checklistDraft.stage)}</h2>
              </div>
              <p className="mt-3 max-w-3xl text-sm" style={{ color: 'var(--text-3)' }}>{checklistDraft.message || "Preparing your checklist."}</p>
              {formatChecklistMeta(checklistDraft.meta) && (
                <p className="mt-2 max-w-3xl text-xs uppercase tracking-[0.14em]" style={{ color: 'var(--text-3)' }}>
                  {formatChecklistMeta(checklistDraft.meta)}
                </p>
              )}
            </div>
            <div className="border px-4 py-3 text-sm min-w-[220px]" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
              <div className="text-[11px] font-medium uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Draft Job</div>
              <div className="mt-1 break-all" style={{ color: 'var(--text-2)' }}>{checklistDraft.checklist_draft_id}</div>
            </div>
          </div>

          <div className="mt-6 border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
              <span>Progress</span>
              <span>{Math.max(0, Math.min(100, checklistDraft.progress_pct || 0))}%</span>
            </div>
            <div className="mt-3 h-[6px] overflow-hidden" style={{ background: 'var(--line)' }}>
              <motion.div
                initial={false}
                animate={{ width: `${Math.max(2, Math.min(100, checklistDraft.progress_pct || 0))}%` }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="h-full"
                style={{ background: 'var(--accent)' }}
              />
            </div>
          </div>
        </section>
      )}

      {/* Action Bar */}
      <div className="-mx-4 mt-4 border-t px-4 py-4 md:sticky md:bottom-0 md:z-20 md:-mx-8 md:px-8 md:py-5 md:backdrop-blur-xl" style={{ borderColor: 'var(--line)', background: 'color-mix(in srgb, var(--bg) 96%, transparent)' }}>
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3 text-sm">
            <FileText className="w-4 h-4" style={{ color: 'var(--text-3)' }} />
            <span style={{ color: 'var(--text-2)' }}>
              <span style={{ color: 'var(--text)' }}>{selectedIds.length}</span> of <span style={{ color: 'var(--text)' }}>{sources.length}</span> references selected
            </span>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            {isGenerating && checklistDraft?.checklist_draft_id && (
              <button
                type="button"
                onClick={() => void handlePauseChecklist()}
                disabled={isStopping}
                className="border px-4 py-2 text-sm transition-colors"
                style={{ borderColor: 'var(--line)', color: 'var(--text-2)' }}
              >
                {isStopping ? "Stopping Run" : "Stop Run"}
              </button>
            )}
            {checklistDraft?.status === "COMPLETED" && (
              <button
                type="button"
                onClick={() => router.push(`/projects/${projectId}/checklist/result`)}
                className="border px-4 py-2 text-sm transition-colors"
                style={{ borderColor: 'var(--line)', color: 'var(--text-2)' }}
              >
                View Results
              </button>
            )}
            <button
              type="button"
              disabled={isGenerating || selectedIds.length === 0 || !document?.document_id}
              onClick={() => void handleGenerateChecklist()}
              className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium disabled:opacity-60"
              style={{ background: 'var(--invert)', color: 'var(--invert-fg)' }}
            >
              {isGenerating ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {isGenerating ? "Generating Checklist" : (checklistDraft ? "Regenerate Checklist" : "Generate Checklist")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
