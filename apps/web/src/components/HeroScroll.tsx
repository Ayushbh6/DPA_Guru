"use client";

import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { CheckCircle2, FileText, ShieldCheck } from "lucide-react";
import { useRef } from "react";

export default function HeroScroll() {
  const ref = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const textOpacity = useTransform(scrollYProgress, [0, 0.58, 1], [1, 0.94, 0.42]);
  const visualOpacity = useTransform(scrollYProgress, [0, 0.65, 1], [1, 0.84, 0.28]);
  const visualY = useTransform(scrollYProgress, [0, 1], [0, prefersReducedMotion ? 0 : -42]);

  return (
    <section
      ref={ref}
      className="relative flex min-h-[88svh] w-full items-center border-b border-border bg-background px-5 pt-16 md:min-h-[90svh] md:px-8"
    >
      <div className="mx-auto grid w-full max-w-7xl items-center gap-10 pb-14 pt-10 md:grid-cols-[0.92fr_1.08fr] md:pb-20">
        <motion.div
          style={{ opacity: textOpacity }}
          className="max-w-2xl"
          initial={prefersReducedMotion ? false : { opacity: 0, y: 18 }}
          animate={prefersReducedMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
        >
          <h1 className="text-6xl font-semibold leading-none text-foreground md:text-8xl">
            Checker
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground md:text-lg">
            AI-assisted DPA reviews with evidence, criteria, and approval decisions in one calm workspace.
          </p>
          <div className="mt-8 flex flex-wrap gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
            <span className="rounded-full border border-border bg-muted px-3 py-1">Evidence-led</span>
            <span className="rounded-full border border-border bg-muted px-3 py-1">Criteria-first</span>
            <span className="rounded-full border border-border bg-muted px-3 py-1">Human approved</span>
          </div>
        </motion.div>

        <motion.div
          style={{ opacity: visualOpacity, y: visualY }}
          className="relative"
          initial={prefersReducedMotion ? false : { opacity: 0, y: 22 }}
          animate={prefersReducedMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.75, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm md:p-5">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div className="flex items-center gap-3">
                <div className="grid size-10 place-items-center rounded-lg border border-border bg-muted">
                  <ShieldCheck className="size-5 text-primary" />
                </div>
                <div>
                  <div className="text-sm font-medium text-foreground">Atlassian Vendor Review</div>
                  <div className="mt-1 text-xs text-muted-foreground">Approval Pack ready</div>
                </div>
              </div>
              <span className="rounded-full bg-[var(--success-bg)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--success)]">
                Low risk
              </span>
            </div>

            <div className="grid gap-3 py-4 md:grid-cols-3">
              {[
                ["Documents", "1 primary"],
                ["Criteria", "8 approved"],
                ["Evidence", "24 quotes"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-border bg-muted/45 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
                  <div className="mt-2 text-sm font-semibold text-foreground">{value}</div>
                </div>
              ))}
            </div>

            <div className="rounded-lg border border-border bg-background p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <FileText className="size-4 text-primary" />
                DPA review summary
              </div>
              <div className="mt-4 grid gap-2">
                <div className="h-2 rounded-full bg-muted" />
                <div className="h-2 w-5/6 rounded-full bg-muted" />
                <div className="h-2 w-2/3 rounded-full bg-muted" />
              </div>
              <div className="mt-5 flex items-start gap-3 rounded-lg border border-border bg-muted/45 p-3">
                <CheckCircle2 className="mt-0.5 size-4 text-[var(--success)]" />
                <div>
                  <div className="text-sm font-medium text-foreground">Approve</div>
                  <div className="mt-1 text-xs leading-5 text-muted-foreground">
                    The final decision remains tied to criteria and source evidence.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
