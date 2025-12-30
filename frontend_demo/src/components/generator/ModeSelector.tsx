import { motion } from 'framer-motion';
import { Mic, FileText } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

interface ModeSelectorProps {
  onSelect: (mode: 'voice' | 'form') => void;
}

export const ModeSelector: React.FC<ModeSelectorProps> = ({ onSelect }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto"
    >
      <Card
        className="p-8 cursor-pointer hover:border-accent transition-all group"
        onClick={() => onSelect('voice')}
      >
        <Mic className="w-12 h-12 text-accent mb-4 group-hover:scale-110 transition-transform" />
        <h3 className="text-heading-md font-semibold mb-3">Talk to Nova</h3>
        <p className="text-foreground-secondary mb-4">
          Have a natural conversation with our AI coach. Just speak your goals and preferences.
        </p>
        <Badge>Recommended</Badge>
      </Card>

      <Card
        className="p-8 cursor-pointer hover:border-accent transition-all group"
        onClick={() => onSelect('form')}
      >
        <FileText className="w-12 h-12 text-accent-light mb-4 group-hover:scale-110 transition-transform" />
        <h3 className="text-heading-md font-semibold mb-3">Fill Out a Form</h3>
        <p className="text-foreground-secondary">
          Prefer typing? Answer a few quick questions and get your program.
        </p>
      </Card>
    </motion.div>
  );
};
