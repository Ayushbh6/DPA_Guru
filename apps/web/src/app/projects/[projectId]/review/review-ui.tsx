"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  Clock3,
  FileText,
  LoaderCircle,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { getProjectDocumentViewerUrl, type AnalysisFindingDetail, type OutputV2Report } from "@/lib/uploadApi";

export const REVIEW_STAGE_LABELS: Record<string, string> = {
  QUEUED: "Queued",
  PREFETCHING_EVIDENCE: "Gathering Evidence",
  REVIEWING_CHECKS: "Reviewing Checks",
  SYNTHESIZING: "Finalizing Report",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

const STATUS_STYLES: Record<string, string> = {
  COMPLIANT: "border-emerald-400/25 bg-emerald-400/10 text-emerald-100",
  NON_COMPLIANT: "border-red-400/25 bg-red-400/10 text-red-100",
  PARTIAL: "border-amber-400/25 bg-amber-400/10 text-amber-100",
  UNKNOWN: "border-neutral-400/20 bg-neutral-400/10 text-neutral-500",
};

const RISK_STYLES: Record<string, string> = {
  LOW: "border-sky-400/25 bg-sky-400/10 text-sky-100",
  MEDIUM: "border-amber-400/25 bg-amber-400/10 text-amber-100",
  HIGH: "border-red-400/25 bg-red-400/10 text-red-100",
};

function getTimestampMs(value?: string | null) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

export function formatPercent(value: number) {
  return `${Math.max(0, Math.min(100, Math.round(value)))}%`;
}

export function formatReviewStage(stage: string | undefined, status: string | undefined) {
  if (!stage) return status || "Queued";
  return REVIEW_STAGE_LABELS[stage] || stage.replaceAll("_", " ");
}

export function formatElapsedMs(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const seconds = totalSeconds % 60;
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const hours = Math.floor(totalSeconds / 3600);
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function useReviewElapsed(startedAt?: string | null, completedAt?: string | null, active = false) {
  const startedMs = useMemo(() => getTimestampMs(startedAt), [startedAt]);
  const completedMs = useMemo(() => getTimestampMs(completedAt), [completedAt]);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [active]);

  const endMs = completedMs ?? now;
  if (!startedMs) return "00:00";
  return formatElapsedMs(endMs - startedMs);
}

function badgeClass(base: string, value: string, styles: Record<string, string>) {
  return `${base} ${styles[value] ?? "border-neutral-400/20 bg-neutral-400/10 text-neutral-500"}`;
}

export function StatusBadge({ value }: { value: string }) {
  return (
    <span
      className={badgeClass(
        "inline-flex items-center rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.18em]",
        value,
        STATUS_STYLES,
      )}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function RiskBadge({ value }: { value: string }) {
  return (
    <span
      className={badgeClass(
        "inline-flex items-center rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.18em]",
        value,
        RISK_STYLES,
      )}
    >
      {value}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: number }) {
  const percent = Math.round(value * 100);
  const tone =
    percent >= 85
      ? "border-emerald-400/20 bg-emerald-400/8 text-emerald-100"
      : percent >= 60
        ? "border-amber-400/20 bg-amber-400/8 text-amber-100"
        : "border-red-400/20 bg-red-400/8 text-red-100";
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.18em] ${tone}`}>
      {percent}% confidence
    </span>
  );
}

function findingBorderTone(finding: AnalysisFindingDetail) {
  if (finding.assessment.status === "NON_COMPLIANT") return "border-red-400/20";
  if (finding.assessment.status === "PARTIAL") return "border-amber-400/20";
  if (finding.assessment.status === "COMPLIANT") return "border-emerald-400/20";
  return "border-neutral-400/20";
}

export function ReviewHero({
  report,
  elapsed,
}: {
  report: OutputV2Report;
  elapsed: string;
}) {
  const riskTone =
    report.overall.risk_level === "HIGH"
      ? "border-red-400/20 bg-red-400/10 text-red-100"
      : report.overall.risk_level === "MEDIUM"
        ? "border-amber-400/20 bg-amber-400/10 text-amber-100"
        : "border-emerald-400/20 bg-emerald-400/10 text-emerald-100";

  return (
    <section className="relative overflow-hidden px-6 py-7 md:px-8 md:py-8" style={{ border: '1px solid var(--line)', background: 'var(--bg-1)' }}>
      <div className="relative z-10 grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_320px]">
        <div>
          <div
            className="inline-flex items-center gap-2 px-3 py-1 text-[11px] uppercase tracking-[0.2em]"
            style={{ border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Final Review Report
          </div>
          <h2 className="mt-5 max-w-4xl text-3xl font-semibold leading-tight md:text-[2.5rem]" style={{ color: 'var(--text)' }}>
            {report.overall.summary}
          </h2>
          <p className="mt-5 max-w-4xl text-sm leading-7 md:text-[15px]" style={{ color: 'var(--text-2)' }}>{report.risk_rationale}</p>
        </div>

        <div className="grid gap-3">
          <div className={`border px-5 py-4 ${riskTone}`}>
            <div className="text-[10px] uppercase tracking-[0.18em] text-inherit/70">Overall Risk</div>
            <div className="mt-3 text-2xl font-semibold">{report.overall.risk_level}</div>
            <div className="mt-2 text-sm text-inherit/75">Score {Math.round(report.overall.score)}</div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="px-4 py-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                <Clock3 className="h-3.5 w-3.5" />
                Review Time
              </div>
              <div className="mt-3 text-xl font-medium" style={{ color: 'var(--text)' }}>{elapsed}</div>
            </div>
            <div className="px-4 py-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
              <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Coverage</div>
              <div className="mt-3 text-xl font-medium" style={{ color: 'var(--text)' }}>{report.checks.length} checks</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ReviewReportView({
  report,
  findings,
  elapsed,
  projectId,
  documentId,
  documentMimeType,
}: {
  report: OutputV2Report;
  findings: AnalysisFindingDetail[];
  elapsed: string;
  projectId: string;
  documentId?: string | null;
  documentMimeType?: string | null;
}) {
  const supportsPageJump = !!documentId && (documentMimeType ?? "").toLowerCase() === "application/pdf";
  const supportsDocumentOpen = !!documentId;

  return (
    <div className="grid gap-6 pb-6">
      <ReviewHero report={report} elapsed={elapsed} />

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="grid gap-6">
          <div className="p-6 md:p-7" style={{ border: '1px solid var(--line)', background: 'var(--bg-1)' }}>
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Highlights</div>
                <div className="mt-4 grid gap-3">
                  {report.highlights.map((item) => (
                    <div key={item} className="border-l border-emerald-400/40 pl-4 text-sm leading-7" style={{ color: 'var(--text-2)' }}>
                      {item}
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Next Actions</div>
                <div className="mt-4 grid gap-3">
                  {report.next_actions.map((item) => (
                    <div key={item} className="border-l border-amber-400/40 pl-4 text-sm leading-7" style={{ color: 'var(--text-2)' }}>
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <section className="grid gap-4">
            {findings.map((finding) => (
              <article
                key={finding.check_id}
                className={`border p-5 md:p-6 ${findingBorderTone(finding)}`}
                style={{ background: 'var(--bg-1)' }}
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>{finding.check_id}</div>
                    <h3 className="mt-3 text-2xl leading-tight" style={{ color: 'var(--text)' }}>{finding.title}</h3>
                    <div className="mt-2 text-sm" style={{ color: 'var(--text-3)' }}>{finding.category}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge value={finding.assessment.status} />
                    <RiskBadge value={finding.assessment.risk} />
                    <ConfidenceBadge value={finding.assessment.confidence} />
                  </div>
                </div>

                <div className="mt-6 text-sm leading-8" style={{ color: 'var(--text-2)' }}>{finding.assessment.risk_rationale}</div>

                {finding.assessment.abstain_reason && (
                  <div className="mt-5 flex gap-3 border border-amber-400/15 bg-amber-400/7 p-4 text-sm text-amber-50/85">
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>{finding.assessment.abstain_reason}</div>
                  </div>
                )}

                <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
                  <div className="grid gap-5">
                    {!!finding.assessment.evidence_quotes.length && (
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Evidence Quotes</div>
                        <div className="mt-3 grid gap-3">
                          {finding.assessment.evidence_quotes.map((quote, index) => (
                            <div key={`${finding.check_id}-${quote.page}-${index}`} className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                              <div className="flex items-center justify-between gap-4">
                                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Page {quote.page}</div>
                                {supportsDocumentOpen ? (
                                  <a
                                    href={getProjectDocumentViewerUrl(projectId, supportsPageJump ? quote.page : undefined)}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center gap-1 text-[10px] uppercase tracking-[0.18em] transition-colors"
                                    style={{ color: 'var(--text-3)' }}
                                    onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-2)')}
                                    onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                                  >
                                    Open in DPA
                                    <ArrowUpRight className="h-3 w-3" />
                                  </a>
                                ) : null}
                              </div>
                              <div className="mt-3 text-sm leading-8" style={{ color: 'var(--text-2)' }}>{quote.quote}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {!!finding.assessment.kb_citations.length && (
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Knowledge Base Citations</div>
                        <div className="mt-3 grid gap-3">
                          {finding.assessment.kb_citations.map((citation, index) => (
                            <div key={`${finding.check_id}-${citation.source_id}-${index}`} className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                              <div className="flex items-start justify-between gap-4">
                                <div>
                                  <div className="text-sm" style={{ color: 'var(--text)' }}>{citation.source_ref}</div>
                                  <div className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>{citation.source_id}</div>
                                </div>
                              </div>
                              <div className="mt-3 text-sm leading-8" style={{ color: 'var(--text-2)' }}>{citation.source_excerpt}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <aside className="grid content-start gap-3">
                    <div className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                      <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Citation Pages</div>
                      <div className="mt-3 text-sm" style={{ color: 'var(--text)' }}>
                        {finding.citation_pages.length ? finding.citation_pages.join(", ") : "No mapped pages"}
                      </div>
                    </div>
                    {!!finding.assessment.missing_elements.length && (
                      <div className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                        <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Missing Elements</div>
                        <div className="mt-3 grid gap-2">
                          {finding.assessment.missing_elements.map((item) => (
                            <div key={`${finding.check_id}-${item}`} className="text-sm leading-7" style={{ color: 'var(--text-2)' }}>
                              {item}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </aside>
                </div>
              </article>
            ))}
          </section>
        </div>

        <aside className="grid content-start gap-4 xl:sticky xl:top-0">
          <div className="p-5" style={{ border: '1px solid var(--line)', background: 'var(--bg-1)' }}>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
              <FileText className="h-3.5 w-3.5" />
              Report Snapshot
            </div>
            <div className="mt-4 grid gap-3">
              <div className="px-4 py-3" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Overall Confidence</div>
                <div className="mt-2 text-lg" style={{ color: 'var(--text)' }}>{Math.round(report.confidence * 100)}%</div>
              </div>
              <div className="px-4 py-3" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Review State</div>
                <div className="mt-2 text-lg" style={{ color: 'var(--text)' }}>{report.review_state}</div>
              </div>
              <div className="px-4 py-3" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Review Required</div>
                <div className="mt-2 text-lg" style={{ color: 'var(--text)' }}>{report.review_required ? "Yes" : "No"}</div>
              </div>
            </div>
          </div>

          <Link
            href={`/projects/${projectId}/review`}
            className="inline-flex items-center justify-between border px-4 py-3 text-sm transition-colors"
            style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
          >
            <span>Back to Review Control</span>
            <ArrowUpRight className="h-4 w-4" />
          </Link>
        </aside>
      </section>
    </div>
  );
}

export function ReportUnavailable({
  title,
  body,
  cta,
}: {
  title: string;
  body: string;
  cta?: React.ReactNode;
}) {
  return (
    <section className="border px-6 py-8 md:px-8" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)' }}>
      <div className="max-w-2xl">
        <div className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.2em]" style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-3)' }}>
          <ShieldAlert className="h-3.5 w-3.5" />
          Final Review
        </div>
        <h2 className="mt-5 text-2xl font-semibold" style={{ color: 'var(--text)' }}>{title}</h2>
        <p className="mt-3 text-sm leading-7" style={{ color: 'var(--text-2)' }}>{body}</p>
        {cta ? <div className="mt-6">{cta}</div> : null}
      </div>
    </section>
  );
}

export function ReportLoadError({ message }: { message: string }) {
  return (
    <div className="flex gap-3 border border-red-400/20 bg-red-400/6 p-4 text-sm text-red-100/85">
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{message}</div>
    </div>
  );
}

export function ReportLoadingState() {
  return (
    <div className="flex items-center gap-3 border p-6" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)', color: 'var(--text-2)' }}>
      <LoaderCircle className="h-4 w-4 animate-spin" />
      Preparing the full review report...
    </div>
  );
}
