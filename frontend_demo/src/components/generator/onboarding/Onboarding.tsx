import { useState } from 'react';
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
}

const STEP_LABELS = ['Personal', 'Goals', 'Experience', 'Schedule', 'Advanced'];

export const Onboarding = ({ onComplete }: OnboardingProps) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formData, setFormData] = useState<OnboardingData>({
    name: '',
    email: localStorage.getItem('nowva_user_email') || '',
    age: '',
    sex: '',
    height_cm: '',
    weight_kg: '',
    goal_category: '',
    goal_raw: '',
    specific_sport: 'none',
    fitness_level: '',
    injury_history: 'none',
    days_per_week: '',
    session_duration: '60',
    duration_weeks: '12',
    has_vbt_capability: false,
    user_notes: '',
  });

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
