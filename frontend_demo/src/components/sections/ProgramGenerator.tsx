import { useState } from 'react';
import { EmailGate } from '@/components/ui/EmailGate';
import { ModeSelector } from '@/components/generator/ModeSelector';
import { VoiceInterface } from '@/components/generator/VoiceInterface';
import { FormInterface } from '@/components/generator/FormInterface';

export const ProgramGenerator = () => {
  const [emailSubmitted, setEmailSubmitted] = useState(false);
  const [interactionMode, setInteractionMode] = useState<'voice' | 'form' | null>(null);

  const handleEmailSubmit = (_email: string) => {
    setEmailSubmitted(true);
  };

  const handleModeSelect = (mode: 'voice' | 'form') => {
    setInteractionMode(mode);
  };

  return (
    <section id="program-generator" className="relative py-24 md:py-32 overflow-hidden">
      {/* Subtle amber-tinted background to signal conversion zone */}
      <div className="absolute inset-0 bg-gradient-to-b from-background via-background to-background" />
      <div className="absolute inset-0 opacity-30" style={{
        backgroundImage: 'radial-gradient(ellipse at 50% 0%, rgba(255, 184, 0, 0.06), transparent 60%)'
      }} />

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
