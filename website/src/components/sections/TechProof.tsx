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

const SPECS = [
  "Multi-camera 3D triangulation",
  "20+ keypoints · 30 fps",
  "IK solve ~1–2 ms / frame",
  "Fault-to-cue < 50 ms",
  "Severity: mild / moderate / severe",
  "Anatomy-calibrated thresholds",
] as const;

const PRIVACY_POINTS = [
  "No cloud video processing",
  "No uploads — footage never leaves the rack",
  "Coaching runs on the rack's own computer",
] as const;

function ShotFigure({ shot, delay }: { shot: Shot; delay: number }) {
  return (
    <Reveal delay={delay} className={shot.wide ? "md:col-span-2" : undefined}>
      <figure className="group flex h-full flex-col overflow-hidden rounded-xl border border-border bg-[#0a0a0b]">
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
              <span className="gradient-text">The intelligence works today.</span>
            </>
          }
          lead="This is live telemetry from our biomechanics engine — the same software that will run inside every Nowva Rack. Real skeletons, real fault detection, real sessions in our lab."
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
            <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
              {SPECS.map((spec) => (
                <p key={spec} className="flex items-center gap-3 font-mono text-sm text-fg">
                  <span className="size-1 shrink-0 rounded-full bg-accent" aria-hidden />
                  {spec}
                </p>
              ))}
            </div>
            <p className="mt-7 border-t border-border pt-5 font-mono text-[0.65rem] uppercase tracking-[0.18em] text-fg-2">
              Measured on our lab prototype
            </p>
          </div>
        </Reveal>

        <Reveal className="mt-14">
          <div className="grid items-center gap-8 rounded-2xl border border-accent/25 bg-surface p-8 md:grid-cols-[auto_1fr] md:p-10">
            <ShieldCheck
              className="size-12 text-accent-ink md:size-14"
              strokeWidth={1.4}
              aria-hidden
            />
            <div>
              <h3 className="font-display text-2xl font-bold tracking-tight text-fg">
                Cameras that never phone home.
              </h3>
              <p className="mt-3 max-w-2xl leading-relaxed text-fg-2">
                Everything runs on a dedicated AI computer inside the rack.
                Your video is processed on-device and never leaves it — no
                cloud, no uploads, no account required to lift. Edge AI isn&apos;t
                just faster. It&apos;s the only version of this product we&apos;d put in
                our own homes.
              </p>
              <ul className="mt-5 flex flex-wrap gap-x-8 gap-y-2">
                {PRIVACY_POINTS.map((point) => (
                  <li
                    key={point}
                    className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-accent-ink"
                  >
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
