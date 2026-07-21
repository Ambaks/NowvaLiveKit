import { Check } from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { PreorderForm } from "@/components/preorder/PreorderForm";
import { DELIVERY, PRICE_MONTHLY, PRICE_UPFRONT } from "@/lib/constants";

const TRAINER_POINTS = [
  "A few sessions a week",
  "Watching you between sets, at best",
  "A bill that never ends",
] as const;

const NOWVA_POINTS = [
  "Every rep of every session",
  "Corrections in under 50 ms",
  "Yours, in your home",
] as const;

const RESERVE_POINTS = [
  "$0 due today",
  "Founding-batch priority",
  `Ships ${DELIVERY}`,
  "Cancel anytime with one email",
] as const;

export function Pricing() {
  return (
    <section id="reserve" className="border-t border-border bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-36">
        <SectionHeading
          eyebrow="Pricing"
          title={
            <>
              A world-class coach costs $2,000 a month.{" "}
              <span className="gradient-text">Yours costs $200.</span>
            </>
          }
          align="center"
          className="max-w-4xl"
        />

        <div className="mt-16 grid gap-8 lg:grid-cols-[1fr_0.9fr]">
          {/* comparison */}
          <Reveal>
            <div className="grid h-full gap-5 sm:grid-cols-2">
              <div className="flex flex-col rounded-2xl border border-border bg-surface p-7">
                <p className="eyebrow text-fg-3!">Personal trainer</p>
                <p className="mt-5 font-display text-3xl font-extrabold tracking-tight text-fg-2">
                  $1,500–2,500
                  <span className="font-mono text-sm font-normal text-fg-3"> /mo</span>
                </p>
                <p className="mt-1 text-xs text-fg-2">in major US cities</p>
                <ul className="mt-6 space-y-3">
                  {TRAINER_POINTS.map((point) => (
                    <li key={point} className="text-sm leading-relaxed text-fg-2">
                      {point}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="glow-accent flex flex-col rounded-2xl border border-accent/50 bg-surface p-7">
                <p className="eyebrow">Nowva Rack</p>
                <p className="mt-5 font-display text-3xl font-extrabold tracking-tight text-fg">
                  ${PRICE_UPFRONT.toLocaleString("en-US")}
                  <span className="font-mono text-sm font-normal text-fg-2"> once</span>
                </p>
                <p className="mt-1 font-display text-xl font-bold text-fg">
                  + ${PRICE_MONTHLY}
                  <span className="font-mono text-sm font-normal text-fg-2"> /mo</span>
                </p>
                <p className="mt-1 text-xs text-fg-2">membership starts after month 2</p>
                <ul className="mt-6 space-y-3">
                  {NOWVA_POINTS.map((point) => (
                    <li key={point} className="text-sm leading-relaxed text-fg">
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <p className="mt-6 text-sm leading-relaxed text-fg-2">
              The rack costs less than{" "}
              <strong className="font-semibold text-fg">six weeks of a trainer</strong>.
              The membership costs less than{" "}
              <strong className="font-semibold text-fg">one session a week</strong>.
            </p>
          </Reveal>

          {/* reservation card */}
          <Reveal delay={0.12}>
            <div className="rounded-2xl border border-border bg-surface p-7 md:p-9">
              <h3 className="font-display text-2xl font-bold tracking-tight text-fg">
                Reserve your Nowva Rack
              </h3>
              <ul className="mt-6 space-y-2.5">
                {RESERVE_POINTS.map((point) => (
                  <li key={point} className="flex items-center gap-3">
                    <Check className="size-3.5 shrink-0 text-accent-ink" aria-hidden />
                    <span className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-2">
                      {point}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-7">
                <PreorderForm />
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
