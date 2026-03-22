"use client";

import { useRef, useState } from "react";
import { Upload, X, LoaderCircle } from "lucide-react";
import { motion } from "framer-motion";
import { createUpload } from "@/lib/uploadApi";
import { useProject } from "../ProjectProvider";

const MAX_UPLOAD_MB = 50;

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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const document = detail?.document;
  const parseJob = detail?.parse_job;

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
        <div className="border border-red-300/20 bg-red-400/5 px-4 py-3 text-sm text-red-100/85">
          {uploadError}
        </div>
      )}

      {!document && (
        <section className="border border-white/10 bg-[rgba(8,8,26,0.86)] p-8 md:p-12">
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
            className="mt-8 border border-dashed px-6 py-14 transition-all cursor-pointer"
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
            <div className="mx-auto flex max-w-2xl flex-col items-center text-center pointer-events-none">
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
        <>
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
            </section>
          )}
        </>
      )}
    </div>
  );
}
