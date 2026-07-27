"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useScroll,
  useTransform,
} from "motion/react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import rackAngle from "@/images/rack-angle.png";

const TRUST_STATS = [
  { prefix: "<", target: 50, suffix: " ms", label: "fault-to-cue" },
  { prefix: "", target: 30, suffix: " fps", label: "3D analysis" },
  { prefix: "", target: 100, suffix: "%", label: "on-device" },
] as const;

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

/* Count-up lands as the CSS hero-rise stats row settles. The base delay
   mirrors --rise-base: long when the intro wipe plays, short when the
   intro is skipped (html[data-intro="off"], set pre-hydration). When the
   3D intro stage takes over (html[data-intro="3d"]) the rise is held until
   the nv:intro-done event, so the count waits for that signal instead. */
const COUNT_DELAY_S = 1.8;
const COUNT_DELAY_INTRO_OFF_S = 0.7;
const COUNT_DELAY_INTRO_DONE_S = 0.75;
const COUNT_DONE_FAILSAFE_MS = 10_000;
const COUNT_STAGGER_S = 0.08;
const COUNT_DURATION_S = 0.9;

const rise = (index: number) => ({ "--rise": index }) as React.CSSProperties;

function StatCount({ target, stagger }: { target: number; stagger: number }) {
  const reducedMotion = useReducedMotion();
  const count = useMotionValue(0);
  const rounded = useTransform(count, (latest) => Math.round(latest));

  useEffect(() => {
    if (reducedMotion) {
      count.set(target);
      return;
    }
    const start = (baseDelay: number) =>
      animate(count, target, {
        duration: COUNT_DURATION_S,
        delay: baseDelay + stagger,
        ease: EASE,
      });

    const intro = document.documentElement.dataset.intro;
    if (intro === "3d") {
      let controls: ReturnType<typeof animate> | undefined;
      const go = () => {
        if (controls) return;
        controls = start(COUNT_DELAY_INTRO_DONE_S);
      };
      window.addEventListener("nv:intro-done", go, { once: true });
      const failsafe = window.setTimeout(go, COUNT_DONE_FAILSAFE_MS);
      return () => {
        window.removeEventListener("nv:intro-done", go);
        window.clearTimeout(failsafe);
        controls?.stop();
      };
    }

    const controls = start(
      intro === "off"
        ? COUNT_DELAY_INTRO_OFF_S
        : intro === "done"
          ? COUNT_DELAY_INTRO_DONE_S
          : COUNT_DELAY_S,
    );
    return () => controls.stop();
  }, [count, target, stagger, reducedMotion]);

  return (
    <motion.span
      className="inline-block text-right"
      style={{ minWidth: `${String(target).length}ch` }}
    >
      {rounded}
    </motion.span>
  );
}

export function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  });
  const imageY = useTransform(scrollYProgress, [0, 1], [0, 70]);

  return (
    <section
      ref={sectionRef}
      className="relative flex min-h-svh items-center overflow-hidden pb-24 pt-28 md:pb-28 md:pt-32"
    >
      {/* Blueprint grid lives on its own layer so its fade mask never
          touches the overlaid copy. */}
      <div aria-hidden className="grid-bg grid-fade absolute inset-0" />

      {/* Full-bleed render: full viewport height, anchored left; the blend
          treatment melts its white plate into the theme so it has no edges. */}
      <div className="hero-img-in absolute inset-0">
        <motion.div style={{ y: imageY }} className="absolute inset-0">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 46% 52% at 74% 48%, var(--glow), transparent 72%)",
            }}
          />
          <Image
            src={rackAngle}
            alt="Early CAD render of the Nowva Rack — a power rack enclosed in a curved shell with an integrated display"
            fill
            preload
            sizes="100vw"
            className="render-blend object-contain object-center md:object-right"
          />
          <div
            className="absolute inset-y-0 right-0 w-full md:w-[58%]"
            aria-hidden
          >
            <div className="scanline" />
          </div>
        </motion.div>
      </div>

      {/* Legibility scrim between the render and the copy */}
      <div aria-hidden className="hero-scrim pointer-events-none absolute inset-0" />

      <div className="relative mx-auto w-full max-w-6xl px-5 md:px-8">
        <div className="hero-copy md:mr-auto md:w-[54%] lg:w-1/2">
          <div className="hero-rise" style={rise(0)}>
            <Badge pulse>The engine is live · Founding batch open</Badge>
          </div>

          <h1
            className="hero-rise mt-7 font-display text-5xl font-extrabold leading-[1.02] tracking-tight text-fg sm:text-6xl xl:text-[4rem]"
            style={rise(1)}
          >
            The first rack
            <br />
            <span className="gradient-text gradient-text-animated">that coaches you.</span>
          </h1>

          <p
            className="hero-rise mt-6 max-w-xl text-lg leading-relaxed text-fg-2"
            style={rise(2)}
          >
            Cameras in the steel. A biomechanics engine underneath. A voice
            that catches faults mid-rep and corrects you before your next
            one — a coach that programs your training and plans your
            nutrition. No phone propped on a bench. No wearable. Just lift.
          </p>

          <div
            className="hero-rise mt-9 flex flex-wrap items-center gap-4"
            style={rise(3)}
          >
            <Button href="#reserve" size="lg" cta="hero">
              Reserve Your Rack — $0
            </Button>
            <Button href="#technology" variant="ghost" size="lg" cta="hero-secondary">
              See it think
            </Button>
          </div>

          <dl
            className="hero-rise mt-12 flex max-w-md divide-x divide-border border-y border-border"
            style={rise(4)}
          >
            {TRUST_STATS.map((stat, index) => (
              <div key={stat.label} className="flex-1 py-4 pl-4 first:pl-0 sm:pl-6">
                <dt className="font-mono text-[0.65rem] uppercase tracking-[0.18em] text-fg-2">
                  {stat.label}
                </dt>
                <dd className="mt-1 font-mono text-lg text-accent-ink">
                  {stat.prefix}
                  <StatCount
                    target={stat.target}
                    stagger={index * COUNT_STAGGER_S}
                  />
                  {stat.suffix}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <p className="hero-img-in absolute bottom-6 right-6 hidden font-mono text-[0.65rem] tracking-[0.2em] text-fg-3 md:block lg:right-10">
        NV-01 · EARLY CAD RENDER
      </p>
    </section>
  );
}
