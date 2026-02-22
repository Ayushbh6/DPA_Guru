"use client";

import { useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

interface ScrollRevealTextProps {
  children: React.ReactNode;
  className?: string;
}

export default function ScrollRevealText({ children, className = "" }: ScrollRevealTextProps) {
  const textRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        textRef.current,
        {
          opacity: 0,
          y: 80,
          scale: 0.95,
          filter: "blur(10px)",
        },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          filter: "blur(0px)",
          duration: 1.5,
          ease: "power3.out",
          scrollTrigger: {
            trigger: textRef.current,
            start: "top 85%",
            end: "top 20%",
            scrub: true,
            // Apple-style fade out as you scroll past it
            onLeave: () => {
              gsap.to(textRef.current, { opacity: 0, y: -80, scale: 1.05, filter: "blur(10px)", duration: 0.8, ease: "power2.inOut" });
            },
            onEnterBack: () => {
              gsap.to(textRef.current, { opacity: 1, y: 0, scale: 1, filter: "blur(0px)", duration: 0.8, ease: "power2.out" });
            },
            onLeaveBack: () => {
               gsap.to(textRef.current, { opacity: 0, y: 80, scale: 0.95, filter: "blur(10px)", duration: 0.8, ease: "power2.inOut" });
            }
          },
        }
      );
    }, textRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={textRef} className={`py-40 flex items-center justify-center text-center ${className}`}>
      <h2
        className="text-4xl md:text-6xl lg:text-7xl font-medium tracking-tight max-w-5xl px-6 leading-tight"
        style={{
          background: 'linear-gradient(135deg, #ffffff 0%, rgba(180,180,255,0.85) 50%, rgba(255,255,255,0.55) 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
        }}
      >
        {children}
      </h2>
    </div>
  );
}
