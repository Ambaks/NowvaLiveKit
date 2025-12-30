import { useRef } from 'react';
import { motion } from 'framer-motion';
import { Scan, Home, Palette, MessageSquare } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const futureFeatures = [
  {
    icon: Scan,
    title: 'Lab-Grade Biomechanics',
    description: 'Advanced pose detection with real-time coaching, performance analysis, and intelligent autoregulation',
  },
  {
    icon: Home,
    title: 'Space-Saving Design',
    description: 'Our engineering team has perfected a foldable hardware design that seamlessly fits into your home',
  },
  {
    icon: Palette,
    title: 'Artistically Crafted',
    description: 'Collaborating with world-class artists to create equipment that\'s as beautiful as it is functional',
  },
  {
    icon: MessageSquare,
    title: 'Human-Like AI Conversations',
    description: 'Talk to our state-of-the-art voice agent',
  },
];

export const TheFuture = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section ref={ref} className="relative min-h-screen flex items-center justify-center overflow-hidden py-24 md:py-32">
      {/* Stunning gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-purple-900 via-blue-900 to-cyan-900 opacity-30" />
      <div className="absolute inset-0 bg-gradient-mesh opacity-40" />

      {/* Content */}
      <div className="section-container relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-display-md md:text-display-xl font-bold mb-6">
            The <span className="gradient-text">Future</span> of Strength Training
          </h2>
          <p className="text-body-lg md:text-heading-md text-foreground-secondary max-w-3xl mx-auto">
            We're not just building software — we're revolutionizing how you train. Here's what's coming next.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
          {futureFeatures.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: index * 0.15 }}
              className="glass-card p-8 backdrop-blur-xl bg-background/60"
            >
              <div className="flex items-start gap-4">
                <div className="p-3 rounded-lg bg-gradient-to-br from-accent/20 to-accent/5">
                  <feature.icon className="w-8 h-8 text-accent" />
                </div>
                <div className="flex-1">
                  <h3 className="text-heading-md font-semibold mb-2">{feature.title}</h3>
                  <p className="text-foreground-secondary">{feature.description}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};
