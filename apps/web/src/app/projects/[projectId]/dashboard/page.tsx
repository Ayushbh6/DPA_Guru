"use client";

import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { Archive, ChevronDown, LoaderCircle, RotateCcw, Star, Trash2, Upload, X } from "lucide-react";
import {
  CheckboxChip,
  CheckerPanel,
  CheckerSurface,
  FormGrid,
  MetricTile,
  SectionHeader,
  SelectField,
  StatusBadge,
  SwitchRow,
} from "@/components/checker-ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  archiveVendorDocument,
  createVendorDocumentUpload,
  getDocumentParsedText,
  hardDeleteVendorDocument,
  markVendorDocumentPrimary,
  restoreVendorDocument,
  updateVendorReview,
  type BusinessCriticality,
  type ProjectDocumentSummary,
  type VendorRegion,
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

const CONTEXT_REGION_OPTIONS: Array<{ value: VendorRegion; label: string }> = [
  { value: "US", label: "United States" },
  { value: "EU_EEA", label: "EU / EEA" },
  { value: "UK", label: "United Kingdom" },
  { value: "OTHER", label: "Other / global" },
  { value: "UNKNOWN", label: "Unknown" },
];

const CONTEXT_CRITICALITY_OPTIONS: BusinessCriticality[] = ["low", "medium", "high"];

type ReviewContextDraft = {
  vendor_name: string;
  intended_use_case: string;
  data_types: string;
  shares_personal_data: boolean;
  shares_customer_data: boolean;
  shares_employee_data: boolean;
  shares_sensitive_data: boolean;
  has_ai_features: boolean;
  business_criticality: BusinessCriticality;
  vendor_region: VendorRegion;
  processes_eu_personal_data: boolean;
  transfers_data_outside_eea: boolean;
};

type ReviewContextBooleanKey =
  | "shares_personal_data"
  | "shares_customer_data"
  | "shares_employee_data"
  | "shares_sensitive_data"
  | "has_ai_features";

const CONTEXT_BOOLEAN_FLAGS: Array<{ key: ReviewContextBooleanKey; label: string }> = [
  { key: "shares_personal_data", label: "Personal data" },
  { key: "shares_customer_data", label: "Customer" },
  { key: "shares_employee_data", label: "Employee" },
  { key: "shares_sensitive_data", label: "Sensitive" },
  { key: "has_ai_features", label: "AI" },
];

function contextDraftFromDetail(detail: ReturnType<typeof useProject>["detail"]): ReviewContextDraft {
  const context = detail?.vendor_context;
  return {
    vendor_name: context?.vendor_name || detail?.project.vendor_name || "",
    intended_use_case: context?.intended_use_case || detail?.project.intended_use_case || "",
    data_types: (context?.data_types || []).join(", "),
    shares_personal_data: context?.shares_personal_data ?? true,
    shares_customer_data: context?.shares_customer_data ?? false,
    shares_employee_data: context?.shares_employee_data ?? false,
    shares_sensitive_data: context?.shares_sensitive_data ?? false,
    has_ai_features: context?.has_ai_features ?? false,
    business_criticality: (context?.business_criticality || detail?.project.business_criticality || "medium") as BusinessCriticality,
    vendor_region: (context?.vendor_region || "UNKNOWN") as VendorRegion,
    processes_eu_personal_data: context?.processes_eu_personal_data ?? true,
    transfers_data_outside_eea: context?.transfers_data_outside_eea ?? false,
  };
}

function parseDataTypes(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

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
  const [contextDraft, setContextDraft] = useState<ReviewContextDraft>(() => contextDraftFromDetail(null));
  const [savingContext, setSavingContext] = useState(false);
  const [deleteDocument, setDeleteDocument] = useState<ProjectDocumentSummary | null>(null);
  const [parsedTextOpen, setParsedTextOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const documents = useMemo(() => {
    const rows = detail?.documents?.length ? detail.documents : detail?.document ? [detail.document] : [];
    return rows;
  }, [detail?.document, detail?.documents]);
  const primaryDocument = documents.find((doc) => doc.is_primary) || detail?.document || documents[0] || null;
  const parseJob = detail?.parse_job;
  const syncContextDraft = useEffectEvent(() => {
    setContextDraft(contextDraftFromDetail(detail));
  });

  useEffect(() => {
    syncContextDraft();
  }, [detail?.project.project_id, detail?.vendor_context]);

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

  const contextDataTypes = useMemo(() => parseDataTypes(contextDraft.data_types), [contextDraft.data_types]);
  const contextComplete = Boolean(
    contextDraft.vendor_name.trim() &&
      contextDraft.intended_use_case.trim() &&
      contextDataTypes.length &&
      contextDraft.business_criticality &&
      contextDraft.vendor_region &&
      contextDraft.processes_eu_personal_data !== null &&
      contextDraft.transfers_data_outside_eea !== null,
  );

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

  async function saveReviewContext() {
    if (!projectId || savingContext) return;
    setSavingContext(true);
    setWorkspaceError(null);
    try {
      const dataTypes = contextDataTypes.length ? contextDataTypes : ["not_specified"];
      await updateVendorReview(projectId, {
        name: contextDraft.vendor_name.trim() ? `${contextDraft.vendor_name.trim()} Vendor Review` : undefined,
        vendor_context: {
          vendor_name: contextDraft.vendor_name.trim() || null,
          intended_use_case: contextDraft.intended_use_case.trim() || null,
          data_types: dataTypes,
          shares_personal_data: contextDraft.shares_personal_data,
          shares_customer_data: contextDraft.shares_customer_data,
          shares_employee_data: contextDraft.shares_employee_data,
          shares_sensitive_data: contextDraft.shares_sensitive_data,
          has_ai_features: contextDraft.has_ai_features,
          business_criticality: contextDraft.business_criticality,
          vendor_region: contextDraft.vendor_region,
          processes_eu_personal_data: contextDraft.processes_eu_personal_data,
          transfers_data_outside_eea: contextDraft.transfers_data_outside_eea,
        },
      });
      await Promise.all([refreshProject(false), refreshSidebar()]);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to save review context.");
    } finally {
      setSavingContext(false);
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

  async function confirmHardDeleteDocument() {
    if (!projectId || !deleteDocument) return;
    const document = deleteDocument;
    const replacementId = replacementFor(document);
    setDeleteDocument(null);
    await runDocumentAction(document.document_id, () =>
      hardDeleteVendorDocument(projectId, document.document_id, document.is_primary ? replacementId : null),
    );
  }

  return (
    <div className="grid gap-4 md:gap-6">
      {uploadError && (
        <Alert variant="destructive">
          <AlertDescription>{uploadError}</AlertDescription>
        </Alert>
      )}

      <CheckerSurface className="p-5 md:p-7">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(260px,0.85fr)]">
          <SectionHeader
            label="Vendor context"
            title={detail?.vendor_context?.vendor_name || detail?.project.vendor_name || detail?.project.name}
            description={detail?.vendor_context?.intended_use_case || detail?.project.intended_use_case || "Complete the use case before running final review."}
          />
          <div className="grid grid-cols-2 gap-3">
            <MetricTile label="Documents" value={documents.filter((doc) => doc.lifecycle_status === "active").length} />
            <MetricTile label="Criticality" value={detail?.vendor_context?.business_criticality || "Incomplete"} tone={contextComplete ? "success" : "warning"} />
          </div>
        </div>

        <div className="mt-6 border-t border-border pt-5">
          <SectionHeader
            label="Review context"
            title={contextComplete ? "Ready for final review" : "Complete the review context"}
            description="These values drive criteria generation and the final Approval Pack."
            action={
              <Button
                type="button"
                onClick={() => void saveReviewContext()}
                disabled={savingContext || !contextComplete}
                className="h-10 rounded-lg"
              >
                {savingContext ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : null}
                Save Context
              </Button>
            }
          />

          <FormGrid className="mt-5 lg:grid-cols-2">
            <div className="grid gap-1.5">
              <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Vendor</label>
              <Input
                value={contextDraft.vendor_name}
                onChange={(event) => setContextDraft((current) => ({ ...current, vendor_name: event.target.value }))}
                className="h-10 rounded-lg bg-background"
              />
            </div>
            <div className="grid gap-1.5">
              <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Data types</label>
              <Input
                value={contextDraft.data_types}
                onChange={(event) => setContextDraft((current) => ({ ...current, data_types: event.target.value }))}
                placeholder="customer_personal_data, employee_personal_data"
                className="h-10 rounded-lg bg-background"
              />
            </div>
          </FormGrid>

          <div className="mt-4 grid gap-1.5">
            <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Intended use case</label>
            <Textarea
              value={contextDraft.intended_use_case}
              onChange={(event) => setContextDraft((current) => ({ ...current, intended_use_case: event.target.value }))}
              rows={3}
              className="min-h-24 resize-none rounded-lg bg-background text-sm leading-6"
            />
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <SelectField
              label="Criticality"
              value={contextDraft.business_criticality}
              onValueChange={(business_criticality) => setContextDraft((current) => ({ ...current, business_criticality }))}
              options={CONTEXT_CRITICALITY_OPTIONS.map((option) => ({ value: option, label: option }))}
            />
            <SelectField
              label="Vendor region"
              value={contextDraft.vendor_region}
              onValueChange={(vendor_region) => setContextDraft((current) => ({ ...current, vendor_region }))}
              options={CONTEXT_REGION_OPTIONS}
            />
            <div className="grid gap-2">
              <SwitchRow
                id="processes-eu-data"
                label="EU data"
                checked={contextDraft.processes_eu_personal_data}
                onCheckedChange={(processes_eu_personal_data) => setContextDraft((current) => ({ ...current, processes_eu_personal_data }))}
              />
              <SwitchRow
                id="transfers-eea"
                label="EEA transfer"
                checked={contextDraft.transfers_data_outside_eea}
                onCheckedChange={(transfers_data_outside_eea) => setContextDraft((current) => ({ ...current, transfers_data_outside_eea }))}
              />
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {CONTEXT_BOOLEAN_FLAGS.map(({ key, label }) => (
              <CheckboxChip
                key={key}
                label={label}
                checked={contextDraft[key]}
                onCheckedChange={(checked) => setContextDraft((current) => ({ ...current, [key]: checked }))}
              />
            ))}
          </div>
        </div>
      </CheckerSurface>

      <CheckerSurface className="p-5 md:p-7">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
          <SectionHeader
            label="Document manager"
            title="Upload primary and supporting review documents."
            description="Checker reviews all active parsed documents. One active Main DPA must be marked primary before final review."
          />
          <div className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr]">
              <SelectField
                label="Document type"
                value={documentType}
                onValueChange={setDocumentType}
                options={DOCUMENT_TYPE_OPTIONS}
              />
              <div className="grid gap-1.5">
                <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Display name</label>
                <Input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Display name"
                  className="h-10 rounded-lg bg-background"
                />
              </div>
            </div>
            {documentType === "main_dpa" && (
              <CheckboxChip
                label="Make primary DPA"
                checked={makePrimary}
                onCheckedChange={setMakePrimary}
                className="w-fit"
              />
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
              className={`flex w-full items-center justify-center gap-3 rounded-lg border border-dashed px-4 py-7 text-sm transition-colors ${
                isDragging
                  ? "border-primary bg-primary/10 text-foreground"
                  : "border-border bg-muted/45 text-muted-foreground hover:bg-muted"
              }`}
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
              <Upload className="size-5" />
              <span>Drop PDF/DOCX or click to upload</span>
            </button>
          </div>
        </div>

        <div className="mt-6 grid gap-3">
          {documents.length ? documents.map((document) => {
            const isWorking = workingDocumentId === document.document_id;
            const replacementId = replacementFor(document);
            return (
              <CheckerPanel key={document.document_id} className="p-4">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="break-words text-base font-medium text-foreground">{document.display_name || document.filename}</h3>
                      {document.is_primary && <StatusBadge tone="success"><Star className="size-3" />Primary</StatusBadge>}
                      <StatusBadge>{documentTypeLabel(document.document_type)}</StatusBadge>
                      <StatusBadge tone={document.parse_status === "COMPLETED" ? "success" : document.parse_status === "FAILED" ? "danger" : "warning"}>{formatStatus(document.parse_status)}</StatusBadge>
                      {document.lifecycle_status === "archived" && <StatusBadge tone="warning">Archived</StatusBadge>}
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">
                      {document.filename} · {formatNumber(document.page_count)} pages · {formatNumber(document.token_count_estimate)} tokens
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {document.lifecycle_status === "active" && document.document_type === "main_dpa" && !document.is_primary && (
                      <Button type="button" variant="outline" size="sm" disabled={isWorking} onClick={() => void runDocumentAction(document.document_id, () => markVendorDocumentPrimary(projectId, document.document_id))}>
                        <Star data-icon="inline-start" /> Make Primary
                      </Button>
                    )}
                    {document.lifecycle_status === "archived" ? (
                      <Button type="button" variant="outline" size="sm" disabled={isWorking} onClick={() => void runDocumentAction(document.document_id, () => restoreVendorDocument(projectId, document.document_id))}>
                        <RotateCcw data-icon="inline-start" /> Restore
                      </Button>
                    ) : (
                      <Button type="button" variant="outline" size="sm" disabled={isWorking} onClick={() => void runDocumentAction(document.document_id, () => archiveVendorDocument(projectId, document.document_id, document.is_primary ? replacementId : null))}>
                        <Archive data-icon="inline-start" /> Archive
                      </Button>
                    )}
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      disabled={isWorking}
                      onClick={() => setDeleteDocument(document)}
                    >
                      {isWorking ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <Trash2 data-icon="inline-start" />}
                      Delete
                    </Button>
                  </div>
                </div>
              </CheckerPanel>
            );
          }) : (
            <div className="rounded-lg border border-dashed border-border px-4 py-8 text-sm text-muted-foreground">
              No documents uploaded yet.
            </div>
          )}
        </div>
      </CheckerSurface>

      {primaryDocument && (
        <>
          <CheckerSurface className="overflow-hidden p-4 md:p-6">
            <SectionHeader
              label="Primary DPA"
              title={primaryDocument.display_name || primaryDocument.filename}
            />

            <div className="mt-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
              <MetricTile label="Parse status" value={formatStatus(primaryDocument.parse_status)} tone={primaryDocument.parse_status === "COMPLETED" ? "success" : primaryDocument.parse_status === "FAILED" ? "danger" : "warning"} />
              <MetricTile label="Pages" value={formatNumber(primaryDocument.page_count)} />
              <MetricTile label="Token estimate" value={formatNumber(primaryDocument.token_count_estimate)} />
              <MetricTile label="Characters" value={loadingParsedText ? "Loading..." : formatNumber(approximateCharacters)} />
            </div>

            <div className="mt-5 overflow-hidden rounded-lg border border-border bg-background">
              <button
                type="button"
                aria-expanded={parsedTextOpen}
                onClick={() => setParsedTextOpen((open) => !open)}
                className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left text-sm font-medium text-foreground transition-colors hover:bg-muted/50"
              >
                Parsed primary DPA text
                <ChevronDown className={`size-4 text-muted-foreground transition-transform ${parsedTextOpen ? "rotate-180" : ""}`} />
              </button>
              {parsedTextOpen ? (
                <div className="border-t border-border bg-muted/35">
                  {loadingParsedText ? (
                    <div className="flex items-center gap-3 px-4 py-4 text-sm text-muted-foreground">
                      <LoaderCircle className="size-4 animate-spin" /> Loading parsed structure...
                    </div>
                  ) : parsedTextError ? (
                    <div className="px-4 py-4 text-sm text-destructive">{parsedTextError}</div>
                  ) : (
                    <pre className="max-h-[50svh] overflow-auto overscroll-contain px-4 py-4 text-xs leading-6 whitespace-pre-wrap text-muted-foreground md:max-h-[420px]">
                      {parsedText || "No parsed markdown is available for this document yet."}
                    </pre>
                  )}
                </div>
              ) : null}
            </div>
          </CheckerSurface>

          {parseJob && parseJob.status !== "COMPLETED" && (
            <CheckerSurface className="p-4 md:p-7">
              <SectionHeader
                label="Document processing"
                title={
                  <span className="inline-flex items-center gap-3">
                    {parseJob.status === "FAILED" ? <X className="size-5 text-destructive" /> : <LoaderCircle className="size-5 animate-spin text-muted-foreground" />}
                    {formatParseStage(parseJob.stage)}
                  </span>
                }
                description={parseJob.message || "Processing the uploaded document."}
              />

              <Progress className="mt-6" value={Math.max(0, Math.min(100, parseJob.progress_pct || 0))}>
                <ProgressLabel>Progress</ProgressLabel>
                <ProgressValue />
              </Progress>
            </CheckerSurface>
          )}
        </>
      )}
      <Dialog open={!!deleteDocument} onOpenChange={(open) => !open && setDeleteDocument(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete document?</DialogTitle>
            <DialogDescription>
              This permanently removes &quot;{deleteDocument?.display_name || deleteDocument?.filename}&quot; and its stored parsed content.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleteDocument(null)}>
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={() => void confirmHardDeleteDocument()}>
              Delete Document
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
