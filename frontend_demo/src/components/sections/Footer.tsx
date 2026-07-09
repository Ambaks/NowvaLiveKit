import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { WorkWithUs } from './WorkWithUs';
import { trackEvent } from '@/lib/analytics';

export const Footer = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleCTAClick = () => {
    trackEvent('cta_click', { location: 'footer' });
    document.getElementById('program-generator')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <>
      <footer className="relative border-t border-border">
        {/* Gradient top border accent */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent/20 to-transparent" />

        <div className="section-container py-16 md:py-20">
          {/* Top row: brand + CTA */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-8 mb-16">
            <div>
              <h2 className="font-display font-bold text-2xl md:text-3xl tracking-wider text-foreground mb-2">
                NOWVA AI
              </h2>
              <p className="text-foreground-secondary text-body-md">
                Train with intelligence.
              </p>
            </div>
            <button
              onClick={handleCTAClick}
              className="button-primary"
            >
              Get Your Free Program
            </button>
          </div>

          {/* Separator */}
          <div className="separator mb-12" />

          {/* Link columns */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-16">
            <div>
              <h4 className="text-caption uppercase tracking-widest text-foreground-tertiary mb-4 font-semibold">Product</h4>
              <div className="space-y-3">
                <a href="#how-it-works" className="block text-body-sm text-foreground-secondary hover:text-accent transition-colors">
                  How It Works
                </a>
                <a href="#the-rack" className="block text-body-sm text-foreground-secondary hover:text-accent transition-colors">
                  The Rack
                </a>
                <a href="#sample-program" className="block text-body-sm text-foreground-secondary hover:text-accent transition-colors">
                  Free Program
                </a>
              </div>
            </div>
            <div>
              <h4 className="text-caption uppercase tracking-widest text-foreground-tertiary mb-4 font-semibold">Company</h4>
              <div className="space-y-3">
                <a href="mailto:contact@nowva.ai" className="block text-body-sm text-foreground-secondary hover:text-accent transition-colors">
                  Contact
                </a>
                <button
                  onClick={() => setIsModalOpen(true)}
                  className="block text-body-sm text-foreground-secondary hover:text-accent transition-colors"
                >
                  Work With Us
                </button>
              </div>
            </div>
            <div>
              <h4 className="text-caption uppercase tracking-widest text-foreground-tertiary mb-4 font-semibold">Legal</h4>
              <div className="space-y-3">
                <a href="#" className="block text-body-sm text-foreground-secondary hover:text-accent transition-colors">
                  Privacy Policy
                </a>
                <a href="#" className="block text-body-sm text-foreground-secondary hover:text-accent transition-colors">
                  Terms of Service
                </a>
              </div>
            </div>
          </div>

          {/* Bottom bar */}
          <div className="separator mb-8" />
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-foreground-tertiary text-body-sm">
              &copy; 2026 Nowva. All rights reserved.
            </p>
            <p className="text-foreground-tertiary text-caption">
              Precision intelligence for human performance.
            </p>
          </div>
        </div>
      </footer>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
        <WorkWithUs />
      </Modal>
    </>
  );
};
