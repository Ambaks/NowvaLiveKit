import { Suspense, lazy, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { RackVisualization } from '@/components/sections/RackVisualization';

const BiomechanicsCanvas = lazy(() => import('./BiomechanicsCanvas'));

/** One-shot WebGL capability probe. */
function detectWebGL(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl2') || canvas.getContext('webgl'))
    );
  } catch {
    return false;
  }
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

const Readout = ({
  label,
  value,
  className,
  valueClass = 'text-accent',
}: {
  label: string;
  value: string;
  className: string;
  valueClass?: string;
}) => (
  <div className={`absolute ${className}`}>
    <div className="bg-background/70 backdrop-blur-sm border border-accent/15 rounded-lg px-2.5 py-1.5">
      <div className="font-mono text-[7px] text-accent/50 tracking-[0.15em]">{label}</div>
      <div className={`font-mono text-xs font-semibold leading-none ${valueClass}`}>{value}</div>
    </div>
  </div>
);

/**
 * Live 3D-biomechanics HUD used in the hero. Progressive enhancement:
 *  - WebGL available          → real three.js skeleton scene (BiomechanicsCanvas)
 *  - no WebGL / lazy-loading  → the hand-built SVG rack visualization (still rich)
 *  - prefers-reduced-motion   → the 3D scene renders a single static frame
 */
export const BiomechanicsScene = ({ className = '' }: { className?: string }) => {
  // Resolve capability once, at mount, via a lazy initializer (client-only app).
  const [webgl] = useState<boolean | null>(() => (typeof window === 'undefined' ? null : detectWebGL()));
  const reducedMotion = usePrefersReducedMotion();

  return (
    <div className={`relative select-none ${className}`}>
      <div className="relative aspect-[3/4] rounded-3xl overflow-hidden bg-background/40 border border-accent/10 backdrop-blur-md shadow-elevation-3">
        {/* CV scan grid backdrop */}
        <div className="absolute inset-0 cv-grid-overlay opacity-40" aria-hidden="true" />

        {/* 3D scene (or SVG fallback) */}
        <div className="absolute inset-0" aria-hidden="true">
          {webgl === false ? (
            <RackVisualization showReadouts={false} className="h-full [&>div]:h-full" />
          ) : webgl ? (
            <Suspense
              fallback={
                <div className="absolute inset-0 flex items-center justify-center">
                  <RackVisualization showReadouts={false} className="h-full [&>div]:h-full opacity-70" />
                </div>
              }
            >
              <BiomechanicsCanvas reducedMotion={reducedMotion} />
            </Suspense>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <RackVisualization showReadouts={false} className="h-full [&>div]:h-full opacity-70" />
            </div>
          )}
        </div>

        {/* Corner brackets — subtle "targeting" frame */}
        <div className="pointer-events-none absolute inset-3 rounded-2xl" aria-hidden="true">
          {['top-0 left-0 border-t border-l', 'top-0 right-0 border-t border-r', 'bottom-0 left-0 border-b border-l', 'bottom-0 right-0 border-b border-r'].map(
            (pos) => (
              <span key={pos} className={`absolute ${pos} w-5 h-5 border-accent/30 rounded-[3px]`} />
            ),
          )}
        </div>

        {/* HUD readouts (decorative) */}
        <div aria-hidden="true">
          <motion.div
            className="absolute top-[6%] left-[8%] flex items-center gap-1.5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8 }}
          >
            <motion.span
              className="w-1.5 h-1.5 rounded-full bg-emerald-400"
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            />
            <span className="font-mono text-[8px] text-accent/60 tracking-[0.2em]">3D · TRACKING</span>
          </motion.div>

          <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1.0 }}>
            <Readout label="HIP DEPTH" value="Below ∥" className="left-[6%] top-[42%]" />
          </motion.div>
          <motion.div initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1.15 }}>
            <Readout label="R. KNEE" value="118°" className="right-[7%] top-[34%]" valueClass="text-cta" />
          </motion.div>

          <motion.div
            className="absolute left-1/2 -translate-x-1/2 bottom-[7%]"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.3 }}
          >
            <div className="flex items-center gap-3 bg-background/70 backdrop-blur-sm border border-accent/15 rounded-lg px-3 py-1.5">
              <div>
                <div className="font-mono text-[7px] text-accent/50 tracking-[0.15em]">VELOCITY</div>
                <div className="font-mono text-xs text-accent font-semibold">0.72 m/s</div>
              </div>
              <div className="w-px h-5 bg-accent/15" />
              <div>
                <div className="font-mono text-[7px] text-accent/50 tracking-[0.15em]">REP</div>
                <div className="font-mono text-xs text-foreground font-semibold">3 / 5</div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
};
