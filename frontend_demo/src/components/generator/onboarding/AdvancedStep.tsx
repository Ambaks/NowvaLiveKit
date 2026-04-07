import { OnboardingStep } from './OnboardingStep';
import { Gauge, FileText, Wrench } from 'lucide-react';

interface AdvancedStepProps {
  data: {
    has_vbt_capability: boolean;
    user_notes: string;
    equipment_tier: string;
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
        <label className="flex items-center text-sm font-medium mb-3">
          <Wrench className="w-4 h-4 mr-2 text-accent" />
          What equipment do you have access to?
        </label>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            { value: '1', label: 'Tier 1', desc: 'Barbell, rack, bench, pull-up bar, floor space' },
            { value: '2', label: 'Tier 2', desc: '+ Dumbbells' },
            { value: '3', label: 'Tier 3', desc: '+ Bands' },
          ].map((option) => (
            <button
              key={option.value}
              onClick={() => onChange('equipment_tier', option.value)}
              className={`
                p-4 rounded-lg border-2 text-left transition-all
                ${data.equipment_tier === option.value
                  ? 'border-accent bg-accent/10'
                  : 'border-surface-light hover:border-accent/50'
                }
              `}
            >
              <div className="font-medium text-sm">{option.label}</div>
              <div className="text-xs text-foreground-tertiary mt-0.5">{option.desc}</div>
            </button>
          ))}
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
          placeholder="Add additional notes like exercise preferences..."
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
