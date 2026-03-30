import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useInView } from '@/hooks/useInView';

const images = [
  {
    src: '/rack-front.png',
    alt: 'Nowva Rack — front view',
    caption: 'Front View',
    description: 'Integrated cameras and display. Minimal footprint.',
  },
  {
    src: '/rack-angle.png',
    alt: 'Nowva Rack — perspective view',
    caption: 'Perspective View',
    description: 'Premium construction. Built to last.',
  },
];

const ImageSlot = ({
  image,
  delay,
  className = '',
}: {
  image: (typeof images)[0];
  delay: number;
  className?: string;
}) => {
  const [hasError, setHasError] = useState(false);
  const [loaded, setLoaded] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.7, delay, ease: 'easeOut' }}
      className={`group relative ${className}`}
    >
      <div className="relative aspect-[4/5] rounded-2xl overflow-hidden bg-surface border border-border transition-all duration-500 group-hover:border-accent/20 group-hover:shadow-glow-cyan">
        {/* Actual image */}
        {!hasError && (
          <img
            src={image.src}
            alt={image.alt}
            onLoad={() => setLoaded(true)}
            onError={() => setHasError(true)}
            className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-500 ${
              loaded ? 'opacity-100' : 'opacity-0'
            }`}
          />
        )}

        {/* Placeholder shown while loading or on error */}
        {(!loaded || hasError) && (
          <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-surface-light to-surface">
            <div className="text-center px-8">
              <div className="w-14 h-14 mx-auto mb-4 rounded-xl bg-accent/10 border border-accent/15 flex items-center justify-center">
                <svg className="w-7 h-7 text-accent/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
                </svg>
              </div>
              <p className="text-foreground-tertiary text-sm font-medium">{image.caption}</p>
              <p className="text-foreground-tertiary/50 text-xs mt-1">
                Place image at <span className="font-mono text-accent/50">public{image.src}</span>
              </p>
            </div>
          </div>
        )}

        {/* Subtle overlay gradient at bottom */}
        <div className="absolute bottom-0 inset-x-0 h-28 bg-gradient-to-t from-background/80 to-transparent" />

        {/* Corner brackets */}
        <div className="absolute top-3 left-3 w-6 h-6 border-t border-l border-accent/25 rounded-tl-sm" />
        <div className="absolute top-3 right-3 w-6 h-6 border-t border-r border-accent/25 rounded-tr-sm" />
        <div className="absolute bottom-3 left-3 w-6 h-6 border-b border-l border-accent/25 rounded-bl-sm" />
        <div className="absolute bottom-3 right-3 w-6 h-6 border-b border-r border-accent/25 rounded-br-sm" />
      </div>

      {/* Caption below image */}
      <div className="mt-5 px-1">
        <h4 className="font-display text-heading-md font-semibold text-foreground mb-1">
          {image.caption}
        </h4>
        <p className="text-body-sm text-foreground-secondary">
          {image.description}
        </p>
      </div>
    </motion.div>
  );
};

export const ProductShowcase = () => {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true });

  return (
    <section ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      <div className="section-container relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="mb-16 max-w-2xl"
        >
          <p className="eyebrow mb-4">First Look</p>
          <h2 className="font-display text-display-md md:text-display-lg font-bold text-foreground mb-5">
            What we&apos;re{' '}
            <span className="text-accent">building</span>
          </h2>
          <p className="text-body-lg text-foreground-secondary">
            Early CAD renders of the Nowva Rack. The design is evolving — the intelligence inside it is already real.
          </p>
        </motion.div>

        {/* Image grid — offset for visual interest */}
        <div className="grid md:grid-cols-2 gap-6 md:gap-8 items-start">
          <ImageSlot
            image={images[0]}
            delay={0.1}
          />
          <ImageSlot
            image={images[1]}
            delay={0.25}
            className="md:mt-16"
          />
        </div>
      </div>
    </section>
  );
};
