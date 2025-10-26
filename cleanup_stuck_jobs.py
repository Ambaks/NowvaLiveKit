"""
Cleanup script to mark stuck jobs as failed
Run this when you have jobs stuck in 'in_progress' status after server restarts
"""
import sys
sys.path.insert(0, 'src')

from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

def cleanup_stuck_jobs(hours_threshold=1):
    """
    Mark jobs as failed if they've been in_progress for more than X hours

    Args:
        hours_threshold: How many hours before considering a job stuck (default: 1)
    """
    engine = create_engine(os.getenv('DATABASE_URL'))

    cutoff_time = datetime.utcnow() - timedelta(hours=hours_threshold)

    with engine.connect() as conn:
        # First, find stuck jobs
        result = conn.execute(text("""
            SELECT id, progress, created_at, started_at
            FROM program_generation_jobs
            WHERE status = 'in_progress'
            AND (started_at < :cutoff OR (created_at < :cutoff AND started_at IS NULL))
            ORDER BY created_at DESC
        """), {"cutoff": cutoff_time})

        stuck_jobs = list(result)

        if not stuck_jobs:
            print("No stuck jobs found!")
            return

        print(f"Found {len(stuck_jobs)} stuck jobs (older than {hours_threshold} hour(s)):")
        print("=" * 80)
        for job in stuck_jobs:
            print(f"  ID: {str(job[0])[:8]}... | Progress: {job[1]}% | Started: {job[3]}")

        print("\n" + "=" * 80)
        response = input(f"\nMark all {len(stuck_jobs)} jobs as FAILED? (yes/no): ")

        if response.lower() != 'yes':
            print("Cancelled.")
            return

        # Mark them as failed
        result = conn.execute(text("""
            UPDATE program_generation_jobs
            SET status = 'failed',
                error_message = 'Job terminated - server was restarted while job was running',
                completed_at = NOW()
            WHERE status = 'in_progress'
            AND (started_at < :cutoff OR (created_at < :cutoff AND started_at IS NULL))
        """), {"cutoff": cutoff_time})

        conn.commit()

        print(f"\n✅ Marked {result.rowcount} jobs as failed")
        print("\nThese jobs can now be retried if needed.")

if __name__ == "__main__":
    cleanup_stuck_jobs(hours_threshold=1)
