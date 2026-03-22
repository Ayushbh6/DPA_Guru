"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Upload, X, LoaderCircle, ChevronDown } from "lucide-react";
import { motion } from "framer-motion";
import { createUpload, getDocumentParsedText } from "@/lib/uploadApi";
import { useProject } from "../ProjectProvider";

const MAX_UPLOAD_MB = 50;

const PARSE_STAGE_LABELS: Record<string, string> = {
  UPLOADING: "Uploading",
  VALIDATING: "Validating file",
  CLASSIFYING_PDF: "Classifying PDF",
  PARSING_MISTRAL_OCR: "Extracting text",
  COUNTING_TOKENS: "Estimating tokens",
  PERSISTING_RESULTS: "Saving artifacts",
  READY_FOR_REFERENCE_SELECTION: "Ready for checklist generation",
  FAILED: "Failed",
};

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
  } = useProject();

  const [isDragging, setIsDragging] = useState(false);
  const [parsedText, setParsedText] = useState("");
  const [loadingParsedText, setLoadingParsedText] = useState(false);
  const [parsedTextError, setParsedTextError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const document = detail?.document;
  const parseJob = detail?.parse_job;

  useEffect(() => {
    let cancelled = false;

    async function loadParsedText() {
      if (!document?.document_id || document.parse_status !== "COMPLETED") {
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
        const response = await getDocumentParsedText(document.document_id);
        if (!cancelled) {
          setParsedText(response.text);
        }
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
  }, [document?.document_id, document?.parse_status]);

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

  return (
    <div className="grid gap-6">
      {uploadError && document && (
        <div className="border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {uploadError}
        </div>
      )}

      {!document && (
        <section className="p-8 md:p-12" style={{ border: '1px solid var(--line)', background: 'var(--bg-1)' }}>
          <div className="max-w-3xl">
            <div className="text-[11px] uppercase tracking-[0.22em]" style={{ color: 'var(--text-3)' }}>Empty Project</div>
            <h2 className="mt-4 text-4xl font-semibold tracking-tight md:text-5xl" style={{ color: 'var(--text)' }}>
              Upload the DPA that this analysis session will own.
            </h2>
            <p className="mt-4 max-w-2xl text-base leading-7" style={{ color: 'var(--text-3)' }}>
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
            className="mt-8 border border-dashed px-6 py-14 transition-all cursor-pointer"
            style={{
              borderColor: isDragging ? 'var(--accent)' : 'var(--line-2)',
              background: isDragging ? 'color-mix(in srgb, var(--accent) 5%, transparent)' : 'var(--bg-2)',
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
            <div className="mx-auto flex max-w-2xl flex-col items-center text-center pointer-events-none">
              <div className="flex h-16 w-16 items-center justify-center" style={{ border: '1px solid var(--line)', background: 'var(--bg-2)' }}>
                <Upload className="h-7 w-7" style={{ color: 'var(--text-2)' }} />
              </div>
              <div className="mt-6 text-xl font-medium" style={{ color: 'var(--text)' }}>Drop a single DPA here or click to select a file</div>
              <div className="mt-3 text-sm" style={{ color: 'var(--text-3)' }}>PDF or DOCX • Single file • Max {MAX_UPLOAD_MB}MB</div>
            </div>
          </div>

          {uploadError && <div className="mt-4 border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">{uploadError}</div>}
        </section>
      )}

      {document && (
        <>
          <section className="border overflow-hidden" style={{ background: 'var(--bg-1)', borderColor: 'var(--line)' }}>
            <div className="h-px" style={{ background: 'var(--line-2)' }} />
            <div className="p-5 md:p-7">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.2em]" style={{ color: 'var(--text-3)' }}>Project Document</div>
                  <h2 className="mt-2 text-2xl font-semibold tracking-tight md:text-4xl" style={{ color: 'var(--text)' }}>{document.filename}</h2>
                  <p className="mt-3 max-w-3xl" style={{ color: 'var(--text-3)' }}>
                    The parsed DPA and every derived workflow artifact now belong to this project workspace.
                  </p>
                </div>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                  <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Parse Status</div>
                  <div className="mt-2 text-sm" style={{ color: 'var(--text)' }}>{formatStatus(document.parse_status || "UNKNOWN")}</div>
                </div>
                <div className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                  <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Pages</div>
                  <div className="mt-2 text-sm" style={{ color: 'var(--text)' }}>{formatNumber(document.page_count)}</div>
                </div>
                <div className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                  <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Token Estimate</div>
                  <div className="mt-2 text-sm" style={{ color: 'var(--text)' }}>{formatNumber(document.token_count_estimate)}</div>
                </div>
                <div className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                  <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Approx. Characters</div>
                  <div className="mt-2 text-sm" style={{ color: 'var(--text)' }}>
                    {loadingParsedText ? "Loading..." : formatNumber(approximateCharacters)}
                  </div>
                </div>
              </div>

              <details
                className="mt-5 overflow-hidden border"
                style={{ borderColor: 'var(--line)', background: 'var(--bg)' }}
              >
                <summary
                  className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm"
                  style={{ color: 'var(--text)', background: 'var(--bg)' }}
                >
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Parse Structure</div>
                    <div className="mt-1 text-sm" style={{ color: 'var(--text-2)' }}>
                      Expand to inspect the parsed markdown text used for downstream analysis.
                    </div>
                  </div>
                  <ChevronDown className="h-4 w-4 shrink-0" style={{ color: 'var(--text-3)' }} />
                </summary>
                <div style={{ borderTop: '1px solid var(--line)', background: 'var(--bg-2)' }}>
                  {loadingParsedText ? (
                    <div className="flex items-center gap-3 px-4 py-4 text-sm" style={{ color: 'var(--text-2)' }}>
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      Loading parsed structure...
                    </div>
                  ) : parsedTextError ? (
                    <div className="px-4 py-4 text-sm" style={{ color: '#fca5a5' }}>
                      {parsedTextError}
                    </div>
                  ) : (
                    <pre
                      className="max-h-[420px] overflow-auto px-4 py-4 text-xs leading-6 whitespace-pre-wrap"
                      style={{ color: 'var(--text-2)' }}
                    >
                      {parsedText || "No parsed markdown is available for this document yet."}
                    </pre>
                  )}
                </div>
              </details>
            </div>
          </section>

          {parseJob && parseJob.status !== "COMPLETED" && (
            <section className="border p-5 md:p-7" style={{ background: 'var(--bg-1)', borderColor: 'var(--line)' }}>
              <div>
                <div className="text-xs uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Document Processing</div>
                <div className="mt-2 flex items-center gap-3">
                  {parseJob.status === "FAILED" ? (
                    <X className="h-5 w-5 text-red-500" />
                  ) : (
                    <LoaderCircle className="h-5 w-5 animate-spin" style={{ color: 'var(--text-2)' }} />
                  )}
                  <h2 className="text-xl" style={{ color: 'var(--text)' }}>{formatParseStage(parseJob.stage)}</h2>
                </div>
                <p className="mt-3 max-w-3xl text-sm" style={{ color: 'var(--text-3)' }}>{parseJob.message || "Processing the uploaded DPA."}</p>
              </div>

              <div className="mt-6 p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                  <span>Progress</span>
                  <span>{Math.max(0, Math.min(100, parseJob.progress_pct || 0))}%</span>
                </div>
                <div className="mt-3 h-[4px] overflow-hidden" style={{ background: 'var(--bg-2)' }}>
                  <motion.div
                    initial={false}
                    animate={{ width: `${Math.max(2, Math.min(100, parseJob.progress_pct || 0))}%` }}
                    transition={{ duration: 0.35, ease: "easeOut" }}
                    className="h-full"
                    style={{ background: 'var(--accent)' }}
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
