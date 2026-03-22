"use client";

import { useEffect, useMemo, useState } from "react";
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
  VALIDATING_OUTPUT: "Finalizing Checklist",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

function formatChecklistStage(stage: string | undefined) {
  if (!stage) return "Starting Checklist";
  return CHECKLIST_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

export default function SetupChecklistPage() {
  const router = useRouter();
  const {
    projectId,
    detail,
    sources,
    workspaceError,
    setWorkspaceError,
    setDetail,
    connectChecklistSocket,
  } = useProject();

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [instruction, setInstruction] = useState("");

  const document = detail?.document;
  const parseJob = detail?.parse_job;
  const checklistDraft = detail?.checklist_draft;

  const parseReady = document?.parse_status === "COMPLETED";
  const isGenerating = checklistDraft && !["COMPLETED", "FAILED"].includes(checklistDraft.status);

  useEffect(() => {
    if (sources.length > 0) {
      const preselected = checklistDraft?.selected_source_ids?.length
        ? checklistDraft.selected_source_ids
        : sources.map((src) => src.source_id);
      
      setSelected((prev) => {
        if (Object.keys(prev).length) return prev; // Keep user edits if already set
        return Object.fromEntries(sources.map((src) => [src.source_id, preselected.includes(src.source_id)]));
      });
      
      if (checklistDraft?.user_instruction && !instruction) {
        setInstruction(checklistDraft.user_instruction);
      }
    }
  }, [sources, checklistDraft]);

  const selectedIds = useMemo(
    () => sources.filter((src) => selected[src.source_id]).map((src) => src.source_id),
    [selected, sources],
  );

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
        user_instruction: instruction.trim() || null,
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
                user_instruction: instruction.trim() || null,
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
    try {
      const snapshot = await cancelChecklistDraft(checklistDraft.checklist_draft_id);
      setDetail((prev) => (prev ? { ...prev, checklist_draft: snapshot } : prev));
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to stop checklist generation.");
    }
  }

  if (!parseReady) {
    return (
      <div className="border border-white/10 bg-[rgba(8,8,26,0.86)] p-8">
        <h2 className="text-xl text-white/90">Document Not Ready</h2>
        <p className="mt-2 text-white/50">Please upload a document and wait for parsing to complete before setting up the checklist.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 pb-6">
      <section className="border p-5 md:p-7" style={{ background: "rgba(7,7,22,0.88)", borderColor: "rgba(255,255,255,0.08)" }}>
        <div className="flex items-center justify-between gap-4 mb-5">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-white/70" />
            <div>
              <div className="text-sm md:text-base text-white/85 font-medium">Regulatory Reference Corpus</div>
              <div className="text-xs md:text-sm text-white/40">Only the selected sources may define the legal obligations in the checklist.</div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSelected(Object.fromEntries(sources.map((s) => [s.source_id, true])))}
            className="text-xs uppercase tracking-[0.16em] border border-white/10 px-3 py-2 text-white/70 hover:bg-white/5 transition-colors"
          >
            Select All
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sources.map((src) => {
            const checked = Boolean(selected[src.source_id]);
            return (
              <button
                type="button"
                key={src.source_id}
                onClick={() => setSelected((prev) => ({ ...prev, [src.source_id]: !prev[src.source_id] }))}
                className="relative text-left border p-4 transition-all duration-200 group"
                style={{
                  borderColor: checked ? "rgba(99,102,241,0.35)" : "rgba(255,255,255,0.08)",
                  background: checked ? "rgba(99,102,241,0.06)" : "rgba(255,255,255,0.012)",
                  boxShadow: checked ? "inset 0 0 0 1px rgba(99,102,241,0.12)" : "none",
                }}
              >
                <div className="absolute inset-x-0 top-0 h-px opacity-70" style={{ background: checked ? "linear-gradient(90deg, transparent, rgba(99,102,241,0.55), rgba(20,184,166,0.3), transparent)" : "transparent" }} />
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-5 h-5 border flex items-center justify-center"
                      style={{
                        borderColor: checked ? "rgba(99,102,241,0.5)" : "rgba(255,255,255,0.15)",
                        background: checked ? "rgba(99,102,241,0.22)" : "transparent",
                      }}
                    >
                      {checked && <Check className="w-3.5 h-3.5 text-white" />}
                    </div>
                    <span className="text-[10px] uppercase tracking-[0.16em] text-white/35">{src.authority}</span>
                  </div>
                  <span className="text-[10px] uppercase tracking-[0.16em] border border-white/10 px-2 py-1 text-white/55">
                    {src.kind}
                  </span>
                </div>
                <div className="mt-3 min-h-[68px] leading-snug text-white/85">{src.title}</div>
                <div className="mt-4 flex items-center justify-between gap-3">
                  <div className="truncate text-xs text-white/35">{src.source_id}</div>
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex items-center gap-1 text-xs text-white/60 hover:text-white transition-colors"
                  >
                    Open <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <section className="border p-5 md:p-7" style={{ background: "rgba(7,7,22,0.88)", borderColor: "rgba(255,255,255,0.08)" }}>
        <div className="flex items-center gap-3 mb-4">
          <WandSparkles className="w-5 h-5 text-white/70" />
          <div>
            <div className="text-sm md:text-base text-white/85 font-medium">Optional Checklist Instructions</div>
            <div className="text-xs md:text-sm text-white/40">Strong preference only. The agent will not invent unsupported legal obligations.</div>
          </div>
        </div>
        <textarea
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder='Example: "Emphasize subprocessors, audit rights, and breach notice language. If Article 28 obligations appear fragmented, still keep them separate in the checklist."'
          className="w-full min-h-[140px] border border-white/10 bg-black/20 px-4 py-3 text-sm text-white/85 placeholder:text-white/25 outline-none focus:border-white/20 resize-y"
        />
      </section>

      {checklistDraft && (
        <section className="border p-5 md:p-7" style={{ background: "rgba(7,7,22,0.88)", borderColor: "rgba(255,255,255,0.08)" }}>
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-white/35">Checklist Generation</div>
              <div className="mt-2 flex items-center gap-3">
                {checklistDraft.status === "COMPLETED" ? (
                  <Sparkles className="w-5 h-5 text-emerald-300" />
                ) : checklistDraft.status === "FAILED" ? (
                  <X className="w-5 h-5 text-red-300" />
                ) : (
                  <LoaderCircle className="w-5 h-5 animate-spin text-white/75" />
                )}
                <h2 className="text-xl text-white/90">{formatChecklistStage(checklistDraft.stage)}</h2>
              </div>
              <p className="mt-3 max-w-3xl text-sm text-white/45">{checklistDraft.message || "Preparing your checklist."}</p>
            </div>
            <div className="border border-white/10 bg-white/[0.02] px-4 py-3 text-sm min-w-[220px]">
              <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Draft Job</div>
              <div className="mt-1 break-all text-white/70">{checklistDraft.checklist_draft_id}</div>
            </div>
          </div>

          <div className="mt-6 border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-white/35">
              <span>Progress</span>
              <span>{Math.max(0, Math.min(100, checklistDraft.progress_pct || 0))}%</span>
            </div>
            <div className="mt-3 h-[6px] bg-white/5 overflow-hidden">
              <motion.div
                initial={false}
                animate={{ width: `${Math.max(2, Math.min(100, checklistDraft.progress_pct || 0))}%` }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="h-full"
                style={{
                  background:
                    "linear-gradient(90deg, rgba(99,102,241,0.95), rgba(139,92,246,0.95), rgba(20,184,166,0.85))",
                  boxShadow: "0 0 22px rgba(99,102,241,0.45)",
                }}
              />
            </div>
          </div>
        </section>
      )}

      {/* Action Bar */}
      <div className="sticky bottom-0 z-20 -mx-5 mt-4 border-t border-white/10 bg-[rgba(6,6,16,0.96)] p-5 backdrop-blur-xl md:-mx-8 md:px-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3 text-sm">
            <FileText className="w-4 h-4 text-white/60" />
            <span className="text-white/75">
              <span className="text-white">{selectedIds.length}</span> of <span className="text-white">{sources.length}</span> references selected
            </span>
          </div>

          <div className="flex items-center gap-3">
            {isGenerating && checklistDraft?.checklist_draft_id && (
              <button
                type="button"
                onClick={() => void handlePauseChecklist()}
                className="border border-white/10 px-4 py-2 text-sm text-white/75 transition-colors hover:bg-white/5"
              >
                Pause AI
              </button>
            )}
            {checklistDraft?.status === "COMPLETED" && (
              <button
                type="button"
                onClick={() => router.push(`/projects/${projectId}/checklist/result`)}
                className="border border-white/10 px-4 py-2 text-sm text-white/75 hover:bg-white/5 transition-colors"
              >
                View Results
              </button>
            )}
            <button
              type="button"
              disabled={isGenerating || selectedIds.length === 0 || !document?.document_id}
              onClick={() => void handleGenerateChecklist()}
              className="inline-flex items-center gap-2 bg-white px-5 py-2.5 text-sm font-medium text-black disabled:opacity-60"
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
