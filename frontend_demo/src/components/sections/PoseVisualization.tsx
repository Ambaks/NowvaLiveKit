import { motion } from 'framer-motion';

// Joint positions for athletic standing pose (viewBox 0 0 400 480)
const joints = [
  { id: 'head', x: 200, y: 48, size: 9 },
  { id: 'neck', x: 200, y: 82, size: 4 },
  { id: 'l_shoulder', x: 152, y: 104, size: 6 },
  { id: 'r_shoulder', x: 248, y: 104, size: 6 },
  { id: 'l_elbow', x: 124, y: 172, size: 5 },
  { id: 'r_elbow', x: 276, y: 172, size: 5 },
  { id: 'l_wrist', x: 108, y: 236, size: 4 },
  { id: 'r_wrist', x: 292, y: 236, size: 4 },
  { id: 'torso', x: 200, y: 155, size: 4 },
  { id: 'hip', x: 200, y: 218, size: 5 },
  { id: 'l_hip', x: 174, y: 226, size: 5 },
  { id: 'r_hip', x: 226, y: 226, size: 5 },
  { id: 'l_knee', x: 164, y: 318, size: 5 },
  { id: 'r_knee', x: 236, y: 318, size: 5 },
  { id: 'l_ankle', x: 156, y: 408, size: 4 },
  { id: 'r_ankle', x: 244, y: 408, size: 4 },
  { id: 'l_foot', x: 142, y: 420, size: 3 },
  { id: 'r_foot', x: 258, y: 420, size: 3 },
];

// Bone connections [from_index, to_index]
const bones: [number, number][] = [
  [0, 1],   // head → neck
  [1, 2],   // neck → l_shoulder
  [1, 3],   // neck → r_shoulder
  [2, 4],   // l_shoulder → l_elbow
  [4, 6],   // l_elbow → l_wrist
  [3, 5],   // r_shoulder → r_elbow
  [5, 7],   // r_elbow → r_wrist
  [1, 8],   // neck → torso
  [8, 9],   // torso → hip
  [9, 10],  // hip → l_hip
  [9, 11],  // hip → r_hip
  [10, 12], // l_hip → l_knee
  [12, 14], // l_knee → l_ankle
  [11, 13], // r_hip → r_knee
  [13, 15], // r_knee → r_ankle
  [14, 16], // l_ankle → l_foot
  [15, 17], // r_ankle → r_foot
];

// Data readouts positioned relative to the visualization
const readouts = [
  { label: 'R. KNEE', value: '172°', left: '66%', top: '65%' },
  { label: 'HIP FLEX', value: '168°', left: '8%', top: '44%' },
  { label: 'SYMMETRY', value: '96.2%', left: '66%', top: '20%' },
];

export const PoseVisualization = ({ className = '' }: { className?: string }) => {
  return (
    <div className={`relative select-none ${className}`}>
      <div className="relative aspect-[4/5] rounded-2xl overflow-hidden bg-gradient-to-b from-surface-light/80 to-surface/60 border border-border">
        {/* Grid overlay */}
        <div className="absolute inset-0 cv-grid-overlay opacity-70" />

        {/* SVG skeleton */}
        <svg
          viewBox="0 0 400 480"
          className="absolute inset-0 w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Node glow */}
            <filter id="node-glow" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Stronger glow for head */}
            <filter id="head-glow" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Bone glow */}
            <filter id="bone-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Scan gradient */}
            <linearGradient id="scan-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00E5FF" stopOpacity="0" />
              <stop offset="40%" stopColor="#00E5FF" stopOpacity="0.15" />
              <stop offset="50%" stopColor="#00E5FF" stopOpacity="0.5" />
              <stop offset="60%" stopColor="#00E5FF" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#00E5FF" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Scan band */}
          <motion.rect
            x={0}
            width={400}
            height={60}
            fill="url(#scan-grad)"
            initial={{ y: -60 }}
            animate={{ y: [-60, 500, -60] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut', repeatDelay: 0.5 }}
          />

          {/* Breathing wrapper */}
          <motion.g
            animate={{ y: [0, -2.5, 0] }}
            transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
          >
            {/* Bones — draw in with stagger */}
            {bones.map(([from, to], i) => (
              <motion.path
                key={`bone-${i}`}
                d={`M ${joints[from].x} ${joints[from].y} L ${joints[to].x} ${joints[to].y}`}
                stroke="#00E5FF"
                strokeWidth={2.5}
                strokeLinecap="round"
                fill="none"
                filter="url(#bone-glow)"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 0.65 }}
                transition={{ duration: 0.5, delay: 0.4 + i * 0.04, ease: 'easeOut' }}
              />
            ))}

            {/* Joint nodes — fade in with stagger */}
            {joints.map((joint, i) => (
              <g key={`joint-${i}`}>
                {/* Outer pulse ring */}
                <motion.circle
                  cx={joint.x}
                  cy={joint.y}
                  r={joint.size + 4}
                  fill="none"
                  stroke="#00E5FF"
                  strokeWidth={0.5}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: [0, 0.3, 0], r: [joint.size + 2, joint.size + 8, joint.size + 2] }}
                  transition={{
                    duration: 3,
                    delay: 1.5 + i * 0.2,
                    repeat: Infinity,
                    ease: 'easeInOut',
                  }}
                />
                {/* Node */}
                <motion.circle
                  cx={joint.x}
                  cy={joint.y}
                  fill="#00E5FF"
                  filter={joint.id === 'head' ? 'url(#head-glow)' : 'url(#node-glow)'}
                  initial={{ opacity: 0, r: 0 }}
                  animate={{ opacity: 1, r: joint.size }}
                  transition={{
                    duration: 0.35,
                    delay: 0.7 + i * 0.04,
                    ease: 'backOut',
                  }}
                />
              </g>
            ))}

            {/* Angle indicator — right knee */}
            <motion.g
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1.8 }}
            >
              {/* Small arc near right knee */}
              <motion.path
                d="M 240 304 A 16 16 0 0 1 240 332"
                stroke="#00E5FF"
                strokeWidth={1}
                fill="none"
                opacity={0.5}
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.6, delay: 2.0 }}
              />
              {/* Tick marks */}
              <line x1="232" y1="302" x2="240" y2="304" stroke="#00E5FF" strokeWidth={0.8} opacity={0.4} />
              <line x1="232" y1="334" x2="240" y2="332" stroke="#00E5FF" strokeWidth={0.8} opacity={0.4} />
            </motion.g>

            {/* Angle indicator — hip */}
            <motion.g
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2.0 }}
            >
              <motion.path
                d="M 186 212 A 14 14 0 0 0 186 234"
                stroke="#00E5FF"
                strokeWidth={1}
                fill="none"
                opacity={0.5}
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.6, delay: 2.2 }}
              />
            </motion.g>
          </motion.g>
        </svg>

        {/* Corner brackets */}
        <motion.div
          className="absolute top-3 left-3 w-8 h-8 border-t-2 border-l-2 border-accent/50 rounded-tl"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.0 }}
        />
        <motion.div
          className="absolute top-3 right-3 w-8 h-8 border-t-2 border-r-2 border-accent/50 rounded-tr"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.1 }}
        />
        <motion.div
          className="absolute bottom-3 left-3 w-8 h-8 border-b-2 border-l-2 border-accent/50 rounded-bl"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
        />
        <motion.div
          className="absolute bottom-3 right-3 w-8 h-8 border-b-2 border-r-2 border-accent/50 rounded-br"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.3 }}
        />

        {/* LIVE indicator */}
        <motion.div
          className="absolute top-5 left-12 flex items-center gap-2"
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 1.4 }}
        >
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-emerald-400"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
          <span className="font-mono text-[10px] text-accent/60 tracking-[0.2em]">
            CV TRACKING
          </span>
        </motion.div>

        {/* Data readouts */}
        {readouts.map((readout, i) => (
          <motion.div
            key={readout.label}
            className="absolute"
            style={{ left: readout.left, top: readout.top }}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 2.0 + i * 0.2 }}
          >
            <div className="bg-background/70 backdrop-blur-sm border border-accent/15 rounded-lg px-2.5 py-1.5">
              <div className="font-mono text-[8px] text-accent/50 tracking-[0.15em] mb-0.5">
                {readout.label}
              </div>
              <div className="font-mono text-sm text-accent font-semibold leading-none">
                {readout.value}
              </div>
            </div>
          </motion.div>
        ))}

        {/* Bottom bar velocity readout */}
        <motion.div
          className="absolute bottom-12 left-1/2 -translate-x-1/2"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 2.6 }}
        >
          <div className="flex items-center gap-4 bg-background/70 backdrop-blur-sm border border-accent/15 rounded-lg px-4 py-2">
            <div>
              <div className="font-mono text-[8px] text-accent/50 tracking-[0.15em]">BAR VELOCITY</div>
              <div className="font-mono text-sm text-accent font-semibold">0.82 m/s</div>
            </div>
            <div className="w-px h-6 bg-accent/15" />
            <div>
              <div className="font-mono text-[8px] text-accent/50 tracking-[0.15em]">REP</div>
              <div className="font-mono text-sm text-foreground font-semibold">3 / 5</div>
            </div>
          </div>
        </motion.div>

        {/* Bottom gradient fade */}
        <div className="absolute bottom-0 inset-x-0 h-20 bg-gradient-to-t from-background to-transparent" />
      </div>
    </div>
  );
};
