import HeroScroll from "@/components/HeroScroll";
import ScrollRevealText from "@/components/ScrollRevealText";
import ActionSection from "@/components/ActionSection";

export default function Home() {
  return (
    <main className="relative flex min-h-screen flex-col items-center overflow-hidden">
      <HeroScroll />

      <section className="relative z-10 w-full py-4 md:py-8">
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
        className="flex w-full items-center justify-center py-10 text-[10px] font-medium uppercase tracking-[0.28em]"
        style={{ borderTop: '1px solid var(--line)', color: 'var(--text-3)' }}
      >
        © 2026 Checker
      </footer>
    </main>
  );
}
