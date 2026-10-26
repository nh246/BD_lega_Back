import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime, timedelta
from app.core.database import SessionLocal
from app.models import Schedule


def fix_all_schedules():
    db = SessionLocal()
    try:
        schedules = db.query(Schedule).all()
        updated_count = 0
        for s in schedules:
            st = (s.start_time or "").strip()
            et = (s.end_time or "").strip()

            is_bad = False
            if not et or et == st:
                is_bad = True
            elif "(30m)" in et:
                is_bad = True
            elif et.startswith(st) and len(et) > len(st):
                is_bad = True

            if is_bad and st:
                parsed_dt = None
                clean_st = st.replace(".", "").strip()
                for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M"]:
                    try:
                        parsed_dt = datetime.strptime(clean_st, fmt)
                        break
                    except ValueError:
                        continue

                if parsed_dt:
                    new_end_dt = parsed_dt + timedelta(minutes=30)
                    old_st, old_et = s.start_time, s.end_time
                    s.start_time = parsed_dt.strftime("%I:%M %p")
                    s.end_time = new_end_dt.strftime("%I:%M %p")
                    print(f"Updated Schedule {s.id} (Date: {s.date}): '{old_st}' - '{old_et}' -> '{s.start_time}' - '{s.end_time}'")
                    updated_count += 1

        db.commit()
        print(f"\n[OK] Successfully updated {updated_count} schedules.")
    finally:
        db.close()


if __name__ == "__main__":
    fix_all_schedules()
