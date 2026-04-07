import { useRef } from 'react';
import { motion } from 'framer-motion';
import { Scan, Mic, Brain } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const features = [
  {
    number: '01',
    icon: Scan,
    title: 'Lab-Grade Biomechanics',
    description:
      'Our computer vision models track 33 skeletal landmarks in real-time, delivering biomechanical analysis that rivals motion-capture labs — from your phone camera.',
    detail: 'Pose detection \u00b7 Joint angles \u00b7 Bar path tracking \u00b7 Velocity measurement',
    imagePlaceholder: 'Add pose detection overlay screenshot',
    imageHint: 'Skeleton/joint visualization on an athlete',
    layout: 'text-left' as const,
  },
  {
    number: '02',
    icon: Mic,
    title: 'Real-Time Voice Coaching',
    description:
      'Talk to Nova, our AI coaching agent. Get real-time form cues, program adjustments, and performance insights — all through natural conversation.',
    detail: 'Natural language \u00b7 Context-aware \u00b7 Real-time feedback \u00b7 Adaptive',
    imagePlaceholder: 'Add gym/voice coaching photo',
    imageHint: 'Athlete with earbuds in gym environment',
    layout: 'text-right' as const,
  },
  {
    number: '03',
    icon: Brain,
    title: 'Adaptive Intelligence',
    description:
      'Every session feeds our models. Your program evolves with you — auto-regulating intensity, predicting plateaus, and optimizing recovery based on your unique data.',
    detail: 'Autoregulation \u00b7 Plateau prediction \u00b7 Recovery optimization',
    imagePlaceholder: null,
    imageHint: null,
    layout: 'full-width' as const,
  },
];

const FeatureBlock = ({
  feature,
}: {
  feature: (typeof features)[0];
}) => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  if (feature.layout === 'full-width') {
    return (
      <motion.div
        ref={ref}
        initial={{ opacity: 0, scale: 0.94 }}
        animate={isInView ? { opacity: 1, scale: 1 } : {}}
        transition={{ duration: 0.7, delay: 0.1, ease: 'easeOut' }}
        className="relative py-24 text-center"
      >
        {/* Large background number */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span className="font-display text-[12rem] md:text-[18rem] font-extrabold text-foreground/[0.02] select-none">
            {feature.number}
          </span>
        </div>

        <div className="relative z-10 max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-3 mb-6">
            <div className="p-2.5 rounded-lg bg-accent/10 border border-accent/20">
              <feature.icon className="w-5 h-5 text-accent" />
            </div>
            <span className="eyebrow">{feature.number}</span>
          </div>

          <h3 className="font-display text-display-md md:text-display-lg font-bold text-foreground mb-6">
            {feature.title}
          </h3>

          <p className="text-body-lg text-foreground-secondary mb-8 max-w-2xl mx-auto">
            {feature.description}
          </p>

          <p className="text-caption uppercase tracking-widest text-accent/70">
            {feature.detail}
          </p>
        </div>
      </motion.div>
    );
  }

  const isTextLeft = feature.layout === 'text-left';

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, x: isTextLeft ? -40 : 40 }}
      animate={isInView ? { opacity: 1, x: 0 } : {}}
      transition={{ duration: 0.7, delay: 0.1, ease: 'easeOut' }}
      className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center py-16 md:py-24"
    >
      {/* Text */}
      <div className={isTextLeft ? 'order-1' : 'order-1 lg:order-2'}>
        {/* Background number */}
        <div className="relative">
          <span className="absolute -top-16 -left-4 font-display text-[8rem] md:text-[10rem] font-extrabold text-foreground/[0.03] select-none leading-none">
            {feature.number}
          </span>

          <div className="relative z-10">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2.5 rounded-lg bg-accent/10 border border-accent/20">
                <feature.icon className="w-5 h-5 text-accent" />
              </div>
              <span className="eyebrow">{feature.number}</span>
            </div>

            <h3 className="font-display text-heading-xl md:text-display-md font-bold text-foreground mb-5">
              {feature.title}
            </h3>

            <p className="text-body-lg text-foreground-secondary mb-6 leading-relaxed">
              {feature.description}
            </p>

            <p className="text-caption uppercase tracking-widest text-accent/70">
              {feature.detail}
            </p>
          </div>
        </div>
      </div>

      {/* Image placeholder */}
      <div className={isTextLeft ? 'order-2' : 'order-2 lg:order-1'}>
        <div className="relative aspect-[4/3] rounded-2xl overflow-hidden bg-surface border border-border">
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center px-8">
              <div className="w-12 h-12 mx-auto mb-3 rounded-lg bg-accent/10 flex items-center justify-center">
                <svg className="w-6 h-6 text-accent/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
                </svg>
              </div>
              <p className="text-foreground-tertiary text-sm">{feature.imagePlaceholder}</p>
              <p className="text-foreground-tertiary/60 text-xs mt-1">{feature.imageHint}</p>
            </div>
          </div>
          {/* CV grid on image */}
          <div className="absolute inset-0 cv-grid-overlay opacity-50" />
          {/* Corner brackets */}
          <div className="absolute top-3 left-3 w-6 h-6 border-t border-l border-accent/30 rounded-tl-sm" />
          <div className="absolute top-3 right-3 w-6 h-6 border-t border-r border-accent/30 rounded-tr-sm" />
          <div className="absolute bottom-3 left-3 w-6 h-6 border-b border-l border-accent/30 rounded-bl-sm" />
          <div className="absolute bottom-3 right-3 w-6 h-6 border-b border-r border-accent/30 rounded-br-sm" />
        </div>
      </div>
    </motion.div>
  );
};

export const TechShowcase = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section id="technology" ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Subtle background */}
      <div className="absolute inset-0 bg-gradient-mesh-dark opacity-50" />

      <div className="section-container relative z-10">
        {/* Section header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="mb-8"
        >
          <p className="eyebrow mb-4">The Technology</p>
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground max-w-3xl">
            Built on{' '}
            <span className="text-accent">computer vision</span>{' '}
            that sees what you can&apos;t
          </h2>
        </motion.div>

        <div className="separator my-8" />

        {/* Feature blocks */}
        {features.map((feature, index) => (
          <div key={feature.number}>
            <FeatureBlock feature={feature} />
            {index < features.length - 1 && <div className="separator" />}
          </div>
        ))}
      </div>
    </section>
  );
};
