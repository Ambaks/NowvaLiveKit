import { useState } from 'react';
import { motion } from 'framer-motion';
import { Onboarding } from './onboarding/Onboarding';
import type { OnboardingData } from './onboarding/Onboarding';
import { ProgramGenerationStatus } from './ProgramGenerationStatus';
import { programsApi } from '@/api/programs';

type FormState = 'form' | 'generating' | 'complete';

export const FormInterface = () => {
  const [state, setState] = useState<FormState>('form');
  const [jobId, setJobId] = useState<string | null>(null);
  const [programId, setProgramId] = useState<string | null>(null);
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
      };

      const response = await programsApi.generateProgram(requestData);
      setJobId(response.job_id);
      setState('generating');
    } catch (err) {
      console.error('Error starting program generation:', err);
      setError(err instanceof Error ? err.message : 'Failed to start program generation');
    }
  };

  const handleGenerationComplete = (generatedProgramId: string) => {
    setProgramId(generatedProgramId);
    setState('complete');
  };

  const handleGenerationError = (errorMessage: string) => {
    setError(errorMessage);
    setState('form');
  };

  const handleReset = () => {
    setState('form');
    setJobId(null);
    setProgramId(null);
    setError(null);
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
    >
      {error && (
        <div className="max-w-2xl mx-auto mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-600">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {state === 'form' && (
        <Onboarding onComplete={handleFormComplete} />
      )}

      {(state === 'generating' || state === 'complete') && jobId && (
        <ProgramGenerationStatus
          jobId={jobId}
          onComplete={handleGenerationComplete}
          onError={handleGenerationError}
          onReset={handleReset}
        />
      )}
    </motion.div>
  );
};
