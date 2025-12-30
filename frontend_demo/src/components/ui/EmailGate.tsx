import { useState, type FormEvent } from 'react';
import { motion } from 'framer-motion';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Sparkles, Zap, CheckCircle2 } from 'lucide-react';

interface EmailGateProps {
  onSubmit: (email: string) => void;
}

export const EmailGate: React.FC<EmailGateProps> = ({ onSubmit }) => {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [isInputFocused, setIsInputFocused] = useState(false);
  const [isHovering, setIsHovering] = useState(false);

  const validateEmail = (email: string) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    if (!validateEmail(email)) {
      setError('Please enter a valid email address');
      return;
    }

    localStorage.setItem('nowva_user_email', email);
    onSubmit(email);
  };

  const benefits = [
    'Personalized to your goals & experience',
    'Evidence-based programming',
    'Large discounts and premium acces to future products'
  ];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5 }}
      className="max-w-2xl mx-auto"
    >
      <div
        className="relative group"
        onMouseEnter={() => setIsHovering(true)}
        onMouseLeave={() => setIsHovering(false)}
      >
        {/* Animated gradient border effect - purple to pink */}
        <div
          className="absolute -inset-1 animate-gradient-x transition-opacity duration-300 pointer-events-none"
          style={{
            opacity: isHovering || isInputFocused ? 0.3 : 0.2,
            backgroundImage: 'linear-gradient(90deg, #a855f7, #ec4899, #f472b6, #a855f7)',
            backgroundSize: '300% 100%',
            filter: 'blur(24px)',
            willChange: 'opacity, background-position',
          }}
        />

        {/* Main card */}
        <div className="relative bg-background-tertiary/90 backdrop-blur-xl rounded-3xl p-8 md:p-12 border border-border overflow-hidden">
          {/* Animated gradient background - always visible */}
          <div
            className="absolute inset-0 rounded-3xl pointer-events-none animate-gradient-x"
            style={{
              backgroundImage: 'linear-gradient(90deg, rgba(168, 85, 247, 0.05), rgba(236, 72, 153, 0.08), rgba(244, 114, 182, 0.05), rgba(168, 85, 247, 0.05))',
              backgroundSize: '300% 100%',
              opacity: 0.8,
            }}
          />

          {/* Gradient overlays - purple to pink - intensify on hover */}
          <div
            className="absolute inset-0 rounded-3xl pointer-events-none transition-opacity duration-500"
            style={{
              background: 'linear-gradient(to bottom right, rgba(168, 85, 247, 0.1), rgba(236, 72, 153, 0.1), rgba(244, 114, 182, 0.1))',
              opacity: isHovering || isInputFocused ? 1 : 0,
            }}
          />
          <div
            className="absolute top-0 right-0 w-64 h-64 rounded-full blur-3xl pointer-events-none transition-opacity duration-500"
            style={{
              background: 'linear-gradient(to bottom right, rgba(168, 85, 247, 0.2), transparent)',
              opacity: isHovering || isInputFocused ? 1 : 0,
            }}
          />
          <div
            className="absolute bottom-0 left-0 w-64 h-64 rounded-full blur-3xl pointer-events-none transition-opacity duration-500"
            style={{
              background: 'linear-gradient(to top right, rgba(236, 72, 153, 0.25), rgba(244, 114, 182, 0.2), transparent)',
              opacity: isHovering || isInputFocused ? 1 : 0,
            }}
          />

          {/* Content */}
          <div className="relative z-10">
            {/* Icon and badge */}
            <div className="flex justify-center mb-6">
              <motion.div
                animate={{ rotate: [0, 5, -5, 0] }}
                transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                className="relative"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-purple-500 to-pink-500 rounded-2xl blur-md opacity-50" />
                <div className="relative bg-gradient-to-br from-purple-500 to-pink-500 p-4 rounded-2xl">
                  <Sparkles className="w-8 h-8 text-white" />
                </div>
              </motion.div>
            </div>

            {/* Heading */}
            <motion.h3
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="text-heading-lg md:text-heading-xl font-bold mb-3 text-center"
            >
              Get Your{' '}
              <span className="gradient-text">Free Personalized Program</span>
            </motion.h3>

            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="text-body-lg text-foreground-secondary text-center mb-8 max-w-lg mx-auto"
            >
              Join thousands of athletes training smarter with AI-powered programming
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
                  <CheckCircle2 className="w-5 h-5 text-purple-500 flex-shrink-0" />
                  <span className="text-body-md">{benefit}</span>
                </motion.div>
              ))}
            </motion.div>

            {/* Form */}
            <motion.form
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7 }}
              onSubmit={handleSubmit}
              className="space-y-4"
            >
              <div className="flex flex-col sm:flex-row gap-3">
                <Input
                  type="email"
                  placeholder="your@email.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError('');
                  }}
                  onFocus={() => setIsInputFocused(true)}
                  onBlur={() => setIsInputFocused(false)}
                  error={error}
                  className="flex-1 text-lg"
                />

                <Button
                  type="submit"
                  size="lg"
                  className="sm:w-auto w-full whitespace-nowrap group"
                >
                  <span>Start Now</span>
                  <Zap className="w-4 h-4 ml-2 group-hover:scale-110 transition-transform" />
                </Button>
              </div>
            </motion.form>

            {/* Trust signals */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.9 }}
              className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-4 text-xs text-foreground-tertiary"
            >
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-success" />
                <span>100% Free Forever</span>
              </div>
              <div className="hidden sm:block w-1 h-1 bg-foreground-tertiary rounded-full" />
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-success" />
                <span>No Credit Card Required</span>
              </div>
              <div className="hidden sm:block w-1 h-1 bg-foreground-tertiary rounded-full" />
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-success" />
                <span>Unsubscribe Anytime</span>
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};