"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Check,
  ExternalLink,
  FileText,
  LoaderCircle,
  Search,
  ShieldCheck,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { motion } from "framer-motion";

import {
  checklistDraftEventsUrl,
  createChecklistDraft,
  getUploadResult,
  listReferenceSources,
  type ChecklistDraftItem,
  type ChecklistDraftStatus,
  type ReferenceSource,
  type UploadJobStatus,
} from "@/lib/uploadApi";

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

function formatNumber(value: number | null | undefined) {
  if (value == null) return "—";
  return new Intl.NumberFormat().format(value);
}

function formatChecklistStage(stage: string | undefined) {
  if (!stage) return "Starting Checklist";
  return CHECKLIST_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

function groupChecksByCategory(checks: ChecklistDraftItem[]) {
  const groups = new Map<string, ChecklistDraftItem[]>();
  for (const check of checks) {
    const category = check.category || "Other";
    const existing = groups.get(category) || [];
    existing.push(check);
    groups.set(category, existing);
  }
  return Array.from(groups.entries());
}

function hasSocketError(payload: unknown): payload is { error?: string } {
  return !!payload && typeof payload === "object" && "error" in payload;
}

export default function AnalysisSetupPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params?.jobId;

  const [job, setJob] = useState<UploadJobStatus | null>(null);
  const [sources, setSources] = useState<ReferenceSource[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [draftJob, setDraftJob] = useState<ChecklistDraftStatus | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pingTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [jobResult, refs] = await Promise.all([getUploadResult(jobId), listReferenceSources()]);
        if (cancelled) return;
        setJob(jobResult);
        setSources(refs);
        setSelected(Object.fromEntries(refs.map((src) => [src.source_id, true])));
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load setup page data.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    return () => {
      if (pingTimerRef.current) window.clearInterval(pingTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const selectedIds = useMemo(
    () => sources.filter((src) => selected[src.source_id]).map((src) => src.source_id),
    [sources, selected],
  );

  const groupedChecks = useMemo(
    () => groupChecksByCategory(draftJob?.result?.checks || []),
    [draftJob?.result?.checks],
  );

  function closeSocket() {
    if (pingTimerRef.current) {
      window.clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }

  function connectChecklistSocket(draftId: string) {
    closeSocket();
    const ws = new WebSocket(checklistDraftEventsUrl(draftId));
    wsRef.current = ws;

    ws.onopen = () => {
      pingTimerRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 15000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ChecklistDraftStatus | { error?: string };
        if (hasSocketError(payload) && payload.error) {
          setError(payload.error);
          setGenerating(false);
          return;
        }
        const snapshot = payload as ChecklistDraftStatus;
        setDraftJob(snapshot);
        if (snapshot.status === "COMPLETED") {
          setGenerating(false);
          closeSocket();
        } else if (snapshot.status === "FAILED") {
          setGenerating(false);
          setError(snapshot.error_message || "Checklist generation failed.");
          closeSocket();
        }
      } catch {
        setError("Received invalid checklist job event.");
        setGenerating(false);
      }
    };

    ws.onerror = () => {
      setError("Checklist event stream disconnected.");
    };

    ws.onclose = () => {
      if (pingTimerRef.current) {
        window.clearInterval(pingTimerRef.current);
        pingTimerRef.current = null;
      }
    };
  }

  async function onGenerateChecklist() {
    if (!job?.document_id) return;
    if (!selectedIds.length) {
      setError("Select at least one reference source to continue.");
      return;
    }
    setGenerating(true);
    setError(null);
    setDraftJob(null);
    try {
      const res = await createChecklistDraft({
        document_id: job.document_id,
        selected_source_ids: selectedIds,
        user_instruction: instruction.trim() || null,
      });
      connectChecklistSocket(res.checklist_draft_id);
    } catch (e) {
      setGenerating(false);
      setError(e instanceof Error ? e.message : "Failed to start checklist generation.");
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[var(--background)] text-white">
      <div className="pointer-events-none fixed inset-0 z-0">
        <div className="absolute -top-[20%] left-[8%] w-[50vw] h-[50vw] bg-[radial-gradient(circle,rgba(99,102,241,0.12),transparent_62%)]" />
        <div className="absolute top-[8%] right-[8%] w-[46vw] h-[46vw] bg-[radial-gradient(circle,rgba(139,92,246,0.09),transparent_62%)]" />
        <div className="absolute bottom-[-10%] right-[15%] w-[55vw] h-[35vw] bg-[radial-gradient(circle,rgba(20,184,166,0.08),transparent_62%)]" />
      </div>

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-32">
        <div className="flex items-center justify-between gap-4 border-b border-white/10 pb-5">
          <Link href="/" className="inline-flex items-center gap-2 text-white/65 hover:text-white transition-colors text-sm">
            <ArrowLeft className="w-4 h-4" />
            Back
          </Link>
          <div className="text-xs uppercase tracking-[0.2em] text-white/35">Checklist Setup</div>
        </div>

        <div className="mt-8 grid gap-6">
          {loading && (
            <div className="border border-white/10 bg-white/[0.02] p-8 flex items-center gap-4">
              <LoaderCircle className="w-5 h-5 animate-spin text-white/75" />
              <span className="text-white/75">Loading document summary and reference sources...</span>
            </div>
          )}

          {error && (
            <div className="border border-red-300/20 bg-red-400/5 p-4 text-sm text-red-100/85">{error}</div>
          )}

          {!loading && job?.result && (
            <>
              <motion.section
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: "easeOut" }}
                className="border overflow-hidden"
                style={{
                  background: "rgba(8,8,26,0.9)",
                  borderColor: "rgba(99,102,241,0.18)",
                  boxShadow: "0 0 0 1px rgba(99,102,241,0.05), 0 25px 80px rgba(0,0,0,0.35)",
                }}
              >
                <div
                  className="h-px"
                  style={{
                    background:
                      "linear-gradient(90deg, transparent, rgba(99,102,241,0.55), rgba(139,92,246,0.55), rgba(20,184,166,0.35), transparent)",
                  }}
                />
                <div className="p-5 md:p-7">
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div>
                      <div className="text-xs uppercase tracking-[0.2em] text-white/35">Processed Document</div>
                      <h1
                        className="mt-2 text-2xl md:text-4xl font-semibold tracking-tight"
                        style={{
                          background:
                            "linear-gradient(135deg,#fff 0%,rgba(210,214,255,0.92) 45%,rgba(255,255,255,0.72) 100%)",
                          WebkitBackgroundClip: "text",
                          WebkitTextFillColor: "transparent",
                        }}
                      >
                        Generate Review Checklist
                      </h1>
                      <p className="mt-3 text-white/45 max-w-3xl">
                        Select the legal sources that should shape the checklist, then optionally steer the agent with custom instructions.
                      </p>
                    </div>
                    <div className="border border-white/10 bg-white/[0.02] px-4 py-3 text-sm min-w-[220px]">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Document</div>
                      <div className="mt-1 text-white/70 break-all">{job.document_id}</div>
                    </div>
                  </div>

                  <div className="mt-6 grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
                    <div className="border border-white/10 bg-white/[0.015] p-4">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Filename</div>
                      <div className="mt-2 text-sm text-white/85 break-words">{job.result.filename}</div>
                    </div>
                    <div className="border border-white/10 bg-white/[0.015] p-4">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Parser Route</div>
                      <div className="mt-2 text-sm text-white/85">{job.result.parser_route || "—"}</div>
                    </div>
                    <div className="border border-white/10 bg-white/[0.015] p-4">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Pages</div>
                      <div className="mt-2 text-sm text-white/85">{formatNumber(job.result.page_count)}</div>
                    </div>
                    <div className="border border-white/10 bg-white/[0.015] p-4">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Token Estimate</div>
                      <div className="mt-2 text-sm text-white/85">{formatNumber(job.result.token_count_estimate)}</div>
                    </div>
                  </div>
                </div>
              </motion.section>

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
                        <div className="mt-3 text-white/85 leading-snug min-h-[68px]">{src.title}</div>
                        <div className="mt-4 flex items-center justify-between gap-3">
                          <div className="text-xs text-white/35 truncate">{src.source_id}</div>
                          <a
                            href={src.url}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
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
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder='Example: "Emphasize subprocessors, audit rights, and breach notice language. If Article 28 obligations appear fragmented, still keep them separate in the checklist."'
                  className="w-full min-h-[140px] border border-white/10 bg-black/20 px-4 py-3 text-sm text-white/85 placeholder:text-white/25 outline-none focus:border-white/20 resize-y"
                />
              </section>

              {draftJob && (
                <section className="border p-5 md:p-7" style={{ background: "rgba(7,7,22,0.88)", borderColor: "rgba(255,255,255,0.08)" }}>
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div>
                      <div className="text-xs uppercase tracking-[0.18em] text-white/35">Checklist Generation</div>
                      <div className="mt-2 flex items-center gap-3">
                        {draftJob.status === "COMPLETED" ? (
                          <Sparkles className="w-5 h-5 text-emerald-300" />
                        ) : draftJob.status === "FAILED" ? (
                          <Search className="w-5 h-5 text-red-300" />
                        ) : (
                          <LoaderCircle className="w-5 h-5 animate-spin text-white/75" />
                        )}
                        <h2 className="text-xl text-white/90">{formatChecklistStage(draftJob.stage)}</h2>
                      </div>
                      <p className="mt-3 text-sm text-white/45 max-w-3xl">{draftJob.message || "Preparing your checklist."}</p>
                    </div>
                    <div className="border border-white/10 bg-white/[0.02] px-4 py-3 text-sm min-w-[220px]">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Draft Job</div>
                      <div className="mt-1 text-white/70 break-all">{draftJob.checklist_draft_id}</div>
                    </div>
                  </div>

                  <div className="mt-6 border border-white/10 bg-white/[0.02] p-4">
                    <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-white/35">
                      <span>Progress</span>
                      <span>{Math.max(0, Math.min(100, draftJob.progress_pct || 0))}%</span>
                    </div>
                    <div className="mt-3 h-[6px] bg-white/5 overflow-hidden">
                      <motion.div
                        initial={false}
                        animate={{ width: `${Math.max(2, Math.min(100, draftJob.progress_pct || 0))}%` }}
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

              {draftJob?.result && (
                <section className="border overflow-hidden" style={{ background: "rgba(8,8,26,0.9)", borderColor: "rgba(99,102,241,0.18)" }}>
                  <div
                    className="h-px"
                    style={{
                      background:
                        "linear-gradient(90deg, transparent, rgba(99,102,241,0.55), rgba(139,92,246,0.55), rgba(20,184,166,0.35), transparent)",
                    }}
                  />
                  <div className="p-5 md:p-7">
                    <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-white/35">Validated Structured Output</div>
                        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white/92">Checklist Draft Ready</h2>
                        <p className="mt-3 text-white/45 max-w-3xl">
                          Rendered from the final validated `ChecklistDraftOutput`. This draft is source-backed, DPA-aware, and ready for review.
                        </p>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="border border-white/10 bg-white/[0.015] p-4 min-w-[180px]">
                          <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Version</div>
                          <div className="mt-2 text-sm text-white/85">{draftJob.result.version}</div>
                        </div>
                        <div className="border border-white/10 bg-white/[0.015] p-4 min-w-[180px]">
                          <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Confidence</div>
                          <div className="mt-2 text-sm text-white/85">{Math.round(draftJob.result.meta.confidence * 100)}%</div>
                        </div>
                      </div>
                    </div>

                    {draftJob.result.meta.generation_summary && (
                      <div className="mt-6 border border-white/10 bg-white/[0.02] p-4 text-sm text-white/70">
                        {draftJob.result.meta.generation_summary}
                      </div>
                    )}

                    {!!draftJob.result.meta.open_questions.length && (
                      <div className="mt-6 border border-amber-300/20 bg-amber-300/5 p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-amber-100/60">Open Questions</div>
                        <div className="mt-3 grid gap-2">
                          {draftJob.result.meta.open_questions.map((question) => (
                            <div key={question} className="text-sm text-amber-50/85">
                              {question}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="mt-8 grid gap-8">
                      {groupedChecks.map(([category, checks]) => (
                        <div key={category}>
                          <div className="text-xs uppercase tracking-[0.2em] text-white/35">{category}</div>
                          <div className="mt-4 grid gap-4">
                            {checks.map((check) => (
                              <div key={check.check_id} className="border border-white/10 bg-white/[0.015] p-4 md:p-5">
                                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                                  <div>
                                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">{check.check_id}</div>
                                    <h3 className="mt-2 text-lg text-white/90">{check.title}</h3>
                                  </div>
                                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]">
                                    <span className="border border-white/10 px-2 py-1 text-white/55">{check.severity}</span>
                                    <span className="border border-white/10 px-2 py-1 text-white/55">{check.required ? "Required" : "Optional"}</span>
                                  </div>
                                </div>

                                <div className="mt-4 grid lg:grid-cols-2 gap-4">
                                  <div className="border border-white/10 bg-black/15 p-4">
                                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Evidence Hint</div>
                                    <div className="mt-2 text-sm text-white/80">{check.evidence_hint}</div>
                                  </div>
                                  <div className="border border-white/10 bg-black/15 p-4">
                                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Draft Rationale</div>
                                    <div className="mt-2 text-sm text-white/80">{check.draft_rationale}</div>
                                  </div>
                                </div>

                                <div className="mt-4 grid lg:grid-cols-3 gap-4">
                                  <div className="border border-white/10 bg-black/15 p-4">
                                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Legal Basis</div>
                                    <div className="mt-3 grid gap-2">
                                      {check.legal_basis.map((item) => (
                                        <div key={item} className="text-sm text-white/75">
                                          {item}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                  <div className="border border-white/10 bg-black/15 p-4">
                                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Pass Criteria</div>
                                    <div className="mt-3 grid gap-2">
                                      {check.pass_criteria.map((item) => (
                                        <div key={item} className="text-sm text-white/75">
                                          {item}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                  <div className="border border-white/10 bg-black/15 p-4">
                                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Fail Criteria</div>
                                    <div className="mt-3 grid gap-2">
                                      {check.fail_criteria.map((item) => (
                                        <div key={item} className="text-sm text-white/75">
                                          {item}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                </div>

                                <div className="mt-4 border border-white/10 bg-black/15 p-4">
                                  <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Source Support</div>
                                  <div className="mt-3 grid gap-3">
                                    {check.sources.map((source) => (
                                      <div key={`${source.authority}-${source.source_ref}`} className="border border-white/10 bg-white/[0.02] p-3">
                                        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                                          <div>
                                            <div className="text-sm text-white/82">{source.authority}</div>
                                            <div className="text-xs text-white/40 mt-1">{source.source_ref}</div>
                                          </div>
                                          <a
                                            href={source.source_url}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="inline-flex items-center gap-1 text-xs text-white/60 hover:text-white transition-colors"
                                          >
                                            Open Source <ExternalLink className="w-3 h-3" />
                                          </a>
                                        </div>
                                        <div className="mt-3 text-sm text-white/72 leading-relaxed">{source.source_excerpt}</div>
                                        {source.interpretation_notes && (
                                          <div className="mt-3 text-xs text-white/45">{source.interpretation_notes}</div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </div>

      {!loading && (
        <div className="fixed bottom-0 inset-x-0 z-20 border-t border-white/10 bg-[rgba(6,6,16,0.88)] backdrop-blur-xl">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div className="flex items-center gap-3 text-sm">
              <FileText className="w-4 h-4 text-white/60" />
              <span className="text-white/75">
                <span className="text-white">{selectedIds.length}</span> of <span className="text-white">{sources.length}</span> references selected
              </span>
            </div>

            <div className="flex items-center gap-3">
              <Link href="/" className="border border-white/10 px-4 py-2 text-sm text-white/75 hover:bg-white/5 transition-colors">
                Back
              </Link>
              <button
                type="button"
                disabled={generating || selectedIds.length === 0 || !job?.document_id}
                onClick={onGenerateChecklist}
                className="inline-flex items-center gap-2 bg-white text-black px-5 py-2.5 text-sm font-medium disabled:opacity-60"
              >
                {generating ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                {generating ? "Generating Checklist" : "Generate Checklist"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
