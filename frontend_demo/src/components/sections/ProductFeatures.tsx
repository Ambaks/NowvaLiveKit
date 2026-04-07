import { useRef } from 'react';
import { motion } from 'framer-motion';
import { Scan, Mic, Brain, Gem } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const features = [
  {
    icon: Scan,
    title: 'Built-In Computer Vision',
    description:
      'Dual cameras integrated into the uprights track over 20 body keypoints in 3D with lab-grade accuracy. Every angle measured, every rep counted, every deviation caught — no wearables needed.',
    detail: 'Pose estimation · Deep Learning · Barbell tracking · Velocity tracking',
    span: 'large' as const,
  },
  {
    icon: Mic,
    title: 'Real-Time Voice Coaching',
    description:
      'Nova, your AI coach, lives in the rack. Get real-time form cues, teaching, and program adjustments through natural conversation.',
    detail: 'Powered by LLMs · Context-aware · Built in memory',
    span: 'small' as const,
  },
  {
    icon: Brain,
    title: 'Adaptive Intelligence',
    description:
      'Every session feeds the system. Your training auto-regulates based on velocity, RPE, and fatigue — predicting plateaus before they happen, like a world class coach would.',
    detail: 'Autoregulation · Fatigue management · Periodization',
    span: 'small' as const,
  },
  {
    icon: Gem,
    title: 'Designed to Impress',
    description:
      'Premium steel construction with a minimal footprint. Clean lines, integrated cable management, and an integrated touchscreen display. A rack that elevates any training space.',
    detail: 'Compact footprint · Premium materials · Home gym ready',
    span: 'large' as const,
  },
];

// Mini animated visualization for the CV card
const CVMiniViz = () => (
  <div className="absolute top-4 right-4 w-20 h-24 opacity-20 group-hover:opacity-40 transition-opacity duration-500">
    <svg viewBox="0 0 60 72" className="w-full h-full">
      {/* Simplified skeleton */}
      {[
        'M 30 8 L 30 20', // head-neck
        'M 20 26 L 30 20 L 40 26', // shoulders
        'M 20 26 L 16 38', // l arm
        'M 40 26 L 44 38', // r arm
        'M 30 20 L 30 40', // torso
        'M 22 44 L 30 40 L 38 44', // hips
        'M 22 44 L 20 58', // l leg
        'M 38 44 L 40 58', // r leg
      ].map((d, i) => (
        <motion.path
          key={i}
          d={d}
          stroke="#00E5FF"
          strokeWidth={1.5}
          strokeLinecap="round"
          fill="none"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.4, delay: 0.5 + i * 0.05 }}
        />
      ))}
      <motion.circle cx="30" cy="6" r="3" fill="#00E5FF"
        animate={{ opacity: [0.6, 1, 0.6] }}
        transition={{ duration: 2, repeat: Infinity }}
      />
    </svg>
  </div>
);

// Mini waveform for voice card
const WaveformMini = () => (
  <div className="absolute bottom-4 right-4 flex items-end gap-[3px] h-8 opacity-20 group-hover:opacity-40 transition-opacity duration-500">
    {[12, 20, 8, 24, 16, 10, 22, 14, 18, 6].map((h, i) => (
      <motion.div
        key={i}
        className="w-[3px] bg-accent rounded-full"
        animate={{ height: [h * 0.3, h, h * 0.5, h * 0.8, h * 0.3] }}
        transition={{ duration: 1.8 + i * 0.1, repeat: Infinity, ease: 'easeInOut', delay: i * 0.08 }}
      />
    ))}
  </div>
);

export const ProductFeatures = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section id="the-rack" ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      <div className="absolute inset-0 bg-background-secondary/40" />

      <div className="section-container relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="mb-14"
        >
          <p className="eyebrow mb-4">The Rack</p>
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground max-w-3xl mb-5">
            Everything your coach does.{' '}
            <span className="text-accent">Built into the steel.</span>
          </h2>
          <p className="text-body-lg text-foreground-secondary max-w-2xl">
            The Nowva Rack integrates computer vision, voice AI, and adaptive programming directly into a premium squat rack — no phone, no wearable, no compromise.
          </p>
        </motion.div>

        {/* Bento grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 24 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.15 + index * 0.1, ease: 'easeOut' }}
              className={`
                relative overflow-hidden group
                bg-surface/80 border border-border rounded-2xl p-8 md:p-10
                hover:border-accent/20 hover:bg-surface transition-all duration-300
                ${feature.span === 'large' ? 'md:col-span-2' : 'md:col-span-1'}
              `}
            >
              {/* Hover gradient */}
              <div className="absolute inset-0 bg-gradient-to-br from-accent/[0.03] via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

              {/* Mini visualization */}
              {index === 0 && <CVMiniViz />}
              {index === 1 && <WaveformMini />}

              <div className="relative z-10">
                {/* Icon */}
                <div className="mb-6">
                  <div className="inline-flex p-2.5 rounded-lg bg-accent/[0.06] border border-accent/10 group-hover:bg-accent/10 group-hover:border-accent/20 transition-all duration-300">
                    <feature.icon className="w-5 h-5 text-accent" />
                  </div>
                </div>

                <h3 className="font-display text-heading-md font-semibold text-foreground mb-3 group-hover:text-accent transition-colors duration-300">
                  {feature.title}
                </h3>
                <p className="text-body-md text-foreground-secondary leading-relaxed mb-4">
                  {feature.description}
                </p>
                <p className="text-caption uppercase tracking-widest text-accent/50">
                  {feature.detail}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};
