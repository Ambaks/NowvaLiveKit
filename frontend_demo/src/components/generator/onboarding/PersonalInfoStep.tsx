import { OnboardingStep } from './OnboardingStep';
import { Input } from '@/components/ui/Input';

interface PersonalInfoStepProps {
  data: {
    name: string;
    email: string;
    age: string;
    sex: string;
    height_cm: string;
    weight_kg: string;
  };
  onChange: (field: string, value: string) => void;
}

export const PersonalInfoStep = ({ data, onChange }: PersonalInfoStepProps) => {
  return (
    <OnboardingStep
      title="Let's start with the basics"
      subtitle="Tell us a bit about yourself so we can personalize your program."
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-medium mb-2">Full Name</label>
          <Input
            type="text"
            placeholder="John Doe"
            value={data.name}
            onChange={(e) => onChange('name', e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Email</label>
          <Input
            type="email"
            placeholder="john@example.com"
            value={data.email}
            onChange={(e) => onChange('email', e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Age</label>
          <Input
            type="number"
            placeholder="25"
            min="13"
            max="100"
            value={data.age}
            onChange={(e) => onChange('age', e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Biological Sex</label>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => onChange('sex', 'M')}
              className={`
                px-4 py-3 rounded-lg border-2 transition-all font-medium
                ${data.sex === 'M'
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-surface-light hover:border-accent/50'
                }
              `}
            >
              Male
            </button>
            <button
              onClick={() => onChange('sex', 'F')}
              className={`
                px-4 py-3 rounded-lg border-2 transition-all font-medium
                ${data.sex === 'F'
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-surface-light hover:border-accent/50'
                }
              `}
            >
              Female
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Height (cm)</label>
          <Input
            type="number"
            placeholder="175"
            min="100"
            max="250"
            step="0.1"
            value={data.height_cm}
            onChange={(e) => onChange('height_cm', e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Weight (kg)</label>
          <Input
            type="number"
            placeholder="75"
            min="30"
            max="200"
            step="0.1"
            value={data.weight_kg}
            onChange={(e) => onChange('weight_kg', e.target.value)}
          />
        </div>
      </div>
    </OnboardingStep>
  );
};
