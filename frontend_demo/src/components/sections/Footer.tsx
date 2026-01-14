import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { WorkWithUs } from './WorkWithUs';

export const Footer = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  return (
    <>
      <footer className="py-12 border-t border-border">
        <div className="section-container">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="text-foreground-secondary text-sm">
              © 2025 Nowva. All rights reserved.
            </div>

            <div className="flex gap-6">
              <a href="#" className="text-foreground-secondary hover:text-foreground transition-colors">
                Privacy
              </a>
              <a href="#" className="text-foreground-secondary hover:text-foreground transition-colors">
                Terms
              </a>
              <a href="mailto:contact@nowva.ai" className="text-foreground-secondary hover:text-foreground transition-colors">
                Contact
              </a>
              <button
                onClick={() => setIsModalOpen(true)}
                className="text-foreground-secondary hover:text-foreground transition-colors"
              >
                Work With Us
              </button>
            </div>
          </div>
        </div>
      </footer>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
        <WorkWithUs />
      </Modal>
    </>
  );
};
