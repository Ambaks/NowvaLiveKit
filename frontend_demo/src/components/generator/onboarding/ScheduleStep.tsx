import { OnboardingStep } from './OnboardingStep';
import { Input } from '@/components/ui/Input';
import { Calendar, Clock, TrendingUp } from 'lucide-react';

interface ScheduleStepProps {
  data: {
    days_per_week: string;
    session_duration: string;
    duration_weeks: string;
  };
  onChange: (field: string, value: string) => void;
}

export const ScheduleStep = ({ data, onChange }: ScheduleStepProps) => {
  const daysOptions = [2, 3, 4, 5, 6];
  const sessionOptions = [30, 45, 60, 75, 90];

  return (
    <OnboardingStep
      title="Let's plan your schedule"
      subtitle="We'll create a program that fits your lifestyle."
    >
      <div>
        <label className="flex items-center text-sm font-medium mb-3">
          <Calendar className="w-4 h-4 mr-2 text-accent" />
          How many days per week can you train?
        </label>
        <div className="grid grid-cols-3 md:grid-cols-5 gap-3">
          {daysOptions.map((days) => {
            const isSelected = data.days_per_week === days.toString();
            return (
              <button
                key={days}
                onClick={() => onChange('days_per_week', days.toString())}
                className={`
                  py-3 rounded-lg border-2 transition-all font-semibold
                  ${isSelected
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-surface-light hover:border-accent/50'
                  }
                `}
              >
                {days} {days === 1 ? 'day' : 'days'}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <label className="flex items-center text-sm font-medium mb-3">
          <Clock className="w-4 h-4 mr-2 text-accent" />
          How long is each training session?
        </label>
        <div className="grid grid-cols-3 md:grid-cols-5 gap-3">
          {sessionOptions.map((minutes) => {
            const isSelected = data.session_duration === minutes.toString();
            return (
              <button
                key={minutes}
                onClick={() => onChange('session_duration', minutes.toString())}
                className={`
                  py-3 rounded-lg border-2 transition-all font-semibold
                  ${isSelected
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-surface-light hover:border-accent/50'
                  }
                `}
              >
                {minutes}min
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <label className="flex items-center text-sm font-medium mb-2">
          <TrendingUp className="w-4 h-4 mr-2 text-accent" />
          Program Duration (weeks)
        </label>
        <Input
          type="number"
          placeholder="12"
          min="2"
          max="12"
          value={data.duration_weeks}
          onChange={(e) => onChange('duration_weeks', e.target.value)}
        />
        <p className="text-xs text-foreground-tertiary mt-1">
          Maximum 12 weeks. Most effective programs run 8-12 weeks
        </p>
      </div>
    </OnboardingStep>
  );
};
