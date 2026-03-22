"use client";

import { useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Shield } from "lucide-react";

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
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: containerRef.current,
          start: "top top",
          end: "+=2200",
          scrub: 1,
          pin: true,
          anticipatePin: 1,
        },
      });

      // Phase 1: Fade out title, tilt the document into 3D view
      tl.to(textRef.current, { opacity: 0, y: -50, filter: "blur(10px)", duration: 1 }, 0);
      tl.to(bookRef.current, {
        rotateX: 60,
        rotateZ: -20,
        scale: 0.9,
        duration: 2,
        ease: "power2.inOut"
      }, 0);

      // Phase 2: Open the cover
      tl.to(coverRef.current, {
        rotateY: -160,
        duration: 2,
        ease: "power2.inOut",
      }, 1.5);

      // Phase 3: Animate the scanner line
      tl.fromTo(scannerRef.current, {
        top: "0%",
        opacity: 0,
      }, {
        top: "100%",
        opacity: 1,
        duration: 3,
        ease: "linear"
      }, 2.5);

    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="relative w-full overflow-hidden">
      <div
        ref={stickyRef}
        className="h-screen w-full flex items-center justify-center relative pt-16"
        style={{ background: 'var(--bg)' }}
      >
        {/* Main Title */}
        <div ref={textRef} className="absolute inset-0 flex flex-col items-center justify-center z-20 pointer-events-none">
          <h1
            className="text-7xl md:text-9xl font-bold tracking-tight text-center"
            style={{ color: 'var(--text)' }}
          >
            Merlin AI
          </h1>
          <p
            className="text-xs md:text-sm tracking-[0.3em] uppercase font-light mt-4"
            style={{ color: 'var(--accent)' }}
          >
            DPA Analyzer
          </p>
        </div>

        {/* 3D Scene */}
        <div className="relative w-full h-full flex items-center justify-center [perspective:2500px] z-10">

          {/* The Document Container */}
          <div
            ref={bookRef}
            className="relative w-[336px] h-[440px] md:w-[476px] md:h-[622px] translate-y-[8px] md:translate-y-[19px] [transform-style:preserve-3d]"
            style={{
              boxShadow: '0 0 0 1px var(--line), 0 30px 80px rgba(0,0,0,0.2)',
            }}
          >
            {/* Back Cover / Inside Pages */}
            <div
              className="absolute inset-0 overflow-hidden flex flex-col p-6 md:p-10"
              style={{ background: 'var(--bg-1)', border: '1px solid var(--line)' }}
            >
              <div
                className="flex items-center justify-between mb-8 pb-4"
                style={{ borderBottom: '1px solid var(--line)' }}
              >
                <Shield className="w-5 h-5 md:w-6 md:h-6" style={{ color: 'var(--text-3)' }} />
                <span
                  className="text-[10px] md:text-xs tracking-widest uppercase font-medium"
                  style={{ color: 'var(--text-3)' }}
                >
                  Analysis Mode
                </span>
              </div>

              {/* Skeleton Document with Scanner */}
              <div className="space-y-5 md:space-y-6 flex-1 relative">
                {/* Scanner Line */}
                <div
                  ref={scannerRef}
                  className="absolute left-0 right-0 h-px z-20"
                  style={{
                    top: '0%',
                    background: 'var(--accent)',
                    boxShadow: '0 0 10px 2px var(--accent)',
                  }}
                />

                <div className="w-full h-2 md:h-2.5" style={{ background: 'var(--line-2)' }} />
                <div className="w-3/4 h-2 md:h-2.5" style={{ background: 'var(--line-2)' }} />

                {/* Highlighted Risk Clause */}
                <div
                  className="w-full h-16 md:h-20 p-3 relative overflow-hidden flex flex-col justify-center space-y-2"
                  style={{ background: 'var(--bg-2)', borderLeft: '2px solid var(--accent)' }}
                >
                  <div className="w-1/4 h-1.5 md:h-2" style={{ background: 'var(--text-3)' }} />
                  <div className="w-full h-1.5 md:h-2" style={{ background: 'var(--line-2)' }} />
                  <div className="w-5/6 h-1.5 md:h-2" style={{ background: 'var(--line-2)' }} />
                </div>

                <div className="w-5/6 h-2 md:h-2.5" style={{ background: 'var(--line)' }} />
                <div className="w-full h-2 md:h-2.5" style={{ background: 'var(--line)' }} />
                <div className="w-4/6 h-2 md:h-2.5" style={{ background: 'var(--line)' }} />
              </div>
            </div>

            {/* Front Cover */}
            <div
              ref={coverRef}
              className="absolute inset-0 origin-left [transform-style:preserve-3d] z-30 flex items-center justify-center"
              style={{
                background: 'var(--bg-2)',
                border: '1px solid var(--line)',
              }}
            >
              <Shield
                className="w-10 h-10 md:w-12 md:h-12 stroke-1"
                style={{ color: 'var(--text-3)' }}
              />
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}

