"""
Repair script: backend/repair_bookings.py
For every Booking whose schedule_id is null or whose Schedule row is missing,
attach/create a valid Schedule so dashboards stop crashing.
Prints a summary of repaired rows.
"""

import sys
import os
import uuid
from pathlib import Path
from datetime import datetime, date, timedelta, timezone

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal, Base, engine
import app.models  # Ensure models loaded
from app.models import Booking, Schedule, LawyerProfile, User


def repair_bookings():
    print("=" * 60)
    print("BD Legal Guide AI — Repairing Bookings Data")
    print("=" * 60)

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        bookings = db.query(Booking).all()
        total_inspected = len(bookings)
        repaired_count = 0
        repaired_details = []

        today = date.today()

        for idx, booking in enumerate(bookings):
            needs_repair = False
            reason = ""

            if not booking.schedule_id:
                needs_repair = True
                reason = "schedule_id was NULL"
            else:
                schedule = db.query(Schedule).filter(Schedule.id == booking.schedule_id).first()
                if not schedule:
                    needs_repair = True
                    reason = f"referenced schedule {booking.schedule_id} does not exist in DB"

            if needs_repair:
                # Find or assign a lawyer
                lawyer_id = booking.lawyer_id
                if not lawyer_id:
                    fallback_lawyer = db.query(LawyerProfile).first()
                    if fallback_lawyer:
                        lawyer_id = fallback_lawyer.id
                        booking.lawyer_id = lawyer_id

                # Pick a reasonable schedule date:
                # If booking has created_at, use created_at.date() or today
                if booking.created_at:
                    if hasattr(booking.created_at, "date"):
                        s_date = booking.created_at.date()
                    else:
                        s_date = today
                else:
                    s_date = today

                # Create a valid schedule row
                new_schedule_id = uuid.uuid4()
                start_time = "10:00 AM"
                end_time = "10:30 AM"

                new_schedule = Schedule(
                    id=new_schedule_id,
                    lawyer_id=lawyer_id,
                    date=s_date,
                    start_time=start_time,
                    end_time=end_time,
                    is_booked=True,
                )
                db.add(new_schedule)
                db.flush()

                # Attach schedule to booking
                booking.schedule_id = new_schedule_id
                repaired_count += 1
                repaired_details.append({
                    "booking_id": str(booking.id),
                    "reason": reason,
                    "new_schedule_id": str(new_schedule_id),
                    "date": str(s_date),
                    "start_time": start_time,
                })

        db.commit()

        print(f"\n[*] Total bookings inspected: {total_inspected}")
        print(f"[*] Total bookings repaired:  {repaired_count}")

        if repaired_details:
            print("\nDetails of repaired bookings:")
            for item in repaired_details:
                print(f"  - Booking [{item['booking_id']}]: {item['reason']} -> Attached Schedule [{item['new_schedule_id']}] on {item['date']} at {item['start_time']}")
        else:
            print("  All bookings already have valid schedule references. No repairs needed.")

        print("\n" + "=" * 60)
        print("Database repair complete!")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"[!] Error during repair: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    repair_bookings()
