import type { Program } from '@/types/program';

export const sampleProgram: Program = {
  metadata: {
    name: "Basketball Power Development",
    description: "Example of a 4-week power program designed to improve vertical jump, explosiveness, and on-court performance for a basketball player",
    duration_weeks: 4,
    days_per_week: 4,
    goal: "Power",
    fitness_level: "Intermediate",
    sport: "Basketball"
  },
  weeks: [
    {
      week_number: 1,
      phase: "Accumulation",
      workouts: [
        {
          day_number: 1,
          name: "Lower Power - Olympic Lifts",
          description: "Build explosive strength with Olympic movements",
          exercises: [
            {
              name: "Power Clean",
              notes: "Focus on bar speed and triple extension",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 6, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 4, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 }
              ]
            },
            {
              name: "Back Squat (Speed Emphasis)",
              notes: "Move the bar explosively - 60% 1RM for speed",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.75-0.95 m/s", intensity_percent: "60%", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 5, velocity_target: "0.75-0.95 m/s", intensity_percent: "62.5%", rpe: 6, rest_seconds: 150 },
                { set_number: 3, reps: 5, velocity_target: "0.75-0.95 m/s", intensity_percent: "65%", rpe: 7, rest_seconds: 150 }
              ]
            },
            {
              name: "Romanian Deadlift",
              sets: [
                { set_number: 1, reps: 6, intensity_percent: "65%", rpe: 6, rest_seconds: 120 },
                { set_number: 2, reps: 6, intensity_percent: "67.5%", rpe: 6, rest_seconds: 120 },
                { set_number: 3, reps: 6, intensity_percent: "70%", rpe: 7, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 2,
          name: "Upper Power - Pressing",
          description: "Develop upper body explosiveness",
          exercises: [
            {
              name: "Push Press",
              notes: "Explosive hip drive into press",
              sets: [
                { set_number: 1, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 7, rest_seconds: 150 },
                { set_number: 3, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 7, rest_seconds: 150 }
              ]
            },
            {
              name: "Bench Press (Speed)",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "60%", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "62.5%", rpe: 6, rest_seconds: 150 },
                { set_number: 3, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "65%", rpe: 7, rest_seconds: 150 }
              ]
            },
            {
              name: "Barbell Row (Explosive)",
              notes: "Pull explosively - feel every rep",
              sets: [
                { set_number: 1, reps: 6, intensity_percent: "65%", rpe: 6, rest_seconds: 120 },
                { set_number: 2, reps: 6, intensity_percent: "67.5%", rpe: 6, rest_seconds: 120 },
                { set_number: 3, reps: 6, intensity_percent: "70%", rpe: 7, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 3,
          name: "Lower Strength-Speed",
          description: "Build force production capacity",
          exercises: [
            {
              name: "Hang Clean",
              notes: "Start from mid-thigh, explosive pull",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 6, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 }
              ]
            },
            {
              name: "Front Squat",
              sets: [
                { set_number: 1, reps: 5, intensity_percent: "70%", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 5, intensity_percent: "72.5%", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 5, intensity_percent: "75%", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Speed Deadlift",
              notes: "Light weight, maximum speed",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "50%", rpe: 5, rest_seconds: 120 },
                { set_number: 2, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "52.5%", rpe: 5, rest_seconds: 120 },
                { set_number: 3, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "55%", rpe: 6, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 4,
          name: "Full Body Power Complex",
          description: "Mixed power work - upper and lower",
          exercises: [
            {
              name: "Push Jerk",
              notes: "Aggressive dip and drive under bar",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 6, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 7, rest_seconds: 180 }
              ]
            },
            {
              name: "Box Jump Squat",
              notes: "Barbell on back, jump for maximum height",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.9-1.2 m/s", intensity_percent: "30%", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 5, velocity_target: "0.9-1.2 m/s", intensity_percent: "32.5%", rpe: 6, rest_seconds: 150 },
                { set_number: 3, reps: 5, velocity_target: "0.9-1.2 m/s", intensity_percent: "35%", rpe: 7, rest_seconds: 150 }
              ]
            },
            {
              name: "Overhead Press",
              sets: [
                { set_number: 1, reps: 6, intensity_percent: "65%", rpe: 6, rest_seconds: 120 },
                { set_number: 2, reps: 6, intensity_percent: "67.5%", rpe: 7, rest_seconds: 120 },
                { set_number: 3, reps: 6, intensity_percent: "70%", rpe: 7, rest_seconds: 120 }
              ]
            }
          ]
        }
      ]
    },
    {
      week_number: 2,
      phase: "Accumulation",
      workouts: [
        {
          day_number: 1,
          name: "Lower Power - Olympic Lifts",
          description: "Progressive volume - build work capacity",
          exercises: [
            {
              name: "Power Clean",
              notes: "Increase volume, maintain bar speed",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 6, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 4, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 5, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Back Squat (Speed Emphasis)",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.75-0.95 m/s", intensity_percent: "62.5%", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 5, velocity_target: "0.75-0.95 m/s", intensity_percent: "65%", rpe: 7, rest_seconds: 150 },
                { set_number: 3, reps: 5, velocity_target: "0.75-0.95 m/s", intensity_percent: "67.5%", rpe: 7, rest_seconds: 150 }
              ]
            },
            {
              name: "Romanian Deadlift",
              sets: [
                { set_number: 1, reps: 6, intensity_percent: "67.5%", rpe: 6, rest_seconds: 120 },
                { set_number: 2, reps: 6, intensity_percent: "70%", rpe: 7, rest_seconds: 120 },
                { set_number: 3, reps: 6, intensity_percent: "72.5%", rpe: 7, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 2,
          name: "Upper Power - Pressing",
          description: "Increased intensity on pressing movements",
          exercises: [
            {
              name: "Push Press",
              sets: [
                { set_number: 1, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 7, rest_seconds: 150 },
                { set_number: 2, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 7, rest_seconds: 150 },
                { set_number: 3, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 7, rest_seconds: 150 },
                { set_number: 4, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 8, rest_seconds: 150 }
              ]
            },
            {
              name: "Bench Press (Speed)",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "62.5%", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "65%", rpe: 7, rest_seconds: 150 },
                { set_number: 3, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "67.5%", rpe: 7, rest_seconds: 150 }
              ]
            },
            {
              name: "Barbell Row (Explosive)",
              sets: [
                { set_number: 1, reps: 6, intensity_percent: "67.5%", rpe: 7, rest_seconds: 120 },
                { set_number: 2, reps: 6, intensity_percent: "70%", rpe: 7, rest_seconds: 120 },
                { set_number: 3, reps: 6, intensity_percent: "72.5%", rpe: 7, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 3,
          name: "Lower Strength-Speed",
          description: "Volume progression week",
          exercises: [
            {
              name: "Hang Clean",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 4, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Front Squat",
              sets: [
                { set_number: 1, reps: 5, intensity_percent: "72.5%", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 5, intensity_percent: "75%", rpe: 8, rest_seconds: 180 },
                { set_number: 3, reps: 5, intensity_percent: "77.5%", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Speed Deadlift",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "52.5%", rpe: 5, rest_seconds: 120 },
                { set_number: 2, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "55%", rpe: 6, rest_seconds: 120 },
                { set_number: 3, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "57.5%", rpe: 6, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 4,
          name: "Full Body Power Complex",
          description: "Peak volume week",
          exercises: [
            {
              name: "Push Jerk",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 4, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Box Jump Squat",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.9-1.2 m/s", intensity_percent: "32.5%", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 5, velocity_target: "0.9-1.2 m/s", intensity_percent: "35%", rpe: 7, rest_seconds: 150 },
                { set_number: 3, reps: 5, velocity_target: "0.9-1.2 m/s", intensity_percent: "37.5%", rpe: 7, rest_seconds: 150 }
              ]
            },
            {
              name: "Overhead Press",
              sets: [
                { set_number: 1, reps: 6, intensity_percent: "67.5%", rpe: 7, rest_seconds: 120 },
                { set_number: 2, reps: 6, intensity_percent: "70%", rpe: 7, rest_seconds: 120 },
                { set_number: 3, reps: 6, intensity_percent: "72.5%", rpe: 8, rest_seconds: 120 }
              ]
            }
          ]
        }
      ]
    },
    {
      week_number: 3,
      phase: "Intensification",
      workouts: [
        {
          day_number: 1,
          name: "Lower Power - Peak Velocity",
          description: "Peak power output - maximum bar speed",
          exercises: [
            {
              name: "Power Clean",
              notes: "Reduce reps, maximize velocity",
              sets: [
                { set_number: 1, reps: 2, velocity_target: "1.0-1.2 m/s", rpe: 7, rest_seconds: 240 },
                { set_number: 2, reps: 2, velocity_target: "1.0-1.2 m/s", rpe: 8, rest_seconds: 240 },
                { set_number: 3, reps: 2, velocity_target: "1.0-1.2 m/s", rpe: 8, rest_seconds: 240 },
                { set_number: 4, reps: 2, velocity_target: "1.0-1.2 m/s", rpe: 8, rest_seconds: 240 }
              ]
            },
            {
              name: "Back Squat (Speed Emphasis)",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "65%", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "67.5%", rpe: 8, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.8-1.0 m/s", intensity_percent: "70%", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Romanian Deadlift",
              sets: [
                { set_number: 1, reps: 5, intensity_percent: "70%", rpe: 7, rest_seconds: 150 },
                { set_number: 2, reps: 5, intensity_percent: "72.5%", rpe: 8, rest_seconds: 150 }
              ]
            }
          ]
        },
        {
          day_number: 2,
          name: "Upper Power - Maximum Output",
          description: "Peak pressing power",
          exercises: [
            {
              name: "Push Press",
              notes: "Heavy weights, explosive execution",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 8, rest_seconds: 180 },
                { set_number: 3, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Bench Press (Speed)",
              sets: [
                { set_number: 1, reps: 4, velocity_target: "0.75-0.95 m/s", intensity_percent: "65%", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 4, velocity_target: "0.75-0.95 m/s", intensity_percent: "67.5%", rpe: 7, rest_seconds: 180 },
                { set_number: 3, reps: 4, velocity_target: "0.75-0.95 m/s", intensity_percent: "70%", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Barbell Row (Explosive)",
              sets: [
                { set_number: 1, reps: 5, intensity_percent: "70%", rpe: 7, rest_seconds: 150 },
                { set_number: 2, reps: 5, intensity_percent: "72.5%", rpe: 8, rest_seconds: 150 }
              ]
            }
          ]
        },
        {
          day_number: 3,
          name: "Lower Strength-Speed",
          description: "Maximum power production",
          exercises: [
            {
              name: "Hang Clean",
              sets: [
                { set_number: 1, reps: 2, velocity_target: "1.0-1.2 m/s", rpe: 7, rest_seconds: 240 },
                { set_number: 2, reps: 2, velocity_target: "1.0-1.2 m/s", rpe: 8, rest_seconds: 240 },
                { set_number: 3, reps: 2, velocity_target: "1.0-1.2 m/s", rpe: 8, rest_seconds: 240 }
              ]
            },
            {
              name: "Front Squat",
              sets: [
                { set_number: 1, reps: 4, intensity_percent: "75%", rpe: 8, rest_seconds: 210 },
                { set_number: 2, reps: 4, intensity_percent: "77.5%", rpe: 8, rest_seconds: 210 },
                { set_number: 3, reps: 4, intensity_percent: "80%", rpe: 9, rest_seconds: 210 }
              ]
            },
            {
              name: "Speed Deadlift",
              sets: [
                { set_number: 1, reps: 2, velocity_target: "0.9-1.1 m/s", intensity_percent: "55%", rpe: 6, rest_seconds: 150 },
                { set_number: 2, reps: 2, velocity_target: "0.9-1.1 m/s", intensity_percent: "57.5%", rpe: 7, rest_seconds: 150 }
              ]
            }
          ]
        },
        {
          day_number: 4,
          name: "Full Body Power Complex",
          description: "Peak power week",
          exercises: [
            {
              name: "Push Jerk",
              sets: [
                { set_number: 1, reps: 2, velocity_target: "0.9-1.1 m/s", rpe: 8, rest_seconds: 240 },
                { set_number: 2, reps: 2, velocity_target: "0.9-1.1 m/s", rpe: 8, rest_seconds: 240 },
                { set_number: 3, reps: 2, velocity_target: "0.9-1.1 m/s", rpe: 8, rest_seconds: 240 }
              ]
            },
            {
              name: "Box Jump Squat",
              sets: [
                { set_number: 1, reps: 4, velocity_target: "1.0-1.3 m/s", intensity_percent: "35%", rpe: 7, rest_seconds: 180 },
                { set_number: 2, reps: 4, velocity_target: "1.0-1.3 m/s", intensity_percent: "37.5%", rpe: 8, rest_seconds: 180 }
              ]
            },
            {
              name: "Overhead Press",
              sets: [
                { set_number: 1, reps: 5, intensity_percent: "70%", rpe: 8, rest_seconds: 150 },
                { set_number: 2, reps: 5, intensity_percent: "72.5%", rpe: 8, rest_seconds: 150 }
              ]
            }
          ]
        }
      ]
    },
    {
      week_number: 4,
      phase: "Deload",
      workouts: [
        {
          day_number: 1,
          name: "Lower Power - Recovery",
          description: "Deload week - maintain velocity, reduce volume",
          exercises: [
            {
              name: "Power Clean",
              notes: "Light weight, maintain technique and speed",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 4, rest_seconds: 150 },
                { set_number: 2, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 5, rest_seconds: 150 }
              ]
            },
            {
              name: "Back Squat (Speed)",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.8-1.0 m/s", intensity_percent: "50%", rpe: 4, rest_seconds: 120 },
                { set_number: 2, reps: 5, velocity_target: "0.8-1.0 m/s", intensity_percent: "50%", rpe: 4, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 2,
          name: "Upper Power - Recovery",
          description: "Active recovery, light pressing",
          exercises: [
            {
              name: "Push Press",
              sets: [
                { set_number: 1, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 4, rest_seconds: 120 },
                { set_number: 2, reps: 4, velocity_target: "0.8-1.0 m/s", rpe: 5, rest_seconds: 120 }
              ]
            },
            {
              name: "Bench Press (Speed)",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "50%", rpe: 4, rest_seconds: 120 },
                { set_number: 2, reps: 5, velocity_target: "0.7-0.9 m/s", intensity_percent: "50%", rpe: 4, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 3,
          name: "Lower Strength-Speed - Recovery",
          description: "Light technical work",
          exercises: [
            {
              name: "Hang Clean",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 4, rest_seconds: 150 },
                { set_number: 2, reps: 3, velocity_target: "0.9-1.1 m/s", rpe: 5, rest_seconds: 150 }
              ]
            },
            {
              name: "Front Squat",
              sets: [
                { set_number: 1, reps: 5, intensity_percent: "55%", rpe: 4, rest_seconds: 120 },
                { set_number: 2, reps: 5, intensity_percent: "55%", rpe: 4, rest_seconds: 120 }
              ]
            }
          ]
        },
        {
          day_number: 4,
          name: "Full Body Power - Recovery",
          description: "Final recovery session",
          exercises: [
            {
              name: "Push Jerk",
              sets: [
                { set_number: 1, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 4, rest_seconds: 150 },
                { set_number: 2, reps: 3, velocity_target: "0.85-1.05 m/s", rpe: 5, rest_seconds: 150 }
              ]
            },
            {
              name: "Box Jump Squat",
              sets: [
                { set_number: 1, reps: 5, velocity_target: "1.0-1.3 m/s", intensity_percent: "25%", rpe: 4, rest_seconds: 120 }
              ]
            }
          ]
        }
      ]
    }
  ]
};
