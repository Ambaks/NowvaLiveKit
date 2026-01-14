import { OnboardingStep } from './OnboardingStep';
import { GraduationCap, User, Trophy } from 'lucide-react';

interface ExperienceStepProps {
  data: {
    fitness_level: string;
    injury_history: string;
  };
  onChange: (field: string, value: string) => void;
}

const fitnessLevels = [
  {
    value: 'beginner',
    label: 'Beginner',
    icon: User,
    description: 'New to structured training or less than 1 year experience'
  },
  {
    value: 'intermediate',
    label: 'Intermediate',
    icon: GraduationCap,
    description: '1-3 years of consistent training with proper form'
  },
  {
    value: 'advanced',
    label: 'Advanced',
    icon: Trophy,
    description: '3+ years of structured training with proven results'
  }
];

export const ExperienceStep = ({ data, onChange }: ExperienceStepProps) => {
  return (
    <OnboardingStep
      title="What's your experience level?"
      subtitle="This helps us set appropriate intensity and volume for your program."
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {fitnessLevels.map((level) => {
          const Icon = level.icon;
          const isSelected = data.fitness_level === level.value;

          return (
            <button
              key={level.value}
              onClick={() => onChange('fitness_level', level.value)}
              className={`
                p-6 rounded-xl border-2 text-center transition-all
                ${isSelected
                  ? 'border-accent bg-accent/10 shadow-lg scale-105'
                  : 'border-surface-light hover:border-accent/50 hover:bg-surface-light/50'
                }
              `}
            >
              <Icon className={`w-10 h-10 mx-auto mb-3 ${isSelected ? 'text-accent' : 'text-foreground-secondary'}`} />
              <h3 className="font-semibold text-lg mb-1">{level.label}</h3>
              <p className="text-sm text-foreground-secondary">{level.description}</p>
            </button>
          );
        })}
      </div>

      <div className="mt-8">
        <label className="block text-sm font-medium mb-2">
          Current or Past Injuries (Optional)
        </label>
        <textarea
          className="w-full px-4 py-3 bg-surface border border-surface-light rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/50 transition-all resize-none"
          rows={4}
          placeholder="e.g., Previous right shoulder impingement (2 years ago, fully healed), or type 'none'"
          value={data.injury_history}
          onChange={(e) => onChange('injury_history', e.target.value)}
          maxLength={1000}
        />
        <p className="text-xs text-foreground-tertiary mt-1">
          This helps us avoid exercises that might aggravate past injuries ({data.injury_history.length}/1000 characters)
        </p>
      </div>
    </OnboardingStep>
  );
};
