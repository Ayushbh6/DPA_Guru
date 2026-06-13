"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Archive, BookOpen, FileText, Hash, LoaderCircle, RotateCcw, Star, Trash2, Type, Upload, X } from "lucide-react";
import { motion } from "framer-motion";
import {
  archiveVendorDocument,
  createVendorDocumentUpload,
  getDocumentParsedText,
  hardDeleteVendorDocument,
  markVendorDocumentPrimary,
  restoreVendorDocument,
  type ProjectDocumentSummary,
  type VendorDocumentType,
} from "@/lib/uploadApi";
import { useProject } from "../ProjectProvider";

const MAX_UPLOAD_MB = 50;

const DOCUMENT_TYPE_OPTIONS: Array<{ value: VendorDocumentType; label: string }> = [
  { value: "main_dpa", label: "Main DPA" },
  { value: "privacy_policy", label: "Privacy Policy" },
  { value: "security_toms", label: "Security/TOMs" },
  { value: "subprocessors", label: "Subprocessors" },
  { value: "data_transfer_terms", label: "Transfer Terms" },
  { value: "ai_terms", label: "AI Terms" },
  { value: "service_terms", label: "Service Terms" },
  { value: "security_certification", label: "Security Certification" },
  { value: "custom_agreement", label: "Custom Agreement" },
  { value: "other", label: "Other" },
];

const PARSE_STAGE_LABELS: Record<string, string> = {
  UPLOADING: "Uploading",
  VALIDATING: "Validating file",
  CLASSIFYING_PDF: "Classifying PDF",
  PARSING_MISTRAL_OCR: "Extracting text",
  COUNTING_TOKENS: "Estimating tokens",
  PERSISTING_RESULTS: "Saving artifacts",
  READY_FOR_REFERENCE_SELECTION: "Ready for criteria generation",
  FAILED: "Failed",
};

function formatParseStage(stage: string | undefined) {
  if (!stage) return "Processing";
  return PARSE_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

function parseStatusStyle(status: string): CSSProperties {
  if (status === "COMPLETED") return { color: "var(--status-compliant)", background: "var(--status-compliant-bg)" };
  if (status === "FAILED") return { color: "var(--status-noncompliant)", background: "var(--status-noncompliant-bg)" };
  return { color: "var(--status-partial)", background: "var(--status-partial-bg)" };
}

function formatStatus(status: string | null | undefined) {
  return (status || "UNKNOWN").replaceAll("_", " ");
}

function formatNumber(value: number | null | undefined) {
  if (value == null) return "-";
  return new Intl.NumberFormat().format(value);
}

function documentTypeLabel(value: string | null | undefined) {
  return DOCUMENT_TYPE_OPTIONS.find((item) => item.value === value)?.label || "Other";
}

export default function DashboardPage() {
  const {
    projectId,
    detail,
    uploadError,
    setUploadError,
    refreshProject,
    refreshSidebar,
    setDetail,
    connectUploadSocket,
    setWorkspaceError,
  } = useProject();

  const [isDragging, setIsDragging] = useState(false);
  const [documentType, setDocumentType] = useState<VendorDocumentType>("main_dpa");
  const [displayName, setDisplayName] = useState("");
  const [makePrimary, setMakePrimary] = useState(false);
  const [workingDocumentId, setWorkingDocumentId] = useState<string | null>(null);
  const [parsedText, setParsedText] = useState("");
  const [loadingParsedText, setLoadingParsedText] = useState(false);
  const [parsedTextError, setParsedTextError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const documents = useMemo(() => {
    const rows = detail?.documents?.length ? detail.documents : detail?.document ? [detail.document] : [];
    return rows;
  }, [detail?.document, detail?.documents]);
  const primaryDocument = documents.find((doc) => doc.is_primary) || detail?.document || documents[0] || null;
  const parseJob = detail?.parse_job;

  useEffect(() => {
    let cancelled = false;

    async function loadParsedText() {
      if (!primaryDocument?.document_id || primaryDocument.parse_status !== "COMPLETED") {
        if (!cancelled) {
          setParsedText("");
          setParsedTextError(null);
          setLoadingParsedText(false);
        }
        return;
      }

      setLoadingParsedText(true);
      setParsedTextError(null);
      try {
        const response = await getDocumentParsedText(primaryDocument.document_id);
        if (!cancelled) setParsedText(response.text);
      } catch (error) {
        if (!cancelled) {
          setParsedText("");
          setParsedTextError(error instanceof Error ? error.message : "Failed to load parsed structure.");
        }
      } finally {
        if (!cancelled) setLoadingParsedText(false);
      }
    }

    void loadParsedText();
    return () => {
      cancelled = true;
    };
  }, [primaryDocument?.document_id, primaryDocument?.parse_status]);

  const approximateCharacters = useMemo(() => {
    if (!parsedText) return null;
    return parsedText.replace(/\s+/g, " ").trim().length;
  }, [parsedText]);

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

    try {
      const shouldMakePrimary = documentType === "main_dpa" && (makePrimary || !documents.some((doc) => doc.is_primary && doc.lifecycle_status === "active"));
      const bootstrap = await createVendorDocumentUpload(file, projectId, {
        document_type: documentType,
        display_name: displayName.trim() || null,
        make_primary: shouldMakePrimary,
      });
      const optimisticDocument: ProjectDocumentSummary = {
        document_id: bootstrap.document_id,
        filename: file.name,
        mime_type: file.type || (file.name.toLowerCase().endsWith(".pdf") ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        page_count: 0,
        document_type: documentType,
        display_name: displayName.trim() || null,
        is_primary: shouldMakePrimary,
        lifecycle_status: "active",
        active: true,
        parse_status: "QUEUED",
        uploaded_at: new Date().toISOString(),
      };
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              documents: [...(prev.documents || []), optimisticDocument],
              document: shouldMakePrimary || !prev.document ? optimisticDocument : prev.document,
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
      setDisplayName("");
      setMakePrimary(false);
      connectUploadSocket(bootstrap.job_id);
      void refreshProject(false);
      await refreshSidebar();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed.");
    }
  }

  async function runDocumentAction(documentId: string, action: () => Promise<ProjectDocumentSummary>) {
    setWorkingDocumentId(documentId);
    setWorkspaceError(null);
    try {
      await action();
      await Promise.all([refreshProject(false), refreshSidebar()]);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Document action failed.");
    } finally {
      setWorkingDocumentId(null);
    }
  }

  function replacementFor(document: ProjectDocumentSummary) {
    return documents.find(
      (candidate) =>
        candidate.document_id !== document.document_id &&
        candidate.document_type === "main_dpa" &&
        candidate.lifecycle_status === "active",
    )?.document_id;
  }

  return (
    <div className="grid gap-4 md:gap-6">
      {uploadError && (
        <div className="border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {uploadError}
        </div>
      )}

      <section className="p-5 md:p-7" style={{ background: "var(--bg-1)" }}>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>Vendor Context</div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight" style={{ color: "var(--text)" }}>
              {detail?.vendor_context?.vendor_name || detail?.project.vendor_name || detail?.project.name}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7" style={{ color: "var(--text-2)" }}>
              {detail?.vendor_context?.intended_use_case || detail?.project.intended_use_case || "Complete the use case before running final review."}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3" style={{ background: "var(--bg-2)" }}>
              <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>Documents</div>
              <div className="mt-2 text-xl font-semibold" style={{ color: "var(--text)" }}>{documents.filter((doc) => doc.lifecycle_status === "active").length}</div>
            </div>
            <div className="p-3" style={{ background: "var(--bg-2)" }}>
              <div className="text-[11px] uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>Criticality</div>
              <div className="mt-2 text-sm font-semibold capitalize" style={{ color: "var(--text)" }}>{detail?.vendor_context?.business_criticality || "Incomplete"}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="p-5 md:p-7" style={{ background: "var(--bg-1)" }}>
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <div className="text-[11px] uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>Document Manager</div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight" style={{ color: "var(--text)" }}>Upload primary and supporting review documents.</h2>
            <p className="mt-3 text-sm leading-7" style={{ color: "var(--text-2)" }}>
              Checker reviews all active parsed documents. One active Main DPA must be marked primary before final review.
            </p>
          </div>
          <div className="w-full max-w-xl">
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr]">
              <select
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value as VendorDocumentType)}
                className="px-3 py-2.5 text-sm outline-none"
                style={{ border: "1px solid var(--line)", background: "var(--bg-2)", color: "var(--text)" }}
              >
                {DOCUMENT_TYPE_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Display name"
                className="px-3 py-2.5 text-sm outline-none"
                style={{ border: "1px solid var(--line)", background: "var(--bg-2)", color: "var(--text)" }}
              />
            </div>
            {documentType === "main_dpa" && (
              <label className="mt-3 flex items-center gap-3 text-sm" style={{ color: "var(--text-2)" }}>
                <input type="checkbox" checked={makePrimary} onChange={(event) => setMakePrimary(event.target.checked)} />
                Make primary DPA
              </label>
            )}
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
            <button
              type="button"
              className="mt-4 flex w-full items-center justify-center gap-3 border border-dashed px-4 py-7 text-sm transition-all"
              style={{
                borderColor: isDragging ? "var(--accent)" : "var(--line-2)",
                background: isDragging ? "color-mix(in srgb, var(--accent) 5%, transparent)" : "var(--bg-2)",
                color: "var(--text-2)",
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
              <Upload className="h-5 w-5" />
              <span>Drop PDF/DOCX or click to upload</span>
            </button>
          </div>
        </div>

        <div className="mt-6 grid gap-3">
          {documents.length ? documents.map((document) => {
            const isWorking = workingDocumentId === document.document_id;
            const replacementId = replacementFor(document);
            return (
              <div key={document.document_id} className="border p-4" style={{ borderColor: "var(--line)", background: "var(--bg-2)" }}>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="break-words text-base font-medium" style={{ color: "var(--text)" }}>{document.display_name || document.filename}</h3>
                      {document.is_primary && <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]" style={{ background: "var(--status-compliant-bg)", color: "var(--status-compliant)" }}><Star className="h-3 w-3" />Primary</span>}
                      <span className="px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]" style={{ background: "var(--bg)", color: "var(--text-3)" }}>{documentTypeLabel(document.document_type)}</span>
                      <span className="px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]" style={parseStatusStyle(document.parse_status || "UNKNOWN")}>{formatStatus(document.parse_status)}</span>
                      {document.lifecycle_status === "archived" && <span className="px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]" style={{ background: "var(--status-partial-bg)", color: "var(--status-partial)" }}>Archived</span>}
                    </div>
                    <div className="mt-2 text-xs" style={{ color: "var(--text-3)" }}>
                      {document.filename} · {formatNumber(document.page_count)} pages · {formatNumber(document.token_count_estimate)} tokens
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {document.lifecycle_status === "active" && document.document_type === "main_dpa" && !document.is_primary && (
                      <button type="button" disabled={isWorking} onClick={() => void runDocumentAction(document.document_id, () => markVendorDocumentPrimary(projectId, document.document_id))} className="inline-flex items-center gap-2 border px-3 py-2 text-xs" style={{ borderColor: "var(--line)", color: "var(--text-2)" }}>
                        <Star className="h-3.5 w-3.5" /> Make Primary
                      </button>
                    )}
                    {document.lifecycle_status === "archived" ? (
                      <button type="button" disabled={isWorking} onClick={() => void runDocumentAction(document.document_id, () => restoreVendorDocument(projectId, document.document_id))} className="inline-flex items-center gap-2 border px-3 py-2 text-xs" style={{ borderColor: "var(--line)", color: "var(--text-2)" }}>
                        <RotateCcw className="h-3.5 w-3.5" /> Restore
                      </button>
                    ) : (
                      <button type="button" disabled={isWorking} onClick={() => void runDocumentAction(document.document_id, () => archiveVendorDocument(projectId, document.document_id, document.is_primary ? replacementId : null))} className="inline-flex items-center gap-2 border px-3 py-2 text-xs" style={{ borderColor: "var(--line)", color: "var(--text-2)" }}>
                        <Archive className="h-3.5 w-3.5" /> Archive
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={isWorking}
                      onClick={() => {
                        if (confirm(`Hard delete "${document.display_name || document.filename}"? This removes stored document content immediately.`)) {
                          void runDocumentAction(document.document_id, () => hardDeleteVendorDocument(projectId, document.document_id, document.is_primary ? replacementId : null));
                        }
                      }}
                      className="inline-flex items-center gap-2 border px-3 py-2 text-xs text-red-400"
                      style={{ borderColor: "rgba(248,113,113,0.35)" }}
                    >
                      {isWorking ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />} Delete
                    </button>
                  </div>
                </div>
              </div>
            );
          }) : (
            <div className="border border-dashed px-4 py-8 text-sm" style={{ borderColor: "var(--line)", color: "var(--text-3)" }}>
              No documents uploaded yet.
            </div>
          )}
        </div>
      </section>

      {primaryDocument && (
        <>
          <section className="overflow-hidden" style={{ background: "var(--bg-1)" }}>
            <div className="p-4 md:p-6">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>Primary DPA</div>
                  <h2 className="mt-2 break-words text-xl font-semibold tracking-tight md:text-2xl" style={{ color: "var(--text)" }}>{primaryDocument.display_name || primaryDocument.filename}</h2>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
                <div className="p-3 md:p-4" style={{ background: "var(--bg-2)" }}>
                  <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>
                    <FileText className="h-3.5 w-3.5" /> Parse Status
                  </div>
                  <div className="mt-2">
                    <span className="inline-flex items-center border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em]" style={parseStatusStyle(primaryDocument.parse_status || "UNKNOWN")}>
                      {formatStatus(primaryDocument.parse_status)}
                    </span>
                  </div>
                </div>
                <div className="p-3 md:p-4" style={{ background: "var(--bg-2)" }}>
                  <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>
                    <BookOpen className="h-3.5 w-3.5" /> Pages
                  </div>
                  <div className="mt-2 text-base font-semibold md:text-lg" style={{ color: "var(--text)" }}>{formatNumber(primaryDocument.page_count)}</div>
                </div>
                <div className="p-3 md:p-4" style={{ background: "var(--bg-2)" }}>
                  <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>
                    <Hash className="h-3.5 w-3.5" /> Token Estimate
                  </div>
                  <div className="mt-2 text-base font-semibold md:text-lg" style={{ color: "var(--text)" }}>{formatNumber(primaryDocument.token_count_estimate)}</div>
                </div>
                <div className="p-3 md:p-4" style={{ background: "var(--bg-2)" }}>
                  <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>
                    <Type className="h-3.5 w-3.5" /> Characters
                  </div>
                  <div className="mt-2 text-base font-semibold md:text-lg" style={{ color: "var(--text)" }}>
                    {loadingParsedText ? "Loading..." : formatNumber(approximateCharacters)}
                  </div>
                </div>
              </div>

              <details className="mt-5 overflow-hidden border" style={{ borderColor: "var(--line)", background: "var(--bg)" }}>
                <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm" style={{ color: "var(--text)", background: "var(--bg)" }}>
                  Parsed primary DPA text
                </summary>
                <div style={{ borderTop: "1px solid var(--line)", background: "var(--bg-2)" }}>
                  {loadingParsedText ? (
                    <div className="flex items-center gap-3 px-4 py-4 text-sm" style={{ color: "var(--text-2)" }}>
                      <LoaderCircle className="h-4 w-4 animate-spin" /> Loading parsed structure...
                    </div>
                  ) : parsedTextError ? (
                    <div className="px-4 py-4 text-sm" style={{ color: "#fca5a5" }}>{parsedTextError}</div>
                  ) : (
                    <pre className="max-h-[50svh] overflow-auto overscroll-contain px-4 py-4 text-xs leading-6 whitespace-pre-wrap md:max-h-[420px]" style={{ color: "var(--text-2)" }}>
                      {parsedText || "No parsed markdown is available for this document yet."}
                    </pre>
                  )}
                </div>
              </details>
            </div>
          </section>

          {parseJob && parseJob.status !== "COMPLETED" && (
            <section className="border p-4 md:p-7" style={{ background: "var(--bg-1)", borderColor: "var(--line)" }}>
              <div>
                <div className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>Document Processing</div>
                <div className="mt-2 flex items-center gap-3">
                  {parseJob.status === "FAILED" ? <X className="h-5 w-5 text-red-500" /> : <LoaderCircle className="h-5 w-5 animate-spin" style={{ color: "var(--text-2)" }} />}
                  <h2 className="text-xl" style={{ color: "var(--text)" }}>{formatParseStage(parseJob.stage)}</h2>
                </div>
                <p className="mt-3 max-w-3xl text-sm" style={{ color: "var(--text-3)" }}>{parseJob.message || "Processing the uploaded document."}</p>
              </div>

              <div className="mt-6 p-4" style={{ border: "1px solid var(--line)", background: "var(--bg)" }}>
                <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                  <span>Progress</span>
                  <span>{Math.max(0, Math.min(100, parseJob.progress_pct || 0))}%</span>
                </div>
                <div className="mt-3 h-[4px] overflow-hidden" style={{ background: "var(--bg-2)" }}>
                  <motion.div
                    initial={false}
                    animate={{ width: `${Math.max(2, Math.min(100, parseJob.progress_pct || 0))}%` }}
                    transition={{ duration: 0.35, ease: "easeOut" }}
                    className="h-full"
                    style={{ background: "var(--accent)" }}
                  />
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
