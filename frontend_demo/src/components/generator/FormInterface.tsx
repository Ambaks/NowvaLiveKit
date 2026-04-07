import { useState } from 'react';
import { motion } from 'framer-motion';
import { Mail } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Onboarding } from './onboarding/Onboarding';
import type { OnboardingData } from './onboarding/Onboarding';
import { programsApi } from '@/api/programs';

interface FormInterfaceProps {
  prefillData?: Record<string, unknown> | null;
}

type FormState = 'form' | 'submitted';

export const FormInterface = ({ prefillData }: FormInterfaceProps) => {
  const [state, setState] = useState<FormState>('form');
  const [error, setError] = useState<string | null>(null);

  const handleFormComplete = async (data: OnboardingData) => {
    try {
      setError(null);

      const userId = localStorage.getItem('nowva_user_id');
      if (!userId) {
        setError('User session not found. Please refresh and enter your email again.');
        return;
      }

      const requestData = {
        user_id: userId,
        name: data.name,
        email: data.email,
        height_cm: parseFloat(data.height_cm),
        weight_kg: parseFloat(data.weight_kg),
        goal_category: data.goal_category,
        goal_raw: data.goal_raw,
        duration_weeks: parseInt(data.duration_weeks),
        days_per_week: parseInt(data.days_per_week),
        fitness_level: data.fitness_level,
        age: parseInt(data.age),
        sex: data.sex,
        session_duration: parseInt(data.session_duration),
        injury_history: data.injury_history || 'none',
        specific_sport: data.specific_sport || 'none',
        has_vbt_capability: data.has_vbt_capability,
        user_notes: data.user_notes || '',
        send_email: true,
        training_season: data.training_season || undefined,
        games_per_week: data.games_per_week ? parseInt(data.games_per_week) : 0,
        equipment_tier: data.equipment_tier ? parseInt(data.equipment_tier) : 2,
      };

      await programsApi.generateProgram(requestData);
      setState('submitted');
    } catch (err) {
      console.error('Error starting program generation:', err);
      setError(err instanceof Error ? err.message : 'Failed to start program generation');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
    >
      {error && (
        <div className="max-w-2xl mx-auto mb-6 p-4 bg-danger/10 border border-danger/20 rounded-lg text-danger">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {state === 'form' && (
        <Onboarding onComplete={handleFormComplete} prefillData={prefillData} />
      )}

      {state === 'submitted' && (
        <div className="max-w-2xl mx-auto">
          <Card className="p-12 text-center">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="mb-6 flex justify-center"
            >
              <Mail className="w-16 h-16 text-accent" />
            </motion.div>

            <h3 className="text-heading-lg font-semibold mb-2">
              Your program is being generated!
            </h3>

            <p className="text-foreground-secondary mt-4">
              You'll receive it in your email in under 5 minutes.
              If you don't see it, check your spam folder.
            </p>
          </Card>
        </div>
      )}
    </motion.div>
  );
};
