"use client";

import Link from "next/link";
import { ArrowUpRight, CheckCircle2, CircleAlert, FileText, ListChecks, ShieldCheck } from "lucide-react";

import { StatusBadge } from "@/components/checker-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import type { AnalysisFindingDetail, ApprovalPackResponse, OutputV2Report } from "@/lib/uploadApi";

type PackRecord = Record<string, unknown>;

function asRecords(value: unknown): PackRecord[] {
  return Array.isArray(value) ? value.filter((item): item is PackRecord => !!item && typeof item === "object") : [];
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}

function getPackString(pack: PackRecord, key: string) {
  const value = pack[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function titleize(value: string) {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getTone(value: string): "success" | "warning" | "danger" | "neutral" {
  const normalized = value.toUpperCase();
  if (normalized.includes("HIGH") || normalized.includes("NON")) return "danger";
  if (normalized.includes("MEDIUM") || normalized.includes("PARTIAL")) return "warning";
  if (normalized.includes("LOW") || normalized.includes("COMPLIANT")) return "success";
  return "neutral";
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function TopRisksList({ rows, findings }: { rows: PackRecord[]; findings: AnalysisFindingDetail[] }) {
  const fallbackRows: PackRecord[] = findings
    .filter((finding) => finding.assessment.risk !== "LOW" || finding.assessment.status !== "COMPLIANT")
    .slice(0, 4)
    .map((finding) => ({
      title: finding.title,
      risk: finding.assessment.risk,
      status: finding.assessment.status,
      rationale: finding.assessment.risk_rationale,
    }));
  const displayRows = rows.length ? rows.slice(0, 4) : fallbackRows;

  return (
    <section className="rounded-xl border border-border/70 bg-muted/30 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
          <CircleAlert data-icon="inline-start" />
          Top risks
        </div>
        <Badge variant="outline" className="rounded-full text-[11px]">
          {displayRows.length}
        </Badge>
      </div>

      <div className="mt-4 flex flex-col">
        {displayRows.length ? (
          displayRows.map((row, index) => {
            const title = String(row.title || row.check_id || "Finding");
            const risk = String(row.risk || "LOW");
            const status = String(row.status || "COMPLIANT");
            const rationale = typeof row.rationale === "string" ? row.rationale : null;

            return (
              <div key={`${title}-${index}`} className="border-t border-border/60 py-3 first:border-t-0 first:pt-0 last:pb-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium leading-5 text-foreground">{title}</div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <StatusBadge tone={getTone(risk)}>{risk}</StatusBadge>
                      <StatusBadge tone={getTone(status)}>{status.replaceAll("_", " ")}</StatusBadge>
                    </div>
                  </div>
                </div>
                {rationale ? (
                  <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">
                    {rationale}
                  </p>
                ) : null}
              </div>
            );
          })
        ) : (
          <div className="rounded-lg bg-background/70 px-3 py-2 text-sm text-muted-foreground">
            No material risks were identified in the approved criteria.
          </div>
        )}
      </div>
    </section>
  );
}

function VendorFollowUp({ questions }: { questions: string[] }) {
  return (
    <section className="rounded-xl border border-border/70 bg-muted/30 p-4">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
        <ListChecks data-icon="inline-start" />
        Vendor follow-up
      </div>

      {questions.length ? (
        <ol className="mt-4 flex list-decimal flex-col gap-3 pl-5 text-sm leading-6 text-muted-foreground">
          {questions.slice(0, 6).map((question, index) => (
            <li key={`${question}-${index}`}>{question}</li>
          ))}
        </ol>
      ) : (
        <div className="mt-4 flex items-start gap-3 rounded-lg bg-background/70 px-3 py-3">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--status-compliant)]" />
          <div>
            <div className="text-sm font-medium text-foreground">No vendor follow-up needed</div>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              The current Approval Pack does not include open vendor questions.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function NextActions({ report }: { report?: OutputV2Report | null }) {
  const actions = report?.next_actions ?? [];

  return (
    <section className="rounded-xl border border-border/70 bg-muted/30 p-4">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
        <ShieldCheck data-icon="inline-start" />
        Conditions & next actions
      </div>
      <div className="mt-4 flex flex-col gap-3">
        {actions.length ? (
          actions.slice(0, 5).map((action) => (
            <div key={action} className="flex items-start gap-3 text-sm leading-6 text-muted-foreground">
              <CheckCircle2 className="mt-1 size-3.5 shrink-0 text-[var(--status-compliant)]" />
              <span>{action}</span>
            </div>
          ))
        ) : (
          <div className="text-sm leading-6 text-muted-foreground">
            No additional next actions were generated for this approval.
          </div>
        )}
      </div>
    </section>
  );
}

export function ApprovalPackView({
  approvalPack,
  report,
  findings,
  projectId,
}: {
  approvalPack: ApprovalPackResponse;
  report?: OutputV2Report | null;
  findings: AnalysisFindingDetail[];
  projectId: string;
}) {
  const pack = approvalPack.pack as PackRecord;
  const topRisks = asRecords(pack.top_risks);
  const vendorQuestions = asStrings(pack.vendor_questions);
  const internalMemo = getPackString(pack, "internal_memo");
  const generatedAt = formatDate(approvalPack.published_at || approvalPack.updated_at || approvalPack.created_at);
  const recommendation = titleize(String(approvalPack.recommendation || "approve"));
  const confidence = Math.round(approvalPack.confidence * 100);

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl border border-border/70 bg-card/95 p-5 shadow-sm md:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Approval Pack
            </div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{recommendation}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">
              {approvalPack.recommendation_summary}
            </p>
          </div>

          <div className="grid min-w-[240px] grid-cols-2 rounded-xl border border-border/70 bg-muted/30 text-sm">
            <div className="p-3">
              <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Confidence
              </div>
              <div className="mt-2 text-2xl font-semibold text-foreground">{confidence}%</div>
            </div>
            <div className="border-l border-border/70 p-3">
              <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Review required
              </div>
              <div className="mt-2 text-2xl font-semibold text-foreground">
                {approvalPack.review_required ? "Yes" : "No"}
              </div>
            </div>
          </div>
        </div>

        <Separator className="my-5" />

        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.55fr)]">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              <FileText data-icon="inline-start" />
              Executive summary
            </div>
            <div className="mt-3 text-sm leading-7 text-muted-foreground">
              {internalMemo || report?.risk_rationale || approvalPack.recommendation_summary}
            </div>
          </div>
          <div className="self-start rounded-xl border border-border/70 bg-muted/30 p-4">
            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Generated
            </div>
            <div className="mt-2 text-sm text-foreground">{generatedAt || "Recently"}</div>
            <div className="mt-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Version
            </div>
            <div className="mt-2 text-sm text-foreground">{approvalPack.version}</div>
          </div>
        </div>
      </section>

      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.72fr)]">
        <TopRisksList rows={topRisks} findings={findings} />
        <div className="grid gap-4">
          <VendorFollowUp questions={vendorQuestions} />
          <NextActions report={report} />
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border/70 bg-card/80 p-4 md:flex-row md:items-center md:justify-between">
        <div className="text-sm leading-6 text-muted-foreground">
          The detailed report remains available as an evidence view for criteria-by-criteria review.
        </div>
        <Button render={<Link href={`/vendor-reviews/${projectId}/review/report?view=findings`} />} variant="outline" className="shrink-0">
          Detailed findings
          <ArrowUpRight data-icon="inline-end" />
        </Button>
      </div>
    </div>
  );
}
