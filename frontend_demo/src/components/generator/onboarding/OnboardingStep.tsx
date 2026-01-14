import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface OnboardingStepProps {
  children: ReactNode;
  title: string;
  subtitle?: string;
}

export const OnboardingStep = ({ children, title, subtitle }: OnboardingStepProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.3 }}
      className="w-full"
    >
      <div className="mb-8">
        <h2 className="text-heading-lg font-bold mb-2">{title}</h2>
        {subtitle && (
          <p className="text-foreground-secondary text-base">{subtitle}</p>
        )}
      </div>
      <div className="space-y-6">
        {children}
      </div>
    </motion.div>
  );
};
