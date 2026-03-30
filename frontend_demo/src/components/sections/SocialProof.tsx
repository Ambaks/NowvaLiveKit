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

const stats = [
  { end: 500, suffix: '+', label: 'Athletes in Beta', delay: 0 },
  { end: 10000, suffix: '+', label: 'Programs Generated', delay: 0.15 },
  { end: 60, suffix: 's', prefix: '<', label: 'Average Generation', delay: 0.3 },
];

export const SocialProof = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section ref={ref} className="relative py-14 md:py-16 overflow-hidden">
      {/* Top separator */}
      <div className="separator" />

      <div className="section-container relative z-10">
        <div className="flex flex-col md:flex-row items-center justify-center gap-8 md:gap-0 py-8">
          {stats.map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 16 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.2 + stat.delay }}
              className="text-center flex-1 relative"
            >
              {/* Vertical divider between stats (desktop) */}
              {i > 0 && (
                <div className="hidden md:block absolute left-0 top-1/2 -translate-y-1/2 w-px h-12 bg-gradient-to-b from-transparent via-border-light to-transparent" />
              )}

              <div className="font-display text-display-md md:text-display-lg font-bold text-foreground leading-none mb-2">
                {stat.prefix && <span className="text-accent">{stat.prefix}</span>}
                <CountUp end={stat.end} suffix={stat.suffix} duration={1.8} />
              </div>
              <div className="font-mono text-[11px] tracking-[0.15em] uppercase text-foreground-tertiary">
                {stat.label}
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Bottom separator */}
      <div className="separator" />
    </section>
  );
};
