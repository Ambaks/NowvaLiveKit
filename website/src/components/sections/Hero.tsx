"use client";

import { Fragment, useRef } from "react";
import Image from "next/image";
import { motion, useScroll, useTransform } from "motion/react";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import rackAngle from "@/images/rack-angle.png";

const rise = (index: number) => ({ "--rise": index }) as React.CSSProperties;

const CAPABILITIES = [
  {
    index: "01",
    title: "State-of-the-Art Voice Agent",
    body: "A coach you talk to mid-set — it hears you, answers, and cues your next rep.",
  },
  {
    index: "02",
    title: "Superhuman Vision",
    body: "Cameras that track every joint of every rep, catching what you can't feel.",
  },
  {
    index: "03",
    title: "Elite Strength & Conditioning",
    body: "Programming, progression, and recovery — full coaching intelligence.",
  },
] as const;

export function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  });
  const imageY = useTransform(scrollYProgress, [0, 1], [0, 70]);

  return (
    <>
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
          <h1
            className="hero-rise mt-9 font-display text-5xl font-extrabold leading-[1.02] tracking-tight text-fg sm:text-6xl xl:text-[4rem]"
            style={rise(1)}
          >
            The first rack
            <br />
            <span className="gradient-text gradient-text-animated">that coaches you.</span>
          </h1>

          <p
            className="hero-rise mt-8 max-w-xl text-lg leading-relaxed text-fg-2"
            style={rise(2)}
          >
            Cameras in the steel. A biomechanics engine underneath. A voice
            that catches faults mid-rep and corrects you before your next
            one — a coach that programs your training and plans your
            nutrition. No phone propped on a bench. No wearable. Just lift.
          </p>

          <div
            className="hero-rise mt-12 flex flex-wrap items-center gap-4"
            style={rise(3)}
          >
            <Button href="#reserve" size="lg" cta="hero">
              Reserve Your Rack — $0
            </Button>
          </div>
        </div>
      </div>

      <p className="hero-img-in absolute bottom-6 right-6 hidden font-mono text-[0.65rem] tracking-[0.2em] text-fg-3 md:block lg:right-10">
        NV-01 · EARLY CAD RENDER
      </p>
    </section>

    {/* Capability manifest: what's inside the rack, as a spec readout —
        silver-etched titles between hairline rules, below the hero fold. */}
    <div className="relative mx-auto w-full max-w-6xl px-5 pb-20 pt-12 md:px-8 md:pb-24 md:pt-16">
      <div className="flex flex-col gap-8 lg:flex-row lg:items-stretch lg:gap-10 xl:gap-12">
        {CAPABILITIES.map((capability, index) => (
          <Fragment key={capability.index}>
            {index > 0 && (
              <div
                aria-hidden
                className="h-px w-full bg-linear-to-r from-transparent via-border-strong to-transparent lg:h-auto lg:w-px lg:self-stretch lg:bg-linear-to-b"
              />
            )}
            <Reveal delay={index * 0.12} className="flex-1">
              <p className="font-mono text-xs tracking-[0.22em] text-accent-ink">
                {capability.index}
              </p>
              <h2 className="silver-text gradient-text-animated mt-3 font-display text-lg font-bold tracking-tight lg:whitespace-nowrap xl:text-xl">
                {capability.title}
              </h2>
              <p className="mt-2 max-w-xs text-sm leading-relaxed text-fg-2">
                {capability.body}
              </p>
            </Reveal>
          </Fragment>
        ))}
      </div>
    </div>
    </>
  );
}
