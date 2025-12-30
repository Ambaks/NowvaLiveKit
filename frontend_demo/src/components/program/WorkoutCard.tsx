import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import type { Workout } from '@/types/program';
import { Dumbbell, Clock, Lock, Sparkles } from 'lucide-react';

interface WorkoutCardProps {
  workout: Workout;
  showFullWorkout?: boolean;
}

export const WorkoutCard: React.FC<WorkoutCardProps> = ({ workout, showFullWorkout = false }) => {
  const totalExercises = workout.exercises.length;
  const estimatedDuration = workout.exercises.reduce((total, exercise) => {
    const exerciseTime = exercise.sets.reduce((sum, set) => {
      return sum + (set.rest_seconds / 60) + 1; // 1 min per set + rest
    }, 0);
    return total + exerciseTime;
  }, 0);

  return (
    <Card className="hover:border-accent group overflow-hidden relative">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-heading-md font-semibold mb-1 group-hover:text-accent transition-colors">{workout.name}</h3>
          <p className="text-body-sm text-foreground-secondary">{workout.description}</p>
        </div>
        <Badge>Day {workout.day_number}</Badge>
      </div>

      <div className="flex gap-4 mb-6 text-foreground-tertiary">
        <div className="flex items-center gap-2 group-hover:text-accent transition-colors">
          <Dumbbell className="w-4 h-4" />
          <span className="text-sm">{totalExercises} exercises</span>
        </div>
        <div className="flex items-center gap-2 group-hover:text-accent transition-colors">
          <Clock className="w-4 h-4" />
          <span className="text-sm">~{Math.round(estimatedDuration)} min</span>
        </div>
      </div>

      <div className="space-y-3 relative">
        {/* Show first exercise clearly */}
        {workout.exercises.slice(0, 1).map((exercise, idx) => (
          <div key={idx} className="border-l-2 border-accent/30 pl-4">
            <h4 className="font-medium text-foreground mb-2">{exercise.name}</h4>
            {exercise.notes && (
              <p className="text-xs text-foreground-tertiary italic mb-2">{exercise.notes}</p>
            )}
            <div className="space-y-1">
              {exercise.sets.map((set, setIdx) => (
                <div key={setIdx} className="text-sm text-foreground-secondary flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs text-foreground-tertiary min-w-[50px]">Set {set.set_number}</span>
                  <span>{set.reps} reps</span>
                  {set.velocity_target && (
                    <>
                      <span className="text-foreground-tertiary">•</span>
                      <span className="text-accent font-medium">{set.velocity_target}</span>
                    </>
                  )}
                  {set.intensity_percent && (
                    <>
                      <span className="text-foreground-tertiary">•</span>
                      <span>@ {set.intensity_percent}</span>
                    </>
                  )}
                  <span className="text-foreground-tertiary">•</span>
                  <span>RPE {set.rpe}</span>
                  <span className="text-foreground-tertiary">•</span>
                  <span>{set.rest_seconds}s rest</span>
                </div>
              ))}
            </div>
          </div>
        ))}

        {/* Blurred remaining exercises with conversion overlay */}
        {!showFullWorkout && workout.exercises.length > 1 && (
          <div className="relative">
            {/* Blurred content */}
            <div className="select-none pointer-events-none" style={{ filter: 'blur(3px)' }}>
              {workout.exercises.slice(1).map((exercise, idx) => (
                <div key={idx + 1} className="border-l-2 border-accent/30 pl-4 mb-3">
                  <h4 className="font-medium text-foreground mb-2">{exercise.name}</h4>
                  {exercise.notes && (
                    <p className="text-xs text-foreground-tertiary italic mb-2">{exercise.notes}</p>
                  )}
                  <div className="space-y-1">
                    {exercise.sets.map((set, setIdx) => (
                      <div key={setIdx} className="text-sm text-foreground-secondary flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs text-foreground-tertiary min-w-[50px]">Set {set.set_number}</span>
                        <span>{set.reps} reps</span>
                        <span className="text-foreground-tertiary">•</span>
                        <span>RPE {set.rpe}</span>
                        <span className="text-foreground-tertiary">•</span>
                        <span>{set.rest_seconds}s rest</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Conversion overlay - more subtle */}
            <div className="absolute inset-0 flex items-center justify-center" style={{
              background: 'linear-gradient(to top, rgba(255, 255, 255, 0.85), rgba(255, 255, 255, 0.6), rgba(255, 255, 255, 0.3))'
            }}>
              <div className="text-center px-4 py-6 bg-background/80 backdrop-blur-sm rounded-2xl border border-purple-500/20">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-linear-to-br from-purple-500 to-pink-500 mb-3">
                  <Lock className="w-6 h-6 text-white" />
                </div>
                <p className="text-sm font-semibold text-foreground mb-1 flex items-center justify-center gap-2">
                  <Sparkles className="w-4 h-4 text-purple-500" />
                  {totalExercises - 1} More Exercises
                </p>
                <p className="text-xs text-foreground-tertiary">
                  Get your free personalized program
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Show all exercises if unlocked */}
        {showFullWorkout && workout.exercises.slice(1).map((exercise, idx) => (
          <div key={idx + 1} className="border-l-2 border-accent/30 pl-4">
            <h4 className="font-medium text-foreground mb-2">{exercise.name}</h4>
            {exercise.notes && (
              <p className="text-xs text-foreground-tertiary italic mb-2">{exercise.notes}</p>
            )}
            <div className="space-y-1">
              {exercise.sets.map((set, setIdx) => (
                <div key={setIdx} className="text-sm text-foreground-secondary flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs text-foreground-tertiary min-w-[50px]">Set {set.set_number}</span>
                  <span>{set.reps} reps</span>
                  {set.velocity_target && (
                    <>
                      <span className="text-foreground-tertiary">•</span>
                      <span className="text-accent font-medium">{set.velocity_target}</span>
                    </>
                  )}
                  {set.intensity_percent && (
                    <>
                      <span className="text-foreground-tertiary">•</span>
                      <span>@ {set.intensity_percent}</span>
                    </>
                  )}
                  <span className="text-foreground-tertiary">•</span>
                  <span>RPE {set.rpe}</span>
                  <span className="text-foreground-tertiary">•</span>
                  <span>{set.rest_seconds}s rest</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
