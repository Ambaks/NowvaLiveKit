import { useRef } from 'react';
import { motion } from 'framer-motion';
import { Activity, Hash, AlertTriangle, Brain } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const features = [
  {
    icon: Activity,
    title: 'Biomechanics diagnosis',
    description:
      'Not just tracking — diagnosis. The engine triangulates 20+ keypoints in 3D and measures depth, bar path, tempo and symmetry against your own anatomy, so cues fit your body instead of a generic template.',
    detail: '3D triangulation · Depth · Bar path · Joint angles',
    span: 'large' as const,
  },
  {
    icon: Hash,
    title: 'Rep & velocity counting',
    description:
      'Every rep counted automatically, with bar speed on each one — so you and the system both know when a set is genuinely slowing down.',
    detail: 'Auto rep count · Bar velocity',
    span: 'small' as const,
  },
  {
    icon: AlertTriangle,
    title: 'Fault detection',
    description:
      'Knees caving, hips shooting up, uneven depth — common breakdown patterns are flagged the moment they appear, before they become a habit or an injury.',
    detail: 'Pattern flags · Live feedback',
    span: 'small' as const,
  },
  {
    icon: Brain,
    title: 'Adaptive programming',
    description:
      'Every session feeds the plan. Training auto-regulates from velocity, RPE and fatigue signals, adjusting load and volume the way a good coach would — and relaying it through the on-device voice coach.',
    detail: 'Autoregulation · Fatigue management · Periodization',
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
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground max-w-3xl mb-5 text-balance">
            Everything a great coach does.{' '}
            <span className="text-accent">Built into the steel.</span>
          </h2>
          <p className="text-body-lg text-foreground-secondary max-w-2xl">
            Computer vision, a biomechanics engine, and adaptive programming — integrated
            directly into a premium squat rack. No phone, no wearable, no compromise.
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
              {index === 3 && <WaveformMini />}

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
