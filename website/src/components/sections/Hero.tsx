"use client";

import { useRef } from "react";
import Image from "next/image";
import { motion, useScroll, useTransform } from "motion/react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Viewfinder } from "@/components/ui/Viewfinder";
import rackAngle from "@/images/rack-angle.png";

const TRUST_STATS = [
  { value: "<50 ms", label: "fault-to-cue" },
  { value: "30 fps", label: "3D analysis" },
  { value: "100%", label: "on-device" },
] as const;

const rise = (index: number) => ({ "--rise": index }) as React.CSSProperties;

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
      className="grid-bg grid-fade relative overflow-hidden pb-24 pt-32 md:pb-32 md:pt-40"
    >
      <div className="mx-auto grid max-w-6xl items-center gap-14 px-5 md:grid-cols-[1.05fr_0.95fr] md:px-8">
        <div>
          <div className="hero-rise" style={rise(0)}>
            <Badge pulse>Founding batch · Ships Spring/Summer 2027</Badge>
          </div>

          <h1
            className="hero-rise mt-7 font-display text-5xl font-extrabold leading-[1.02] tracking-tight text-fg sm:text-6xl lg:text-7xl"
            style={rise(1)}
          >
            Your coach.
            <br />
            <span className="gradient-text">Built into the steel.</span>
          </h1>

          <p
            className="hero-rise mt-6 max-w-xl text-lg leading-relaxed text-fg-2"
            style={rise(2)}
          >
            The Nowva Rack watches every rep with built-in cameras, diagnoses
            your form in real time, and coaches you out loud — like a
            world-class trainer who never looks away. No phone. No wearable.
            Just lift.
          </p>

          <div
            className="hero-rise mt-9 flex flex-wrap items-center gap-4"
            style={rise(3)}
          >
            <Button href="#reserve" size="lg" cta="hero">
              Reserve Your Rack
            </Button>
            <Button href="#technology" variant="ghost" size="lg" cta="hero-secondary">
              See the technology
            </Button>
          </div>

          <dl
            className="hero-rise mt-12 flex max-w-md divide-x divide-border border-y border-border"
            style={rise(4)}
          >
            {TRUST_STATS.map((stat) => (
              <div key={stat.label} className="flex-1 py-4 pl-4 first:pl-0 sm:pl-6">
                <dt className="font-mono text-[0.65rem] uppercase tracking-[0.18em] text-fg-2">
                  {stat.label}
                </dt>
                <dd className="mt-1 font-mono text-lg text-accent-ink">
                  {stat.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="hero-img-in">
          <motion.div style={{ y: imageY }}>
            <Viewfinder label="NV-01 / PROTOTYPE" className="mx-auto max-w-md md:max-w-none">
              <div
                aria-hidden
                className="absolute inset-0 -z-10 scale-110 rounded-full opacity-80"
                style={{
                  background:
                    "radial-gradient(ellipse 60% 55% at 50% 45%, var(--glow), transparent 70%)",
                }}
              />
              <div className="relative overflow-hidden">
                <Image
                  src={rackAngle}
                  alt="Early CAD render of the Nowva Rack — a squat rack enclosed in a curved shell with an integrated display"
                  preload
                  sizes="(max-width: 768px) 92vw, 520px"
                  className="render-blend w-full"
                />
                <div className="scanline" aria-hidden />
              </div>
            </Viewfinder>
            <p className="mt-4 text-center font-mono text-[0.65rem] tracking-[0.2em] text-fg-2">
              EARLY CAD RENDER — DESIGN EVOLVING
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
