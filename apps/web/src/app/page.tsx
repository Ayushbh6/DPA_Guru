import HeroScroll from "@/components/HeroScroll";
import ScrollRevealText from "@/components/ScrollRevealText";
import ActionSection from "@/components/ActionSection";

export default function Home() {
  return (
    <main className="relative flex min-h-screen flex-col items-center" style={{ background: 'var(--bg)' }}>
      <HeroScroll />

      <section className="w-full py-4 md:py-8 relative z-10">
        <ScrollRevealText>
          Understand your obligations with absolute clarity.
        </ScrollRevealText>

        <ScrollRevealText>
          AI that reads every clause and surfaces risks before you sign.
        </ScrollRevealText>

        <ScrollRevealText>
          Upload your Data Processing Agreement for an instant compliance review.
        </ScrollRevealText>
      </section>

      <ActionSection />

      <footer
        className="w-full py-8 flex items-center justify-center text-[10px] tracking-[0.25em] uppercase font-light"
        style={{ borderTop: '1px solid var(--line)', color: 'var(--text-3)' }}
      >
        © 2026 Merlin AI
      </footer>
    </main>
  );
}
