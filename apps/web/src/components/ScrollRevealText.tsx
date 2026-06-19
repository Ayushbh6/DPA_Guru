"use client";

import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

interface ScrollRevealTextProps {
  children: React.ReactNode;
  className?: string;
}

export default function ScrollRevealText({ children, className = "" }: ScrollRevealTextProps) {
  const ref = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 85%", "center center", "end 15%"],
  });
  const opacity = useTransform(scrollYProgress, [0, 0.5, 1], prefersReducedMotion ? [1, 1, 1] : [0.22, 1, 0.22]);
  const y = useTransform(scrollYProgress, [0, 0.5, 1], prefersReducedMotion ? [0, 0, 0] : [42, 0, -42]);

  return (
    <motion.div
      ref={ref}
      style={{ opacity, y }}
      className={`mx-auto flex min-h-[46svh] w-full max-w-6xl items-center justify-center px-5 py-10 text-center md:min-h-[54svh] md:py-16 ${className}`}
    >
      <h2 className="max-w-4xl text-3xl font-semibold leading-[1.08] text-foreground md:text-5xl lg:text-6xl">
        {children}
      </h2>
    </motion.div>
  );
}
