import { ThemedLogo } from "@/components/ui/Logo";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/SectionHeading";

const PARAGRAPHS = [
  "Elite lifters get a second set of eyes on every rep. Everyone else gets an app that can't see them. That gap — between the coaching a few can afford and the coaching everyone deserves — is the unfairness we set out to fix.",
  "The only honest way to fix it is the full stack: a biomechanics engine that actually understands movement, the cameras and steel it lives in, and edge AI so it's instant and private. No shortcuts, no cloud, no bolt-on webcam.",
  "The founding batch is how we get there. First racks ship Spring/Summer 2027 — and founding owners shape what Nova becomes.",
] as const;

export function Mission() {
  return (
    <section id="mission" className="relative overflow-hidden">
      {/* W monogram watermark */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 top-1/2 -translate-y-1/2 opacity-[0.04] dark:opacity-[0.05]"
      >
        <ThemedLogo size={520} />
      </div>

      <div className="mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-36">
        <SectionHeading
          eyebrow="Mission"
          title={
            <>
              Coaching this good shouldn&apos;t cost{" "}
              <span className="gradient-text">$25,000 a year.</span>
            </>
          }
        />
        <div className="mt-10 max-w-2xl space-y-6">
          {PARAGRAPHS.map((paragraph, index) => (
            <Reveal key={index} delay={index * 0.1}>
              <p className="text-lg leading-relaxed text-fg-2">{paragraph}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
