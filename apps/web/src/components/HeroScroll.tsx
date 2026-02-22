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
          end: "+=3000",
          scrub: 1,
          pin: true,
          anticipatePin: 1,
        },
      });

      // Initial state: Title is visible, document is flat top-down view.
      
      // Phase 1: Fade out title, tilt the document into 3D view like an Apple product reveal
      tl.to(textRef.current, { opacity: 0, y: -50, filter: "blur(10px)", duration: 1 }, 0);
      tl.to(bookRef.current, { 
        rotateX: 60, 
        rotateZ: -20, 
        scale: 0.9, 
        duration: 2, 
        ease: "power2.inOut" 
      }, 0);

      // Phase 2: Open the cover elegantly
      tl.to(coverRef.current, {
        rotateY: -160,
        duration: 2,
        ease: "power2.inOut",
      }, 1.5);

      // Phase 3: Animate the glowing scanner line inside the document
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
      >
        {/* Main Title (Fades out) */}
        <div ref={textRef} className="absolute inset-0 flex flex-col items-center justify-center z-20 pointer-events-none">
          <h1
            className="text-7xl md:text-9xl font-bold tracking-tight text-center"
            style={{
              background: 'linear-gradient(160deg, #ffffff 0%, rgba(210,210,255,0.9) 45%, rgba(255,255,255,0.75) 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Merlin AI
          </h1>
          <p className="text-xs md:text-sm tracking-[0.3em] uppercase font-light mt-28" style={{ color: 'rgba(139,92,246,0.7)' }}>
            DPA Analyzer
          </p>
        </div>

        {/* 3D Scene */}
        <div className="relative w-full h-full flex items-center justify-center [perspective:2500px] z-10">

          {/* Ambient glow behind the document */}
          <div className="absolute w-[500px] h-[500px] md:w-[700px] md:h-[700px] bg-[radial-gradient(ellipse,rgba(99,102,241,0.18),transparent_60%)] pointer-events-none translate-y-4" />

          {/* The Document Container */}
          <div 
            ref={bookRef} 
            className="relative w-[336px] h-[440px] md:w-[476px] md:h-[622px] translate-y-[8px] md:translate-y-[19px] [transform-style:preserve-3d] shadow-[0_0_0_1px_rgba(99,102,241,0.15),0_30px_120px_rgba(99,102,241,0.12)]"
          >
            {/* Back Cover / Inside Glowing Pages */}
            <div className="absolute inset-0 border overflow-hidden flex flex-col p-6 md:p-10" style={{ background: '#08081a', borderColor: 'rgba(99,102,241,0.2)' }}>
              <div className="flex items-center justify-between mb-8 border-b border-white/10 pb-4">
                 <Shield className="w-5 h-5 md:w-6 md:h-6 text-white/30" />
                 <span className="text-[10px] md:text-xs tracking-widest uppercase text-white/30 font-medium">Analysis Mode</span>
              </div>
              
              {/* Skeleton Document with Glowing Data */}
              <div className="space-y-5 md:space-y-6 flex-1 relative">
                 {/* Scanner Line */}
                 <div ref={scannerRef} className="absolute left-0 right-0 h-[2px] z-20" style={{ top: '0%', background: 'linear-gradient(90deg, transparent, #6366f1, #8b5cf6, #14b8a6, transparent)', boxShadow: '0 0 16px rgba(99,102,241,0.8)' }} />

                 <div className="w-full h-2 md:h-3 bg-white/10" />
                 <div className="w-3/4 h-2 md:h-3 bg-white/10" />
                 
                 {/* Highlighted Risk Clause */}
                 <div className="w-full h-16 md:h-20 bg-white/5 border-l-2 border-white/40 p-3 relative overflow-hidden flex flex-col justify-center space-y-2">
                    <div className="w-1/4 h-1.5 md:h-2 bg-white/40" />
                    <div className="w-full h-1.5 md:h-2 bg-white/20" />
                    <div className="w-5/6 h-1.5 md:h-2 bg-white/20" />
                 </div>
                 
                 <div className="w-5/6 h-2 md:h-3 bg-white/10" />
                 <div className="w-full h-2 md:h-3 bg-white/10" />
                 <div className="w-4/6 h-2 md:h-3 bg-white/10" />
              </div>
            </div>

            {/* Front Cover (Glassmorphism) */}
            <div 
              ref={coverRef}
              className="absolute inset-0 origin-left [transform-style:preserve-3d] z-30 flex items-center justify-center shadow-2xl backdrop-blur-xl"
              style={{ background: 'rgba(6,6,20,0.82)', border: '1px solid rgba(99,102,241,0.22)' }}
            >
              {/* Outer Glow on Cover */}
              <div className="absolute inset-0 shadow-[inset_0_0_50px_rgba(255,255,255,0.05)] pointer-events-none" />
              
              <div className="flex flex-col items-center">
                <Shield className="w-10 h-10 md:w-12 md:h-12 text-white/30 stroke-1" />
              </div>
            </div>
            
          </div>
        </div>

      </div>
    </div>
  );
}
