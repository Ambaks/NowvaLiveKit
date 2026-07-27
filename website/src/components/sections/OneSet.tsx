"use client";

import { Volume2 } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/SectionHeading";

const EASE = [0.22, 1, 0.36, 1] as const;

const BEATS = [
  {
    step: "01",
    title: "You rack in.",
    copy: "Nova sizes you up before the bar leaves the hooks — your proportions, your stance, the range you actually have. By rep one, it knows what your squat should look like.",
  },
  {
    step: "02",
    title: "You descend.",
    copy: "Your skeleton, reconstructed in 3D 30 times a second. Every joint angle measured while the rep is still happening.",
  },
  {
    step: "03",
    title: "You drift.",
    copy: "Your stance has crept narrow as you fatigue — you can't feel it, Nova can see it. It knows how far off you are and says the fix out loud, before your next rep.",
    cue: "Widen your stance — about ten degrees.",
  },
  {
    step: "04",
    title: "You finish.",
    copy: "Reps counted. Depth graded. A plain-English recap, your next set adjusted before you're back under the bar — and your program and nutrition targets updated by the time you leave.",
  },
] as const;

export function OneSet() {
  const reduced = useReducedMotion();

  return (
    <section className="border-y border-border bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-32">
        <SectionHeading
          eyebrow="One set with Nowva"
          title="Step in. Nova takes it from there."
        />

        <div className="relative mt-16 grid gap-10 md:grid-cols-4 md:gap-6">
          {/* Connecting line (md+): base track plus an accent sweep that draws
              across the four steps as the row scrolls into view. */}
          <div
            aria-hidden
            className="absolute inset-x-0 top-0 hidden h-0.5 overflow-hidden bg-border md:block"
          >
            <motion.div
              className="h-full w-full bg-linear-to-r from-accent via-accent/50 to-accent/15"
              style={{ transformOrigin: "left" }}
              initial={reduced ? { opacity: 0 } : { scaleX: 0 }}
              whileInView={reduced ? { opacity: 1 } : { scaleX: 1 }}
              viewport={{ once: true, margin: "-12% 0px" }}
              transition={{ duration: 0.9, delay: 0.1, ease: EASE }}
            />
          </div>

          {BEATS.map((beat, index) => (
            <Reveal key={beat.step} delay={index * 0.12}>
              <div className="relative h-full border-t border-border pt-6 md:border-t-0">
                <motion.span
                  aria-hidden
                  className="absolute -top-px left-0 h-px w-10 bg-accent md:top-0 md:h-0.5"
                  style={{ transformOrigin: "left" }}
                  initial={reduced ? { opacity: 0 } : { scaleX: 0 }}
                  whileInView={reduced ? { opacity: 1 } : { scaleX: 1 }}
                  viewport={{ once: true, margin: "-12% 0px" }}
                  transition={{
                    duration: 0.6,
                    delay: 0.2 + index * 0.12,
                    ease: EASE,
                  }}
                />
                <span className="font-mono text-xs text-accent-ink">{beat.step}</span>
                <h3 className="mt-3 font-display text-lg font-bold tracking-tight text-fg">
                  {beat.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-fg-2">{beat.copy}</p>
                {"cue" in beat && (
                  <span className="mt-5 inline-flex items-center gap-2.5 rounded-full border border-accent/40 bg-accent/10 px-4 py-2">
                    <Volume2 className="size-3.5 text-accent-ink" aria-hidden />
                    <span className="font-mono text-sm text-accent-ink">
                      &ldquo;{beat.cue}&rdquo;
                    </span>
                  </span>
                )}
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
