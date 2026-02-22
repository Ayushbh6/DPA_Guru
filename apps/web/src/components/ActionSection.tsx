"use client";

import { Upload, FileText } from "lucide-react";
import { motion } from "framer-motion";

export default function ActionSection() {
  return (
    <section className="relative z-40 isolate w-full h-[100svh] flex items-center justify-center px-6">
      <div className="absolute inset-0" style={{ background: 'var(--background)' }} />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(99,102,241,0.14),transparent_55%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_80%_100%,rgba(20,184,166,0.08),transparent_55%)]" />
      <div className="absolute inset-x-0 top-0 h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(99,102,241,0.5), rgba(139,92,246,0.5), rgba(20,184,166,0.4), transparent)' }} />
      <div className="max-w-3xl w-full relative z-10">
        <motion.div 
          initial={{ opacity: 0, y: 40, filter: "blur(8px)" }}
          whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 1, ease: "easeOut" }}
          viewport={{ once: true, margin: "-50px" }}
          className="relative z-10 border p-8 md:p-14 flex flex-col items-center text-center overflow-hidden"
          style={{
            background: 'rgba(8,8,26,0.92)',
            borderColor: 'rgba(99,102,241,0.18)',
            boxShadow: '0 0 0 1px rgba(99,102,241,0.06), 0 40px 140px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.04)',
          }}
        >
          {/* Gradient accent line at top of card */}
          <div className="absolute inset-x-0 top-0 h-[1px] pointer-events-none" style={{ background: 'linear-gradient(90deg, transparent 0%, rgba(99,102,241,0.6) 30%, rgba(139,92,246,0.6) 60%, rgba(20,184,166,0.4) 85%, transparent 100%)' }} />

          {/* Subtle Glow Background */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[500px] h-[500px] bg-[radial-gradient(ellipse,rgba(99,102,241,0.08),transparent_60%)] pointer-events-none" />

          <h2
            className="text-4xl md:text-6xl font-semibold tracking-tight mb-4 pb-2"
            style={{
              background: 'linear-gradient(135deg, #ffffff 0%, rgba(199,199,255,0.85) 50%, rgba(255,255,255,0.7) 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Begin Analysis.
          </h2>
          
          <p className="text-white/40 text-lg md:text-xl mb-10 max-w-xl font-light tracking-wide leading-relaxed">
            Upload your Data Processing Agreement for an instant, comprehensive review.
          </p>

          {/* Drag & Drop Zone */}
          <div
            className="w-full max-w-lg p-8 md:p-10 mb-8 flex flex-col items-center justify-center group cursor-pointer transition-all duration-500 relative"
            style={{
              border: '1px dashed rgba(99,102,241,0.25)',
              background: 'rgba(99,102,241,0.03)',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.borderColor = 'rgba(99,102,241,0.5)';
              (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.06)';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.borderColor = 'rgba(99,102,241,0.25)';
              (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.03)';
            }}
          >
            <motion.div
              whileHover={{ scale: 1.1 }}
              className="w-14 h-14 bg-white/5 flex items-center justify-center mb-4"
            >
              <Upload className="w-6 h-6 text-white/50 group-hover:text-white transition-colors" />
            </motion.div>
            <span className="text-base font-medium text-white/70 group-hover:text-white transition-colors">
              Drag and drop your document here
            </span>
            <span className="text-xs text-white/30 mt-2">
              Supports PDF, DOCX
            </span>
          </div>

          {/* Main CTA */}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="bg-white text-black px-10 py-4 text-base font-medium tracking-wide transition-colors flex items-center gap-3"
          >
            Select File
            <FileText className="w-4 h-4" />
          </motion.button>
        </motion.div>
      </div>
    </section>
  );
}
