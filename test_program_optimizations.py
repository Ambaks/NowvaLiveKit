#!/usr/bin/env python3
"""
Test script for program generation optimizations.
Tests 2-week, 5-week, and 12-week programs to compare timing improvements.

Run with: conda run -n nowva python3 test_program_optimizations.py
Or activate the conda environment first: conda activate nowva
"""
import asyncio
import sys
import os
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from api.services.program_generator_v2 import generate_program_background
from db.database import SessionLocal
from db.models import ProgramGenerationJob
import uuid


async def test_program_generation():
    """Run three program generation tests sequentially"""

    print("="*80)
    print("PROGRAM GENERATION OPTIMIZATION TEST")
    print("="*80)
    print("\nThis test will generate three programs:")
    print("1. 2-week program (SHORT CAG, batch size=1)")
    print("2. 5-week program (MEDIUM CAG, batch size=3, VBT enabled)")
    print("3. 12-week program (FULL CAG, batch size=4)")
    print("\nEach program will be generated sequentially and saved to the programs folder.")
    print("="*80)

    # Test user ID (you can replace with actual user ID)
    test_user_id = "702a82ef-5915-4433-9f01-9a473e39aaf4"  # From your previous tests

    # Test configurations
    tests = [
        {
            "name": "2-Week Short Program",
            "duration_weeks": 2,
            "params": {
                "duration_weeks": 2,
                "height_cm": 180,
                "weight_kg": 80,
                "age": 30,
                "sex": "M",
                "goal_category": "Strength",
                "goal_raw": "Build foundational strength",
                "fitness_level": "Beginner",
                "days_per_week": 3,
                "session_duration": 60,
                "injury_history": "none",
                "specific_sport": "none",
                "has_vbt_capability": False,
                "user_notes": "Keep it simple and focused"
            }
        },
        {
            "name": "5-Week Medium Program (VBT)",
            "duration_weeks": 5,
            "params": {
                "duration_weeks": 5,
                "height_cm": 185,
                "weight_kg": 90,
                "age": 28,
                "sex": "M",
                "goal_category": "Power",
                "goal_raw": "Develop explosive power for Olympic lifts",
                "fitness_level": "Intermediate",
                "days_per_week": 4,
                "session_duration": 75,
                "injury_history": "none",
                "specific_sport": "Olympic Weightlifting",
                "has_vbt_capability": True,
                "user_notes": "Focus on velocity-based training for Olympic lifts"
            }
        },
        {
            "name": "12-Week Long Program",
            "duration_weeks": 12,
            "params": {
                "duration_weeks": 12,
                "height_cm": 175,
                "weight_kg": 85,
                "age": 35,
                "sex": "M",
                "goal_category": "Hypertrophy",
                "goal_raw": "Build muscle mass and strength over 12 weeks",
                "fitness_level": "Advanced",
                "days_per_week": 5,
                "session_duration": 90,
                "injury_history": "minor lower back issues",
                "specific_sport": "Bodybuilding",
                "has_vbt_capability": False,
                "user_notes": "Include proper deload weeks and progressive overload"
            }
        }
    ]

    results = []

    for i, test_config in enumerate(tests, 1):
        print(f"\n{'='*80}")
        print(f"TEST {i}/3: {test_config['name']}")
        print(f"Duration: {test_config['duration_weeks']} weeks")
        print(f"VBT Enabled: {test_config['params']['has_vbt_capability']}")
        print(f"{'='*80}\n")

        # Create a job ID for this test
        job_id = str(uuid.uuid4())

        # Create job record in database
        db = SessionLocal()
        try:
            job = ProgramGenerationJob(
                id=job_id,
                user_id=test_user_id,
                status="pending",
                progress=0
            )
            db.add(job)
            db.commit()
            print(f"✅ Created job: {job_id}\n")
        except Exception as e:
            print(f"❌ Error creating job: {e}")
            db.rollback()
            continue
        finally:
            db.close()

        # Start timing
        test_start = time.time()

        # Generate the program
        try:
            await generate_program_background(
                job_id=job_id,
                user_id=test_user_id,
                params=test_config['params']
            )

            test_elapsed = time.time() - test_start

            print(f"\n{'='*80}")
            print(f"✅ TEST {i} COMPLETED: {test_config['name']}")
            print(f"Total time: {test_elapsed:.2f}s ({test_elapsed/60:.2f} minutes)")
            print(f"Time per week: {test_elapsed/test_config['duration_weeks']:.2f}s")
            print(f"{'='*80}\n")

            results.append({
                "name": test_config['name'],
                "duration": test_config['duration_weeks'],
                "time": test_elapsed,
                "time_per_week": test_elapsed/test_config['duration_weeks'],
                "vbt": test_config['params']['has_vbt_capability']
            })

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ TEST {i} FAILED: {test_config['name']}")
            print(f"Error: {e}")
            print(f"{'='*80}\n")
            import traceback
            traceback.print_exc()
            continue

        # Brief pause between tests
        if i < len(tests):
            print(f"\n⏳ Waiting 5 seconds before next test...\n")
            await asyncio.sleep(5)

    # Print summary
    print("\n" + "="*80)
    print("OPTIMIZATION TEST SUMMARY")
    print("="*80)

    if results:
        print("\nResults:")
        print("-" * 80)
        for r in results:
            vbt_label = " (VBT)" if r['vbt'] else ""
            print(f"{r['name']}{vbt_label}:")
            print(f"  Duration: {r['duration']} weeks")
            print(f"  Total time: {r['time']:.2f}s ({r['time']/60:.2f} minutes)")
            print(f"  Time per week: {r['time_per_week']:.2f}s")
            print()

        print("-" * 80)
        print("\nExpected Improvements:")
        print("- 2-week program: Should be ~60-90s total (vs ~400s before)")
        print("- 5-week program: Should be ~150-250s total (vs ~500s before)")
        print("- 12-week program: Should be ~400-600s total (similar to before)")
        print()
        print("Key Optimizations:")
        print("✅ Dynamic batch sizing (1, 3, 4 weeks based on program length)")
        print("✅ Tiered CAG knowledge (short, medium, full)")
        print("✅ Simplified prompts for shorter programs")
        print("✅ VBT only when explicitly enabled")
        print()

        # Calculate efficiency
        if len(results) >= 2:
            short_efficiency = results[0]['time_per_week']
            medium_efficiency = results[1]['time_per_week']

            print(f"Efficiency Analysis:")
            print(f"- 2-week: {short_efficiency:.2f}s per week")
            print(f"- 5-week: {medium_efficiency:.2f}s per week")
            if len(results) >= 3:
                long_efficiency = results[2]['time_per_week']
                print(f"- 12-week: {long_efficiency:.2f}s per week")
                print(f"\nSpeed improvement (2-week vs 12-week): {long_efficiency/short_efficiency:.2f}x faster per week")

    else:
        print("\n❌ No successful tests completed")

    print("="*80)
    print("\nCheck the 'programs' folder for generated markdown files.")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_program_generation())
