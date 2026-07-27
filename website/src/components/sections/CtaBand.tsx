import { Reveal } from "@/components/ui/Reveal";
import { Button } from "@/components/ui/Button";

export function CtaBand({
  headline,
  sub,
  location,
}: {
  headline: React.ReactNode;
  sub: string;
  location: string;
}) {
  return (
    <section className="aurora-bg grid-bg overflow-hidden border-y border-border bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-24 text-center md:px-8 md:py-32">
        <Reveal>
          <h2 className="font-display text-4xl leading-[1.05] font-extrabold tracking-tight text-balance text-fg md:text-6xl">
            {headline}
          </h2>
        </Reveal>
        <Reveal delay={0.1} y={16}>
          <p className="mt-5 font-mono text-xs tracking-[0.18em] text-fg-2 uppercase md:text-sm">
            {sub}
          </p>
        </Reveal>
        <Reveal delay={0.2} y={16}>
          <div className="mt-10">
            <Button
              href="#reserve"
              size="lg"
              cta={location}
              className="px-9 py-4 text-lg shadow-[0_10px_50px_-16px_var(--glow-cta)]"
            >
              Reserve Your Rack — $0 today
            </Button>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
