import { Reveal } from "@/components/ui/Reveal";

const STATS = [
  { value: "$60–80", label: "per session for a personal trainer" },
  { value: "6%", label: "of gym-goers ever train with one" },
  {
    value: "25–65%",
    label: "of gym injuries linked to poor technique, across published studies",
  },
] as const;

export function Problem() {
  return (
    <section className="border-y border-border bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-32">
        <Reveal>
          <h2 className="max-w-3xl font-display text-3xl font-extrabold leading-tight tracking-tight text-fg md:text-5xl">
            Great coaching is the best thing in fitness.{" "}
            <span className="text-fg-3">Almost nobody has it.</span>
          </h2>
        </Reveal>

        <div className="mt-14 grid gap-10 sm:grid-cols-3">
          {STATS.map((stat, index) => (
            <Reveal key={stat.value} delay={index * 0.12}>
              <div className="border-l-2 border-accent/60 pl-5">
                <p className="font-mono text-3xl text-fg md:text-4xl">{stat.value}</p>
                <p className="mt-2 max-w-[15rem] text-sm leading-relaxed text-fg-2">
                  {stat.label}
                </p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2} className="mt-16">
          <p className="max-w-2xl text-lg leading-relaxed text-fg-2">
            Fitness apps count your workouts. Wearables count your steps.{" "}
            <strong className="font-semibold text-fg">
              None of them can see you.
            </strong>{" "}
            So we built the thing that can.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
