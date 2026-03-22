"use client";

import Link from "next/link";
import { startTransition, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Check,
  ExternalLink,
  FileText,
  FolderPlus,
  LoaderCircle,
  PencilLine,
  Save,
  ShieldCheck,
  Sparkles,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import { motion } from "framer-motion";

import {
  checklistDraftEventsUrl,
  createChecklistDraft,
  createProject,
  createUpload,
  getProject,
  listProjects,
  listReferenceSources,
  renameProject,
  type ChecklistDraftItem,
  type ChecklistDraftStatus,
  type ProjectDetail,
  type ProjectSummary,
  type ReferenceSource,
  type UploadJobStatus,
  uploadEventsUrl,
} from "@/lib/uploadApi";

const MAX_UPLOAD_MB = 50;

const CHECKLIST_STAGE_LABELS: Record<string, string> = {
  QUEUED: "Queued",
  RETRIEVING_KB: "Retrieving Selected Sources",
  EXPANDING_SOURCE_CONTEXT: "Expanding Source Context",
  INSPECTING_DPA: "Inspecting Parsed DPA",
  DRAFTING_CHECKLIST: "Drafting Checklist",
  VALIDATING_OUTPUT: "Validating Structured Output",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

const PARSE_STAGE_LABELS: Record<string, string> = {
  UPLOADING: "Uploading",
  VALIDATING: "Validating file",
  CLASSIFYING_PDF: "Classifying PDF",
  PARSING_MISTRAL_OCR: "Parsing with Mistral OCR",
  COUNTING_TOKENS: "Estimating tokens",
  PERSISTING_RESULTS: "Saving artifacts",
  READY_FOR_REFERENCE_SELECTION: "Ready for checklist generation",
  FAILED: "Failed",
};

function formatChecklistStage(stage: string | undefined) {
  if (!stage) return "Generating";
  return CHECKLIST_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

function formatParseStage(stage: string | undefined) {
  if (!stage) return "Processing";
  return PARSE_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

function formatStatus(status: string) {
  return status.replaceAll("_", " ");
}

function formatNumber(value: number | null | undefined) {
  if (value == null) return "—";
  return new Intl.NumberFormat().format(value);
}

function formatRelativeDate(value: string) {
  const date = new Date(value);
  const diffHours = Math.round((Date.now() - date.getTime()) / (1000 * 60 * 60));
  if (diffHours < 1) return "Just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
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

function SidebarProjectItem({
  project,
  active,
}: {
  project: ProjectSummary;
  active: boolean;
}) {
  return (
    <Link
      href={`/projects/${project.project_id}`}
      className="block border px-4 py-3 transition-colors"
      style={{
        borderColor: active ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.08)",
        background: active ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.02)",
      }}
    >
      <div className="truncate text-sm font-medium text-white/88">{project.name}</div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] uppercase tracking-[0.16em] text-white/38">
        <span>{formatStatus(project.status)}</span>
        <span>{formatRelativeDate(project.last_activity_at)}</span>
      </div>
      {project.document_filename && <div className="mt-2 truncate text-xs text-white/48">{project.document_filename}</div>}
    </Link>
  );
}

function ChecklistResultSection({ draftJob }: { draftJob: ChecklistDraftStatus }) {
  const groupedChecks = useMemo(() => groupChecksByCategory(draftJob.result?.checks || []), [draftJob.result?.checks]);

  if (!draftJob.result) return null;

  return (
    <section className="border overflow-hidden" style={{ background: "rgba(8,8,26,0.92)", borderColor: "rgba(99,102,241,0.18)" }}>
      <div
        className="h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(99,102,241,0.55), rgba(139,92,246,0.55), rgba(20,184,166,0.35), transparent)",
        }}
      />
      <div className="p-5 md:p-7">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-white/35">Validated Structured Output</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white/92">Checklist Draft Ready</h2>
            <p className="mt-3 max-w-3xl text-white/45">
              This project now has a source-backed, DPA-aware checklist draft. The next step is editing and approval before final review.
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
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">{check.check_id}</div>
                        <h3 className="mt-2 text-lg text-white/90">{check.title}</h3>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]">
                        <span className="border border-white/10 px-2 py-1 text-white/55">{check.severity}</span>
                        <span className="border border-white/10 px-2 py-1 text-white/55">{check.required ? "Required" : "Optional"}</span>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                      <div className="border border-white/10 bg-black/15 p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Evidence Hint</div>
                        <div className="mt-2 text-sm text-white/80">{check.evidence_hint}</div>
                      </div>
                      <div className="border border-white/10 bg-black/15 p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Draft Rationale</div>
                        <div className="mt-2 text-sm text-white/80">{check.draft_rationale}</div>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-4 lg:grid-cols-3">
                      <div className="border border-white/10 bg-black/15 p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Legal Basis</div>
                        <div className="mt-3 grid gap-2">
                          {check.legal_basis.map((item) => (
                            <div key={item} className="text-sm text-white/75">{item}</div>
                          ))}
                        </div>
                      </div>
                      <div className="border border-white/10 bg-black/15 p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Pass Criteria</div>
                        <div className="mt-3 grid gap-2">
                          {check.pass_criteria.map((item) => (
                            <div key={item} className="text-sm text-white/75">{item}</div>
                          ))}
                        </div>
                      </div>
                      <div className="border border-white/10 bg-black/15 p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Fail Criteria</div>
                        <div className="mt-3 grid gap-2">
                          {check.fail_criteria.map((item) => (
                            <div key={item} className="text-sm text-white/75">{item}</div>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 border border-white/10 bg-black/15 p-4">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Source Support</div>
                      <div className="mt-3 grid gap-3">
                        {check.sources.map((source) => (
                          <div key={`${source.authority}-${source.source_ref}`} className="border border-white/10 bg-white/[0.02] p-3">
                            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                              <div>
                                <div className="text-sm text-white/82">{source.authority}</div>
                                <div className="mt-1 text-xs text-white/40">{source.source_ref}</div>
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
                            <div className="mt-3 text-sm leading-relaxed text-white/72">{source.source_excerpt}</div>
                            {source.interpretation_notes && <div className="mt-3 text-xs text-white/45">{source.interpretation_notes}</div>}
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
  );
}

export default function ProjectWorkspacePage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  const projectId = params?.projectId;

  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [sources, setSources] = useState<ReferenceSource[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(true);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameMode, setRenameMode] = useState(false);
  const [renaming, setRenaming] = useState(false);

  const uploadSocketRef = useRef<WebSocket | null>(null);
  const uploadPingRef = useRef<number | null>(null);
  const checklistSocketRef = useRef<WebSocket | null>(null);
  const checklistPingRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedIds = useMemo(
    () => sources.filter((src) => selected[src.source_id]).map((src) => src.source_id),
    [selected, sources],
  );

  const currentProject = detail?.project;
  const document = detail?.document;
  const parseJob = detail?.parse_job;
  const checklistDraft = detail?.checklist_draft;
  const parseReady = document?.parse_status === "COMPLETED";
  const pollProjectRefresh = useEffectEvent(() => {
    void refreshProject(false);
  });

  async function refreshSidebar() {
    const items = await listProjects();
    setProjects(items);
  }

  async function refreshProject(showError = true) {
    if (!projectId) return;
    try {
      const result = await getProject(projectId);
      setDetail(result);
      setRenameValue(result.project.name);
      if (result.checklist_draft?.selected_source_ids?.length && sources.length) {
        setSelected((prev) => {
          if (Object.keys(prev).length) return prev;
          return Object.fromEntries(sources.map((src) => [src.source_id, result.checklist_draft?.selected_source_ids.includes(src.source_id)]));
        });
      }
    } catch (error) {
      if (showError) {
        setWorkspaceError(error instanceof Error ? error.message : "Failed to load project.");
      }
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!projectId) return;
      setLoading(true);
      setWorkspaceError(null);
      try {
        const [projectDetail, projectList, referenceSources] = await Promise.all([
          getProject(projectId),
          listProjects(),
          listReferenceSources(),
        ]);
        if (cancelled) return;
        setDetail(projectDetail);
        setProjects(projectList);
        setSources(referenceSources);
        setRenameValue(projectDetail.project.name);
        const preselected = projectDetail.checklist_draft?.selected_source_ids?.length
          ? projectDetail.checklist_draft.selected_source_ids
          : referenceSources.map((src) => src.source_id);
        setSelected(Object.fromEntries(referenceSources.map((src) => [src.source_id, preselected.includes(src.source_id)])));
        setInstruction(projectDetail.checklist_draft?.user_instruction || "");
      } catch (error) {
        if (!cancelled) setWorkspaceError(error instanceof Error ? error.message : "Failed to load project workspace.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    return () => {
      if (uploadPingRef.current) window.clearInterval(uploadPingRef.current);
      uploadSocketRef.current?.close();
      if (checklistPingRef.current) window.clearInterval(checklistPingRef.current);
      checklistSocketRef.current?.close();
    };
  }, []);

  useEffect(() => {
    if (!parseJob && !checklistDraft) return;
    const parseActive = parseJob && !["COMPLETED", "FAILED"].includes(parseJob.status);
    const checklistActive = checklistDraft && !["COMPLETED", "FAILED"].includes(checklistDraft.status);
    if (!parseActive && !checklistActive) return;

    const timer = window.setInterval(() => {
      pollProjectRefresh();
    }, 2000);

    return () => {
      window.clearInterval(timer);
    };
  }, [parseJob, checklistDraft]);

  useEffect(() => {
    if (parseJob?.status === "FAILED" && parseJob.error_message) {
      setUploadError(parseJob.error_message);
    }
  }, [parseJob?.status, parseJob?.error_message]);

  useEffect(() => {
    if (checklistDraft?.status === "FAILED" && checklistDraft.error_message) {
      setWorkspaceError(checklistDraft.error_message);
    }
  }, [checklistDraft?.status, checklistDraft?.error_message]);

  function closeUploadSocket() {
    if (uploadPingRef.current) {
      window.clearInterval(uploadPingRef.current);
      uploadPingRef.current = null;
    }
    if (uploadSocketRef.current) {
      uploadSocketRef.current.close();
      uploadSocketRef.current = null;
    }
  }

  function closeChecklistSocket() {
    if (checklistPingRef.current) {
      window.clearInterval(checklistPingRef.current);
      checklistPingRef.current = null;
    }
    if (checklistSocketRef.current) {
      checklistSocketRef.current.close();
      checklistSocketRef.current = null;
    }
  }

  function connectUploadSocket(jobId: string) {
    closeUploadSocket();
    const ws = new WebSocket(uploadEventsUrl(jobId));
    uploadSocketRef.current = ws;

    ws.onopen = () => {
      uploadPingRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 10000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as UploadJobStatus | { error?: string };
        if ("error" in payload && payload.error) {
          setUploadError(payload.error);
          return;
        }
        setDetail((prev) => (prev ? { ...prev, parse_job: payload } : prev));
        if (payload.status === "FAILED") {
          setUploadError(payload.error_message || "Document processing failed.");
        }
        if (payload.status === "COMPLETED" || payload.status === "FAILED") {
          closeUploadSocket();
          void Promise.all([refreshProject(false), refreshSidebar()]);
        }
      } catch {
        setUploadError("Received invalid upload event.");
      }
    };
  }

  function connectChecklistSocket(draftId: string) {
    closeChecklistSocket();
    const ws = new WebSocket(checklistDraftEventsUrl(draftId));
    checklistSocketRef.current = ws;

    ws.onopen = () => {
      checklistPingRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 15000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ChecklistDraftStatus | { error?: string };
        if ("error" in payload && payload.error) {
          setWorkspaceError(payload.error);
          setGenerating(false);
          return;
        }
        setDetail((prev) => (prev ? { ...prev, checklist_draft: payload } : prev));
        if (payload.status === "FAILED") {
          setWorkspaceError(payload.error_message || "Checklist generation failed.");
        }
        if (payload.status === "COMPLETED" || payload.status === "FAILED") {
          setGenerating(false);
          closeChecklistSocket();
          void Promise.all([refreshProject(false), refreshSidebar()]);
        }
      } catch {
        setWorkspaceError("Received invalid checklist event.");
        setGenerating(false);
      }
    };
  }

  function validateFile(file: File) {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["pdf", "docx"].includes(ext)) return "Only PDF and DOCX files are supported right now.";
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `File must be smaller than ${MAX_UPLOAD_MB}MB.`;
    return null;
  }

  async function handleFile(file: File) {
    if (!projectId) return;
    const validation = validateFile(file);
    if (validation) {
      setUploadError(validation);
      return;
    }
    setUploadError(null);
    setWorkspaceError(null);

    try {
      const bootstrap = await createUpload(file, projectId);
      await refreshProject(false);
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              parse_job: {
                job_id: bootstrap.job_id,
                document_id: bootstrap.document_id,
                project_id: bootstrap.project_id,
                status: "QUEUED",
                stage: "UPLOADING",
                progress_pct: 5,
                message: "Upload received. Queuing background processing.",
                file_type: file.name.endsWith(".pdf") ? "pdf" : "docx",
              },
            }
          : prev,
      );
      connectUploadSocket(bootstrap.job_id);
      await refreshSidebar();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed.");
    }
  }

  async function handleRename() {
    if (!projectId || !renameValue.trim()) return;
    setRenaming(true);
    try {
      const updated = await renameProject(projectId, renameValue);
      setDetail(updated);
      setRenameMode(false);
      await refreshSidebar();
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to rename project.");
    } finally {
      setRenaming(false);
    }
  }

  async function handleNewProject() {
    const project = await createProject();
    startTransition(() => {
      router.push(project.workspace_url || `/projects/${project.project_id}`);
    });
  }

  async function handleGenerateChecklist() {
    if (!document?.document_id) return;
    if (!selectedIds.length) {
      setWorkspaceError("Select at least one reference source to continue.");
      return;
    }
    setGenerating(true);
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
                message: "Checklist generation queued.",
                selected_source_ids: selectedIds,
                user_instruction: instruction.trim() || null,
              },
            }
          : prev,
      );
      connectChecklistSocket(res.checklist_draft_id);
    } catch (error) {
      setGenerating(false);
      setWorkspaceError(error instanceof Error ? error.message : "Failed to start checklist generation.");
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-[var(--background)] px-6 py-10 text-white">
        <div className="mx-auto flex min-h-[70vh] max-w-6xl items-center justify-center gap-3 border border-white/10 bg-white/[0.02]">
          <LoaderCircle className="h-5 w-5 animate-spin text-white/70" />
          <span className="text-white/70">Loading project workspace...</span>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#06060e_0%,#080815_52%,#06060d_100%)] text-white">
      <div className="grid min-h-screen lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="border-r border-white/10 bg-[rgba(5,5,14,0.96)] px-5 py-6">
          <div className="flex items-center gap-3 border-b border-white/8 pb-5">
            <div className="flex h-10 w-10 items-center justify-center border border-white/10 bg-white/[0.03] text-white/90">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-medium text-white/90">Merlin AI</div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-white/38">Project Workspace</div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void handleNewProject()}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 border border-white/12 bg-white px-4 py-3 text-sm font-medium text-black transition-colors hover:bg-white/90"
          >
            <FolderPlus className="h-4 w-4" />
            <span>New Analysis</span>
          </button>

          <div className="mt-8 flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-[0.22em] text-white/36">Projects</div>
            <Link href="/" className="text-xs text-white/48 hover:text-white/75">Home</Link>
          </div>

          <div className="mt-4 space-y-2">
            {projects.map((project) => (
              <SidebarProjectItem key={project.project_id} project={project} active={project.project_id === projectId} />
            ))}
          </div>
        </aside>

        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute -top-[16%] left-[8%] h-[32vw] w-[32vw] bg-[radial-gradient(circle,rgba(99,102,241,0.12),transparent_60%)]" />
            <div className="absolute right-[8%] top-[18%] h-[28vw] w-[28vw] bg-[radial-gradient(circle,rgba(20,184,166,0.08),transparent_62%)]" />
          </div>

          <div className="relative z-10 mx-auto max-w-7xl px-5 py-6 md:px-8 md:py-8">
            <div className="mb-5">
              <Link
                href="/"
                className="inline-flex items-center gap-2 text-sm text-white/50 transition-colors hover:text-white/85"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to Home
              </Link>
            </div>

            <header className="border border-white/10 bg-[rgba(8,8,24,0.86)] px-5 py-5 md:px-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="text-[11px] uppercase tracking-[0.22em] text-white/35">Analysis Session</div>
                  {!renameMode ? (
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      <h1 className="truncate text-3xl font-semibold tracking-tight text-white/95 md:text-4xl">{currentProject?.name}</h1>
                      <button
                        type="button"
                        onClick={() => setRenameMode(true)}
                        className="inline-flex items-center gap-2 text-sm text-white/52 transition-colors hover:text-white/82"
                      >
                        <PencilLine className="h-4 w-4" />
                        Rename
                      </button>
                    </div>
                  ) : (
                    <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                      <input
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        className="w-full border border-white/12 bg-black/25 px-4 py-3 text-white outline-none focus:border-white/25 sm:max-w-xl"
                      />
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => void handleRename()}
                          disabled={renaming || !renameValue.trim()}
                          className="inline-flex items-center gap-2 border border-white/10 bg-white px-4 py-3 text-sm font-medium text-black disabled:opacity-60"
                        >
                          {renaming ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRenameMode(false);
                            setRenameValue(currentProject?.name || "");
                          }}
                          className="inline-flex items-center gap-2 border border-white/10 px-4 py-3 text-sm text-white/72"
                        >
                          <X className="h-4 w-4" />
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                  <p className="mt-4 max-w-3xl text-sm leading-6 text-white/48 md:text-base">
                    One project owns the uploaded DPA, parsing job, checklist draft, and the later final review. Refresh-safe by default.
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="border border-white/10 bg-white/[0.02] px-4 py-4">
                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Project Status</div>
                    <div className="mt-2 text-sm text-white/85">{formatStatus(currentProject?.status || "EMPTY")}</div>
                  </div>
                  <div className="border border-white/10 bg-white/[0.02] px-4 py-4">
                    <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Last Activity</div>
                    <div className="mt-2 text-sm text-white/85">
                      {currentProject?.last_activity_at ? formatRelativeDate(currentProject.last_activity_at) : "Just now"}
                    </div>
                  </div>
                </div>
              </div>
            </header>

            {workspaceError && (
              <div className="mt-5 border border-red-300/20 bg-red-400/5 px-4 py-3 text-sm text-red-100/85">{workspaceError}</div>
            )}

            {uploadError && document && (
              <div className="mt-5 border border-red-300/20 bg-red-400/5 px-4 py-3 text-sm text-red-100/85">{uploadError}</div>
            )}

            {!document && (
              <section className="mt-6 border border-white/10 bg-[rgba(8,8,26,0.86)] p-8 md:p-12">
                <div className="max-w-3xl">
                  <div className="text-[11px] uppercase tracking-[0.22em] text-white/38">Empty Project</div>
                  <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white/95 md:text-5xl">
                    Upload the DPA that this analysis session will own.
                  </h2>
                  <p className="mt-4 max-w-2xl text-base leading-7 text-white/48">
                    This is now a saved workspace. Once a file is uploaded, parsing and checklist generation stay attached to this project.
                  </p>
                </div>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void handleFile(file);
                    event.target.value = "";
                  }}
                />

                <div
                  className="mt-8 border border-dashed px-6 py-14 transition-all"
                  style={{
                    borderColor: isDragging ? "rgba(99,102,241,0.6)" : "rgba(255,255,255,0.12)",
                    background: isDragging ? "rgba(99,102,241,0.08)" : "rgba(255,255,255,0.015)",
                  }}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragLeave={(event) => {
                    event.preventDefault();
                    setIsDragging(false);
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    setIsDragging(false);
                    const file = event.dataTransfer.files?.[0];
                    if (file) void handleFile(file);
                  }}
                >
                  <div className="mx-auto flex max-w-2xl flex-col items-center text-center">
                    <div className="flex h-16 w-16 items-center justify-center border border-white/10 bg-white/[0.03]">
                      <Upload className="h-7 w-7 text-white/68" />
                    </div>
                    <div className="mt-6 text-xl font-medium text-white/88">Drop a single DPA here or click to select a file</div>
                    <div className="mt-3 text-sm text-white/45">PDF or DOCX • Single file • Max {MAX_UPLOAD_MB}MB</div>
                  </div>
                </div>

                {uploadError && <div className="mt-4 border border-red-300/20 bg-red-400/5 px-4 py-3 text-sm text-red-100/85">{uploadError}</div>}
              </section>
            )}

            {document && (
              <div className="mt-6 grid gap-6">
                <section className="border overflow-hidden" style={{ background: "rgba(8,8,26,0.9)", borderColor: "rgba(99,102,241,0.18)" }}>
                  <div
                    className="h-px"
                    style={{
                      background:
                        "linear-gradient(90deg, transparent, rgba(99,102,241,0.55), rgba(139,92,246,0.55), rgba(20,184,166,0.35), transparent)",
                    }}
                  />
                  <div className="p-5 md:p-7">
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-white/35">Project Document</div>
                        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white/92 md:text-4xl">{document.filename}</h2>
                        <p className="mt-3 max-w-3xl text-white/45">
                          The parsed DPA and every derived workflow artifact now belong to this project workspace.
                        </p>
                      </div>
                      <div className="border border-white/10 bg-white/[0.02] px-4 py-3 text-sm min-w-[220px]">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Document</div>
                        <div className="mt-1 break-all text-white/70">{document.document_id}</div>
                      </div>
                    </div>

                    <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <div className="border border-white/10 bg-white/[0.015] p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Parse Status</div>
                        <div className="mt-2 text-sm text-white/85">{formatStatus(document.parse_status || "UNKNOWN")}</div>
                      </div>
                      <div className="border border-white/10 bg-white/[0.015] p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Pages</div>
                        <div className="mt-2 text-sm text-white/85">{formatNumber(document.page_count)}</div>
                      </div>
                      <div className="border border-white/10 bg-white/[0.015] p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Parser Route</div>
                        <div className="mt-2 text-sm text-white/85">{document.parser_route || "Pending"}</div>
                      </div>
                      <div className="border border-white/10 bg-white/[0.015] p-4">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Token Estimate</div>
                        <div className="mt-2 text-sm text-white/85">{formatNumber(document.token_count_estimate)}</div>
                      </div>
                    </div>
                  </div>
                </section>

                {parseJob && parseJob.status !== "COMPLETED" && (
                  <section className="border p-5 md:p-7" style={{ background: "rgba(7,7,22,0.88)", borderColor: "rgba(255,255,255,0.08)" }}>
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-[0.18em] text-white/35">Document Processing</div>
                        <div className="mt-2 flex items-center gap-3">
                          {parseJob.status === "FAILED" ? (
                            <X className="h-5 w-5 text-red-300" />
                          ) : (
                            <LoaderCircle className="h-5 w-5 animate-spin text-white/75" />
                          )}
                          <h2 className="text-xl text-white/90">{formatParseStage(parseJob.stage)}</h2>
                        </div>
                        <p className="mt-3 max-w-3xl text-sm text-white/45">{parseJob.message || "Processing the uploaded DPA."}</p>
                      </div>
                      <div className="border border-white/10 bg-white/[0.02] px-4 py-3 text-sm min-w-[220px]">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Upload Job</div>
                        <div className="mt-1 break-all text-white/70">{parseJob.job_id}</div>
                      </div>
                    </div>

                    <div className="mt-6 border border-white/10 bg-white/[0.02] p-4">
                      <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-white/35">
                        <span>Progress</span>
                        <span>{Math.max(0, Math.min(100, parseJob.progress_pct || 0))}%</span>
                      </div>
                      <div className="mt-3 h-[6px] bg-white/5 overflow-hidden">
                        <motion.div
                          initial={false}
                          animate={{ width: `${Math.max(2, Math.min(100, parseJob.progress_pct || 0))}%` }}
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

                    {checklistDraft.status === "FAILED" && checklistDraft.error_message && (
                      <div className="mt-4 border border-red-300/20 bg-red-400/5 p-4 text-sm text-red-100/85">
                        {checklistDraft.error_message}
                      </div>
                    )}
                  </section>
                )}

                {parseReady && (
                  <>
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
                            <p className="mt-3 max-w-3xl text-sm text-white/45">{checklistDraft.message || "Generating source-backed checklist draft."}</p>
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

                    {parseJob.status === "FAILED" && parseJob.error_message && (
                      <div className="mt-4 border border-red-300/20 bg-red-400/5 p-4 text-sm text-red-100/85">
                        {parseJob.error_message}
                      </div>
                    )}
                  </section>
                )}

                    {checklistDraft?.result && <ChecklistResultSection draftJob={checklistDraft} />}
                  </>
                )}
              </div>
            )}
          </div>
        </section>
      </div>

      {parseReady && (
        <div className="fixed bottom-0 inset-x-0 z-20 border-t border-white/10 bg-[rgba(6,6,16,0.88)] backdrop-blur-xl lg:left-[300px]">
          <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between md:px-8">
            <div className="flex items-center gap-3 text-sm">
              <FileText className="w-4 h-4 text-white/60" />
              <span className="text-white/75">
                <span className="text-white">{selectedIds.length}</span> of <span className="text-white">{sources.length}</span> references selected
              </span>
            </div>

            <div className="flex items-center gap-3">
              <Link href="/" className="border border-white/10 px-4 py-2 text-sm text-white/75 hover:bg-white/5 transition-colors">
                Back Home
              </Link>
              <button
                type="button"
                disabled={generating || selectedIds.length === 0 || !document?.document_id}
                onClick={() => void handleGenerateChecklist()}
                className="inline-flex items-center gap-2 bg-white px-5 py-2.5 text-sm font-medium text-black disabled:opacity-60"
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
