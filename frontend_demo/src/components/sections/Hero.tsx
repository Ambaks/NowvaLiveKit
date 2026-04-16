import { motion } from 'framer-motion';
import { RackVisualization } from './RackVisualization';
import { trackEvent } from '@/lib/analytics';

export const Hero = () => {
  const handleCTAClick = () => {
    trackEvent('cta_click', { location: 'hero' });
    document.getElementById('program-generator')?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleLearnMore = () => {
    document.getElementById('the-rack')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-mesh-dark" />
      <div className="absolute top-1/4 -left-32 w-[600px] h-[600px] bg-accent/[0.04] rounded-full blur-[120px]" />
      <div className="absolute bottom-1/4 right-0 w-[400px] h-[400px] bg-cta/[0.03] rounded-full blur-[100px]" />

      {/* Mobile background rack (atmospheric) */}
      <div className="absolute inset-0 lg:hidden flex items-center justify-center pointer-events-none overflow-hidden">
        <div className="w-[280px] opacity-[0.06] translate-x-24 translate-y-12">
          <RackVisualization />
        </div>
      </div>

      {/* Content */}
      <div className="section-container relative z-10 w-full pt-24 pb-20 md:pt-40 md:pb-32">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-8 items-center">
          {/* Left: Copy */}
          <div className="relative z-20 max-w-2xl">
            {/* In Development badge */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.05 }}
              className="inline-flex items-center gap-2 mb-8 px-4 py-1.5 rounded-full bg-surface/80 border border-border"
            >
              <motion.span
                className="w-1.5 h-1.5 rounded-full bg-cta"
                animate={{ opacity: [1, 0.4, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
              <span className="font-mono text-[11px] tracking-[0.12em] text-foreground-secondary uppercase">
                In Development · 2027
              </span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.15 }}
              className="font-display font-extrabold text-[2.75rem] sm:text-display-lg md:text-display-xl lg:text-display-2xl text-foreground mb-6"
            >
              Intelligence,
              <br />
              <span className="gradient-text">Built In.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="text-body-lg md:text-heading-md text-foreground-secondary max-w-lg mb-8 md:mb-10 leading-relaxed"
            >
              The AI-powered squat rack that watches your form, coaches your lifts, and programs your training — all in real time. No phone. No wearable. Just lift.
            </motion.p>

            {/* Stats strip */}
            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.55 }}
              className="flex flex-col sm:flex-row gap-4"
            >
              <button
                onClick={handleCTAClick}
                className="button-primary text-lg group w-full sm:w-auto text-center justify-center"
              >
                <span className="flex items-center gap-3">
                  Get a Free Program
                  <svg
                    className="w-5 h-5 transition-transform duration-300 group-hover:translate-x-1"
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                  </svg>
                </span>
              </button>
              <button
                onClick={handleLearnMore}
                className="button-secondary text-lg group w-full sm:w-auto text-center justify-center"
              >
                <span className="flex items-center gap-3">
                  See the Technology
                  <svg
                    className="w-4 h-4 transition-transform duration-300 group-hover:translate-y-0.5"
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </span>
              </button>
            </motion.div>
          </div>

          {/* Right: Rack visualization — desktop */}
          <motion.div
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, delay: 0.3, ease: 'easeOut' }}
            className="relative hidden lg:block"
          >
            <RackVisualization />
          </motion.div>
        </div>
      </div>

      {/* Scroll indicator */}
      <motion.div
        className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-3"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2, duration: 0.6 }}
      >
        <span className="text-[10px] uppercase tracking-[0.3em] text-foreground-tertiary font-mono">Scroll</span>
        <motion.div
          className="w-px h-8 bg-gradient-to-b from-accent/50 to-transparent"
          animate={{ scaleY: [1, 0.5, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      </motion.div>
    </section>
  );
};
