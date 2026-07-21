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
    <section className="grid-bg relative overflow-hidden border-y border-border bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-20 text-center md:px-8 md:py-24">
        <Reveal>
          <h2 className="font-display text-3xl font-extrabold tracking-tight text-fg md:text-5xl">
            {headline}
          </h2>
          <p className="mt-4 font-mono text-sm tracking-[0.14em] text-fg-2 uppercase">
            {sub}
          </p>
          <div className="mt-8">
            <Button href="#reserve" size="lg" cta={location}>
              Reserve Your Rack — $0 today
            </Button>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
