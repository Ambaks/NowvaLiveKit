"""
Test script for schedule undo functionality.
Tests basic undo/redo operations on schedule changes.
"""
import sys
sys.path.insert(0, 'src')

from datetime import date, timedelta
from db.database import SessionLocal
from db.models import User, Schedule, Workout, UserGeneratedProgram
from db.schedule_utils import move_workout, skip_workout, swap_workouts
from db.schedule_history import (
    get_recent_changes,
    undo_last_change,
    format_change_for_display
)


def test_undo_move_workout():
    """Test undo on move_workout operation"""
    print("\n=== Testing Undo Move Workout ===")

    db = SessionLocal()
    try:
        # Find a user with schedules
        user = db.query(User).first()
        if not user:
            print("✗ No users found in database")
            return False

        print(f"✓ Testing with user: {user.name} ({user.id})")

        # Find first two non-completed schedules
        schedules = db.query(Schedule).filter(
            Schedule.user_id == user.id,
            Schedule.completed == False,
            Schedule.skipped == False
        ).limit(2).all()

        if len(schedules) < 2:
            print("✗ Need at least 2 uncompleted schedules")
            return False

        schedule1 = schedules[0]
        original_date = schedule1.scheduled_date
        new_date = original_date + timedelta(days=7)

        print(f"✓ Found schedule {schedule1.id} on {original_date}")
        print(f"  Moving to {new_date}")

        # Move the workout
        success, error = move_workout(db, schedule1.id, new_date)
        if not success:
            print(f"✗ Move failed: {error}")
            return False

        print(f"✓ Workout moved successfully")

        # Verify it moved
        db.refresh(schedule1)
        if schedule1.scheduled_date != new_date:
            print(f"✗ Workout date didn't change: {schedule1.scheduled_date}")
            return False

        print(f"✓ Verified new date: {schedule1.scheduled_date}")

        # Check history
        changes = get_recent_changes(db, str(user.id), limit=1)
        if not changes:
            print("✗ No history entry created")
            return False

        latest_change = changes[0]
        print(f"✓ History entry created: {latest_change.description}")

        # Undo the move
        print("\n  Attempting undo...")
        success, error = undo_last_change(db, str(user.id))
        if not success:
            print(f"✗ Undo failed: {error}")
            return False

        print(f"✓ Undo successful")

        # Verify it was undone
        db.refresh(schedule1)
        if schedule1.scheduled_date != original_date:
            print(f"✗ Workout not restored to original date: {schedule1.scheduled_date} (expected {original_date})")
            return False

        print(f"✓ Workout restored to original date: {schedule1.scheduled_date}")

        # Verify history shows undo
        changes = get_recent_changes(db, str(user.id), limit=2)
        undo_entry = changes[0]
        if undo_entry.change_type != "undo":
            print(f"✗ Latest history entry is not 'undo': {undo_entry.change_type}")
            return False

        print(f"✓ Undo recorded in history: {undo_entry.description}")

        print("\n✓✓✓ TEST PASSED: Move and undo work correctly! ✓✓✓")
        return True

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_undo_skip_workout():
    """Test undo on skip_workout operation"""
    print("\n=== Testing Undo Skip Workout ===")

    db = SessionLocal()
    try:
        # Find a user with schedules
        user = db.query(User).first()
        if not user:
            print("✗ No users found in database")
            return False

        print(f"✓ Testing with user: {user.name} ({user.id})")

        # Find a non-completed, non-skipped schedule
        schedule = db.query(Schedule).filter(
            Schedule.user_id == user.id,
            Schedule.completed == False,
            Schedule.skipped == False
        ).first()

        if not schedule:
            print("✗ No available schedules to test with")
            return False

        print(f"✓ Found schedule {schedule.id}")
        print(f"  Original skipped status: {schedule.skipped}")

        # Skip the workout
        success, error = skip_workout(db, schedule.id, reason="Testing undo functionality")
        if not success:
            print(f"✗ Skip failed: {error}")
            return False

        print(f"✓ Workout skipped successfully")

        # Verify it's skipped
        db.refresh(schedule)
        if not schedule.skipped:
            print(f"✗ Workout not marked as skipped")
            return False

        print(f"✓ Verified skipped status: {schedule.skipped}")
        print(f"  Skip reason: {schedule.skip_reason}")

        # Undo the skip
        print("\n  Attempting undo...")
        success, error = undo_last_change(db, str(user.id))
        if not success:
            print(f"✗ Undo failed: {error}")
            return False

        print(f"✓ Undo successful")

        # Verify it was undone
        db.refresh(schedule)
        if schedule.skipped:
            print(f"✗ Workout still marked as skipped")
            return False

        print(f"✓ Workout restored to not skipped: {schedule.skipped}")

        print("\n✓✓✓ TEST PASSED: Skip and undo work correctly! ✓✓✓")
        return True

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_view_history():
    """Test viewing change history"""
    print("\n=== Testing View Change History ===")

    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            print("✗ No users found")
            return False

        changes = get_recent_changes(db, str(user.id), limit=5)
        print(f"\n✓ Found {len(changes)} recent changes:")

        for i, change in enumerate(changes, 1):
            formatted = format_change_for_display(change)
            print(f"  {i}. {formatted}")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("SCHEDULE UNDO SYSTEM TESTS")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Move Workout Undo", test_undo_move_workout()))
    results.append(("Skip Workout Undo", test_undo_skip_workout()))
    results.append(("View History", test_view_history()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")
    print("=" * 60)

    sys.exit(0 if passed == total else 1)
