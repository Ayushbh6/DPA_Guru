"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, CheckCircle2, Download, ExternalLink, LoaderCircle, Plus, Trash2, X } from "lucide-react";
import {
  approveChecklist,
  getApprovedChecklist,
  type ChecklistDraftItem,
  type ChecklistDraftSource,
  type ChecklistItem,
} from "@/lib/uploadApi";
import { downloadChecklistDocx } from "@/lib/docxExport";
import { useProject } from "../../ProjectProvider";

type ReviewDecision = "accepted" | "rejected";

type EditableChecklistRow = ChecklistItem & {
  _decision: ReviewDecision;
  _origin: "ai" | "manual";
};

const MANUAL_SOURCE_URL = "https://example.com/manual-check";

function groupChecksByCategory(checks: EditableChecklistRow[]) {
  const groups = new Map<string, EditableChecklistRow[]>();
  for (const check of checks) {
    const category = check.category || "Other";
    const existing = groups.get(category) || [];
    existing.push(check);
    groups.set(category, existing);
  }
  return Array.from(groups.entries());
}

function manualPlaceholderSource(): ChecklistDraftSource {
  return {
    source_type: "INTERNAL_POLICY",
    authority: "User Added",
    source_ref: "Manual reviewer addition",
    source_url: MANUAL_SOURCE_URL,
    source_excerpt: "This check was added manually during checklist approval.",
    interpretation_notes: "No KB citation attached. Reviewer added this check explicitly.",
  };
}

function isManualSource(source: ChecklistDraftSource) {
  return source.authority === "User Added" && source.source_ref === "Manual reviewer addition";
}

function toEditableChecks(checks: ChecklistDraftItem[] | ChecklistItem[]): EditableChecklistRow[] {
  return checks.map((check) => {
    const allManualSources = check.sources.length > 0 && check.sources.every(isManualSource);
    return {
      check_id: check.check_id,
      title: check.title,
      category: check.category,
      legal_basis: [...check.legal_basis],
      required: true,
      severity: check.severity,
      evidence_hint: check.evidence_hint,
      pass_criteria: [...check.pass_criteria],
      fail_criteria: [...check.fail_criteria],
      sources: check.sources.map((source) => ({ ...source })),
      _decision: "accepted",
      _origin: allManualSources ? "manual" : "ai",
    };
  });
}

function nextManualCheckId(checks: EditableChecklistRow[]) {
  const maxId = checks.reduce((max, check) => {
    if (!check.check_id.startsWith("CUSTOM_")) return max;
    const suffix = Number.parseInt(check.check_id.replace("CUSTOM_", ""), 10);
    return Number.isFinite(suffix) ? Math.max(max, suffix) : max;
  }, 0);
  return `CUSTOM_${String(maxId + 1).padStart(3, "0")}`;
}

function createManualCheck(checks: EditableChecklistRow[]): EditableChecklistRow {
  return {
    check_id: nextManualCheckId(checks),
    title: "",
    category: "Custom",
    legal_basis: [],
    required: true,
    severity: "MEDIUM",
    evidence_hint: "",
    pass_criteria: [],
    fail_criteria: [],
    sources: [manualPlaceholderSource()],
    _decision: "accepted",
    _origin: "manual",
  };
}

function toLines(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function toText(value: string[]) {
  return value.join("\n");
}

function buildApprovalChecks(checks: EditableChecklistRow[]): ChecklistItem[] {
  const accepted = checks.filter((check) => check._decision === "accepted");
  if (!accepted.length) {
    throw new Error("Accept at least one checklist item before approval.");
  }

  return accepted.map((check) => {
    const title = check.title.trim();
    const category = check.category.trim();
    const evidenceHint = check.evidence_hint.trim();
    const legalBasis = check.legal_basis.map((item) => item.trim()).filter(Boolean);
    const passCriteria = check.pass_criteria.map((item) => item.trim()).filter(Boolean);
    const failCriteria = check.fail_criteria.map((item) => item.trim()).filter(Boolean);

    if (!title) throw new Error(`${check.check_id}: title is required.`);
    if (!category) throw new Error(`${check.check_id}: category is required.`);
    if (!evidenceHint) throw new Error(`${check.check_id}: evidence hint is required.`);
    if (!legalBasis.length) throw new Error(`${check.check_id}: add at least one legal basis line.`);
    if (!passCriteria.length) throw new Error(`${check.check_id}: add at least one pass criteria line.`);
    if (!failCriteria.length) throw new Error(`${check.check_id}: add at least one fail criteria line.`);

    return {
      check_id: check.check_id,
      title,
      category,
      legal_basis: legalBasis,
      required: true,
      severity: check.severity,
      evidence_hint: evidenceHint,
      pass_criteria: passCriteria,
      fail_criteria: failCriteria,
      sources: check.sources.length ? check.sources.map((source) => ({ ...source })) : [manualPlaceholderSource()],
    };
  });
}

function checklistCardTone(check: EditableChecklistRow): React.CSSProperties {
  return check._decision === "rejected"
    ? { borderColor: 'var(--line)', background: 'var(--bg)', opacity: 0.55 }
    : { borderColor: 'var(--line)', background: 'var(--bg-2)' };
}

export default function ChecklistResultPage() {
  const { projectId, detail, refreshProject, setWorkspaceError } = useProject();
  const draftJob = detail?.checklist_draft;
  const approvedSummary = detail?.approved_checklist;

  const [version, setVersion] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [checks, setChecks] = useState<EditableChecklistRow[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [loadingApproved, setLoadingApproved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadApproved() {
      if (!projectId || !approvedSummary?.approved_checklist_id) return;
      setLoadingApproved(true);
      try {
        const approved = await getApprovedChecklist(projectId);
        if (cancelled) return;
        setVersion(approved.version);
        setChecks(toEditableChecks(approved.checklist.checks));
        setSelectedSourceIds(approved.selected_source_ids);
        setChangeNote(approved.change_note || "");
      } catch (error) {
        if (!cancelled) {
          setWorkspaceError(error instanceof Error ? error.message : "Failed to load approved checklist.");
        }
      } finally {
        if (!cancelled) setLoadingApproved(false);
      }
    }

    if (approvedSummary?.approved_checklist_id) {
      void loadApproved();
      return () => {
        cancelled = true;
      };
    }

    if (draftJob?.result) {
      setVersion(draftJob.result.version);
      setChecks(toEditableChecks(draftJob.result.checks));
      setSelectedSourceIds(draftJob.result.meta.selected_source_ids);
      setChangeNote("");
    }

    return () => {
      cancelled = true;
    };
  }, [approvedSummary?.approved_checklist_id, draftJob?.result, projectId, setWorkspaceError]);

  const groupedChecks = useMemo(() => groupChecksByCategory(checks), [checks]);
  const acceptedCount = useMemo(() => checks.filter((check) => check._decision === "accepted").length, [checks]);

  function updateCheck(index: number, patch: Partial<EditableChecklistRow>) {
    setChecks((prev) => prev.map((check, current) => (current === index ? { ...check, ...patch } : check)));
  }

  function setDecision(index: number, decision: ReviewDecision) {
    updateCheck(index, { _decision: decision, required: true });
  }

  function addManualRow() {
    setChecks((prev) => [createManualCheck(prev), ...prev]);
  }

  function removeRow(index: number) {
    setChecks((prev) => prev.filter((_, current) => current !== index));
  }

  async function handleApprove() {
    if (!projectId || !version.trim()) return;
    setSaving(true);
    try {
      const approvalChecks = buildApprovalChecks(checks);
      await approveChecklist(projectId, {
        version: version.trim(),
        selected_source_ids: selectedSourceIds,
        checks: approvalChecks,
        change_note: changeNote.trim() || null,
      });
      await refreshProject();
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to approve checklist.");
    } finally {
      setSaving(false);
    }
  }

  async function handleExportDocx() {
    setExporting(true);
    try {
      const approvalChecks = buildApprovalChecks(checks);
      await downloadChecklistDocx({
        projectName: detail?.project.name || "Project",
        version: version.trim() || "draft",
        changeNote: changeNote.trim() || null,
        selectedSourceIds,
        checks: approvalChecks,
        acceptedCount,
        rejectedCount: checks.length - acceptedCount,
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to export checklist DOCX.");
    } finally {
      setExporting(false);
    }
  }

  if (!draftJob?.result && !approvedSummary) {
    return (
      <div className="border p-8" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)' }}>
        <h2 className="text-xl" style={{ color: 'var(--text)' }}>No Results Yet</h2>
        <p className="mt-2" style={{ color: 'var(--text-2)' }}>Please configure and generate the checklist first from the Setup tab.</p>
      </div>
    );
  }

  if (loadingApproved) {
    return (
      <div className="flex items-center gap-3 border p-8" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)', color: 'var(--text-2)' }}>
        <LoaderCircle className="h-4 w-4 animate-spin" />
        Loading approved checklist...
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      <section className="overflow-hidden border" style={{ background: 'var(--bg-1)', borderColor: 'var(--line)' }}>
        <div className="h-px" style={{ background: 'var(--accent)', opacity: 0.4 }} />
        <div className="p-5 md:p-7">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.2em]" style={{ color: 'var(--text-3)' }}>Checklist Approval</div>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight" style={{ color: 'var(--text)' }}>
                {approvedSummary ? "Approved Checklist Loaded" : "Review, Keep, Reject, Or Add Checks"}
              </h2>
              <p className="mt-3 max-w-3xl" style={{ color: 'var(--text-3)' }}>
                Every approved check stays required. Use the tick and cross to decide which AI checks survive, or add your own checks manually.
              </p>
            </div>
            {approvedSummary && (
              <div className="border border-emerald-300/20 bg-emerald-300/5 px-4 py-3 text-sm text-emerald-50/85">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4" />
                  Approved by {approvedSummary.approved_by || "local-dev"}
                </div>
                {approvedSummary.approved_at && <div className="mt-2 text-xs text-emerald-100/60">{new Date(approvedSummary.approved_at).toLocaleString()}</div>}
              </div>
            )}
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
            <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
              <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Version</div>
              <input
                value={version}
                onChange={(event) => setVersion(event.target.value)}
                className="mt-3 w-full border px-3 py-2 text-sm outline-none"
                style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
              />
            </div>
            <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
              <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Change Note</div>
              <input
                value={changeNote}
                onChange={(event) => setChangeNote(event.target.value)}
                className="mt-3 w-full border px-3 py-2 text-sm outline-none"
                style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                placeholder="Optional note about what changed before approval."
              />
            </div>
            <button
              type="button"
              onClick={addManualRow}
              className="inline-flex items-center justify-center gap-2 border px-4 py-3 text-sm transition-colors"
              style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text)' }}
            >
              <Plus className="h-4 w-4" />
              Add Check
            </button>
            <button
              type="button"
              onClick={() => void handleExportDocx()}
              disabled={exporting || acceptedCount === 0}
              className="inline-flex items-center justify-center gap-2 border px-4 py-3 text-sm transition-colors disabled:opacity-50"
              style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text)' }}
            >
              {exporting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Download DOCX
            </button>
          </div>

          <div className="mt-4 flex items-center gap-3 text-sm" style={{ color: 'var(--text-3)' }}>
            <span>{acceptedCount} accepted</span>
            <span style={{ opacity: 0.4 }}>/</span>
            <span>{checks.length - acceptedCount} rejected</span>
          </div>

          <div className="mt-8 grid gap-8">
            {groupedChecks.map(([category, grouped]) => (
              <div key={category}>
                <div className="text-xs uppercase tracking-[0.2em]" style={{ color: 'var(--text-3)' }}>{category}</div>
                <div className="mt-4 grid gap-4">
                  {grouped.map((check) => {
                    const index = checks.findIndex((item) => item.check_id === check.check_id);
                    const current = checks[index];
                    const isManual = current?._origin === "manual";
                    const isRejected = current?._decision === "rejected";

                    return (
                      <div key={check.check_id} className="border p-4 md:p-5" style={checklistCardTone(current)}>
                        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                          <div className="flex-1">
                            <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>
                              <span>{current.check_id}</span>
                              <span className="border px-2 py-1 text-[9px] tracking-[0.14em]" style={{ borderColor: 'var(--line)', color: 'var(--text-3)' }}>Required</span>
                              {isManual && <span className="border border-amber-200/15 px-2 py-1 text-[9px] tracking-[0.14em] text-amber-100/65">Manual</span>}
                            </div>
                            <input
                              value={current.title}
                              onChange={(event) => updateCheck(index, { title: event.target.value })}
                              className="mt-2 w-full border px-3 py-2 text-lg outline-none"
                              style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                              placeholder="Checklist title"
                            />
                          </div>
                          <div className="grid gap-3 md:w-[240px]">
                            <select
                              value={current.severity || "MEDIUM"}
                              onChange={(event) => updateCheck(index, { severity: event.target.value })}
                              className="border px-3 py-2 text-sm outline-none"
                              style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                            >
                              <option value="LOW">LOW</option>
                              <option value="MEDIUM">MEDIUM</option>
                              <option value="HIGH">HIGH</option>
                              <option value="MANDATORY">MANDATORY</option>
                            </select>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => setDecision(index, "accepted")}
                                className="inline-flex flex-1 items-center justify-center gap-2 border px-3 py-2 text-sm transition-colors"
                                style={!isRejected ? { borderColor: 'rgba(110,231,183,0.3)', background: 'rgba(110,231,183,0.1)', color: 'var(--text)' } : { borderColor: 'var(--line)', color: 'var(--text-2)' }}
                              >
                                <Check className="h-4 w-4" />
                                Accept
                              </button>
                              <button
                                type="button"
                                onClick={() => setDecision(index, "rejected")}
                                className="inline-flex flex-1 items-center justify-center gap-2 border px-3 py-2 text-sm transition-colors"
                                style={isRejected ? { borderColor: 'rgba(253,164,175,0.3)', background: 'rgba(253,164,175,0.1)', color: 'var(--text)' } : { borderColor: 'var(--line)', color: 'var(--text-2)' }}
                              >
                                <X className="h-4 w-4" />
                                Reject
                              </button>
                              {isManual && (
                                <button
                                  type="button"
                                  onClick={() => removeRow(index)}
                                  className="inline-flex items-center justify-center border px-3 py-2 transition-colors"
                                  style={{ borderColor: 'var(--line)', color: 'var(--text-2)' }}
                                  aria-label={`Delete ${current.check_id}`}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="mt-4 grid gap-4 lg:grid-cols-2">
                          <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                            <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Category</div>
                            <input
                              value={current.category}
                              onChange={(event) => updateCheck(index, { category: event.target.value })}
                              className="mt-3 w-full border px-3 py-2 text-sm outline-none"
                              style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                            />
                          </div>
                          <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                            <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Evidence Hint</div>
                            <textarea
                              value={current.evidence_hint}
                              onChange={(event) => updateCheck(index, { evidence_hint: event.target.value })}
                              rows={4}
                              className="mt-3 w-full border px-3 py-2 text-sm outline-none"
                              style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                            />
                          </div>
                        </div>

                        <div className="mt-4 grid gap-4 lg:grid-cols-3">
                          <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                            <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Legal Basis</div>
                            <textarea
                              value={toText(current.legal_basis)}
                              onChange={(event) => updateCheck(index, { legal_basis: toLines(event.target.value) })}
                              rows={5}
                              className="mt-3 w-full border px-3 py-2 text-sm outline-none"
                              style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                              placeholder="One line per legal basis entry"
                            />
                          </div>
                          <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                            <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Pass Criteria</div>
                            <textarea
                              value={toText(current.pass_criteria)}
                              onChange={(event) => updateCheck(index, { pass_criteria: toLines(event.target.value) })}
                              rows={5}
                              className="mt-3 w-full border px-3 py-2 text-sm outline-none"
                              style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                              placeholder="One line per pass condition"
                            />
                          </div>
                          <div className="border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                            <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Fail Criteria</div>
                            <textarea
                              value={toText(current.fail_criteria)}
                              onChange={(event) => updateCheck(index, { fail_criteria: toLines(event.target.value) })}
                              rows={5}
                              className="mt-3 w-full border px-3 py-2 text-sm outline-none"
                              style={{ borderColor: 'var(--line)', background: 'var(--bg)', color: 'var(--text)' }}
                              placeholder="One line per fail condition"
                            />
                          </div>
                        </div>

                        <div className="mt-4 border p-4" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)' }}>
                          <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Source Support</div>
                          <div className="mt-3 grid gap-3">
                            {current.sources.map((source) => {
                              const manualSource = isManualSource(source);
                              return (
                                <div key={`${source.authority}-${source.source_ref}`} className="border p-3" style={{ borderColor: 'var(--line)', background: 'var(--bg)' }}>
                                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                    <div>
                                      <div className="text-sm" style={{ color: 'var(--text)' }}>{source.authority}</div>
                                      <div className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>{source.source_ref}</div>
                                    </div>
                                    {!manualSource && (
                                      <a
                                        href={source.source_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="inline-flex items-center gap-1 text-xs transition-colors" style={{ color: 'var(--text-2)' }}
                                      >
                                        Open Source <ExternalLink className="h-3 w-3" />
                                      </a>
                                    )}
                                  </div>
                                  <div className="mt-3 text-sm leading-relaxed" style={{ color: 'var(--text-2)' }}>{source.source_excerpt}</div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm" style={{ color: 'var(--text-3)' }}>Only accepted checks will be stored in the approved checklist version.</div>
            <button
              type="button"
              onClick={() => void handleApprove()}
              disabled={saving || !version.trim() || acceptedCount === 0}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium transition-opacity disabled:opacity-50"
              style={{ background: 'var(--invert)', color: 'var(--invert-fg)' }}
            >
              {saving && <LoaderCircle className="h-4 w-4 animate-spin" />}
              {approvedSummary ? "Save Approved Version" : "Approve Checklist"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
