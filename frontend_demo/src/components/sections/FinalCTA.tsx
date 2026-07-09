import { useRef } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { useInView } from '@/hooks/useInView';
import { trackEvent } from '@/lib/analytics';

export const FinalCTA = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  const handleCTAClick = () => {
    trackEvent('cta_click', { location: 'final_cta' });
    document.getElementById('program-generator')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <section ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Ambient glow */}
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            'radial-gradient(ellipse at 50% 40%, rgba(0, 229, 255, 0.06), transparent 60%)',
        }}
        aria-hidden="true"
      />

      <div className="section-container relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="relative max-w-4xl mx-auto text-center rounded-2xl border border-border bg-surface/60 backdrop-blur-xl px-6 py-14 md:px-16 md:py-20"
        >
          {/* Gradient top hairline */}
          <div
            className="absolute top-0 left-1/2 -translate-x-1/2 w-2/3 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent"
            aria-hidden="true"
          />

          <p className="eyebrow mb-4">Start Today</p>
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground mb-5 text-balance">
            The rack ships in 2027.
            <br />
            <span className="gradient-text-amber">Your program is ready now.</span>
          </h2>
          <p className="text-body-lg text-foreground-secondary max-w-xl mx-auto mb-10">
            Try the intelligence that will run inside Nowva. Generate a personalized,
            evidence-based training program in about a minute — free, no card required.
          </p>

          <button
            onClick={handleCTAClick}
            className="button-primary text-lg group gap-3 mx-auto"
          >
            Get My Free Program
            <ArrowRight
              className="w-5 h-5 transition-transform duration-300 group-hover:translate-x-1"
              aria-hidden="true"
            />
          </button>
        </motion.div>
      </div>
    </section>
  );
};
