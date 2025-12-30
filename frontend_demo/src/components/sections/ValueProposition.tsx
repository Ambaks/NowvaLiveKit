import { useRef } from 'react';
import { motion } from 'framer-motion';
import { BookOpen, User, Zap, Dumbbell, TrendingDown, Activity, Sparkles, Star } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const features = [
  {
    icon: BookOpen,
    title: 'Evidence-Based',
    description: 'Built on proven periodization principles and progressive overload',
    gradient: 'from-blue-500 to-cyan-500',
  },
  {
    icon: User,
    title: 'Personalized',
    description: 'Adapts to your goals, schedule, injuries, and sport-specific needs',
    gradient: 'from-purple-500 to-pink-500',
  },
  {
    icon: Zap,
    title: 'Fast',
    description: 'Get your complete program in as little as 60 seconds',
    gradient: 'from-yellow-500 to-orange-500',
  },
  {
    icon: Dumbbell,
    title: 'Free Weights',
    description: 'No machines needed. Train with barbells, dumbbells, bands, and kettlebells',
    gradient: 'from-emerald-500 to-teal-500',
  },
  {
    icon: TrendingDown,
    title: 'Auto-Deloads',
    description: 'Smart recovery weeks prevent burnout and optimize progress',
    gradient: 'from-pink-500 to-rose-500',
  },
  {
    icon: Activity,
    title: 'VBT Support',
    description: 'Advanced velocity-based training for power and athletic goals',
    gradient: 'from-indigo-500 to-purple-500',
  },
];

export const ValueProposition = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Stunning animated gradient background */}
      <div className="absolute inset-0 bg-linear-to-br from-indigo-50 via-purple-50 to-pink-50 opacity-70" />
      <div className="absolute inset-0">
        <div className="absolute top-1/3 left-1/3 w-96 h-96 bg-purple-300/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '0s' }} />
        <div className="absolute bottom-1/3 right-1/3 w-96 h-96 bg-pink-300/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
        <div className="absolute top-2/3 left-2/3 w-96 h-96 bg-indigo-300/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
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
            Why <span className="gradient-text">Nowva</span>?
          </h2>

          <p className="text-body-lg text-foreground-secondary max-w-2xl mx-auto">
            The most intelligent, personalized training platform designed for serious athletes
          </p>
        </motion.div>

        {/* Feature grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="relative group"
            >
              {/* Animated gradient border */}
              <div className="absolute -inset-0.5 rounded-2xl opacity-0 group-hover:opacity-75 blur transition-all duration-500">
                <div className={`absolute inset-0 bg-linear-to-r ${feature.gradient}`} />
              </div>

              {/* Card content */}
              <div className="relative bg-background rounded-2xl p-8 h-full border border-border group-hover:border-transparent transition-all duration-300 group-hover:shadow-xl">
                {/* Icon with gradient background */}
                <div className="mb-6">
                  <div className={`inline-flex p-3 rounded-xl bg-linear-to-br ${feature.gradient} bg-opacity-10 group-hover:scale-110 transition-transform duration-300`}>
                    <feature.icon className="w-8 h-8 text-purple-600" />
                  </div>
                </div>

                {/* Content */}
                <h3 className="text-heading-md font-semibold mb-3 group-hover:text-purple-600 transition-colors">
                  {feature.title}
                </h3>
                <p className="text-foreground-secondary leading-relaxed">
                  {feature.description}
                </p>

                {/* Decorative gradient dot */}
                <div className={`absolute top-4 right-4 w-2 h-2 rounded-full bg-linear-to-r ${feature.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />
              </div>
            </motion.div>
          ))}
        </div>

        {/* CTA footer */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.8 }}
          className="text-center mt-16"
        >
          <div className="inline-flex flex-col sm:flex-row items-center gap-4 bg-linear-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/20 rounded-2xl px-8 py-4">
            <Sparkles className="w-6 h-6 text-purple-500" />
            <div className="text-center sm:text-left">
              <p className="text-body-md font-semibold text-foreground mb-1">
                Join thousands of athletes training smarter
              </p>
              <p className="text-sm text-foreground-secondary">
                Get your free personalized program today
              </p>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
