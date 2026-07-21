import { Volume2 } from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/SectionHeading";

const BEATS = [
  {
    step: "01",
    title: "You rack in.",
    copy: "Nova calibrates to your body in the first seconds of standing — femur length, torso ratio, stance width. Your thresholds, not a template's.",
  },
  {
    step: "02",
    title: "You descend.",
    copy: "Twenty-plus keypoints reconstructed in 3D, thirty times a second. Joint angles solved in one to two milliseconds.",
  },
  {
    step: "03",
    title: "You drift.",
    copy: "Fault detected, severity graded, correction spoken — in under 50 milliseconds. Specific, not generic: Nova knows which knee, how far, and whether it matters for your anatomy.",
    cue: "Knees out.",
  },
  {
    step: "04",
    title: "You finish.",
    copy: "Reps counted. Depth graded. A set recap in plain English, and your next set adjusted before you're back under the bar.",
  },
] as const;

export function OneSet() {
  return (
    <section className="border-y border-border bg-bg-2">
      <div className="mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-32">
        <SectionHeading
          eyebrow="One set with Nowva"
          title="Step in. Nova takes it from there."
        />

        <div className="mt-16 grid gap-10 md:grid-cols-4 md:gap-6">
          {BEATS.map((beat, index) => (
            <Reveal key={beat.step} delay={index * 0.12}>
              <div className="relative h-full border-t border-border pt-6 md:border-t-2">
                <span
                  aria-hidden
                  className="absolute -top-px left-0 h-px w-10 bg-accent md:h-0.5"
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
