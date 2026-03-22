import {
  AlignmentType,
  BorderStyle,
  Document,
  HeadingLevel,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";
import type { AnalysisFindingDetail, ChecklistItem, OutputV2Report } from "@/lib/uploadApi";

const COLORS = {
  text: "1F2937",
  muted: "6B7280",
  border: "D1D5DB",
  accent: "1D4ED8",
  surface: "F3F4F6",
  success: "065F46",
  warning: "92400E",
  danger: "991B1B",
};

type KpiItem = {
  label: string;
  value: string;
};

type ChecklistExportInput = {
  projectName: string;
  version: string;
  changeNote?: string | null;
  selectedSourceIds: string[];
  checks: ChecklistItem[];
  acceptedCount: number;
  rejectedCount: number;
};

type FinalReportExportInput = {
  projectName: string;
  elapsed?: string | null;
  report: OutputV2Report;
  findings: AnalysisFindingDetail[];
};

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "export";
}

function borderlessCell(children: Paragraph[]) {
  return new TableCell({
    children,
    width: { size: 20, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
      bottom: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
      left: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
      right: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
    },
    margins: { top: 120, bottom: 120, left: 140, right: 140 },
    shading: { fill: "FFFFFF" },
  });
}

function kpiTable(items: KpiItem[]) {
  const cells = items.map((item) =>
    borderlessCell([
      new Paragraph({
        children: [new TextRun({ text: item.label.toUpperCase(), color: COLORS.muted, size: 18, bold: true })],
      }),
      new Paragraph({
        spacing: { before: 80 },
        children: [new TextRun({ text: item.value, color: COLORS.text, size: 28, bold: true })],
      }),
    ]),
  );

  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [new TableRow({ children: cells })],
  });
}

function detailTable(rows: Array<[string, string]>) {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: rows.map(([label, value]) =>
      new TableRow({
        children: [
          new TableCell({
            children: [new Paragraph({ children: [new TextRun({ text: label, bold: true, color: COLORS.muted })] })],
            width: { size: 28, type: WidthType.PERCENTAGE },
            shading: { fill: COLORS.surface },
            borders: {
              top: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
              bottom: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
              left: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
              right: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
            },
            margins: { top: 90, bottom: 90, left: 120, right: 120 },
          }),
          new TableCell({
            children: [new Paragraph({ children: [new TextRun({ text: value || "-" })] })],
            width: { size: 72, type: WidthType.PERCENTAGE },
            borders: {
              top: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
              bottom: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
              left: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
              right: { style: BorderStyle.SINGLE, color: COLORS.border, size: 1 },
            },
            margins: { top: 90, bottom: 90, left: 120, right: 120 },
          }),
        ],
      }),
    ),
  });
}

function heading(text: string, level: (typeof HeadingLevel)[keyof typeof HeadingLevel], spacingBefore = 240) {
  return new Paragraph({
    heading: level,
    spacing: { before: spacingBefore, after: 120 },
    children: [new TextRun({ text, color: COLORS.text })],
  });
}

function body(text: string) {
  return new Paragraph({
    spacing: { after: 100 },
    children: [new TextRun({ text, color: COLORS.text, size: 22 })],
  });
}

function bullets(items: string[]) {
  if (!items.length) {
    return [new Paragraph({ children: [new TextRun({ text: "None.", color: COLORS.muted })] })];
  }
  return items.map(
    (item) =>
      new Paragraph({
        bullet: { level: 0 },
        spacing: { after: 80 },
        children: [new TextRun({ text: item, color: COLORS.text, size: 22 })],
      }),
  );
}

function sourceParagraphs(check: ChecklistItem) {
  if (!check.sources.length) {
    return [new Paragraph({ children: [new TextRun({ text: "No source support attached.", color: COLORS.muted })] })];
  }
  return check.sources.flatMap((source) => [
    new Paragraph({
      spacing: { before: 80 },
      children: [new TextRun({ text: `${source.authority} — ${source.source_ref}`, bold: true, color: COLORS.text })],
    }),
    new Paragraph({
      children: [new TextRun({ text: source.source_excerpt, color: COLORS.text, size: 22 })],
    }),
    new Paragraph({
      children: [new TextRun({ text: source.source_url, color: COLORS.accent, size: 20 })],
    }),
  ]);
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function groupedChecklistChecks(checks: ChecklistItem[]) {
  const groups = new Map<string, ChecklistItem[]>();
  for (const check of checks) {
    const category = check.category || "Other";
    const existing = groups.get(category) || [];
    existing.push(check);
    groups.set(category, existing);
  }
  return Array.from(groups.entries());
}

export async function downloadChecklistDocx(input: ChecklistExportInput) {
  const categories = new Set(input.checks.map((check) => check.category || "Other"));
  const mandatoryCount = input.checks.filter((check) => String(check.severity).toUpperCase() === "MANDATORY").length;
  const highSeverityCount = input.checks.filter((check) => ["HIGH", "MANDATORY"].includes(String(check.severity).toUpperCase())).length;

  const children: Array<Paragraph | Table> = [
    heading("Approved Checklist", HeadingLevel.TITLE, 0),
    body(`Project: ${input.projectName}`),
    detailTable([
      ["Version", input.version],
      ["Generated", new Date().toLocaleString()],
      ["Change Note", input.changeNote?.trim() || "No change note recorded"],
    ]),
    heading("KPI Summary", HeadingLevel.HEADING_1),
    kpiTable([
      { label: "Total Checks", value: String(input.checks.length) },
      { label: "Accepted", value: String(input.acceptedCount) },
      { label: "Rejected", value: String(input.rejectedCount) },
      { label: "Categories", value: String(categories.size) },
      { label: "High / Mandatory", value: String(highSeverityCount || mandatoryCount) },
    ]),
    heading("Selected Sources", HeadingLevel.HEADING_1),
    body(`Reference source count: ${input.selectedSourceIds.length}`),
    ...bullets(input.selectedSourceIds),
  ];

  for (const [category, checks] of groupedChecklistChecks(input.checks)) {
    children.push(heading(category, HeadingLevel.HEADING_1));
    for (const check of checks) {
      children.push(
        heading(`${check.check_id} — ${check.title}`, HeadingLevel.HEADING_2),
        detailTable([
          ["Severity", String(check.severity)],
          ["Required", check.required ? "Yes" : "No"],
          ["Category", check.category],
        ]),
        heading("Evidence Hint", HeadingLevel.HEADING_3),
        body(check.evidence_hint),
        heading("Legal Basis", HeadingLevel.HEADING_3),
        ...bullets(check.legal_basis),
        heading("Pass Criteria", HeadingLevel.HEADING_3),
        ...bullets(check.pass_criteria),
        heading("Fail Criteria", HeadingLevel.HEADING_3),
        ...bullets(check.fail_criteria),
        heading("Source Support", HeadingLevel.HEADING_3),
        ...sourceParagraphs(check),
      );
    }
  }

  const document = new Document({
    creator: "Merlin AI",
    title: `Approved Checklist - ${input.projectName}`,
    sections: [{ children }],
  });

  const blob = await Packer.toBlob(document);
  saveBlob(blob, `${slugify(input.projectName)}_approved_checklist_v${slugify(input.version)}.docx`);
}

function countFindingStatuses(findings: AnalysisFindingDetail[]) {
  const counts = { compliant: 0, nonCompliant: 0, partial: 0, unknown: 0 };
  for (const finding of findings) {
    switch (finding.assessment.status) {
      case "COMPLIANT":
        counts.compliant += 1;
        break;
      case "NON_COMPLIANT":
        counts.nonCompliant += 1;
        break;
      case "PARTIAL":
        counts.partial += 1;
        break;
      default:
        counts.unknown += 1;
    }
  }
  return counts;
}

export async function downloadFinalReportDocx(input: FinalReportExportInput) {
  const counts = countFindingStatuses(input.findings);
  const children: Array<Paragraph | Table> = [
    heading("Final Review Report", HeadingLevel.TITLE, 0),
    body(`Project: ${input.projectName}`),
    detailTable([
      ["Generated", new Date().toLocaleString()],
      ["Run ID", input.report.run_id],
      ["Model", input.report.model_version],
      ["Policy Version", input.report.policy_version],
      ["Elapsed", input.elapsed || "Unavailable"],
    ]),
    heading("KPI Summary", HeadingLevel.HEADING_1),
    kpiTable([
      { label: "Total Checks", value: String(input.report.checks.length) },
      { label: "Compliant", value: String(counts.compliant) },
      { label: "Needs Attention", value: String(counts.nonCompliant + counts.partial + counts.unknown) },
      { label: "Overall Risk", value: input.report.overall.risk_level },
      { label: "Confidence", value: `${Math.round(input.report.confidence * 100)}%` },
    ]),
    heading("Executive Summary", HeadingLevel.HEADING_1),
    body(input.report.overall.summary),
    body(input.report.risk_rationale),
    heading("Highlights", HeadingLevel.HEADING_1),
    ...bullets(input.report.highlights),
    heading("Next Actions", HeadingLevel.HEADING_1),
    ...bullets(input.report.next_actions),
  ];

  for (const finding of input.findings) {
    children.push(
      heading(`${finding.check_id} — ${finding.title}`, HeadingLevel.HEADING_2),
      detailTable([
        ["Category", finding.category],
        ["Status", finding.assessment.status],
        ["Risk", finding.assessment.risk],
        ["Confidence", `${Math.round(finding.assessment.confidence * 100)}%`],
        ["Citation Pages", finding.citation_pages.join(", ") || "None"],
      ]),
      heading("Assessment Rationale", HeadingLevel.HEADING_3),
      body(finding.assessment.risk_rationale),
      heading("Evidence Quotes", HeadingLevel.HEADING_3),
      ...(
        finding.assessment.evidence_quotes.length
          ? finding.assessment.evidence_quotes.flatMap((quote) => [
              new Paragraph({
                children: [new TextRun({ text: `Page ${quote.page}`, bold: true, color: COLORS.muted })],
                spacing: { before: 80, after: 40 },
              }),
              body(quote.quote),
            ])
          : [new Paragraph({ children: [new TextRun({ text: "No evidence quotes attached.", color: COLORS.muted })] })]
      ),
      heading("Knowledge Base Citations", HeadingLevel.HEADING_3),
      ...(
        finding.assessment.kb_citations.length
          ? finding.assessment.kb_citations.flatMap((citation) => [
              new Paragraph({
                children: [new TextRun({ text: `${citation.source_ref} (${citation.source_id})`, bold: true, color: COLORS.text })],
                spacing: { before: 80, after: 40 },
              }),
              body(citation.source_excerpt),
            ])
          : [new Paragraph({ children: [new TextRun({ text: "No KB citations attached.", color: COLORS.muted })] })]
      ),
    );

    if (finding.assessment.missing_elements.length) {
      children.push(heading("Missing Elements", HeadingLevel.HEADING_3), ...bullets(finding.assessment.missing_elements));
    }
  }

  const document = new Document({
    creator: "Merlin AI",
    title: `Final Review Report - ${input.projectName}`,
    sections: [{ children }],
  });

  const blob = await Packer.toBlob(document);
  saveBlob(blob, `${slugify(input.projectName)}_final_review_report.docx`);
}
