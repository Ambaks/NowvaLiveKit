"use client";

import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ThemedLogo } from "@/components/ui/Logo";
import { cn } from "@/lib/cn";

/* Ghost W monogram with a slow scroll parallax. Parent section must be
   relative + overflow-hidden; position the mark via className. */
export function LogoWatermark({
  size = 520,
  className,
}: {
  size?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const parallaxY = useTransform(scrollYProgress, [0, 1], [60, -60]);

  return (
    <div
      ref={ref}
      aria-hidden
      className={cn(
        "pointer-events-none absolute opacity-[0.04] dark:opacity-[0.05] [&_img]:max-w-none",
        className,
      )}
    >
      <motion.div style={reduced ? undefined : { y: parallaxY }}>
        <ThemedLogo size={size} />
      </motion.div>
    </div>
  );
}
