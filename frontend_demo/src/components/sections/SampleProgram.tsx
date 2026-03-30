import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useInView } from '@/hooks/useInView';
import { WorkoutCard } from '@/components/program/WorkoutCard';
import { sampleProgram } from '@/data/sampleProgram';
import { cn } from '@/utils/cn';
import { ChevronDown, Calendar } from 'lucide-react';

export const SampleProgram = () => {
  const [selectedWeek, setSelectedWeek] = useState(1);
  const [showAllWorkouts, setShowAllWorkouts] = useState(false);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  const currentWeekData = sampleProgram.weeks.find(w => w.week_number === selectedWeek);
  const displayedWorkouts = showAllWorkouts
    ? currentWeekData?.workouts
    : currentWeekData?.workouts.slice(0, 1);
  const remainingWorkoutsCount = (currentWeekData?.workouts.length || 0) - 1;

  return (
    <section id="sample-program" ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Subtle background */}
      <div className="absolute inset-0 bg-background-secondary/30" />

      <div className="section-container relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
        >
          <p className="eyebrow mb-4">Free Preview</p>

          <h2 className="font-display text-heading-xl md:text-display-md font-bold mb-4 text-foreground">
            See What Nowva AI{' '}
            <span className="text-accent">Creates</span>
          </h2>

          <p className="text-body-lg text-foreground-secondary max-w-2xl mx-auto mb-2">
            {sampleProgram.metadata.description}
          </p>
          <p className="text-body-md text-accent font-medium">
            Powered by the same intelligence that will run inside the Nowva Rack
          </p>
        </motion.div>

        {/* Week Tabs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="flex justify-center gap-3 mb-12 flex-wrap"
        >
          {[1, 2, 3, 4].map(week => {
            const weekData = sampleProgram.weeks.find(w => w.week_number === week);
            return (
              <button
                key={week}
                onClick={() => {
                  setSelectedWeek(week);
                  setShowAllWorkouts(false);
                }}
                className={cn(
                  'px-6 py-3 rounded-xl font-medium transition-all duration-300',
                  selectedWeek === week
                    ? 'bg-surface-light text-foreground border border-accent/30 shadow-glow-cyan'
                    : 'bg-surface text-foreground-secondary hover:bg-surface-light border border-border hover:border-border-light'
                )}
              >
                <div className="text-sm font-semibold">Week {week}</div>
                {weekData && (
                  <div className="text-xs opacity-60">{weekData.phase}</div>
                )}
              </button>
            );
          })}
        </motion.div>

        {/* Workout Cards */}
        <div className="max-w-3xl mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              className="space-y-6"
              initial={{ opacity: 0 }}
              animate={isInView ? { opacity: 1 } : {}}
              transition={{ duration: 0.5 }}
              key={`${selectedWeek}-${showAllWorkouts}`}
            >
              {displayedWorkouts?.map((workout, index) => (
                <motion.div
                  key={`${selectedWeek}-${index}`}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, delay: index * 0.1 }}
                >
                  <WorkoutCard workout={workout} />
                </motion.div>
              ))}

              {/* Expand button */}
              {!showAllWorkouts && remainingWorkoutsCount > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, delay: 0.2 }}
                >
                  <button
                    onClick={() => setShowAllWorkouts(true)}
                    className="w-full bg-surface rounded-2xl p-6 flex items-center justify-center gap-3 border border-border hover:border-accent/20 transition-all group hover:shadow-glow-cyan"
                  >
                    <Calendar className="w-5 h-5 text-accent group-hover:scale-110 transition-transform" />
                    <div className="text-center">
                      <div className="text-lg font-semibold text-foreground mb-1 flex items-center gap-2">
                        View {remainingWorkoutsCount} More Workout{remainingWorkoutsCount !== 1 ? 's' : ''} This Week
                        <ChevronDown className="w-5 h-5 group-hover:translate-y-1 transition-transform" />
                      </div>
                      <p className="text-sm text-foreground-secondary">
                        Complete training for the entire week
                      </p>
                    </div>
                  </button>
                </motion.div>
              )}

              {/* Collapse button */}
              {showAllWorkouts && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.3 }}
                  className="flex justify-center"
                >
                  <button
                    onClick={() => setShowAllWorkouts(false)}
                    className="text-sm text-foreground-secondary hover:text-foreground flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-surface transition-all"
                  >
                    Show Less
                    <ChevronDown className="w-4 h-4 rotate-180" />
                  </button>
                </motion.div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer CTA hint */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="mt-16 text-center"
        >
          <div className="inline-flex items-center gap-2 text-sm text-foreground-tertiary bg-surface/50 border border-border rounded-full px-6 py-3">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-glow-pulse" />
            <span>Get your personalized program in as little as 60 seconds</span>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
