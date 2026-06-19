"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, CheckCircle2, Download, ExternalLink, LoaderCircle, Plus, Trash2, X } from "lucide-react";
import {
  CheckerPanel,
  CheckerSurface,
  MetricTile,
  SectionHeader,
  SelectField,
  StatusBadge,
} from "@/components/checker-ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  approveChecklist,
  CHECKLIST_CATEGORIES,
  type ChecklistCategory,
  getApprovedChecklist,
  type ChecklistDraftItem,
  type ChecklistDraftSource,
  type ChecklistItem,
} from "@/lib/uploadApi";
import { downloadChecklistDocx } from "@/lib/docxExport";
import { useProject } from "../../ProjectProvider";

type ReviewDecision = "accepted" | "rejected";

const SEVERITY_OPTIONS = [
  { value: "LOW", label: "LOW" },
  { value: "MEDIUM", label: "MEDIUM" },
  { value: "HIGH", label: "HIGH" },
  { value: "MANDATORY", label: "MANDATORY" },
] as const;

type EditableChecklistRow = ChecklistItem & {
  _decision: ReviewDecision;
  _origin: "ai" | "manual";
};

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
    source_url: "",
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
    category: CHECKLIST_CATEGORIES[0],
    legal_basis: [],
    required: true,
    severity: "MEDIUM",
    evidence_hint: "",
    pass_criteria: [],
    fail_criteria: [],
    sources: [manualPlaceholderSource()],
    _decision: "rejected",
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
    if (!CHECKLIST_CATEGORIES.includes(category as ChecklistCategory)) {
      throw new Error(`${check.check_id}: choose one of the approved checklist categories.`);
    }
    if (!evidenceHint) throw new Error(`${check.check_id}: evidence hint is required.`);
    if (!legalBasis.length) throw new Error(`${check.check_id}: add at least one legal basis line.`);
    if (!passCriteria.length) throw new Error(`${check.check_id}: add at least one pass criteria line.`);
    if (!failCriteria.length) throw new Error(`${check.check_id}: add at least one fail criteria line.`);

    return {
      check_id: check.check_id,
      title,
      category: category as ChecklistCategory,
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
  const [expandedCheckIds, setExpandedCheckIds] = useState<string[]>([]);

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

  function toggleExpanded(checkId: string) {
    setExpandedCheckIds((prev) =>
      prev.includes(checkId) ? prev.filter((id) => id !== checkId) : [...prev, checkId],
    );
  }

  function updateCheck(index: number, patch: Partial<EditableChecklistRow>) {
    setChecks((prev) => prev.map((check, current) => (current === index ? { ...check, ...patch } : check)));
  }

  function setDecision(index: number, decision: ReviewDecision) {
    updateCheck(index, { _decision: decision, required: true });
  }

  function addManualRow() {
    setChecks((prev) => {
      const manualCheck = createManualCheck(prev);
      setExpandedCheckIds((current) => [...current, manualCheck.check_id]);
      return [manualCheck, ...prev];
    });
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
      <Alert>
        <AlertDescription>
          No results yet. Configure and generate the checklist first from the Criteria tab.
        </AlertDescription>
      </Alert>
    );
  }

  if (loadingApproved) {
    return (
      <CheckerSurface className="flex items-center gap-3 p-8 text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" />
        Loading approved checklist...
      </CheckerSurface>
    );
  }

  return (
    <div className="grid gap-6">
      <CheckerSurface className="p-4 md:p-5 lg:p-7">
        <SectionHeader
          label="Checklist approval"
          title={approvedSummary ? "Approved Checklist Loaded" : "Review, keep, reject, or add checks"}
          description="Every approved check stays required. Accept, reject, or edit criteria before storing the approved checklist."
          action={
            approvedSummary ? (
              <StatusBadge tone="success" className="flex items-center gap-2">
                <CheckCircle2 className="size-3" />
                Approved by {approvedSummary.approved_by || "local-dev"}
              </StatusBadge>
            ) : null
          }
        />
        {approvedSummary?.approved_at && (
          <div className="mt-2 text-xs text-muted-foreground">
            {new Date(approvedSummary.approved_at).toLocaleString()}
          </div>
        )}

        <div className="mt-6 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
          <CheckerPanel className="p-4">
            <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              Version
            </label>
            <Input
              value={version}
              onChange={(event) => setVersion(event.target.value)}
              className="mt-3 h-10 rounded-lg bg-background"
            />
          </CheckerPanel>
          <CheckerPanel className="p-4">
            <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              Change note
            </label>
            <Input
              value={changeNote}
              onChange={(event) => setChangeNote(event.target.value)}
              className="mt-3 h-10 rounded-lg bg-background"
              placeholder="Optional note about what changed before approval."
            />
          </CheckerPanel>
          <Button type="button" variant="outline" onClick={addManualRow} className="h-11 self-end rounded-lg">
            <Plus data-icon="inline-start" />
            Add Check
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void handleExportDocx()}
            disabled={exporting || acceptedCount === 0}
            className="h-11 self-end rounded-lg"
          >
            {exporting ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <Download data-icon="inline-start" />}
            Download DOCX
          </Button>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricTile label="Accepted" value={acceptedCount} tone="success" />
          <MetricTile label="Rejected" value={checks.length - acceptedCount} tone="danger" />
          <MetricTile label="Total" value={checks.length} />
          <MetricTile label="Categories" value={groupedChecks.length} tone="warning" />
        </div>

        <div className="mt-8 grid gap-7">
          {groupedChecks.map(([category, grouped]) => (
            <div key={category}>
              <div className="flex items-center gap-3">
                <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{category}</div>
                <StatusBadge>{grouped.length}</StatusBadge>
              </div>
              <div className="mt-4 grid gap-4">
                {grouped.map((check) => {
                  const index = checks.findIndex((item) => item.check_id === check.check_id);
                  if (index < 0) return null;
                  const current = checks[index]!;
                  const isManual = current._origin === "manual";
                  const isRejected = current._decision === "rejected";
                  const isExpanded = expandedCheckIds.includes(current.check_id);
                  const severityValue = (current.severity || "MEDIUM") as (typeof SEVERITY_OPTIONS)[number]["value"];

                  return (
                    <CheckerPanel
                      key={check.check_id}
                      className={`overflow-hidden ${isRejected ? "opacity-70" : ""}`}
                    >
                      <div className={`h-1 ${isRejected ? "bg-destructive" : "bg-primary"}`} />
                      <div className="p-4 md:p-5">
                        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge>{current.check_id}</StatusBadge>
                              <StatusBadge>Required</StatusBadge>
                              <StatusBadge tone={severityValue === "LOW" ? "success" : severityValue === "MEDIUM" ? "warning" : "danger"}>
                                {severityValue}
                              </StatusBadge>
                              {isManual && <StatusBadge tone="warning">Manual</StatusBadge>}
                            </div>
                            <Input
                              value={current.title}
                              onChange={(event) => updateCheck(index, { title: event.target.value })}
                              className="mt-3 h-11 rounded-lg bg-background text-base font-medium md:text-lg"
                              placeholder="Checklist title"
                            />
                          </div>

                          <div className="grid gap-3 md:w-[270px]">
                            <SelectField
                              label="Severity"
                              value={severityValue}
                              onValueChange={(severity) => updateCheck(index, { severity })}
                              options={[...SEVERITY_OPTIONS]}
                            />
                            <div className="flex items-center gap-2">
                              <Button
                                type="button"
                                variant={isRejected ? "outline" : "secondary"}
                                onClick={() => setDecision(index, "accepted")}
                                className="flex-1 rounded-lg"
                              >
                                <Check data-icon="inline-start" />
                                Accept
                              </Button>
                              <Button
                                type="button"
                                variant={isRejected ? "destructive" : "outline"}
                                onClick={() => setDecision(index, "rejected")}
                                className="flex-1 rounded-lg"
                              >
                                <X data-icon="inline-start" />
                                Reject
                              </Button>
                              {isManual && (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="icon"
                                  onClick={() => removeRow(index)}
                                  aria-label={`Delete ${current.check_id}`}
                                >
                                  <Trash2 />
                                </Button>
                              )}
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              onClick={() => toggleExpanded(current.check_id)}
                              className="rounded-lg md:hidden"
                            >
                              {isExpanded ? "Hide Details" : "Edit Details"}
                            </Button>
                          </div>
                        </div>

                        <div className={`${isExpanded ? "mt-4" : "hidden"} md:mt-4 md:block`}>
                          <div className="grid gap-4 lg:grid-cols-2">
                            <CheckerPanel className="p-4">
                              <SelectField
                                label="Category"
                                value={current.category as ChecklistCategory}
                                onValueChange={(nextCategory) => updateCheck(index, { category: nextCategory })}
                                options={CHECKLIST_CATEGORIES.map((item) => ({ value: item, label: item }))}
                              />
                            </CheckerPanel>
                            <CheckerPanel className="p-4">
                              <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Evidence hint</label>
                              <Textarea
                                value={current.evidence_hint}
                                onChange={(event) => updateCheck(index, { evidence_hint: event.target.value })}
                                rows={4}
                                className="mt-3 min-h-24 rounded-lg bg-background text-sm"
                              />
                            </CheckerPanel>
                          </div>

                          <div className="mt-4 grid gap-4 lg:grid-cols-3">
                            <CheckerPanel className="p-4">
                              <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Legal basis</label>
                              <Textarea
                                value={toText(current.legal_basis)}
                                onChange={(event) => updateCheck(index, { legal_basis: toLines(event.target.value) })}
                                rows={5}
                                className="mt-3 min-h-32 rounded-lg bg-background text-sm"
                                placeholder="One line per legal basis entry"
                              />
                            </CheckerPanel>
                            <CheckerPanel className="p-4">
                              <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Pass criteria</label>
                              <Textarea
                                value={toText(current.pass_criteria)}
                                onChange={(event) => updateCheck(index, { pass_criteria: toLines(event.target.value) })}
                                rows={5}
                                className="mt-3 min-h-32 rounded-lg bg-background text-sm"
                                placeholder="One line per pass condition"
                              />
                            </CheckerPanel>
                            <CheckerPanel className="p-4">
                              <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Fail criteria</label>
                              <Textarea
                                value={toText(current.fail_criteria)}
                                onChange={(event) => updateCheck(index, { fail_criteria: toLines(event.target.value) })}
                                rows={5}
                                className="mt-3 min-h-32 rounded-lg bg-background text-sm"
                                placeholder="One line per fail condition"
                              />
                            </CheckerPanel>
                          </div>

                          <CheckerPanel className="mt-4 p-4">
                            <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Source support</div>
                            <div className="mt-3 grid gap-3">
                              {current.sources.map((source) => {
                                const manualSource = isManualSource(source);
                                return (
                                  <div key={`${source.authority}-${source.source_ref}`} className="rounded-lg border border-border bg-background p-3">
                                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                      <div>
                                        <div className="flex items-center gap-2">
                                          <div className="text-sm font-medium text-foreground">{source.authority}</div>
                                          <StatusBadge>{source.source_type}</StatusBadge>
                                        </div>
                                        <div className="mt-1 text-xs text-muted-foreground">{source.source_ref}</div>
                                      </div>
                                      {!manualSource && (
                                        <a
                                          href={source.source_url}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                                        >
                                          Open Source <ExternalLink className="size-3" />
                                        </a>
                                      )}
                                    </div>
                                    <div className="mt-3 text-sm leading-relaxed text-muted-foreground">{source.source_excerpt}</div>
                                  </div>
                                );
                              })}
                            </div>
                          </CheckerPanel>
                        </div>
                      </div>
                    </CheckerPanel>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="sticky bottom-0 -mx-4 -mb-4 mt-8 flex flex-col gap-3 border-t border-border bg-card/95 px-4 py-4 backdrop-blur md:-mx-5 md:-mb-5 md:px-5 lg:-mx-7 lg:-mb-7 lg:px-7">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-muted-foreground">Only accepted checks will be stored in the approved checklist version.</div>
            <Button
              type="button"
              onClick={() => void handleApprove()}
              disabled={saving || !version.trim() || acceptedCount === 0}
              className="h-10 rounded-lg"
            >
              {saving && <LoaderCircle data-icon="inline-start" className="animate-spin" />}
              {approvedSummary ? "Save Approved Version" : "Approve Checklist"}
            </Button>
          </div>
        </div>
      </CheckerSurface>
    </div>
  );
}
