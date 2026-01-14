import { OnboardingStep } from './OnboardingStep';
import { Input } from '@/components/ui/Input';
import { Dumbbell, Zap, Flame, Trophy } from 'lucide-react';

interface GoalsStepProps {
  data: {
    goal_category: string;
    goal_raw: string;
    specific_sport: string;
  };
  onChange: (field: string, value: string) => void;
}

const goalOptions = [
  {
    value: 'strength',
    label: 'Strength',
    icon: Dumbbell,
    description: 'Build maximum strength and lift heavier weights'
  },
  {
    value: 'hypertrophy',
    label: 'Hypertrophy',
    icon: Flame,
    description: 'Increase muscle size and definition'
  },
  {
    value: 'power',
    label: 'Power',
    icon: Zap,
    description: 'Develop explosive strength and speed'
  },
  {
    value: 'athletic_performance',
    label: 'Athletic Performance',
    icon: Trophy,
    description: 'Improve sport-specific performance (best for in-season athletes)'
  }
];

export const GoalsStep = ({ data, onChange }: GoalsStepProps) => {
  return (
    <OnboardingStep
      title="What's your primary goal?"
      subtitle="Choose what matters most to you right now."
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {goalOptions.map((option) => {
          const Icon = option.icon;
          const isSelected = data.goal_category === option.value;

          return (
            <button
              key={option.value}
              onClick={() => onChange('goal_category', option.value)}
              className={`
                p-6 rounded-xl border-2 text-left transition-all
                ${isSelected
                  ? 'border-accent bg-accent/10 shadow-lg scale-105'
                  : 'border-surface-light hover:border-accent/50 hover:bg-surface-light/50'
                }
              `}
            >
              <Icon className={`w-8 h-8 mb-3 ${isSelected ? 'text-accent' : 'text-foreground-secondary'}`} />
              <h3 className="font-semibold text-lg mb-1">{option.label}</h3>
              <p className="text-sm text-foreground-secondary">{option.description}</p>
            </button>
          );
        })}
      </div>

      <div className="mt-6">
        <label className="block text-sm font-medium mb-2">
          Describe your goal in your own words
        </label>
        <textarea
          className="w-full px-4 py-3 bg-surface border border-surface-light rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/50 transition-all resize-none"
          rows={3}
          placeholder="e.g., I want to get stronger for my upcoming powerlifting meet..."
          value={data.goal_raw}
          onChange={(e) => onChange('goal_raw', e.target.value)}
          maxLength={500}
        />
        <p className="text-xs text-foreground-tertiary mt-1">
          {data.goal_raw.length}/500 characters
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">
          Specific Sport (Optional)
        </label>
        <Input
          type="text"
          placeholder="e.g., basketball, powerlifting, or leave blank"
          value={data.specific_sport}
          onChange={(e) => onChange('specific_sport', e.target.value)}
        />
        <p className="text-xs text-foreground-tertiary mt-1">
          Leave blank if training for general fitness
        </p>
      </div>
    </OnboardingStep>
  );
};
