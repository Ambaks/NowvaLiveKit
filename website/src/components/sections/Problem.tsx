import { Reveal } from "@/components/ui/Reveal";

const STATS = [
  { value: "$100–150", label: "per session for a trainer in major US cities" },
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
            Apps count workouts. Wearables count steps.{" "}
            <span className="gradient-text">Nothing can see you.</span>
          </h2>
        </Reveal>

        <div className="mt-14 grid gap-5 sm:grid-cols-3">
          {STATS.map((stat, index) => (
            <Reveal key={stat.value} delay={index * 0.12} className="h-full">
              <div className="card-lift h-full rounded-2xl border border-border bg-surface p-6">
                <div className="border-l-2 border-accent/60 pl-4">
                  <p className="font-mono text-3xl text-fg md:text-4xl">{stat.value}</p>
                  <p className="mt-2 max-w-[15rem] text-sm leading-relaxed text-fg-2">
                    {stat.label}
                  </p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2} className="mt-16">
          <p className="max-w-2xl text-lg leading-relaxed text-fg-2">
            A great coach catches what you can&apos;t feel — a knee caving, a
            hip shifting, depth quietly shrinking as you fatigue. But that set
            of eyes is priced like a luxury, so almost everyone lifts blind,
            plateaus, gets hurt, and calls it normal.{" "}
            <strong className="font-semibold text-fg">
              So we built the eyes.
            </strong>
          </p>
        </Reveal>
      </div>
    </section>
  );
}
