import { useRef } from 'react';
import { motion } from 'framer-motion';
import { Rocket, Code2, Sparkles, Mail, Linkedin } from 'lucide-react';
import { useInView } from '@/hooks/useInView';

const features = [
  {
    icon: Code2,
    title: 'AI-Powered Programming',
    description: 'Intelligent program generation that adapts to your goals - live now',
  },
  {
    icon: Sparkles,
    title: 'Real-Time Form Analysis',
    description: 'Computer vision that coaches your technique in real-time',
  },
  {
    icon: Rocket,
    title: 'Voice-Controlled Coaching',
    description: 'Natural conversations with AI that understands strength training',
  },
  {
    icon: Sparkles,
    title: 'Space-Saving Hardware',
    description: 'Foldable, compact equipment designed to look as good as it performs',
  },
];

export const WorkWithUs = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  return (
    <div ref={ref} className="relative overflow-hidden">
      {/* Gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-900 via-purple-900 to-cyan-900 opacity-20" />

      {/* Content */}
      <div className="relative z-10 py-16 px-8 md:px-16">
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-display-md md:text-display-lg font-bold mb-6">
            Want to <span className="gradient-text">Work With Us?</span>
          </h2>
          <p className="text-body-lg md:text-heading-md text-foreground-secondary max-w-3xl mx-auto">
            We're building the future of strength training - making world-class coaching accessible through AI, computer vision, and space-saving hardware that looks as good as it performs.
          </p>
        </motion.div>

        {/* Mission Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mb-16"
        >
          <div className="glass-card p-8 md:p-12 backdrop-blur-xl bg-background/80 max-w-4xl mx-auto">
            <h3 className="text-heading-lg font-semibold mb-4 text-center">Our Mission</h3>
            <p className="text-body-lg text-foreground-secondary text-center">
              We're revolutionizing strength training by combining cutting-edge AI, biomechanics, and computer vision to make expert coaching accessible to everyone. Our vision includes space-saving, visually stunning hardware that fits seamlessly into your home.
            </p>
          </div>
        </motion.div>

        {/* What We're Building */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="mb-16"
        >
          <h3 className="text-heading-lg font-semibold mb-8 text-center">What We're Building</h3>
          <div className="grid md:grid-cols-2 gap-6 max-w-5xl mx-auto">
            {features.map((feature, index) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 30 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.5, delay: 0.5 + index * 0.1 }}
                className="glass-card p-6 backdrop-blur-xl bg-background/60"
              >
                <div className="flex items-start gap-4">
                  <div className="p-3 rounded-lg bg-gradient-to-br from-accent/20 to-accent/5">
                    <feature.icon className="w-6 h-6 text-accent" />
                  </div>
                  <div className="flex-1">
                    <h4 className="text-heading-sm font-semibold mb-2">{feature.title}</h4>
                    <p className="text-body-md text-foreground-secondary">{feature.description}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Who We're Looking For */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.9 }}
          className="mb-16"
        >
          <div className="glass-card p-8 md:p-12 backdrop-blur-xl bg-background/80 max-w-4xl mx-auto">
            <h3 className="text-heading-lg font-semibold mb-6 text-center">Join Us</h3>
            <p className="text-body-lg text-foreground-secondary text-center mb-4">
              Whether you're a <strong className="text-foreground">developer</strong>, <strong className="text-foreground">engineer</strong>, <strong className="text-foreground">designer</strong>, or <strong className="text-foreground">business partner</strong> passionate about fitness tech, we'd love to hear from you.
            </p>
          </div>
        </motion.div>

        {/* Contact Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 1.1 }}
          className="max-w-2xl mx-auto"
        >
          <h3 className="text-heading-lg font-semibold mb-6 text-center">Get In Touch</h3>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="mailto:contact@nowva.ai"
              className="glass-card px-8 py-4 backdrop-blur-xl bg-background/80 hover:bg-background/90 transition-colors flex items-center justify-center gap-3 group"
            >
              <Mail className="w-5 h-5 text-accent group-hover:scale-110 transition-transform" />
              <span className="font-medium">contact@nowva.ai</span>
            </a>
            <a
              href="https://www.linkedin.com/in/ambaka-le-gregam-287707215/"
              target="_blank"
              rel="noopener noreferrer"
              className="glass-card px-8 py-4 backdrop-blur-xl bg-background/80 hover:bg-background/90 transition-colors flex items-center justify-center gap-3 group"
            >
              <Linkedin className="w-5 h-5 text-accent group-hover:scale-110 transition-transform" />
              <span className="font-medium">Connect on LinkedIn</span>
            </a>
          </div>
        </motion.div>
      </div>
    </div>
  );
};
