import { useRef } from 'react';
import { motion } from 'framer-motion';
import { Mail, MessageSquare, Dumbbell } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const steps = [
  {
    icon: Mail,
    number: '01',
    title: 'Enter Your Email',
    description: 'Unlock the program generator in seconds. No credit card, no commitment.',
  },
  {
    icon: MessageSquare,
    number: '02',
    title: 'Choose Your Style',
    description: 'Talk to Nova, our AI voice coach, or fill out a quick form — your choice.',
  },
  {
    icon: Dumbbell,
    number: '03',
    title: 'Get Your Program',
    description: 'Personalized, evidence-based training delivered in as little as 60 seconds.',
  },
];

export const HowItWorks = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section id="how-it-works" ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Subtle grid dot pattern */}
      <div className="absolute inset-0 opacity-[0.035]" style={{
        backgroundImage: 'radial-gradient(circle, #00E5FF 1px, transparent 1px)',
        backgroundSize: '32px 32px',
      }} />

      <div className="section-container relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <p className="eyebrow mb-4">How It Works</p>
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground mb-5">
            Three steps. <span className="text-accent">Sixty seconds.</span>
          </h2>
          <p className="text-body-lg text-foreground-secondary max-w-xl mx-auto">
            From email to a fully personalized training program, faster than you can warm up.
          </p>
        </motion.div>

        {/* Steps — horizontal on desktop, vertical on mobile */}
        <div className="relative max-w-5xl mx-auto">
          {/* Connecting line — desktop */}
          <div className="hidden md:block absolute top-[52px] left-[16.67%] right-[16.67%] h-px">
            <motion.div
              initial={{ scaleX: 0 }}
              animate={isInView ? { scaleX: 1 } : {}}
              transition={{ duration: 1.2, delay: 0.5, ease: 'easeOut' }}
              className="w-full h-px bg-gradient-to-r from-accent/40 via-accent/20 to-accent/40 origin-left"
            />
          </div>

          <div className="grid md:grid-cols-3 gap-12 md:gap-8">
            {steps.map((step, index) => (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, x: -30 }}
                animate={isInView ? { opacity: 1, x: 0 } : {}}
                transition={{ duration: 0.5, delay: 0.3 + index * 0.2, ease: 'easeOut' }}
                className="text-center group"
              >
                {/* Step icon with glow */}
                <div className="relative inline-flex mb-8">
                  <div className="absolute inset-0 bg-accent/20 rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                  <div className="relative p-4 rounded-2xl bg-surface border border-border group-hover:border-accent/30 transition-all duration-300">
                    <step.icon className="w-7 h-7 text-accent" />
                  </div>
                </div>

                {/* Number */}
                <p className="text-caption font-mono text-accent/60 mb-3">{step.number}</p>

                {/* Content */}
                <h3 className="font-display text-heading-md font-semibold text-foreground mb-3">
                  {step.title}
                </h3>
                <p className="text-body-md text-foreground-secondary leading-relaxed max-w-xs mx-auto">
                  {step.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
