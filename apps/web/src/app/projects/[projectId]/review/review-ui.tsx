"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
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

function statusTokens(value: string): React.CSSProperties {
  const map: Record<string, { color: string; bg: string }> = {
    COMPLIANT:     { color: 'var(--status-compliant)',    bg: 'var(--status-compliant-bg)' },
    NON_COMPLIANT: { color: 'var(--status-noncompliant)', bg: 'var(--status-noncompliant-bg)' },
    PARTIAL:       { color: 'var(--status-partial)',      bg: 'var(--status-partial-bg)' },
    UNKNOWN:       { color: 'var(--status-unknown)',      bg: 'var(--status-unknown-bg)' },
  };
  const t = map[value] ?? map.UNKNOWN;
  return { color: t.color, background: t.bg, borderColor: t.color };
}

function riskTokens(value: string): React.CSSProperties {
  const map: Record<string, { color: string; bg: string }> = {
    LOW:    { color: 'var(--risk-low)',    bg: 'var(--risk-low-bg)' },
    MEDIUM: { color: 'var(--risk-medium)', bg: 'var(--risk-medium-bg)' },
    HIGH:   { color: 'var(--risk-high)',   bg: 'var(--risk-high-bg)' },
  };
  const t = map[value] ?? { color: 'var(--status-unknown)', bg: 'var(--status-unknown-bg)' };
  return { color: t.color, background: t.bg, borderColor: t.color };
}

function confidenceTokens(percent: number): React.CSSProperties {
  if (percent >= 85) return { color: 'var(--status-compliant)', background: 'var(--status-compliant-bg)', borderColor: 'var(--status-compliant)' };
  if (percent >= 60) return { color: 'var(--status-partial)', background: 'var(--status-partial-bg)', borderColor: 'var(--status-partial)' };
  return { color: 'var(--status-noncompliant)', background: 'var(--status-noncompliant-bg)', borderColor: 'var(--status-noncompliant)' };
}

function findingLeftColor(status: string): string {
  if (status === "NON_COMPLIANT") return 'var(--status-noncompliant)';
  if (status === "PARTIAL") return 'var(--status-partial)';
  if (status === "COMPLIANT") return 'var(--status-compliant)';
  return 'var(--status-unknown)';
}

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

export function StatusBadge({ value }: { value: string }) {
  return (
    <span
      className="inline-flex items-center border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]"
      style={statusTokens(value)}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function RiskBadge({ value }: { value: string }) {
  return (
    <span
      className="inline-flex items-center border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]"
      style={riskTokens(value)}
    >
      {value}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: number }) {
  const percent = Math.round(value * 100);
  return (
    <span
      className="inline-flex items-center border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]"
      style={confidenceTokens(percent)}
    >
      {percent}% confidence
    </span>
  );
}

export function ReviewHero({
  report,
  elapsed,
}: {
  report: OutputV2Report;
  elapsed: string;
}) {
  const riskStyle = riskTokens(report.overall.risk_level);

  return (
    <section className="relative overflow-hidden" style={{ border: '1px solid var(--line)', background: 'var(--bg-1)' }}>
      {/* Risk-colored top accent bar */}
      <div className="h-1" style={{ background: findingLeftColor(report.overall.risk_level === "HIGH" ? "NON_COMPLIANT" : report.overall.risk_level === "MEDIUM" ? "PARTIAL" : "COMPLIANT") }} />

      <div className="px-6 py-7 md:px-8 md:py-8">
        <div className="relative z-10 grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_340px]">
          <div>
            <div
              className="inline-flex items-center gap-2 px-3 py-1.5 text-[11px] uppercase tracking-[0.2em]"
              style={{ border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Final Review Report
            </div>
            <h2 className="mt-5 max-w-4xl text-3xl font-semibold leading-tight md:text-[2.6rem] md:leading-[1.15]" style={{ color: 'var(--text)' }}>
              {report.overall.summary}
            </h2>
            <p className="mt-5 max-w-4xl text-[15px] leading-7" style={{ color: 'var(--text-2)' }}>{report.risk_rationale}</p>
          </div>

          <div className="grid gap-3">
            <div className="border px-5 py-5" style={{ ...riskStyle, borderColor: riskStyle.borderColor }}>
              <div className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ opacity: 0.75 }}>Overall Risk</div>
              <div className="mt-3 text-3xl font-bold">{report.overall.risk_level}</div>
              <div className="mt-2 text-sm" style={{ opacity: 0.8 }}>Score {Math.round(report.overall.score)}</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="px-4 py-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                  <Clock3 className="h-3.5 w-3.5" />
                  Review Time
                </div>
                <div className="mt-3 text-xl font-semibold" style={{ color: 'var(--text)' }}>{elapsed}</div>
              </div>
              <div className="px-4 py-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Coverage</div>
                <div className="mt-3 text-xl font-semibold" style={{ color: 'var(--text)' }}>{report.checks.length} checks</div>
              </div>
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
                <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                  <CheckCircle2 className="h-3.5 w-3.5" style={{ color: 'var(--status-compliant)' }} />
                  Highlights
                </div>
                <div className="mt-4 grid gap-3">
                  {report.highlights.map((item) => (
                    <div key={item} className="border-l-2 pl-4 text-[15px] leading-7" style={{ borderColor: 'var(--status-compliant)', color: 'var(--text-2)' }}>
                      {item}
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                  <ArrowRight className="h-3.5 w-3.5" style={{ color: 'var(--warning)' }} />
                  Next Actions
                </div>
                <div className="mt-4 grid gap-3">
                  {report.next_actions.map((item) => (
                    <div key={item} className="border-l-2 pl-4 text-[15px] leading-7" style={{ borderColor: 'var(--warning)', color: 'var(--text-2)' }}>
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <section className="grid gap-4">
            {findings.map((finding, findingIdx) => (
              <article
                key={finding.check_id}
                className="border overflow-hidden"
                style={{ background: 'var(--bg-1)', borderColor: 'var(--line)' }}
              >
                {/* Colored left accent strip */}
                <div className="flex min-h-0">
                  <div className="w-1 shrink-0" style={{ background: findingLeftColor(finding.assessment.status) }} />
                  <div className="flex-1 p-5 md:p-6">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <div className="flex items-center gap-3">
                          <span className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>{finding.check_id}</span>
                          <span className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>{findingIdx + 1} of {findings.length}</span>
                        </div>
                        <h3 className="mt-3 text-2xl leading-tight" style={{ color: 'var(--text)' }}>{finding.title}</h3>
                        <div className="mt-2 text-sm" style={{ color: 'var(--text-3)' }}>{finding.category}</div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <StatusBadge value={finding.assessment.status} />
                        <RiskBadge value={finding.assessment.risk} />
                        <ConfidenceBadge value={finding.assessment.confidence} />
                      </div>
                    </div>

                    <div className="mt-6 text-[15px] leading-8" style={{ color: 'var(--text-2)' }}>{finding.assessment.risk_rationale}</div>

                    {finding.assessment.abstain_reason && (
                      <div className="mt-5 flex gap-3 border p-4 text-sm" style={{ borderColor: 'var(--warning)', background: 'var(--warning-bg)', color: 'var(--warning)' }}>
                        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                        <div>{finding.assessment.abstain_reason}</div>
                      </div>
                    )}

                <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
                  <div className="grid gap-5">
                    {!!finding.assessment.evidence_quotes.length && (
                      <div>
                        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                          <FileText className="h-3.5 w-3.5" />
                          Evidence Quotes
                        </div>
                        <div className="mt-3 grid gap-3">
                          {finding.assessment.evidence_quotes.map((quote, index) => (
                            <div key={`${finding.check_id}-${quote.page}-${index}`} className="border-l-2 p-4" style={{ borderColor: findingLeftColor(finding.assessment.status), background: 'var(--bg)' }}>
                              <div className="flex items-center justify-between gap-4">
                                <div className="inline-flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                                  <span className="inline-flex items-center justify-center h-5 w-5 text-[9px] font-bold" style={{ background: 'var(--bg-2)', color: 'var(--text-2)' }}>P{quote.page}</span>
                                  Page {quote.page}
                                </div>
                                {supportsDocumentOpen ? (
                                  <a
                                    href={getProjectDocumentViewerUrl(projectId, supportsPageJump ? quote.page : undefined)}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.18em] transition-colors"
                                    style={{ color: 'var(--text-3)' }}
                                    onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-2)')}
                                    onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                                  >
                                    Open in DPA
                                    <ArrowUpRight className="h-3 w-3" />
                                  </a>
                                ) : null}
                              </div>
                              <div className="mt-3 text-sm italic leading-8" style={{ color: 'var(--text-2)' }}>{quote.quote}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {!!finding.assessment.kb_citations.length && (
                      <div className="mt-2">
                        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
                          <BookOpen className="h-3.5 w-3.5" />
                          Knowledge Base Citations
                        </div>
                        <div className="mt-3 grid gap-3">
                          {finding.assessment.kb_citations.map((citation, index) => (
                            <div key={`${finding.check_id}-${citation.source_id}-${index}`} className="border-l-2 p-4" style={{ borderColor: 'var(--accent)', background: 'var(--bg)' }}>
                              <div className="flex items-start justify-between gap-4">
                                <div>
                                  <div className="text-sm font-medium" style={{ color: 'var(--text)' }}>{citation.source_ref}</div>
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
                      <div className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Citation Pages</div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {finding.citation_pages.length ? finding.citation_pages.map((p) => (
                          <span key={p} className="inline-flex items-center justify-center border px-2.5 py-1 text-xs font-medium" style={{ borderColor: 'var(--line-2)', background: 'var(--bg-2)', color: 'var(--text)' }}>
                            {p}
                          </span>
                        )) : <span className="text-sm" style={{ color: 'var(--text-3)' }}>No mapped pages</span>}
                      </div>
                    </div>
                    {!!finding.assessment.missing_elements.length && (
                      <div className="p-4" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--danger)' }}>
                          <TriangleAlert className="h-3 w-3" />
                          Missing Elements
                        </div>
                        <div className="mt-3 grid gap-2">
                          {finding.assessment.missing_elements.map((item) => (
                            <div key={`${finding.check_id}-${item}`} className="border-l-2 pl-3 text-sm leading-7" style={{ borderColor: 'var(--danger)', color: 'var(--text-2)' }}>
                              {item}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </aside>
                </div>
              </div>{/* end flex-1 content */}
                </div>{/* end flex row with left strip */}
              </article>
            ))}
          </section>
        </div>

        <aside className="grid content-start gap-4 xl:sticky xl:top-0">
          <div className="p-5" style={{ border: '1px solid var(--line)', background: 'var(--bg-1)' }}>
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>
              <FileText className="h-3.5 w-3.5" />
              Report Snapshot
            </div>
            <div className="mt-4 grid gap-3">
              <div className="px-4 py-3" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Overall Confidence</div>
                <div className="mt-2 text-lg font-semibold" style={{ color: confidenceTokens(Math.round(report.confidence * 100)).color }}>{Math.round(report.confidence * 100)}%</div>
                <div className="mt-2 h-1.5 w-full overflow-hidden" style={{ background: 'var(--bg-2)' }}>
                  <div className="h-full" style={{ width: `${Math.round(report.confidence * 100)}%`, background: confidenceTokens(Math.round(report.confidence * 100)).color }} />
                </div>
              </div>
              <div className="px-4 py-3" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Review State</div>
                <div className="mt-2 text-lg" style={{ color: 'var(--text)' }}>{report.review_state}</div>
              </div>
              <div className="px-4 py-3" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }}>
                <div className="text-[11px] font-medium uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>Review Required</div>
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
    <div className="flex gap-3 border p-4 text-sm" style={{ borderColor: 'var(--danger)', background: 'var(--danger-bg)', color: 'var(--danger)' }}>
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
