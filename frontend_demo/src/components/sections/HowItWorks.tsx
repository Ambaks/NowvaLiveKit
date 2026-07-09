import { useRef } from 'react';
import { motion } from 'framer-motion';
import { ScanLine, Boxes, Volume2 } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const steps = [
  {
    icon: ScanLine,
    number: '01',
    title: 'It sees you',
    description:
      'Dual cameras built into the uprights capture your lift from two angles — no phone to prop up, no wearable to charge. You just step in and train.',
    detail: 'Dual-camera capture · 20+ keypoints',
  },
  {
    icon: Boxes,
    number: '02',
    title: 'It analyzes your form',
    description:
      'The biomechanics engine triangulates your joints in 3D and measures depth, bar path, tempo and symmetry against your own anatomy — rep after rep.',
    detail: '3D triangulation · Per-rep diagnosis',
  },
  {
    icon: Volume2,
    number: '03',
    title: 'It coaches you out loud',
    description:
      'A voice coach running on-device turns each diagnosis into a clear cue — "drive your knees out", "two more clean reps" — the moment it matters.',
    detail: 'On-device voice · Real-time cues',
  },
];

export const HowItWorks = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section id="how-it-works" ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Subtle grid dot pattern */}
      <div
        className="absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage: 'radial-gradient(circle, #00E5FF 1px, transparent 1px)',
          backgroundSize: '32px 32px',
        }}
        aria-hidden="true"
      />

      <div className="section-container relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-20 max-w-2xl mx-auto"
        >
          <p className="eyebrow mb-4">How It Works</p>
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground mb-5 text-balance">
            See. Analyze. <span className="text-accent">Correct.</span>
          </h2>
          <p className="text-body-lg text-foreground-secondary">
            The same loop a great coach runs — watch the rep, read the movement, call the
            cue — happening live, on every set.
          </p>
        </motion.div>

        {/* Steps — horizontal on desktop, vertical on mobile */}
        <ol className="relative max-w-5xl mx-auto grid md:grid-cols-3 gap-12 md:gap-8 list-none">
          {/* Connecting line — desktop */}
          <div className="hidden md:block absolute top-[52px] left-[16.67%] right-[16.67%] h-px" aria-hidden="true">
            <motion.div
              initial={{ scaleX: 0 }}
              animate={isInView ? { scaleX: 1 } : {}}
              transition={{ duration: 1.2, delay: 0.5, ease: 'easeOut' }}
              className="w-full h-px bg-gradient-to-r from-accent/40 via-accent/20 to-accent/40 origin-left"
            />
          </div>

          {steps.map((step, index) => (
            <motion.li
              key={step.title}
              initial={{ opacity: 0, y: 24 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.3 + index * 0.18, ease: 'easeOut' }}
              className="text-center group"
            >
              {/* Step icon with glow */}
              <div className="relative inline-flex mb-8">
                <div className="absolute inset-0 bg-accent/20 rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <div className="relative p-4 rounded-2xl bg-surface border border-border group-hover:border-accent/30 transition-colors duration-300">
                  <step.icon className="w-7 h-7 text-accent" aria-hidden="true" />
                </div>
              </div>

              <p className="text-caption font-mono text-accent/60 mb-3">{step.number}</p>

              <h3 className="font-display text-heading-md font-semibold text-foreground mb-3">
                {step.title}
              </h3>
              <p className="text-body-md text-foreground-secondary leading-relaxed max-w-xs mx-auto mb-4">
                {step.description}
              </p>
              <p className="text-caption uppercase tracking-widest text-accent/50">
                {step.detail}
              </p>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
};
