import HeroScroll from "@/components/HeroScroll";
import ScrollRevealText from "@/components/ScrollRevealText";
import ActionSection from "@/components/ActionSection";

export default function Home() {
  return (
    <main className="relative flex min-h-screen flex-col items-center" style={{ background: 'var(--background)' }}>

      {/* ── Ambient gradient light sources (fixed, behind everything) ── */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        {/* Indigo bloom — top left */}
        <div className="absolute -top-[30%] -left-[15%] w-[90vw] h-[90vh] bg-[radial-gradient(ellipse,rgba(99,102,241,0.13),transparent_62%)]" />
        {/* Violet bloom — center */}
        <div className="absolute top-[20%] left-1/2 -translate-x-1/2 w-[70vw] h-[70vh] bg-[radial-gradient(ellipse,rgba(139,92,246,0.07),transparent_60%)]" />
        {/* Teal bloom — bottom right */}
        <div className="absolute bottom-[-15%] right-[-10%] w-[60vw] h-[70vh] bg-[radial-gradient(ellipse,rgba(20,184,166,0.09),transparent_60%)]" />
        {/* Subtle dot grid */}
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.5) 1px, transparent 1px)',
            backgroundSize: '32px 32px',
          }}
        />
      </div>

      <HeroScroll />

      <section className="w-full py-40 relative z-10">
        <ScrollRevealText>
          Understand your obligations with absolute clarity.
        </ScrollRevealText>

        <ScrollRevealText>
          Advanced AI deeply analyzes every clause, highlighting potential risks before you sign.
        </ScrollRevealText>

        <ScrollRevealText>
          Upload your Data Processing Agreement for an instant, comprehensive review.
        </ScrollRevealText>
      </section>

      <ActionSection />

      {/* Footer */}
      <footer className="pointer-events-none absolute bottom-0 left-0 w-full py-6 border-t border-white/[0.07] flex items-center justify-center text-white/25 text-[10px] tracking-widest uppercase font-light">
        © 2026 MERLIN AI — ALL RIGHTS RESERVED
      </footer>
    </main>
  );
}
