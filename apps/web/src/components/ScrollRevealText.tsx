"use client";

import { motion } from "framer-motion";

interface ScrollRevealTextProps {
  children: React.ReactNode;
  className?: string;
}

export default function ScrollRevealText({ children, className = "" }: ScrollRevealTextProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-14% 0px" }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className={`mx-auto flex w-full max-w-5xl items-center justify-center px-5 py-10 text-center md:py-14 ${className}`}
    >
      <div className="premium-panel px-6 py-10 md:px-12 md:py-14">
        <h2 className="text-3xl font-semibold leading-[1.08] tracking-[-0.055em] md:text-5xl lg:text-6xl" style={{ color: "var(--text)" }}>
          {children}
        </h2>
      </div>
    </motion.div>
  );
}
