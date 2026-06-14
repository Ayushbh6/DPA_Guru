"use client";

import { useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { ArrowDown, CheckCircle2, FileText, Shield } from "lucide-react";

gsap.registerPlugin(ScrollTrigger);

export default function HeroScroll() {
  const containerRef = useRef<HTMLDivElement>(null);
  const stickyRef = useRef<HTMLDivElement>(null);
  const bookRef = useRef<HTMLDivElement>(null);
  const coverRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const scannerRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion) {
        gsap.set(bookRef.current, { opacity: 0.88, y: 170, scale: 0.88 });
        return;
      }

      gsap.set(bookRef.current, { opacity: 0.22, y: 190, scale: 0.84 });

      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: containerRef.current,
          start: "top top",
          end: "+=1500",
          scrub: 0.7,
          pin: true,
          anticipatePin: 1,
        },
      });

      tl.to(textRef.current, { opacity: 0, y: -26, scale: 0.98, duration: 1 }, 0);
      tl.to(bookRef.current, {
        opacity: 0.96,
        rotateX: 46,
        rotateZ: -8,
        y: 26,
        scale: 0.94,
        duration: 2,
        ease: "power2.inOut"
      }, 0);

      tl.to(coverRef.current, {
        rotateY: -122,
        duration: 2,
        ease: "power2.inOut",
      }, 1.15);

      tl.fromTo(scannerRef.current, {
        yPercent: -10,
        opacity: 0.1,
      }, {
        yPercent: 980,
        opacity: 0.9,
        duration: 2.4,
        ease: "linear"
      }, 1.7);

    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="relative w-full overflow-hidden">
      <div
        ref={stickyRef}
        className="relative flex h-screen w-full items-center justify-center overflow-hidden px-5 pt-16"
      >
        <div
          className="absolute inset-x-0 top-24 mx-auto h-72 max-w-5xl rounded-full blur-3xl"
          style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)" }}
        />

        <div ref={textRef} className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center text-center">
          <div
            className="mb-5 inline-flex items-center gap-2 border px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.24em]"
            style={{ borderColor: "var(--line)", background: "var(--bg-1)", color: "var(--text-3)" }}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--accent)" }} />
            Vendor Review Workspace
          </div>
          <h1
            className="text-7xl font-semibold tracking-[-0.08em] md:text-9xl"
            style={{ color: 'var(--text)' }}
          >
            Checker
          </h1>
          <p
            className="mt-5 max-w-xl text-base leading-7 md:text-lg"
            style={{ color: 'var(--text-2)' }}
          >
            AI-assisted DPA reviews with evidence, criteria, and approval decisions in one calm workspace.
          </p>
          <div className="mt-12 flex items-center gap-2 text-xs" style={{ color: "var(--text-3)" }}>
            <ArrowDown className="h-4 w-4 animate-bounce" />
            Scroll to open the review pack
          </div>
        </div>

        <div className="relative z-10 flex h-full w-full items-center justify-center [perspective:2200px]">
          <div
            ref={bookRef}
            className="relative mt-40 h-[430px] w-[330px] translate-y-[8px] [transform-style:preserve-3d] md:mt-52 md:h-[610px] md:w-[468px] md:translate-y-[22px]"
            style={{
              opacity: 0.22,
              boxShadow: '0 34px 110px color-mix(in srgb, #000 22%, transparent)',
            }}
          >
            <div
              className="absolute inset-0 flex flex-col overflow-hidden rounded-[28px] p-6 md:p-9"
              style={{ background: 'var(--bg)', border: '1px solid var(--line)' }}
            >
              <div
                className="mb-8 flex items-center justify-between rounded-2xl px-3 py-2"
                style={{ background: 'var(--bg-1)', border: '1px solid var(--line)' }}
              >
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 md:h-5 md:w-5" style={{ color: 'var(--accent)' }} />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.18em]" style={{ color: 'var(--text-2)' }}>
                    DPA Review
                  </span>
                </div>
                <span className="rounded-full px-2 py-1 text-[10px]" style={{ background: 'var(--status-partial-bg)', color: 'var(--status-partial)' }}>
                  Draft
                </span>
              </div>

              <div
                className="mb-6 rounded-3xl p-4"
                style={{ borderBottom: '1px solid var(--line)' }}
              >
                <div className="text-[11px] uppercase tracking-[0.16em]" style={{ color: 'var(--text-3)' }}>Recommendation</div>
                <div className="mt-2 flex items-center gap-2 text-xl font-semibold md:text-2xl" style={{ color: 'var(--text)' }}>
                  Conditional approval
                  <CheckCircle2 className="h-5 w-5" style={{ color: 'var(--status-compliant)' }} />
                </div>
              </div>

              <div className="relative flex-1">
                <div
                  ref={scannerRef}
                  className="absolute left-0 right-0 top-0 z-20 h-px"
                  style={{
                    background: 'var(--accent)',
                    boxShadow: '0 0 22px 3px color-mix(in srgb, var(--accent) 70%, transparent)',
                  }}
                />
                <div className="grid gap-4">
                  <div className="h-2.5 w-full rounded-full" style={{ background: 'var(--line-2)' }} />
                  <div className="h-2.5 w-3/4 rounded-full" style={{ background: 'var(--line-2)' }} />
                  <div className="rounded-3xl p-4" style={{ background: 'var(--bg-1)', border: '1px solid var(--line)' }}>
                    <div className="mb-3 flex items-center justify-between">
                      <div className="h-2 w-24 rounded-full" style={{ background: 'var(--text-3)' }} />
                      <span className="rounded-full px-2 py-1 text-[10px]" style={{ background: 'var(--risk-high-bg)', color: 'var(--risk-high)' }}>
                        High risk
                      </span>
                    </div>
                    <div className="grid gap-2">
                      <div className="h-2 rounded-full" style={{ background: 'var(--line-2)' }} />
                      <div className="h-2 w-5/6 rounded-full" style={{ background: 'var(--line-2)' }} />
                    </div>
                  </div>
                  <div className="h-2.5 w-5/6 rounded-full" style={{ background: 'var(--line)' }} />
                  <div className="h-2.5 w-full rounded-full" style={{ background: 'var(--line)' }} />
                  <div className="h-2.5 w-4/6 rounded-full" style={{ background: 'var(--line)' }} />
                </div>
              </div>
            </div>

            <div
              ref={coverRef}
              className="absolute inset-0 z-30 flex origin-left items-center justify-center rounded-[28px] [transform-style:preserve-3d]"
              style={{
                background: 'var(--bg-2)',
                border: '1px solid var(--line)',
              }}
            >
              <div className="text-center">
                <Shield className="mx-auto h-12 w-12 stroke-1 md:h-14 md:w-14" style={{ color: 'var(--text-3)' }} />
                <div className="mt-5 text-[11px] uppercase tracking-[0.28em]" style={{ color: 'var(--text-3)' }}>
                  Processing Agreement
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
