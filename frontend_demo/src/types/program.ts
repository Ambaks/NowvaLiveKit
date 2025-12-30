export interface WorkoutSet {
  set_number: number;
  reps: number;
  intensity_percent?: string;     // "75%" (optional for VBT exercises)
  rpe: number;                    // Rating of Perceived Exertion (1-10)
  rest_seconds: number;
  rir?: number;                   // Reps in Reserve
  velocity_min?: number;          // Min velocity (m/s) for VBT
  velocity_max?: number;          // Max velocity (m/s) for VBT
  velocity_target?: string;       // Display format: "0.9-1.1 m/s"
}

export interface Exercise {
  name: string;
  sets: WorkoutSet[];
  notes?: string;
}

export interface Workout {
  day_number: number;
  name: string;
  description: string;
  exercises: Exercise[];
}

export interface Week {
  week_number: number;
  phase: string;  // "Accumulation" | "Intensification" | "Deload" | "Taper"
  workouts: Workout[];
}

export interface ProgramMetadata {
  name: string;
  description: string;
  duration_weeks: number;
  days_per_week: number;
  goal: string;         // "Strength" | "Hypertrophy" | "Power"
  fitness_level: string; // "Beginner" | "Intermediate" | "Advanced"
  sport?: string;       // e.g., "Basketball"
}

export interface Program {
  metadata: ProgramMetadata;
  weeks: Week[];
}
