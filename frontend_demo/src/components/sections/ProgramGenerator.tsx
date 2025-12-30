import { useState } from 'react';
import { EmailGate } from '@/components/ui/EmailGate';
import { ModeSelector } from '@/components/generator/ModeSelector';
import { VoiceInterface } from '@/components/generator/VoiceInterface';
import { FormInterface } from '@/components/generator/FormInterface';

export const ProgramGenerator = () => {
  const [emailSubmitted, setEmailSubmitted] = useState(false);
  const [interactionMode, setInteractionMode] = useState<'voice' | 'form' | null>(null);
  const [userEmail, setUserEmail] = useState('');

  const handleEmailSubmit = (email: string) => {
    setUserEmail(email);
    setEmailSubmitted(true);
  };

  const handleModeSelect = (mode: 'voice' | 'form') => {
    setInteractionMode(mode);
  };

  return (
    <section id="program-generator" className="relative py-24 md:py-32 overflow-hidden">
      {/* Stunning gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-amber-50 via-yellow-50 to-orange-50 opacity-50" />
      <div className="absolute inset-0 bg-gradient-radial from-transparent via-background/20 to-background/40" />

      <div className="section-container relative z-10">

        {!emailSubmitted ? (
          <EmailGate onSubmit={handleEmailSubmit} />
        ) : interactionMode === null ? (
          <ModeSelector onSelect={handleModeSelect} />
        ) : interactionMode === 'voice' ? (
          <VoiceInterface />
        ) : (
          <FormInterface />
        )}
      </div>
    </section>
  );
};
