import { useState } from 'react';
import { motion, useMotionValueEvent, useScroll, AnimatePresence } from 'framer-motion';
import { trackEvent } from '@/lib/analytics';

export const Navbar = () => {
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { scrollY } = useScroll();

  useMotionValueEvent(scrollY, 'change', (latest) => {
    const previous = scrollY.getPrevious() ?? 0;
    if (latest > previous && latest > 150) {
      setHidden(true);
      setMobileOpen(false);
    } else {
      setHidden(false);
    }
    setScrolled(latest > 50);
  });

  const handleCTAClick = () => {
    trackEvent('cta_click', { location: 'navbar' });
    document.getElementById('program-generator')?.scrollIntoView({ behavior: 'smooth' });
    setMobileOpen(false);
  };

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    setMobileOpen(false);
  };

  const navLinks = [
    { label: 'How It Works', id: 'how-it-works' },
    { label: 'The Rack', id: 'the-rack' },
    { label: 'Free Program', id: 'sample-program' },
  ];

  return (
    <motion.nav
      aria-label="Primary"
      initial={{ y: 0 }}
      animate={{ y: hidden ? -100 : 0 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
        scrolled || mobileOpen
          ? 'bg-background/70 backdrop-blur-2xl border-b border-accent/10'
          : 'bg-transparent'
      }`}
    >
      <div className="section-container flex items-center justify-between h-16 md:h-20">
        {/* Wordmark */}
        <a href="/" className="font-display font-bold text-xl md:text-2xl tracking-wider text-foreground">
          NOWVA AI
        </a>

        {/* Nav links — desktop */}
        <div className="hidden md:flex items-center gap-10">
          {navLinks.map((link) => (
            <button
              key={link.id}
              onClick={() => scrollTo(link.id)}
              className="text-body-sm text-foreground-secondary hover:text-accent transition-colors duration-200"
            >
              {link.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-4">
          {/* CTA */}
          <button
            onClick={handleCTAClick}
            className="bg-cta hover:bg-cta-hover text-background text-sm font-semibold px-5 py-2.5 rounded-lg transition-all duration-300 hover:shadow-glow-amber"
          >
            Get Free Program
          </button>

          {/* Mobile hamburger */}
          <button
            className="md:hidden relative w-6 h-5 flex flex-col justify-center items-center"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
          >
            <motion.span
              className="block w-5 h-[2px] bg-foreground absolute"
              animate={mobileOpen ? { rotate: 45, y: 0 } : { rotate: 0, y: -5 }}
              transition={{ duration: 0.2 }}
            />
            <motion.span
              className="block w-5 h-[2px] bg-foreground absolute"
              animate={mobileOpen ? { opacity: 0, scaleX: 0 } : { opacity: 1, scaleX: 1 }}
              transition={{ duration: 0.15 }}
            />
            <motion.span
              className="block w-5 h-[2px] bg-foreground absolute"
              animate={mobileOpen ? { rotate: -45, y: 0 } : { rotate: 0, y: 5 }}
              transition={{ duration: 0.2 }}
            />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="md:hidden overflow-hidden border-t border-border/50"
          >
            <div className="section-container py-6 flex flex-col gap-1">
              {navLinks.map((link, i) => (
                <motion.button
                  key={link.id}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.05 + i * 0.05 }}
                  onClick={() => scrollTo(link.id)}
                  className="text-left text-body-md text-foreground-secondary hover:text-accent py-3 transition-colors"
                >
                  {link.label}
                </motion.button>
              ))}
              <div className="separator my-2" />
              <motion.button
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 }}
                onClick={handleCTAClick}
                className="text-left text-body-md text-cta font-semibold py-3"
              >
                Get Your Free Program
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
};
