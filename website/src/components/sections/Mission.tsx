"use client";

import { motion, useReducedMotion } from "motion/react";
import { LogoWatermark } from "@/components/ui/LogoWatermark";
import { Reveal } from "@/components/ui/Reveal";

const EASE = [0.22, 1, 0.36, 1] as const;

const STATS = [
  {
    index: "01",
    value: "$100–150",
    meter: 0.82,
    label: "per session for a trainer in major US cities",
  },
  {
    index: "02",
    value: "6%",
    meter: 0.06,
    label: "of gym-goers ever train with one",
  },
  {
    index: "03",
    value: "25–65%",
    meter: 0.45,
    label: "of gym injuries linked to poor technique, across published studies",
  },
] as const;

export function Mission() {
  const reduced = useReducedMotion();

  return (
    <section
      id="mission"
      className="aurora-bg relative overflow-hidden border-y border-border bg-bg-2"
    >
      {/* Blueprint grid + violet wash behind everything, matching the hero. */}
      <div aria-hidden className="grid-bg grid-fade absolute inset-0" />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 55% at 20% 15%, var(--glow), transparent 72%)",
        }}
      />
      <LogoWatermark size={460} className="-bottom-28 -left-24" />

      <div className="relative mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-32">
        <Reveal>
          <p className="eyebrow flex items-center gap-2.5">
            <span
              aria-hidden
              className="pulse-dot size-1.5 rounded-full bg-accent"
            />
            Our purpose
          </p>
        </Reveal>

        <Reveal delay={0.08}>
          <h2 className="mt-5 max-w-3xl font-display text-4xl font-extrabold leading-[1.05] tracking-tight text-fg md:text-6xl">
            Forging a generation of{" "}
            <span className="gradient-text gradient-text-animated">
              athletes.
            </span>
          </h2>
        </Reveal>

        {/* Accent rule draws across as the section enters. */}
        <motion.div
          aria-hidden
          className="mt-12 h-px bg-linear-to-r from-accent via-accent/40 to-transparent"
          style={{ transformOrigin: "left" }}
          initial={reduced ? { opacity: 0 } : { scaleX: 0 }}
          whileInView={reduced ? { opacity: 1 } : { scaleX: 1 }}
          viewport={{ once: true, margin: "-12% 0px" }}
          transition={{ duration: 0.9, delay: 0.15, ease: EASE }}
        />

        <div className="mt-14 grid gap-14 lg:grid-cols-[1.05fr_1fr] lg:gap-20">
          <div className="space-y-7">
            <Reveal>
              <p className="border-l-2 border-accent/60 pl-5 text-lg leading-relaxed text-fg-2">
                We exist to make humanity{" "}
                <strong className="font-semibold text-fg">
                  healthier than it has ever been
                </strong>{" "}
                — by putting premium strength and conditioning, the kind once
                reserved for elite athletes, within everyone&apos;s reach.
              </p>
            </Reveal>
            <Reveal delay={0.1}>
              <p className="font-display text-xl font-medium leading-snug text-fg md:text-2xl">
                Apps count workouts. Wearables count steps.{" "}
                <span className="gradient-text">Nothing can see you.</span>
              </p>
            </Reveal>
            <Reveal delay={0.18}>
              <p className="text-lg leading-relaxed text-fg-2">
                A great coach catches what you can&apos;t feel — a knee caving,
                a hip shifting, depth quietly shrinking as you fatigue. But
                that set of eyes is priced like a luxury, so almost everyone
                lifts blind, plateaus, gets hurt, and calls it normal.{" "}
                <strong className="font-semibold text-fg">
                  So we built the eyes.
                </strong>
              </p>
            </Reveal>
          </div>

          {/* Telemetry stack: the cost-of-coaching numbers as instrument
              readouts, each meter filling to its share when scrolled into view. */}
          <div className="flex flex-col gap-5">
            {STATS.map((stat, index) => (
              <Reveal key={stat.index} delay={0.1 + index * 0.12}>
                <div className="card-lift rounded-2xl border border-border bg-surface/85 p-6 backdrop-blur-sm">
                  <div className="flex items-baseline justify-between gap-4">
                    <p className="silver-text font-mono text-3xl md:text-4xl">
                      {stat.value}
                    </p>
                    <span className="font-mono text-xs text-accent-ink">
                      {stat.index}
                    </span>
                  </div>
                  <div className="meter mt-5">
                    <motion.div
                      className="meter__fill"
                      initial={
                        reduced
                          ? { scaleX: stat.meter, opacity: 0 }
                          : { scaleX: 0 }
                      }
                      whileInView={{ scaleX: stat.meter, opacity: 1 }}
                      viewport={{ once: true, margin: "-12% 0px" }}
                      transition={{
                        duration: 1.1,
                        delay: 0.35 + index * 0.15,
                        ease: EASE,
                      }}
                    />
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-fg-2">
                    {stat.label}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
