import { motion } from 'framer-motion';

// Squat position skeleton inside the rack frame
const joints = [
  { id: 'head', x: 240, y: 132, size: 8 },
  { id: 'neck', x: 240, y: 158, size: 3.5 },
  { id: 'l_shoulder', x: 206, y: 176, size: 5 },
  { id: 'r_shoulder', x: 274, y: 176, size: 5 },
  { id: 'l_elbow', x: 184, y: 218, size: 4 },
  { id: 'r_elbow', x: 296, y: 218, size: 4 },
  { id: 'l_wrist', x: 198, y: 182, size: 3.5 },
  { id: 'r_wrist', x: 282, y: 182, size: 3.5 },
  { id: 'torso', x: 240, y: 228, size: 3.5 },
  { id: 'hip', x: 240, y: 282, size: 4 },
  { id: 'l_hip', x: 220, y: 290, size: 4.5 },
  { id: 'r_hip', x: 260, y: 290, size: 4.5 },
  { id: 'l_knee', x: 202, y: 372, size: 4.5 },
  { id: 'r_knee', x: 278, y: 372, size: 4.5 },
  { id: 'l_ankle', x: 210, y: 448, size: 3.5 },
  { id: 'r_ankle', x: 270, y: 448, size: 3.5 },
  { id: 'l_foot', x: 196, y: 458, size: 3 },
  { id: 'r_foot', x: 284, y: 458, size: 3 },
];

const bones: [number, number][] = [
  [0, 1], [1, 2], [1, 3], [2, 4], [4, 6], [3, 5], [5, 7],
  [1, 8], [8, 9], [9, 10], [9, 11],
  [10, 12], [12, 14], [11, 13], [13, 15],
  [14, 16], [15, 17],
];

export const RackVisualization = ({ className = '' }: { className?: string }) => {
  return (
    <div className={`relative select-none ${className}`}>
      <div className="relative aspect-[3/4] overflow-hidden">
        <svg
          viewBox="0 0 480 600"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Metal gradient for uprights */}
            <linearGradient id="metal-left" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#1E1E22" />
              <stop offset="25%" stopColor="#38383E" />
              <stop offset="55%" stopColor="#42424A" />
              <stop offset="85%" stopColor="#32323A" />
              <stop offset="100%" stopColor="#1E1E22" />
            </linearGradient>
            <linearGradient id="metal-right" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#1E1E22" />
              <stop offset="15%" stopColor="#32323A" />
              <stop offset="45%" stopColor="#42424A" />
              <stop offset="75%" stopColor="#38383E" />
              <stop offset="100%" stopColor="#1E1E22" />
            </linearGradient>
            <linearGradient id="metal-bar" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#42424A" />
              <stop offset="50%" stopColor="#52525A" />
              <stop offset="100%" stopColor="#38383E" />
            </linearGradient>
            <linearGradient id="barbell-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#50505A" />
              <stop offset="50%" stopColor="#60606A" />
              <stop offset="100%" stopColor="#45454E" />
            </linearGradient>

            {/* Glow filters */}
            <filter id="rack-node-glow" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="rack-head-glow" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="rack-bone-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="camera-glow" x="-200%" y="-200%" width="500%" height="500%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="led-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Scan gradient */}
            <linearGradient id="rack-scan" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00E5FF" stopOpacity="0" />
              <stop offset="40%" stopColor="#00E5FF" stopOpacity="0.1" />
              <stop offset="50%" stopColor="#00E5FF" stopOpacity="0.35" />
              <stop offset="60%" stopColor="#00E5FF" stopOpacity="0.1" />
              <stop offset="100%" stopColor="#00E5FF" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* === RACK FRAME === */}

          {/* Left upright */}
          <rect x="72" y="22" width="28" height="536" rx="3" fill="url(#metal-left)" />
          {/* Right upright */}
          <rect x="380" y="22" width="28" height="536" rx="3" fill="url(#metal-right)" />

          {/* Top crossbar */}
          <rect x="72" y="22" width="336" height="14" rx="3" fill="url(#metal-bar)" />
          {/* Subtle edge highlight on crossbar */}
          <rect x="72" y="22" width="336" height="1" rx="0.5" fill="#5A5A62" opacity="0.6" />

          {/* Base plates */}
          <rect x="52" y="550" width="68" height="10" rx="3" fill="url(#metal-left)" />
          <rect x="360" y="550" width="68" height="10" rx="3" fill="url(#metal-right)" />
          {/* Base plate top highlights */}
          <rect x="52" y="550" width="68" height="1" rx="0.5" fill="#5A5A62" opacity="0.4" />
          <rect x="360" y="550" width="68" height="1" rx="0.5" fill="#5A5A62" opacity="0.4" />

          {/* J-hooks */}
          <rect x="100" y="172" width="18" height="7" rx="2" fill="url(#metal-bar)" />
          <rect x="362" y="172" width="18" height="7" rx="2" fill="url(#metal-bar)" />

          {/* Barbell across the J-hooks */}
          <motion.line
            x1="108" y1="175" x2="372" y2="175"
            stroke="url(#barbell-grad)"
            strokeWidth="6"
            strokeLinecap="round"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5, duration: 0.6 }}
          />
          {/* Barbell end caps */}
          <rect x="88" y="168" width="22" height="14" rx="2" fill="#3A3A42" opacity="0.8" />
          <rect x="370" y="168" width="22" height="14" rx="2" fill="#3A3A42" opacity="0.8" />

          {/* Safety arms */}
          <rect x="100" y="390" width="52" height="5" rx="2" fill="url(#metal-bar)" />
          <rect x="328" y="390" width="52" height="5" rx="2" fill="url(#metal-bar)" />

          {/* === LED ACCENT STRIPS (inner uprights) === */}
          <motion.line
            x1="100" y1="50" x2="100" y2="545"
            stroke="#00E5FF"
            strokeWidth="1.5"
            filter="url(#led-glow)"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.25, 0.15, 0.25] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
          />
          <motion.line
            x1="380" y1="50" x2="380" y2="545"
            stroke="#00E5FF"
            strokeWidth="1.5"
            filter="url(#led-glow)"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.25, 0.15, 0.25] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut', delay: 1.2 }}
          />

          {/* === CAMERA MODULES === */}
          {/* Left camera */}
          <motion.circle
            cx="86" cy="52" r="5"
            fill="#00E5FF"
            filter="url(#camera-glow)"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.8, 0.5, 0.8] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut', delay: 0.8 }}
          />
          <circle cx="86" cy="52" r="2.5" fill="#00E5FF" opacity="0.9" />
          {/* Right camera */}
          <motion.circle
            cx="394" cy="52" r="5"
            fill="#00E5FF"
            filter="url(#camera-glow)"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.8, 0.5, 0.8] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut', delay: 1.0 }}
          />
          <circle cx="394" cy="52" r="2.5" fill="#00E5FF" opacity="0.9" />

          {/* === SCAN LINE === */}
          <motion.rect
            x={110}
            width={260}
            height={50}
            fill="url(#rack-scan)"
            initial={{ y: 40 }}
            animate={{ y: [40, 500, 40] }}
            transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut', repeatDelay: 0.3 }}
          />

          {/* === SKELETON (inside rack) === */}
          <motion.g
            animate={{ y: [0, -2, 0] }}
            transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
          >
            {/* Bones */}
            {bones.map(([from, to], i) => (
              <motion.path
                key={`rbone-${i}`}
                d={`M ${joints[from].x} ${joints[from].y} L ${joints[to].x} ${joints[to].y}`}
                stroke="#00E5FF"
                strokeWidth={2}
                strokeLinecap="round"
                fill="none"
                filter="url(#rack-bone-glow)"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 0.55 }}
                transition={{ duration: 0.5, delay: 0.8 + i * 0.035, ease: 'easeOut' }}
              />
            ))}

            {/* Joints */}
            {joints.map((joint, i) => (
              <motion.circle
                key={`rjoint-${i}`}
                cx={joint.x}
                cy={joint.y}
                fill="#00E5FF"
                filter={joint.id === 'head' ? 'url(#rack-head-glow)' : 'url(#rack-node-glow)'}
                initial={{ opacity: 0, r: 0 }}
                animate={{ opacity: 1, r: joint.size }}
                transition={{ duration: 0.3, delay: 1.1 + i * 0.035, ease: 'backOut' }}
              />
            ))}
          </motion.g>

          {/* === DISPLAY SCREEN (on right upright) === */}
          <motion.g
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.8 }}
          >
            <rect x="414" y="200" width="44" height="72" rx="5" fill="#0A0A0B" stroke="#2A2A2E" strokeWidth="1" />
            {/* Screen content — mini waveform */}
            <rect x="420" y="208" width="32" height="3" rx="1" fill="#00E5FF" opacity="0.3" />
            <rect x="420" y="215" width="24" height="2" rx="1" fill="#00E5FF" opacity="0.2" />
            <rect x="420" y="224" width="14" height="8" rx="1" fill="#00E5FF" opacity="0.15" />
            <rect x="438" y="226" width="14" height="6" rx="1" fill="#FFB800" opacity="0.15" />
            {/* Mini graph bars */}
            {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
              <motion.rect
                key={`bar-${i}`}
                x={420 + i * 4}
                width="3"
                rx="0.5"
                fill="#00E5FF"
                opacity="0.4"
                initial={{ height: 4, y: 254 }}
                animate={{
                  height: [4, 6 + Math.random() * 8, 4],
                  y: [254, 250 - Math.random() * 4, 254],
                }}
                transition={{
                  duration: 1.5 + Math.random(),
                  repeat: Infinity,
                  ease: 'easeInOut',
                  delay: i * 0.15,
                }}
              />
            ))}
          </motion.g>
        </svg>

        {/* Data readouts (HTML overlay for better styling) */}
        <motion.div
          className="absolute"
          style={{ right: '8%', top: '60%' }}
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 2.2 }}
        >
          <div className="bg-background/70 backdrop-blur-sm border border-accent/15 rounded-lg px-2.5 py-1.5">
            <div className="font-mono text-[7px] text-accent/50 tracking-[0.15em]">R. KNEE</div>
            <div className="font-mono text-xs text-accent font-semibold leading-none">118°</div>
          </div>
        </motion.div>

        <motion.div
          className="absolute"
          style={{ left: '6%', top: '44%' }}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 2.4 }}
        >
          <div className="bg-background/70 backdrop-blur-sm border border-accent/15 rounded-lg px-2.5 py-1.5">
            <div className="font-mono text-[7px] text-accent/50 tracking-[0.15em]">HIP DEPTH</div>
            <div className="font-mono text-xs text-accent font-semibold leading-none">Below ∥</div>
          </div>
        </motion.div>

        <motion.div
          className="absolute left-1/2 -translate-x-1/2"
          style={{ bottom: '12%' }}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 2.6 }}
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

        {/* LIVE indicator */}
        <motion.div
          className="absolute top-[7%] left-[26%] flex items-center gap-1.5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.6 }}
        >
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-emerald-400"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
          <span className="font-mono text-[8px] text-accent/50 tracking-[0.2em]">TRACKING</span>
        </motion.div>
      </div>
    </div>
  );
};
