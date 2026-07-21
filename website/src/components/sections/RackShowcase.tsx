import Image from "next/image";
import { AudioLines, Gem, ScanEye, Sparkles } from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { Viewfinder } from "@/components/ui/Viewfinder";
import { cn } from "@/lib/cn";
import rackFront from "@/images/rack-front.png";

const CALLOUTS = [
  { x: 27, y: 26, side: "left", label: "Camera array", detail: "machined into the uprights" },
  { x: 49, y: 47, side: "right", label: "Integrated display", detail: "live form telemetry" },
  { x: 80, y: 30, side: "right", label: "Steel shell", detail: "premium, space-saving" },
  { x: 49, y: 87, side: "left", label: "Onboard AI computer", detail: "everything runs in the base" },
] as const;

const FEATURES = [
  {
    icon: ScanEye,
    index: "01",
    title: "Built-in computer vision",
    copy: "Multi-camera 3D pose triangulation tracks 20+ body keypoints at 30 frames per second. Every angle measured, every rep counted, every deviation caught.",
  },
  {
    icon: AudioLines,
    index: "02",
    title: "A coach that speaks",
    copy: "Nova, your AI coach, lives in the rack. Corrections arrive out loud in under 50 milliseconds — before you finish the rep, not after.",
  },
  {
    icon: Sparkles,
    index: "03",
    title: "Adaptive intelligence",
    copy: "Programs generated in about 60 seconds, then autoregulated around your fatigue, velocity, and progress — the way a great coach periodizes.",
  },
  {
    icon: Gem,
    index: "04",
    title: "Designed to impress",
    copy: "Premium steel, an integrated touchscreen, and a minimal footprint. Equipment you want in your home, not hidden in a garage.",
  },
] as const;

export function RackShowcase() {
  return (
    <section id="rack" className="relative overflow-hidden">
      <div className="mx-auto max-w-6xl px-5 py-24 md:px-8 md:py-36">
        <SectionHeading
          eyebrow="The Rack"
          title={
            <>
              Everything your coach does.{" "}
              <span className="gradient-text">Built into the steel.</span>
            </>
          }
          lead="Premium steel. Cameras machined into the uprights. A voice that lives in the frame. The Nowva Rack replaces a monthly coaching bill with a piece of equipment you own."
        />

        <Reveal delay={0.15} className="mt-16">
          <Viewfinder label="NV-01 / FRONT ELEVATION" className="mx-auto max-w-3xl">
            <div className="relative overflow-hidden">
              <Image
                src={rackFront}
                alt="Front view CAD render of the Nowva Rack showing the camera uprights, integrated display, bench, and curved shell"
                sizes="(max-width: 768px) 92vw, 768px"
                className="render-blend w-full"
              />
              {/* engineering-plate callouts (desktop) */}
              <div className="absolute inset-0 hidden md:block" aria-hidden>
                {CALLOUTS.map((callout) => (
                  <div
                    key={callout.label}
                    className="absolute"
                    style={{ left: `${callout.x}%`, top: `${callout.y}%` }}
                  >
                    <span className="absolute -translate-x-1/2 -translate-y-1/2">
                      <span className="block size-2.5 rounded-full border border-accent bg-accent/20" />
                    </span>
                    <span
                      className={cn(
                        "absolute top-0 hidden w-40 -translate-y-1/2 lg:block",
                        callout.side === "left"
                          ? "right-4 text-right"
                          : "left-4 text-left",
                      )}
                    >
                      <span
                        className={cn(
                          "mb-1 block h-px w-8 bg-accent/50",
                          callout.side === "left" ? "ml-auto" : "",
                        )}
                      />
                      <span
                        className={cn(
                          "inline-block rounded-md bg-bg/80 px-2 py-1 backdrop-blur-sm",
                          callout.side === "left" ? "text-right" : "text-left",
                        )}
                      >
                        <span className="block font-mono text-[0.62rem] uppercase tracking-[0.16em] text-accent-ink">
                          {callout.label}
                        </span>
                        <span className="block font-mono text-[0.6rem] leading-snug text-fg-2">
                          {callout.detail}
                        </span>
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </Viewfinder>
          <p className="mt-4 text-center font-mono text-[0.65rem] tracking-[0.2em] text-fg-2">
            EARLY CAD RENDER — DESIGN EVOLVING
          </p>
          {/* callout list (mobile) */}
          <dl className="mx-auto mt-8 grid max-w-md grid-cols-2 gap-4 lg:hidden">
            {CALLOUTS.map((callout) => (
              <div key={callout.label} className="border-l border-accent/50 pl-3">
                <dt className="font-mono text-[0.62rem] uppercase tracking-[0.16em] text-accent-ink">
                  {callout.label}
                </dt>
                <dd className="font-mono text-[0.6rem] text-fg-2">{callout.detail}</dd>
              </div>
            ))}
          </dl>
        </Reveal>

        <div className="mt-20 grid gap-5 md:grid-cols-2">
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.index} delay={index * 0.08}>
              <article className="group relative h-full overflow-hidden rounded-2xl border border-border bg-surface p-7 transition-colors duration-300 hover:border-accent/50">
                <div
                  aria-hidden
                  className="pointer-events-none absolute -right-16 -top-16 size-44 rounded-full opacity-0 transition-opacity duration-500 group-hover:opacity-100"
                  style={{
                    background:
                      "radial-gradient(circle, var(--glow), transparent 70%)",
                  }}
                />
                <div className="flex items-start justify-between">
                  <feature.icon className="size-6 text-accent-ink" strokeWidth={1.6} />
                  <span className="font-mono text-xs text-fg-3">{feature.index}</span>
                </div>
                <h3 className="mt-5 font-display text-xl font-bold tracking-tight text-fg">
                  {feature.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-fg-2">{feature.copy}</p>
              </article>
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-12">
          <a
            href="#reserve"
            data-cta="rack-section"
            className="font-mono text-sm tracking-wide text-accent-ink transition-opacity hover:opacity-75"
          >
            Reserve the founding batch →
          </a>
        </Reveal>
      </div>
    </section>
  );
}
