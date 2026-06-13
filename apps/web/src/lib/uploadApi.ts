export type UploadStage =
  | "UPLOADING"
  | "VALIDATING"
  | "CLASSIFYING_PDF"
  | "PARSING_MISTRAL_OCR"
  | "COUNTING_TOKENS"
  | "PERSISTING_RESULTS"
  | "READY_FOR_REFERENCE_SELECTION"
  | "FAILED";

export type UploadJobStatus = {
  job_id: string;
  document_id: string;
  project_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | string;
  stage: UploadStage | string;
  progress_pct: number;
  message?: string | null;
  file_type: string;
  pdf_classification?: "native" | "scanned" | "mixed" | null;
  parser_route?: string | null;
  page_count?: number | null;
  token_count_estimate?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  result?: ParsedDocumentSummary | null;
  meta?: Record<string, unknown> | null;
};

export type ParsedDocumentSummary = {
  filename: string;
  mime_type: string;
  page_count: number;
  pdf_classification?: string | null;
  parser_route?: string | null;
  token_count_estimate?: number | null;
  extracted_text_format?: string | null;
};

export type UploadBootstrapResponse = {
  job_id: string;
  document_id: string;
  project_id: string;
  vendor_review_id: string;
  status: string;
  ws_url: string;
  status_url: string;
};

export type BusinessCriticality = "low" | "medium" | "high";

export type VendorDocumentType =
  | "main_dpa"
  | "privacy_policy"
  | "security_toms"
  | "subprocessors"
  | "data_transfer_terms"
  | "ai_terms"
  | "service_terms"
  | "security_certification"
  | "custom_agreement"
  | "other";

export type DocumentLifecycleStatus = "active" | "archived" | "deleted";

export type ApprovalRecommendation = "approve" | "approve_with_conditions" | "escalate" | "reject";

export type VendorReviewContext = {
  vendor_name?: string | null;
  vendor_website?: string | null;
  tool_or_service_name?: string | null;
  intended_use_case?: string | null;
  data_types: string[];
  shares_personal_data: boolean;
  shares_customer_data: boolean;
  shares_employee_data: boolean;
  shares_sensitive_data: boolean;
  has_ai_features: boolean;
  business_criticality?: BusinessCriticality | null;
  vendor_region?: "eea" | "uk" | "us" | "global" | "unknown" | null;
  processes_eu_personal_data?: boolean | null;
  transfers_data_outside_eea?: boolean | null;
  internal_owner?: string | null;
  review_deadline?: string | null;
  context_completed_at?: string | null;
};

export type VendorReviewCreationContext = {
  vendor_name: string;
  intended_use_case: string;
  shares_personal_data: boolean;
  business_criticality: BusinessCriticality;
  vendor_website?: string | null;
  tool_or_service_name?: string | null;
  name?: string | null;
};

export type ProjectSummary = {
  vendor_review_id: string;
  project_id: string;
  name: string;
  status:
    | "EMPTY"
    | "UPLOADING"
    | "READY_FOR_CHECKLIST"
    | "CHECKLIST_IN_PROGRESS"
    | "CHECKLIST_READY"
    | "REVIEW_IN_PROGRESS"
    | "COMPLETED"
    | "FAILED"
    | string;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  review_type?: string | null;
  vendor_name?: string | null;
  tool_or_service_name?: string | null;
  intended_use_case?: string | null;
  business_criticality?: BusinessCriticality | string | null;
  current_recommendation?: ApprovalRecommendation | string | null;
  document_count?: number;
  primary_document_id?: string | null;
  primary_document_filename?: string | null;
  document_id?: string | null;
  document_filename?: string | null;
};

export type CreateProjectResponse = ProjectSummary & {
  workspace_url: string;
};

export type ProjectDocumentSummary = {
  document_id: string;
  filename: string;
  mime_type: string;
  page_count: number;
  document_type?: VendorDocumentType | string;
  display_name?: string | null;
  description?: string | null;
  is_primary?: boolean;
  source_kind?: string;
  source_url?: string | null;
  lifecycle_status?: DocumentLifecycleStatus | string;
  active?: boolean;
  archived_at?: string | null;
  archive_expires_at?: string | null;
  deleted_at?: string | null;
  hard_deleted_at?: string | null;
  parse_status?: string | null;
  parser_route?: string | null;
  pdf_classification?: string | null;
  token_count_estimate?: number | null;
  extracted_text_format?: string | null;
  uploaded_at: string;
};

export type ParsedDocumentTextResponse = {
  text: string;
};

export type AnalysisRunSummary = {
  analysis_run_id: string;
  vendor_review_id?: string;
  project_id: string;
  document_id: string;
  primary_document_id?: string | null;
  input_document_ids?: string[];
  status: string;
  model_version: string;
  policy_version: string;
  stage?: string | null;
  progress_pct: number;
  message?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  approved_checklist_id?: string | null;
  started_at: string;
  completed_at?: string | null;
  latency_ms?: number | null;
  cost_usd?: number | null;
};

export type ReferenceSource = {
  source_id: string;
  title: string;
  authority: string;
  kind: "pdf" | "html" | string;
  url: string;
};

export type ReviewSetupPayload = {
  document_id: string;
  selected_source_ids: string[];
};

export const CHECKLIST_CATEGORIES = [
  "Scope, Roles & Instructions",
  "Subprocessors & Personnel",
  "Security & Confidentiality",
  "Data Subject Rights & Assistance",
  "Incidents & Breach Notification",
  "International Transfers & Localization",
  "Retention, Deletion & Exit",
  "Audit, Compliance & Liability",
] as const;

export type ChecklistCategory = (typeof CHECKLIST_CATEGORIES)[number];

export type ChecklistItem = {
  check_id: string;
  title: string;
  category: ChecklistCategory;
  legal_basis: string[];
  required: boolean;
  severity: "LOW" | "MEDIUM" | "HIGH" | "MANDATORY" | string;
  evidence_hint: string;
  pass_criteria: string[];
  fail_criteria: string[];
  sources: ChecklistDraftSource[];
};

export type ChecklistDraftMeta = {
  selected_source_ids: string[];
  confidence: number;
  open_questions: string[];
  generation_summary?: string | null;
};

export type ChecklistDraftSource = {
  source_type: "LAW" | "GUIDELINE" | "INTERNAL_POLICY" | string;
  authority: string;
  source_ref: string;
  source_url: string;
  source_excerpt: string;
  interpretation_notes?: string | null;
};

export type ChecklistDraftItem = {
  check_id: ChecklistItem["check_id"];
  title: ChecklistItem["title"];
  category: ChecklistItem["category"];
  legal_basis: ChecklistItem["legal_basis"];
  required: ChecklistItem["required"];
  severity: ChecklistItem["severity"];
  evidence_hint: ChecklistItem["evidence_hint"];
  pass_criteria: ChecklistItem["pass_criteria"];
  fail_criteria: ChecklistItem["fail_criteria"];
  sources: ChecklistItem["sources"];
  draft_rationale: string;
};

export type ChecklistGovernance = {
  owner: string;
  approval_status: "DRAFT" | "REVIEWED" | "APPROVED" | string;
  approved_by?: string | null;
  approved_at?: string | null;
  policy_version: string;
  change_note?: string | null;
};

export type ChecklistDocument = {
  version: string;
  governance: ChecklistGovernance;
  checks: ChecklistItem[];
};

export type ChecklistDraftOutput = {
  version: string;
  meta: ChecklistDraftMeta;
  checks: ChecklistDraftItem[];
};

export type ChecklistDraftPayload = {
  document_id: string;
  selected_source_ids: string[];
  user_instruction?: string | null;
};

export type ChecklistDraftBootstrapResponse = {
  checklist_draft_id: string;
  document_id: string;
  project_id: string;
  vendor_review_id?: string;
  input_document_ids?: string[];
  status: string;
  ws_url: string;
  status_url: string;
};

export type ChecklistDraftStatus = {
  checklist_draft_id: string;
  document_id: string;
  project_id: string;
  vendor_review_id?: string;
  input_document_ids?: string[];
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | string;
  stage: string;
  progress_pct: number;
  message?: string | null;
  selected_source_ids: string[];
  user_instruction?: string | null;
  meta?: Record<string, unknown> | null;
  result?: ChecklistDraftOutput | null;
  error_code?: string | null;
  error_message?: string | null;
};

export type ReviewSetupResponse = {
  analysis_run_id: string;
  document_id: string;
  project_id: string;
  vendor_review_id?: string;
  selected_source_ids: string[];
  status: string;
};

export type ApprovedChecklistSummary = {
  approved_checklist_id: string;
  vendor_review_id?: string;
  project_id: string;
  document_id: string;
  input_document_ids?: string[];
  version: string;
  selected_source_ids: string[];
  review_mode?: string;
  profile_id?: string;
  auto_approved?: boolean;
  stale_at?: string | null;
  stale_reason?: string | null;
  stale_document_ids?: string[];
  owner: string;
  approval_status: string;
  approved_by?: string | null;
  approved_at?: string | null;
  change_note?: string | null;
  created_at: string;
};

export type ApprovedChecklistResponse = ApprovedChecklistSummary & {
  checklist: ChecklistDocument;
};

export type ApproveChecklistPayload = {
  version: string;
  selected_source_ids: string[];
  checks: ChecklistItem[];
  change_note?: string | null;
};

export type AnalysisRunBootstrapResponse = AnalysisRunSummary & {
  ws_url: string;
  status_url: string;
  finding_count: number;
};

export type AnalysisRunStatus = AnalysisRunSummary & {
  finding_count: number;
};

export type EvidenceSpan = {
  page: number;
  start_offset: number;
  end_offset: number;
};

export type EvidenceQuote = {
  page: number;
  quote: string;
};

export type KbCitation = {
  source_id: string;
  source_ref: string;
  source_excerpt: string;
};

export type CheckAssessmentOutput = {
  check_id: string;
  status: "COMPLIANT" | "NON_COMPLIANT" | "PARTIAL" | "UNKNOWN" | string;
  risk: "LOW" | "MEDIUM" | "HIGH" | string;
  confidence: number;
  evidence_quotes: EvidenceQuote[];
  kb_citations: KbCitation[];
  missing_elements: string[];
  risk_rationale: string;
  abstained: boolean;
  abstain_reason?: string | null;
};

export type CheckResult = {
  check_id: string;
  category: string;
  status: "COMPLIANT" | "NON_COMPLIANT" | "PARTIAL" | "UNKNOWN" | string;
  risk: "LOW" | "MEDIUM" | "HIGH" | string;
  confidence: number;
  abstained: boolean;
  abstain_reason?: string | null;
  review_required: boolean;
  review_state: "PENDING" | "APPROVED" | "REJECTED" | string;
  citation_pages: number[];
  evidence_span_offsets: EvidenceSpan[];
  risk_rationale: string;
};

export type OverallSummary = {
  score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | string;
  summary: string;
};

export type OutputV2Report = {
  run_id: string;
  model_version: string;
  policy_version: string;
  overall: OverallSummary;
  checks: CheckResult[];
  highlights: string[];
  next_actions: string[];
  confidence: number;
  abstained: boolean;
  abstain_reason?: string | null;
  review_required: boolean;
  review_state: "PENDING" | "APPROVED" | "REJECTED" | string;
  citation_pages: number[];
  evidence_span_offsets: EvidenceSpan[];
  risk_rationale: string;
};

export type AnalysisRunReportResponse = {
  report: OutputV2Report;
  findings: AnalysisFindingDetail[];
};

export type ApprovalPackResponse = {
  approval_pack_id: string;
  vendor_review_id: string;
  project_id: string;
  analysis_run_id?: string | null;
  approved_checklist_id?: string | null;
  version: string;
  status: string;
  recommendation: ApprovalRecommendation | string;
  recommendation_summary: string;
  confidence: number;
  review_required: boolean;
  pack: Record<string, unknown>;
  stale_at?: string | null;
  stale_reason?: string | null;
  stale_document_ids?: string[];
  created_at: string;
  updated_at: string;
  published_at?: string | null;
};

export type AnalysisFindingDetail = {
  check_id: string;
  title: string;
  category: string;
  assessment: CheckAssessmentOutput;
  citation_pages: number[];
  evidence_span_offsets: EvidenceSpan[];
};

export type ProjectDetail = {
  project: ProjectSummary;
  vendor_context?: VendorReviewContext;
  documents?: ProjectDocumentSummary[];
  document?: ProjectDocumentSummary | null;
  parse_job?: UploadJobStatus | null;
  checklist_draft?: ChecklistDraftStatus | null;
  approved_checklist?: ApprovedChecklistSummary | null;
  analysis_run?: AnalysisRunSummary | null;
};

export type AuthUserResponse = {
  username: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function getConfiguredApiBaseUrl() {
  const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!configuredBaseUrl) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be set.");
  }
  return configuredBaseUrl;
}

export function getApiBaseUrl() {
  if (typeof window !== "undefined") {
    return "/api/proxy";
  }
  return getConfiguredApiBaseUrl();
}

export function getWsBaseUrl() {
  const apiBase = getConfiguredApiBaseUrl();
  if (apiBase.startsWith("https://")) return apiBase.replace("https://", "wss://");
  if (apiBase.startsWith("http://")) return apiBase.replace("http://", "ws://");
  return apiBase;
}

export function getDocumentFileUrl(documentId: string, page?: number | null) {
  const encodedId = encodeURIComponent(documentId);
  const baseUrl = `${getApiBaseUrl()}/v1/documents/${encodedId}/file`;
  return page && page > 0 ? `${baseUrl}#page=${page}` : baseUrl;
}

export function getDocumentProxyUrl(documentId: string) {
  return `/api/documents/${encodeURIComponent(documentId)}`;
}

export function getProjectDocumentViewerUrl(projectId: string, page?: number | null, documentId?: string | null) {
  const params = new URLSearchParams();
  if (page && page > 0) params.set("page", String(page));
  if (documentId) params.set("documentId", documentId);
  const query = params.toString();
  return `/vendor-reviews/${encodeURIComponent(projectId)}/review/document${query ? `?${query}` : ""}`;
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

async function apiFetch(input: string, init: RequestInit = {}) {
  return fetch(input, {
    ...init,
    credentials: "include",
  });
}

export async function login(username: string, password: string): Promise<AuthUserResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return parseJson<AuthUserResponse>(res);
}

export async function logout(): Promise<void> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/auth/logout`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new ApiError("Failed to log out.", res.status);
  }
}

export async function getCurrentUser(): Promise<AuthUserResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/auth/me`, { cache: "no-store" });
  return parseJson<AuthUserResponse>(res);
}

export async function createProject(name?: string | null): Promise<CreateProjectResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name?.trim() || null }),
  });
  return parseJson<CreateProjectResponse>(res);
}

export async function createVendorReview(payload: VendorReviewCreationContext): Promise<CreateProjectResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<CreateProjectResponse>(res);
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/projects`, { cache: "no-store" });
  return parseJson<ProjectSummary[]>(res);
}

export async function listVendorReviews(): Promise<ProjectSummary[]> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews`, { cache: "no-store" });
  return parseJson<ProjectSummary[]>(res);
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/projects/${projectId}`, { cache: "no-store" });
  return parseJson<ProjectDetail>(res);
}

export async function getVendorReview(reviewId: string): Promise<ProjectDetail> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}`, { cache: "no-store" });
  return parseJson<ProjectDetail>(res);
}

export async function getDocumentParsedText(documentId: string): Promise<ParsedDocumentTextResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/documents/${documentId}/parsed-text`, { cache: "no-store" });
  return parseJson<ParsedDocumentTextResponse>(res);
}

export async function renameProject(projectId: string, name: string): Promise<ProjectDetail> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return parseJson<ProjectDetail>(res);
}

export async function updateVendorReview(
  reviewId: string,
  payload: { name?: string | null; vendor_context?: Partial<VendorReviewContext> | null },
): Promise<ProjectDetail> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ProjectDetail>(res);
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/projects/${projectId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new ApiError(errorBody.detail || "Failed to delete project.", res.status);
  }
}

export type CreateUploadOptions = {
  document_type?: VendorDocumentType | string;
  display_name?: string | null;
  description?: string | null;
  make_primary?: boolean;
};

export async function createUpload(file: File, projectId: string, options: CreateUploadOptions = {}): Promise<UploadBootstrapResponse> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("file", file);
  form.append("document_type", options.document_type || "main_dpa");
  if (options.display_name) form.append("display_name", options.display_name);
  if (options.description) form.append("description", options.description);
  if (options.make_primary) form.append("make_primary", "true");
  const res = await apiFetch(`${getApiBaseUrl()}/v1/uploads`, {
    method: "POST",
    body: form,
  });
  return parseJson<UploadBootstrapResponse>(res);
}

export async function createVendorDocumentUpload(
  file: File,
  reviewId: string,
  options: CreateUploadOptions = {},
): Promise<UploadBootstrapResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("document_type", options.document_type || "main_dpa");
  if (options.display_name) form.append("display_name", options.display_name);
  if (options.description) form.append("description", options.description);
  if (options.make_primary) form.append("make_primary", "true");
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/documents`, {
    method: "POST",
    body: form,
  });
  return parseJson<UploadBootstrapResponse>(res);
}

export async function updateVendorDocument(
  reviewId: string,
  documentId: string,
  payload: { document_type?: VendorDocumentType | string | null; display_name?: string | null; description?: string | null },
): Promise<ProjectDocumentSummary> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/documents/${documentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ProjectDocumentSummary>(res);
}

export async function markVendorDocumentPrimary(reviewId: string, documentId: string): Promise<ProjectDocumentSummary> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/documents/${documentId}/primary`, {
    method: "POST",
  });
  return parseJson<ProjectDocumentSummary>(res);
}

export async function archiveVendorDocument(
  reviewId: string,
  documentId: string,
  replacementDocumentId?: string | null,
): Promise<ProjectDocumentSummary> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/documents/${documentId}/archive`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ replacement_document_id: replacementDocumentId || null }),
  });
  return parseJson<ProjectDocumentSummary>(res);
}

export async function restoreVendorDocument(reviewId: string, documentId: string): Promise<ProjectDocumentSummary> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/documents/${documentId}/restore`, {
    method: "POST",
  });
  return parseJson<ProjectDocumentSummary>(res);
}

export async function hardDeleteVendorDocument(
  reviewId: string,
  documentId: string,
  replacementDocumentId?: string | null,
): Promise<ProjectDocumentSummary> {
  const params = new URLSearchParams();
  if (replacementDocumentId) params.set("replacement_document_id", replacementDocumentId);
  const query = params.toString();
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/documents/${documentId}${query ? `?${query}` : ""}`, {
    method: "DELETE",
  });
  return parseJson<ProjectDocumentSummary>(res);
}

export async function getUploadStatus(jobId: string): Promise<UploadJobStatus> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/uploads/${jobId}`, { cache: "no-store" });
  return parseJson<UploadJobStatus>(res);
}

export async function getUploadResult(jobId: string): Promise<UploadJobStatus> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/uploads/${jobId}/result`, { cache: "no-store" });
  return parseJson<UploadJobStatus>(res);
}

export async function listReferenceSources(): Promise<ReferenceSource[]> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/reference-sources`, { cache: "no-store" });
  return parseJson<ReferenceSource[]>(res);
}

export async function createReviewSetup(payload: ReviewSetupPayload): Promise<ReviewSetupResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/review-setup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ReviewSetupResponse>(res);
}

export async function getApprovedChecklist(projectId: string): Promise<ApprovedChecklistResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/projects/${projectId}/approved-checklist`, { cache: "no-store" });
  return parseJson<ApprovedChecklistResponse>(res);
}

export async function approveChecklist(projectId: string, payload: ApproveChecklistPayload): Promise<ApprovedChecklistResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/projects/${projectId}/approved-checklist`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ApprovedChecklistResponse>(res);
}

export async function createAnalysisRun(projectId: string): Promise<AnalysisRunBootstrapResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/analysis-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
  return parseJson<AnalysisRunBootstrapResponse>(res);
}

export async function createVendorReviewRun(reviewId: string): Promise<AnalysisRunBootstrapResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/review-runs`, {
    method: "POST",
  });
  return parseJson<AnalysisRunBootstrapResponse>(res);
}

export async function getAnalysisRunStatus(runId: string): Promise<AnalysisRunStatus> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/analysis-runs/${runId}`, { cache: "no-store" });
  return parseJson<AnalysisRunStatus>(res);
}

export async function getAnalysisReport(runId: string): Promise<AnalysisRunReportResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/analysis-runs/${runId}/report`, { cache: "no-store" });
  return parseJson<AnalysisRunReportResponse>(res);
}

export async function getApprovalPack(runId: string): Promise<ApprovalPackResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/review-runs/${runId}/approval-pack`, { cache: "no-store" });
  return parseJson<ApprovalPackResponse>(res);
}

export async function createChecklistDraft(payload: ChecklistDraftPayload): Promise<ChecklistDraftBootstrapResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/checklist-drafts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ChecklistDraftBootstrapResponse>(res);
}

export async function createVendorCriteriaDraft(
  reviewId: string,
  userInstruction?: string | null,
): Promise<ChecklistDraftBootstrapResponse> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/vendor-reviews/${reviewId}/criteria-drafts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_instruction: userInstruction || null }),
  });
  return parseJson<ChecklistDraftBootstrapResponse>(res);
}

export async function getChecklistDraftStatus(draftId: string): Promise<ChecklistDraftStatus> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/checklist-drafts/${draftId}`, { cache: "no-store" });
  return parseJson<ChecklistDraftStatus>(res);
}

export async function cancelChecklistDraft(draftId: string): Promise<ChecklistDraftStatus> {
  const res = await apiFetch(`${getApiBaseUrl()}/v1/checklist-drafts/${draftId}/cancel`, {
    method: "POST",
  });
  return parseJson<ChecklistDraftStatus>(res);
}

export function uploadEventsUrl(jobId: string) {
  return `${getWsBaseUrl()}/v1/uploads/${jobId}/events`;
}

export function checklistDraftEventsUrl(draftId: string) {
  return `${getWsBaseUrl()}/v1/checklist-drafts/${draftId}/events`;
}

export function analysisRunEventsUrl(runId: string) {
  return `${getWsBaseUrl()}/v1/analysis-runs/${runId}/events`;
}
