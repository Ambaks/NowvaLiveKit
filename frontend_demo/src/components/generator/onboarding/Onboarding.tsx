import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { ProgressBar } from './ProgressBar';
import { PersonalInfoStep } from './PersonalInfoStep';
import { GoalsStep } from './GoalsStep';
import { ExperienceStep } from './ExperienceStep';
import { ScheduleStep } from './ScheduleStep';
import { AdvancedStep } from './AdvancedStep';
import { ArrowLeft, ArrowRight, Loader2 } from 'lucide-react';

interface OnboardingProps {
  onComplete: (data: OnboardingData) => void;
  prefillData?: Record<string, unknown> | null;
}

export interface OnboardingData {
  // Personal Info
  name: string;
  email: string;
  age: string;
  sex: string;
  height_cm: string;
  weight_kg: string;
  // Goals
  goal_category: string;
  goal_raw: string;
  specific_sport: string;
  training_season: string;
  games_per_week: string;
  // Experience
  fitness_level: string;
  injury_history: string;
  // Schedule
  days_per_week: string;
  session_duration: string;
  duration_weeks: string;
  // Advanced
  has_vbt_capability: boolean;
  user_notes: string;
  equipment_tier: string;
}

const STEP_LABELS = ['Personal', 'Goals', 'Experience', 'Schedule', 'Advanced'];

const buildInitialData = (prefill?: Record<string, unknown> | null): OnboardingData => {
  const defaults: OnboardingData = {
    name: '',
    email: localStorage.getItem('nowva_user_email') || '',
    age: '',
    sex: '',
    height_cm: '',
    weight_kg: '',
    goal_category: '',
    goal_raw: '',
    specific_sport: 'none',
    training_season: '',
    games_per_week: '0',
    fitness_level: '',
    injury_history: 'none',
    days_per_week: '',
    session_duration: '60',
    duration_weeks: '12',
    has_vbt_capability: false,
    user_notes: '',
    equipment_tier: '2',
  };

  if (!prefill) return defaults;

  const converted: Partial<OnboardingData> = {};
  for (const [key, value] of Object.entries(prefill)) {
    if (value === null || value === undefined) continue;
    if (key === 'has_vbt_capability') {
      converted[key] = Boolean(value);
    } else if (key in defaults) {
      converted[key as keyof OnboardingData] = String(value) as never;
    }
  }

  return { ...defaults, ...converted };
};

export const Onboarding = ({ onComplete, prefillData }: OnboardingProps) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPrefillNotice, setShowPrefillNotice] = useState(!!prefillData);

  const initialData = useMemo(() => buildInitialData(prefillData), [prefillData]);
  const [formData, setFormData] = useState<OnboardingData>(initialData);

  const handleChange = (field: string, value: string | boolean) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const validateStep = (step: number): boolean => {
    switch (step) {
      case 1:
        return !!(
          formData.name &&
          formData.email &&
          formData.age &&
          formData.sex &&
          formData.height_cm &&
          formData.weight_kg
        );
      case 2:
        return !!(formData.goal_category && formData.goal_raw);
      case 3:
        return !!formData.fitness_level;
      case 4:
        return !!(
          formData.days_per_week &&
          formData.session_duration &&
          formData.duration_weeks
        );
      case 5:
        return true; // Advanced step is all optional
      default:
        return false;
    }
  };

  const handleNext = () => {
    if (validateStep(currentStep)) {
      if (currentStep < 5) {
        setCurrentStep(currentStep + 1);
      } else {
        handleSubmit();
      }
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onComplete(formData);
    } catch (error) {
      console.error('Error submitting form:', error);
      setIsSubmitting(false);
    }
  };

  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return <PersonalInfoStep data={formData} onChange={handleChange} />;
      case 2:
        return <GoalsStep data={formData} onChange={handleChange} />;
      case 3:
        return <ExperienceStep data={formData} onChange={handleChange} />;
      case 4:
        return <ScheduleStep data={formData} onChange={handleChange} />;
      case 5:
        return <AdvancedStep data={formData} onChange={handleChange} />;
      default:
        return null;
    }
  };

  const isStepValid = validateStep(currentStep);

  return (
    <div className="max-w-3xl mx-auto">
      <Card className="p-8 md:p-12">
        <ProgressBar
          currentStep={currentStep}
          totalSteps={5}
          stepLabels={STEP_LABELS}
        />

        {showPrefillNotice && (
          <div className="mb-6 p-3 bg-accent/10 border border-accent/20 rounded-lg flex justify-between items-center">
            <span className="text-sm text-foreground-secondary">
              We've filled in your details from last time. Feel free to update anything.
            </span>
            <button
              onClick={() => setShowPrefillNotice(false)}
              className="ml-4 text-foreground-tertiary hover:text-foreground text-lg leading-none"
            >
              &times;
            </button>
          </div>
        )}

        <AnimatePresence mode="wait">
          <motion.div key={currentStep}>
            {renderStep()}
          </motion.div>
        </AnimatePresence>

        <div className="flex justify-between mt-8 pt-8 border-t border-surface-light">
          <Button
            onClick={handleBack}
            variant="secondary"
            disabled={currentStep === 1}
            className="flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Button>

          <Button
            onClick={handleNext}
            disabled={!isStepValid || isSubmitting}
            className="flex items-center gap-2 min-w-[140px]"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating...
              </>
            ) : currentStep === 5 ? (
              'Generate Program'
            ) : (
              <>
                Next
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </Button>
        </div>
      </Card>
    </div>
  );
};
