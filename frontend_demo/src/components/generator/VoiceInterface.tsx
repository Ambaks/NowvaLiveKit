import { motion } from 'framer-motion';
import { Mic } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

export const VoiceInterface = () => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="max-w-2xl mx-auto"
    >
      <Card className="p-12 text-center">
        <div className="w-24 h-24 mx-auto mb-6 bg-accent/10 rounded-full flex items-center justify-center">
          <Mic className="w-12 h-12 text-accent" />
        </div>
        <h3 className="text-heading-lg font-semibold mb-4">Voice Interface</h3>
        <p className="text-foreground-secondary mb-6">
          This feature is currently in development. Soon you'll be able to have a natural conversation with Nova to create your perfect program.
        </p>
        <Badge variant="secondary">Coming Soon</Badge>
      </Card>
    </motion.div>
  );
};
