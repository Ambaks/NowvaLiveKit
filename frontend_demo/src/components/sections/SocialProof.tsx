import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useInView } from '@/hooks/useInView';

const CountUp = ({ end, suffix = '', duration = 2 }: { end: number; suffix?: string; duration?: number }) => {
  const ref = useRef<HTMLSpanElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(containerRef, { once: true });
  const [display, setDisplay] = useState('0');

  useEffect(() => {
    if (!isInView) return;
    const startTime = performance.now();

    const tick = (now: number) => {
      const elapsed = (now - startTime) / 1000;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.floor(eased * end);
      setDisplay(current.toLocaleString());
      if (progress < 1) requestAnimationFrame(tick);
      else setDisplay(end.toLocaleString());
    };

    requestAnimationFrame(tick);
  }, [isInView, end, duration]);

  return (
    <div ref={containerRef}>
      <span ref={ref}>{display}</span>{suffix}
    </div>
  );
};

// Honest, capability-based specs — Nowva is pre-launch, so no user/traction claims.
const stats = [
  { end: 20, suffix: '+', label: 'Keypoints tracked in 3D', delay: 0 },
  { end: 2, suffix: '', label: 'Camera angles triangulated', delay: 0.1 },
  { end: 100, suffix: '%', label: 'Voice runs on-device', delay: 0.2 },
  { end: 60, prefix: '<', suffix: 's', label: 'To generate a program', delay: 0.3 },
];

export const SocialProof = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section ref={ref} className="relative py-14 md:py-16 overflow-hidden">
      {/* Top separator */}
      <div className="separator" />

      <div className="section-container relative z-10">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-y-10 gap-x-4 py-10">
          {stats.map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 16 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.2 + stat.delay }}
              className="text-center relative"
            >
              {/* Vertical divider between stats (desktop) */}
              {i > 0 && (
                <div className="hidden md:block absolute left-0 top-1/2 -translate-y-1/2 w-px h-12 bg-gradient-to-b from-transparent via-border-light to-transparent" />
              )}

              <div className="font-display text-heading-xl md:text-display-md font-bold text-foreground leading-none mb-2">
                {stat.prefix && <span className="text-accent">{stat.prefix}</span>}
                <CountUp end={stat.end} suffix={stat.suffix} duration={1.6} />
              </div>
              <div className="font-mono text-[11px] tracking-[0.15em] uppercase text-foreground-tertiary">
                {stat.label}
              </div>
            </motion.div>
          ))}
        </div>

        <p className="text-center text-caption text-foreground-tertiary/70 pb-2">
          Technical specs of the system in development — not usage or traction claims.
        </p>
      </div>

      {/* Bottom separator */}
      <div className="separator" />
    </section>
  );
};
