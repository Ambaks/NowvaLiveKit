import { useState, type FormEvent } from 'react';
import { motion } from 'framer-motion';
import { Input } from '@/components/ui/Input';
import { Zap, CheckCircle2, Loader2, ArrowRight } from 'lucide-react';
import { authApi } from '@/api/auth';
import { trackEvent } from '@/lib/analytics';

interface EmailGateProps {
  onSubmit: (email: string) => void;
}

export const EmailGate: React.FC<EmailGateProps> = ({ onSubmit }) => {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [isInputFocused, setIsInputFocused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const validateEmail = (email: string) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const checkEligibility = async (userEmail: string) => {
    const response = await fetch(`${apiUrl}/api/programs/check-eligibility`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: userEmail }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to check eligibility');
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!validateEmail(email)) {
      setError('Please enter a valid email address');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      await checkEligibility(email);
      await authApi.emailStart(email);
      localStorage.setItem('nowva_user_email', email);
      trackEvent('email_submit', { result: 'success' });
      onSubmit(email);
    } catch (err) {
      console.error('Email submission failed:', err);
      trackEvent('email_submit', { result: 'failure' });
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setIsLoading(false);
    }
  };

  const benefits = [
    'Personalized to your goals & experience',
    'Powered by Nowva AI intelligence',
    'Early access & launch day discounts on the Rack'
  ];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5 }}
      className="max-w-2xl mx-auto"
    >
      <div className="relative group">
        {/* Ambient glow */}
        <div
          className="absolute -inset-4 transition-opacity duration-500 pointer-events-none"
          style={{
            opacity: isInputFocused ? 0.6 : 0.3,
            backgroundImage: 'radial-gradient(ellipse at center, rgba(255, 184, 0, 0.1), transparent 70%)',
          }}
        />

        {/* Main card */}
        <div className="relative bg-surface/90 backdrop-blur-xl rounded-2xl p-8 md:p-12 border border-border overflow-hidden">
          {/* Subtle gradient accent */}
          <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cta/30 to-transparent" />

          {/* Content */}
          <div className="relative z-10">
            {/* Icon */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex justify-center mb-6"
            >
              <div className="p-3 rounded-xl bg-cta/10 border border-cta/20">
                <Zap className="w-6 h-6 text-cta" />
              </div>
            </motion.div>

            {/* Heading */}
            <motion.h3
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="font-display text-heading-lg md:text-heading-xl font-bold mb-3 text-center text-foreground"
            >
              Get Your{' '}
              <span className="gradient-text-amber">Free Program</span>
            </motion.h3>

            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="text-body-lg text-foreground-secondary text-center mb-8 max-w-lg mx-auto"
            >
              Enter your email for a free personalized program and early access to the Nowva Rack
            </motion.p>

            {/* Benefits list */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="grid gap-3 mb-8"
            >
              {benefits.map((benefit, index) => (
                <motion.div
                  key={benefit}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.4 + index * 0.1 }}
                  className="flex items-center gap-3 text-foreground"
                >
                  <CheckCircle2 className="w-5 h-5 text-accent flex-shrink-0" />
                  <span className="text-body-md">{benefit}</span>
                </motion.div>
              ))}
            </motion.div>

            {/* Form */}
            <motion.form
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 }}
              onSubmit={handleSubmit}
              className="flex gap-3"
            >
              <Input
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setError(''); }}
                onFocus={() => setIsInputFocused(true)}
                onBlur={() => setIsInputFocused(false)}
                error={error}
                className="text-lg flex-1"
              />

              <button
                type="submit"
                disabled={isLoading}
                className="button-primary shrink-0 group disabled:opacity-50"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2">
                    Starting...
                    <Loader2 className="w-4 h-4 animate-spin" />
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    Get Started
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </span>
                )}
              </button>
            </motion.form>

            {/* Trust signals */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.9 }}
              className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-4 text-xs text-foreground-tertiary"
            >
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                <span>100% Free Forever</span>
              </div>
              <div className="hidden sm:block w-1 h-1 bg-foreground-tertiary/40 rounded-full" />
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                <span>No Credit Card Required</span>
              </div>
              <div className="hidden sm:block w-1 h-1 bg-foreground-tertiary/40 rounded-full" />
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                <span>Unsubscribe Anytime</span>
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};
