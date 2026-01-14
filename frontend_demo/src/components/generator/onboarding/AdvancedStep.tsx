import { OnboardingStep } from './OnboardingStep';
import { Gauge, FileText } from 'lucide-react';

interface AdvancedStepProps {
  data: {
    has_vbt_capability: boolean;
    user_notes: string;
  };
  onChange: (field: string, value: string | boolean) => void;
}

export const AdvancedStep = ({ data, onChange }: AdvancedStepProps) => {
  return (
    <OnboardingStep
      title="Almost there!"
      subtitle="Just a few optional details to perfect your program."
    >
      <div>
        <label className="flex items-center text-sm font-medium mb-3">
          <Gauge className="w-4 h-4 mr-2 text-accent" />
          Do you have Velocity-Based Training (VBT) equipment?
        </label>
        <p className="text-xs text-foreground-secondary mb-3">
          VBT devices track bar speed for more precise power and Olympic lift training
        </p>
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => onChange('has_vbt_capability', true)}
            className={`
              px-4 py-3 rounded-lg border-2 transition-all font-medium
              ${data.has_vbt_capability
                ? 'border-accent bg-accent/10 text-accent'
                : 'border-surface-light hover:border-accent/50'
              }
            `}
          >
            Yes, I have VBT
          </button>
          <button
            onClick={() => onChange('has_vbt_capability', false)}
            className={`
              px-4 py-3 rounded-lg border-2 transition-all font-medium
              ${!data.has_vbt_capability
                ? 'border-accent bg-accent/10 text-accent'
                : 'border-surface-light hover:border-accent/50'
              }
            `}
          >
            No VBT equipment
          </button>
        </div>
      </div>

      <div>
        <label className="flex items-center text-sm font-medium mb-2">
          <FileText className="w-4 h-4 mr-2 text-accent" />
          Additional Notes (Optional)
        </label>
        <textarea
          className="w-full px-4 py-3 bg-surface border border-surface-light rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/50 transition-all resize-none"
          rows={5}
          placeholder="Any preferences, equipment you have, exercises you prefer/avoid, training timeline, etc.&#10;&#10;e.g., 'Prefer front squats over back squats. Have access to competition barbell and calibrated plates. Training for a meet in 12 weeks.'"
          value={data.user_notes}
          onChange={(e) => onChange('user_notes', e.target.value)}
          maxLength={2000}
        />
        <p className="text-xs text-foreground-tertiary mt-1">
          This helps us customize your program to your preferences ({data.user_notes.length}/2000 characters)
        </p>
      </div>

      <div className="mt-6 p-4 bg-accent/5 border border-accent/20 rounded-lg">
        <h4 className="font-semibold text-sm mb-2 flex items-center">
          <span className="text-accent mr-2">✓</span>
          Ready to generate your program!
        </h4>
        <p className="text-sm text-foreground-secondary">
          Click "Generate Program" to create your personalized barbell training program. This typically takes 30-60 seconds.
        </p>
      </div>
    </OnboardingStep>
  );
};
