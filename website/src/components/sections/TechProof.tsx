import Image, { type StaticImageData } from "next/image";
import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/cn";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/SectionHeading";
import dashKino from "@/images/dash-kino.png";
import dashFaults from "@/images/dash-faults.png";
import dashSide from "@/images/dash-side.png";
import dashFront from "@/images/dash-front.png";
import dashViewport from "@/images/dash-viewport.png";

type Shot = {
  src: StaticImageData;
  alt: string;
  caption: string;
  wide?: boolean;
  /** Crop to a uniform 2:1 card so mixed source ratios line up. */
  cover?: boolean;
};

const SHOTS: Shot[] = [
  {
    src: dashKino,
    alt: "Nowva biomechanics dashboard: 3D skeleton at squat depth with kinodynamic chain solver and fault panels",
    caption: "Live 3D reconstruction — kinodynamic chain solver · 30 fps",
    wide: true,
  },
  {
    src: dashFaults,
    alt: "Fault panel showing knee valgus severe, limited dorsiflexion moderate, and bar drift severe",
    caption: "Fault detection — severity-graded per athlete",
  },
  {
    src: dashSide,
    alt: "Side view of the 3D skeleton at depth with the trunk-lean fault highlighted in red",
    caption: "Side view — trunk-lean fault highlighted live",
    cover: true,
  },
  {
    src: dashFront,
    alt: "Replay dashboard with per-rep baselines, athlete stats, and playback controls",
    caption: "Replay — per-rep baselines and athlete stats",
    cover: true,
  },
  {
    src: dashViewport,
    alt: "Wide lab telemetry view of the reconstructed skeleton over the floor grid",
    caption: "Lab session telemetry — rep 3, frame 11",
    cover: true,
  },
];

type Spec = {
  key: string;
  value: string;
};

const SPECS: Spec[] = [
  { key: "Reconstruction", value: "Multi-camera 3D triangulation" },
  { key: "Pose rate", value: "30 fps · 21 tracked points" },
  { key: "IK solve", value: "~1–2 ms / frame" },
  { key: "Fault-to-cue", value: "< 50 ms" },
  { key: "Severity grading", value: "mild / moderate / severe" },
  { key: "Fault thresholds", value: "calibrated per athlete" },
];

function ShotFigure({ shot, delay }: { shot: Shot; delay: number }) {
  return (
    <Reveal delay={delay} className={shot.wide ? "md:col-span-2" : undefined}>
      {/* Fixed-dark card: the `dark` scope makes theme tokens resolve to dark values in both themes. */}
      <figure className="dark group flex h-full flex-col overflow-hidden rounded-xl border border-border bg-bg">
        <div className={cn("overflow-hidden", shot.cover && "aspect-2/1")}>
          <Image
            src={shot.src}
            alt={shot.alt}
            sizes={shot.wide ? "(max-width: 768px) 92vw, 720px" : "(max-width: 768px) 92vw, 360px"}
            placeholder="blur"
            className={cn(
              "w-full transition-transform duration-700 ease-out group-hover:scale-[1.02]",
              shot.cover && "h-full object-cover",
            )}
          />
        </div>
        <figcaption className="mt-auto flex items-center gap-2.5 border-t border-border px-4 py-3">
          <span className="pulse-dot size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
          <span className="font-mono text-[0.65rem] uppercase tracking-[0.14em] text-fg-2">
            {shot.caption}
          </span>
        </figcaption>
      </figure>
    </Reveal>
  );
}

export function TechProof() {
  return (
    <section id="technology" className="relative">
      <div className="mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-36">
        <SectionHeading
          eyebrow="Technology"
          title={
            <>
              The rack ships in 2027.{" "}
              <span className="gradient-text">The engine works today.</span>
            </>
          }
          lead="This is live telemetry from our biomechanics engine — the same software that ships inside every Nowva Rack. Real athletes, real faults, caught mid-rep in our lab. We proved the engine on the squat, the most unforgiving of the big lifts; every movement that follows runs on the same stack."
        />

        <div className="mt-16 grid gap-5 md:grid-cols-3">
          {SHOTS.slice(0, 2).map((shot, index) => (
            <ShotFigure key={shot.caption} shot={shot} delay={index * 0.08} />
          ))}
          {SHOTS.slice(2).map((shot, index) => (
            <ShotFigure key={shot.caption} shot={shot} delay={index * 0.08} />
          ))}
        </div>

        <Reveal className="mt-14">
          <div className="rounded-2xl border border-border bg-surface p-7 md:p-9">
            <div className="grid gap-x-10 gap-y-4 sm:grid-cols-2">
              {SPECS.map((spec) => (
                <div
                  key={spec.key}
                  className="flex items-baseline justify-between gap-4 border-b border-border pb-3"
                >
                  <span className="font-mono text-[0.65rem] uppercase tracking-[0.18em] text-fg-2">
                    {spec.key}
                  </span>
                  <span className="text-right font-mono text-sm text-fg">
                    {spec.value}
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-7 font-mono text-[0.65rem] uppercase tracking-[0.18em] text-fg-2">
              Measured on our lab prototype
            </p>
          </div>
        </Reveal>

        <Reveal className="mt-14">
          <div className="gradient-border aurora-bg grid items-center gap-8 rounded-2xl p-8 md:grid-cols-[auto_1fr] md:p-10">
            <ShieldCheck
              className="size-12 text-accent-ink md:size-14"
              strokeWidth={1.4}
              aria-hidden
            />
            <div>
              <h3 className="font-display text-2xl font-bold tracking-tight text-fg">
                Fully Local Intelligence.
              </h3>
              <p className="mt-3 max-w-2xl leading-relaxed text-fg-2">
                The biomechanics engine runs in our lab today, processing
                every frame before the next one arrives. Every rack ships
                with a single embedded computer that runs the entire stack —
                multi-camera 3D reconstruction, inverse kinematics, real-time
                fault detection, and Nova&apos;s voice. No server, no cloud,
                no round-trip latency. Your footage never leaves the machine
                it was captured on.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
