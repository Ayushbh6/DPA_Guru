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
          y: 60,
          scale: 0.97,
          filter: "blur(8px)",
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
            start: "top 90%",
            end: "top 35%",
            scrub: true,
            // Apple-style fade out as you scroll past it
            onLeave: () => {
              gsap.to(textRef.current, { opacity: 0, y: -60, scale: 1.02, filter: "blur(8px)", duration: 1, ease: "power2.inOut" });
            },
            onEnterBack: () => {
              gsap.to(textRef.current, { opacity: 1, y: 0, scale: 1, filter: "blur(0px)", duration: 1, ease: "power2.out" });
            },
            onLeaveBack: () => {
               gsap.to(textRef.current, { opacity: 0, y: 60, scale: 0.97, filter: "blur(8px)", duration: 1, ease: "power2.inOut" });
            }
          },
        }
      );
    }, textRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={textRef} className={`py-20 md:py-28 lg:py-36 flex items-center justify-center text-center ${className}`}>
      <h2
        className="text-3xl md:text-5xl lg:text-6xl font-medium tracking-tight max-w-4xl px-6 leading-[1.15]"
        style={{ color: 'var(--text)' }}
      >
        {children}
      </h2>
    </div>
  );
}
