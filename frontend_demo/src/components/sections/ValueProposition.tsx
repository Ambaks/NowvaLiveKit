import { useRef } from 'react';
import { motion } from 'framer-motion';
import { BookOpen, User, Zap, Dumbbell, TrendingDown, Activity } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const features = [
  {
    icon: BookOpen,
    title: 'Evidence-Based',
    description: 'Built on proven periodization principles and progressive overload — not guesswork.',
  },
  {
    icon: User,
    title: 'Personalized',
    description: 'Adapts to your goals, schedule, injuries, and sport-specific needs.',
  },
  {
    icon: Zap,
    title: 'Instant',
    description: 'Your complete program generated in as little as 60 seconds.',
  },
  {
    icon: Dumbbell,
    title: 'Free Weights',
    description: 'No machines needed. Train with barbells, dumbbells, bands, and kettlebells.',
  },
  {
    icon: TrendingDown,
    title: 'Auto-Deloads',
    description: 'Smart recovery weeks prevent burnout and optimize long-term progress.',
  },
  {
    icon: Activity,
    title: 'VBT Support',
    description: 'Advanced velocity-based training for power and athletic performance goals.',
  },
];

export const ValueProposition = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section id="features" ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Subtle background */}
      <div className="absolute inset-0 bg-background-secondary/50" />

      <div className="section-container relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="mb-16"
        >
          <p className="eyebrow mb-4">Features</p>
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground max-w-3xl mb-5">
            Built for athletes who{' '}
            <span className="text-accent">train seriously</span>
          </h2>
          <p className="text-body-lg text-foreground-secondary max-w-2xl">
            The most intelligent, personalized training platform — designed from the ground up for serious athletes.
          </p>
        </motion.div>

        {/* Feature grid — 3x2 with editorial feel */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-px bg-border/50 rounded-2xl overflow-hidden border border-border">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, scale: 0.92 }}
              animate={isInView ? { opacity: 1, scale: 1 } : {}}
              transition={{ duration: 0.4, delay: index * 0.08, ease: 'easeOut' }}
              className="bg-background p-8 md:p-10 group hover:bg-surface transition-colors duration-300"
            >
              {/* Icon */}
              <div className="mb-6">
                <div className="inline-flex p-2.5 rounded-lg bg-accent/[0.06] border border-accent/10 group-hover:bg-accent/10 group-hover:border-accent/20 transition-all duration-300">
                  <feature.icon className="w-5 h-5 text-accent" />
                </div>
              </div>

              {/* Content */}
              <h3 className="font-display text-heading-md font-semibold text-foreground mb-3 group-hover:text-accent transition-colors duration-300">
                {feature.title}
              </h3>
              <p className="text-body-md text-foreground-secondary leading-relaxed">
                {feature.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};
