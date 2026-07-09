import { motion } from 'framer-motion';
import { ArrowRight, ChevronDown, Eye, Waypoints, MessageSquare } from 'lucide-react';
import { RackVisualization } from './RackVisualization';
import { trackEvent } from '@/lib/analytics';

const proofChips = [
  { icon: Eye, label: 'Real-time vision' },
  { icon: Waypoints, label: '3D biomechanics' },
  { icon: MessageSquare, label: 'On-device voice coach' },
];

export const Hero = () => {
  const handleCTAClick = () => {
    trackEvent('cta_click', { location: 'hero' });
    document.getElementById('program-generator')?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleLearnMore = () => {
    document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
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
      <div className="section-container relative z-10 w-full pt-28 pb-20 md:pt-40 md:pb-32">
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
              className="font-display font-extrabold text-[2.75rem] leading-[1.02] sm:text-display-lg md:text-display-xl lg:text-display-2xl text-foreground mb-6 text-balance"
            >
              The coach that
              <br />
              <span className="gradient-text">sees every rep.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="text-body-lg md:text-heading-md text-foreground-secondary max-w-xl mb-8 leading-relaxed"
            >
              Nowva is an AI trainer built into a squat rack. It watches your technique in
              real time, coaches your lifts by voice, and adapts your program as you train —
              no phone, no wearable. Just lift.
            </motion.p>

            {/* Honest capability chips */}
            <motion.ul
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.45 }}
              className="flex flex-wrap gap-x-5 gap-y-3 mb-9"
            >
              {proofChips.map((chip) => (
                <li
                  key={chip.label}
                  className="inline-flex items-center gap-2 text-body-sm text-foreground-secondary"
                >
                  <chip.icon className="w-4 h-4 text-accent" aria-hidden="true" />
                  {chip.label}
                </li>
              ))}
            </motion.ul>

            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.55 }}
              className="flex flex-col sm:flex-row gap-4"
            >
              <button
                onClick={handleCTAClick}
                className="button-primary text-lg group w-full sm:w-auto gap-3"
              >
                Get a Free Program
                <ArrowRight
                  className="w-5 h-5 transition-transform duration-300 group-hover:translate-x-1"
                  aria-hidden="true"
                />
              </button>
              <button
                onClick={handleLearnMore}
                className="button-secondary text-lg group w-full sm:w-auto gap-3"
              >
                See How It Works
                <ChevronDown
                  className="w-4 h-4 transition-transform duration-300 group-hover:translate-y-0.5"
                  aria-hidden="true"
                />
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
        aria-hidden="true"
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
