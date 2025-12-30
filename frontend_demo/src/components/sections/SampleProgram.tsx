import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useInView } from '@/hooks/useInView';
import { WorkoutCard } from '@/components/program/WorkoutCard';
import { sampleProgram } from '@/data/sampleProgram';
import { cn } from '@/utils/cn';
import { ChevronDown, Sparkles, Calendar } from 'lucide-react';

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
    <section ref={ref} className="relative py-24 md:py-32 overflow-hidden">
      {/* Stunning gradient background with animation */}
      <div className="absolute inset-0 bg-linear-to-br from-purple-50 via-pink-50 to-rose-50 opacity-60" />
      <div className="absolute inset-0">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-300/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-pink-300/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="section-container relative z-10">
        {/* Header with conversion messaging */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
        >
         

          <h2 className="text-heading-xl md:text-display-md font-bold mb-4">
            Your Program Will Look Like{' '}
            <span className="gradient-text">This</span>
          </h2>

          <p className="text-body-lg text-foreground-secondary max-w-2xl mx-auto mb-2">
            {sampleProgram.metadata.description}
          </p>
          <p className="text-body-md text-purple-600 font-medium">
            Personalized for your goals, experience, and equipment
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
                  setShowAllWorkouts(false); // Reset expansion when changing weeks
                }}
                className={cn(
                  'px-6 py-3 rounded-xl font-medium transition-all duration-300',
                  selectedWeek === week
                    ? 'bg-linear-to-br from-purple-600 to-pink-600 text-gray-800 shadow-lg shadow-purple-500/30 scale-105'
                    : 'bg-background-tertiary text-foreground-secondary hover:bg-background-secondary border border-border hover:border-purple-500/30'
                )}
              >
                <div className="text-sm font-semibold">Week {week}</div>
                {weekData && (
                  <div className="text-xs opacity-75">{weekData.phase}</div>
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

              {/* Expand button or conversion CTA */}
              {!showAllWorkouts && remainingWorkoutsCount > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, delay: 0.2 }}
                  className="relative"
                >
                  {/* Stunning expand button */}
                  <div className="relative group">
                    {/* Animated gradient border */}
                    <div className="absolute -inset-0.5 bg-linear-to-r from-purple-500 via-pink-500 to-purple-500 rounded-2xl opacity-75 group-hover:opacity-100 blur transition-opacity animate-gradient-x" style={{ backgroundSize: '200% 100%' }} />

                    {/* Button content */}
                    <button
                      onClick={() => setShowAllWorkouts(true)}
                      className="relative w-full bg-background rounded-2xl p-6 flex items-center justify-center gap-3 hover:bg-background-secondary transition-all group"
                    >
                      <Calendar className="w-5 h-5 text-purple-500 group-hover:scale-110 transition-transform" />
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
                  </div>
                </motion.div>
              )}

              {/* Show collapse button when expanded */}
              {showAllWorkouts && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.3 }}
                  className="flex justify-center"
                >
                  <button
                    onClick={() => setShowAllWorkouts(false)}
                    className="text-sm text-foreground-secondary hover:text-foreground flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-background-tertiary transition-all"
                  >
                    Show Less
                    <ChevronDown className="w-4 h-4 rotate-180" />
                  </button>
                </motion.div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Conversion-focused footer */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="mt-16 text-center"
        >
          <div className="inline-flex items-center gap-2 text-sm text-foreground-secondary bg-background-tertiary/80 backdrop-blur-sm border border-border rounded-full px-6 py-3">
            <Sparkles className="w-4 h-4 text-purple-500" />
            <span>Get your personalized program in as little as 60 seconds</span>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
