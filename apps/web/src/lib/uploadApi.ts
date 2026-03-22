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
  status: string;
  ws_url: string;
  status_url: string;
};

export type ProjectSummary = {
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
  parse_status?: string | null;
  parser_route?: string | null;
  pdf_classification?: string | null;
  token_count_estimate?: number | null;
  extracted_text_format?: string | null;
  uploaded_at: string;
};

export type AnalysisRunSummary = {
  analysis_run_id: string;
  project_id: string;
  document_id: string;
  status: string;
  model_version: string;
  policy_version: string;
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
  check_id: string;
  title: string;
  category: string;
  legal_basis: string[];
  required: boolean;
  severity: "LOW" | "MEDIUM" | "HIGH" | "MANDATORY" | string;
  evidence_hint: string;
  pass_criteria: string[];
  fail_criteria: string[];
  sources: ChecklistDraftSource[];
  draft_rationale: string;
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
  status: string;
  ws_url: string;
  status_url: string;
};

export type ChecklistDraftStatus = {
  checklist_draft_id: string;
  document_id: string;
  project_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | string;
  stage: string;
  progress_pct: number;
  message?: string | null;
  selected_source_ids: string[];
  user_instruction?: string | null;
  result?: ChecklistDraftOutput | null;
  error_code?: string | null;
  error_message?: string | null;
};

export type ReviewSetupResponse = {
  analysis_run_id: string;
  document_id: string;
  project_id: string;
  selected_source_ids: string[];
  status: string;
};

export type ProjectDetail = {
  project: ProjectSummary;
  document?: ProjectDocumentSummary | null;
  parse_job?: UploadJobStatus | null;
  checklist_draft?: ChecklistDraftStatus | null;
  analysis_run?: AnalysisRunSummary | null;
};

export function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";
}

export function getWsBaseUrl() {
  const apiBase = getApiBaseUrl();
  if (apiBase.startsWith("https://")) return apiBase.replace("https://", "wss://");
  if (apiBase.startsWith("http://")) return apiBase.replace("http://", "ws://");
  return apiBase;
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
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function createProject(name?: string | null): Promise<CreateProjectResponse> {
  const res = await fetch(`${getApiBaseUrl()}/v1/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name?.trim() || null }),
  });
  return parseJson<CreateProjectResponse>(res);
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${getApiBaseUrl()}/v1/projects`, { cache: "no-store" });
  return parseJson<ProjectSummary[]>(res);
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  const res = await fetch(`${getApiBaseUrl()}/v1/projects/${projectId}`, { cache: "no-store" });
  return parseJson<ProjectDetail>(res);
}

export async function renameProject(projectId: string, name: string): Promise<ProjectDetail> {
  const res = await fetch(`${getApiBaseUrl()}/v1/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return parseJson<ProjectDetail>(res);
}

export async function createUpload(file: File, projectId: string): Promise<UploadBootstrapResponse> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("file", file);
  const res = await fetch(`${getApiBaseUrl()}/v1/uploads`, {
    method: "POST",
    body: form,
  });
  return parseJson<UploadBootstrapResponse>(res);
}

export async function getUploadStatus(jobId: string): Promise<UploadJobStatus> {
  const res = await fetch(`${getApiBaseUrl()}/v1/uploads/${jobId}`, { cache: "no-store" });
  return parseJson<UploadJobStatus>(res);
}

export async function getUploadResult(jobId: string): Promise<UploadJobStatus> {
  const res = await fetch(`${getApiBaseUrl()}/v1/uploads/${jobId}/result`, { cache: "no-store" });
  return parseJson<UploadJobStatus>(res);
}

export async function listReferenceSources(): Promise<ReferenceSource[]> {
  const res = await fetch(`${getApiBaseUrl()}/v1/reference-sources`, { cache: "no-store" });
  return parseJson<ReferenceSource[]>(res);
}

export async function createReviewSetup(payload: ReviewSetupPayload): Promise<ReviewSetupResponse> {
  const res = await fetch(`${getApiBaseUrl()}/v1/review-setup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ReviewSetupResponse>(res);
}

export async function createChecklistDraft(payload: ChecklistDraftPayload): Promise<ChecklistDraftBootstrapResponse> {
  const res = await fetch(`${getApiBaseUrl()}/v1/checklist-drafts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ChecklistDraftBootstrapResponse>(res);
}

export async function getChecklistDraftStatus(draftId: string): Promise<ChecklistDraftStatus> {
  const res = await fetch(`${getApiBaseUrl()}/v1/checklist-drafts/${draftId}`, { cache: "no-store" });
  return parseJson<ChecklistDraftStatus>(res);
}

export function uploadEventsUrl(jobId: string) {
  return `${getWsBaseUrl()}/v1/uploads/${jobId}/events`;
}

export function checklistDraftEventsUrl(draftId: string) {
  return `${getWsBaseUrl()}/v1/checklist-drafts/${draftId}/events`;
}
