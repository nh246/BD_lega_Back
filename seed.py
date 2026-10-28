"""
BD Legal Guide AI - Idempotent Database Seeder
Wraps lawyer-schedule seed in an idempotent SELECT ... WHERE lawyer_id = ... AND date = ... check
so re-seeding never generates duplicate meeting slots.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, date, timedelta

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal, Base, engine
from run_migration import run_migration
from app.seed import seed_database


def run_seed():
    print("[*] Starting idempotent seed process...")
    # First ensure schema and migrations are in place
    run_migration()

    db = SessionLocal()
    try:
        # Run standard seed
        seed_database()
        print("[*] Base seed complete.")

        # Ensure future availability schedules exist idempotently for demo lawyers
        from app.models import LawyerProfile, Schedule
        lawyers = db.query(LawyerProfile).all()
        today = date.today()

        slot_templates = [
            ("10:00 AM", "10:30 AM"),
            ("11:30 AM", "12:00 PM"),
            ("02:00 PM", "02:30 PM"),
            ("03:30 PM", "04:00 PM"),
        ]

        slots_created = 0
        for lawyer in lawyers:
            for day_offset in range(1, 8):
                slot_date = today + timedelta(days=day_offset)
                # Idempotency check: WHERE lawyer_id = ... AND date = ...
                existing_for_day = (
                    db.query(Schedule)
                    .filter(
                        Schedule.lawyer_id == lawyer.id,
                        Schedule.date == slot_date,
                    )
                    .all()
                )
                existing_times = {s.start_time for s in existing_for_day}

                for stime, etime in slot_templates:
                    if stime not in existing_times:
                        import uuid
                        new_slot = Schedule(
                            id=uuid.uuid4(),
                            lawyer_id=lawyer.id,
                            date=slot_date,
                            start_time=stime,
                            end_time=etime,
                            is_booked=False,
                        )
                        db.add(new_slot)
                        slots_created += 1

        db.commit()
        if slots_created > 0:
            print(f" [+] Ensured {slots_created} upcoming availability slots across lawyers (idempotent).")
        else:
            print(" [.] All lawyer schedule slots already exist. No duplicates created.")

    finally:
        db.close()

    print("[*] Seeding finished successfully!")


if __name__ == "__main__":
    run_seed()
