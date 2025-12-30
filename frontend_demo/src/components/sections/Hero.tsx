import { motion } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/Button';

export const Hero = () => {
  const handleCTAClick = () => {
    document.getElementById('program-generator')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Stunning gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50 via-sky-50 to-cyan-50 opacity-70" />
      <div className="absolute inset-0 bg-gradient-mesh opacity-50" />

      {/* Content */}
      <div className="section-container relative z-10 text-center py-32">
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-display-md md:text-display-xl font-bold mb-6"
        >
          Your Personal{' '}
          <span className="gradient-text">AI Strength Coach</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-body-lg md:text-heading-md text-foreground-secondary max-w-3xl mx-auto mb-12"
        >
          Evidence-based free weights programs built in seconds. Talk to Nova or fill out a quick form — your program, your way.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
        >
          <Button size="lg" onClick={handleCTAClick}>
            Get Your Free Program
          </Button>
        </motion.div>
      </div>

      {/* Scroll indicator */}
      <motion.div
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
        animate={{ y: [0, 10, 0] }}
        transition={{ duration: 2, repeat: Infinity }}
      >
        <ChevronDown className="w-6 h-6 text-foreground-tertiary" />
      </motion.div>
    </section>
  );
};
