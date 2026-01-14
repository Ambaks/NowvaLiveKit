import { motion } from 'framer-motion';
import { Check } from 'lucide-react';

interface ProgressBarProps {
  currentStep: number;
  totalSteps: number;
  stepLabels: string[];
}

export const ProgressBar = ({ currentStep, totalSteps, stepLabels }: ProgressBarProps) => {
  return (
    <div className="w-full mb-12">
      {/* Progress bar */}
      <div className="relative">
        <div className="h-2 bg-surface-light rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-accent to-accent-light"
            initial={{ width: 0 }}
            animate={{ width: `${(currentStep / totalSteps) * 100}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      {/* Step indicators */}
      <div className="flex justify-between mt-4">
        {stepLabels.map((label, index) => {
          const stepNumber = index + 1;
          const isCompleted = stepNumber < currentStep;
          const isCurrent = stepNumber === currentStep;

          return (
            <div key={index} className="flex flex-col items-center flex-1">
              <div
                className={`
                  w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold mb-2
                  transition-all duration-300
                  ${isCompleted ? 'bg-accent text-white' : ''}
                  ${isCurrent ? 'bg-accent-light text-white scale-110' : ''}
                  ${!isCompleted && !isCurrent ? 'bg-surface-light text-foreground-tertiary' : ''}
                `}
              >
                {isCompleted ? (
                  <Check className="w-5 h-5" />
                ) : (
                  stepNumber
                )}
              </div>
              <span className={`text-xs text-center ${isCurrent ? 'text-foreground font-semibold' : 'text-foreground-tertiary'}`}>
                {label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
