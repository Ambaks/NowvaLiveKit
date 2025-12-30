import { useRef } from 'react';
import { motion } from 'framer-motion';
import { Mail, MessageSquare, Dumbbell, ArrowRight } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const steps = [
  {
    icon: Mail,
    title: 'Enter Your Email',
    description: 'Unlock the program generator in seconds',
    gradient: 'from-purple-500 to-pink-500'
  },
  {
    icon: MessageSquare,
    title: 'Choose Your Style',
    description: 'Talk to Nova (voice) or fill out a quick form',
    gradient: 'from-pink-500 to-rose-500'
  },
  {
    icon: Dumbbell,
    title: 'Get Your Program',
    description: 'Personalized, evidence-based training in as little as 60 seconds',
    gradient: 'from-rose-500 to-orange-500'
  }
];

export const HowItWorks = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Stunning animated gradient background */}
      <div className="absolute inset-0 bg-linear-to-br from-purple-50 via-pink-50 to-rose-50 opacity-70" />
      <div className="absolute inset-0">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-300/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '0s' }} />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-pink-300/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1.5s' }} />
      </div>

      <div className="section-container relative z-10">
        {/* Header with conversion messaging */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-heading-xl md:text-display-md font-bold mb-4">
            Get Started in <span className="gradient-text">3 Easy Steps</span>
          </h2>

          <p className="text-body-lg text-foreground-secondary max-w-2xl mx-auto">
            From email to personalized program in as lttle as 60 seconds
          </p>
        </motion.div>

        {/* Steps with connecting arrows */}
        <div className="max-w-6xl mx-auto">
          <div className="grid md:grid-cols-3 gap-8 md:gap-4 relative">
            {steps.map((step, index) => (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, y: 30 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.5, delay: index * 0.2 }}
                className="relative"
              >
                {/* Connecting arrow for desktop */}
                {index < steps.length - 1 && (
                  <div className="hidden md:block absolute top-1/2 -right-6 transform -translate-y-1/2 z-20">
                    <ArrowRight className="w-8 h-8 text-purple-400" />
                  </div>
                )}

                {/* Step card with gradient border */}
                <div className="relative group h-full">
                  {/* Animated gradient border */}
                  <div
                    className="absolute -inset-0.5 rounded-2xl opacity-0 group-hover:opacity-100 blur transition-all duration-500 animate-gradient-x"
                    style={{
                      backgroundImage: `linear-gradient(90deg, var(--tw-gradient-stops))`,
                      backgroundSize: '200% 100%',
                    }}
                  >
                    <div className={`absolute inset-0 bg-linear-to-r ${step.gradient} opacity-75`} />
                  </div>

                  {/* Card content */}
                  <div className="relative bg-background rounded-2xl p-8 h-full border border-border group-hover:border-transparent transition-all duration-300">
                    {/* Icon with gradient background */}
                    <div className="mb-6 mt-4">
                      <div className={`inline-flex p-4 rounded-xl bg-linear-to-br ${step.gradient} bg-opacity-10 group-hover:scale-110 transition-transform duration-300`}>
                        <step.icon className="w-10 h-10 text-purple-600" />
                      </div>
                    </div>

                    {/* Content */}
                    <h3 className="text-heading-md font-semibold mb-3 group-hover:text-purple-600 transition-colors">
                      {step.title}
                    </h3>
                    <p className="text-foreground-secondary leading-relaxed">
                      {step.description}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* CTA footer */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.8 }}
          className="text-center mt-16"
        >
          <p className="text-body-lg text-foreground-secondary">
            Ready to transform your training?{' '}
          </p>
        </motion.div>
      </div>
    </section>
  );
};
