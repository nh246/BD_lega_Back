"""
One-time database cleanup script for BD Legal Guide AI.

TASK 1:
- Strips display name suffixes: ' (Free User)', ' (Pro User)', ' (Verified Pro)', ' (Free Lawyer)'
  from users.full_name and lawyer_profiles.name.
- Does NOT delete any user, subscription, or payment rows.

TASK 2:
- Finds 'Advocate Test Profile' and converts it into the PENDING test fixture:
  name: 'Adv. Mahmudul Hasan'
  bar_council_id: 'BD-BAR-2020-1188'
  district: 'Dhaka'
  specialization: 'Family Law & Property'
  contact (phone): '+8801733445566'
  verification_status: 'pending'
  email: 'pending_lawyer@bdlegal.ai'
"""

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import User, LawyerProfile

SUFFIXES = [
    " (Free User)",
    " (Pro User)",
    " (Verified Pro)",
    " (Free Lawyer)",
]


def run_cleanup():
    db = SessionLocal()
    try:
        print("=== Running One-Time DB Cleanup ===")

        # 1. Clean users.full_name
        users = db.query(User).all()
        cleaned_users_count = 0
        for u in users:
            if not u.full_name:
                continue
            orig = u.full_name
            for s in SUFFIXES:
                if s in u.full_name:
                    u.full_name = u.full_name.replace(s, "").strip()
            if u.full_name != orig:
                print(f" [User Name Cleaned] {orig} -> {u.full_name} ({u.email})")
                cleaned_users_count += 1

        # 2. Clean lawyer_profiles.name
        profiles = db.query(LawyerProfile).all()
        cleaned_profiles_count = 0
        for lp in profiles:
            if not lp.name:
                continue
            orig = lp.name
            for s in SUFFIXES:
                if s in lp.name:
                    lp.name = lp.name.replace(s, "").strip()
            if lp.name != orig:
                print(f" [LawyerProfile Name Cleaned] {orig} -> {lp.name}")
                cleaned_profiles_count += 1

        # 3. Convert 'Advocate Test Profile' to PENDING test fixture
        adv_test = (
            db.query(LawyerProfile)
            .filter(
                (LawyerProfile.name == "Advocate Test Profile")
                | (LawyerProfile.bar_council_id == "BD-BAR-2020-1188")
            )
            .first()
        )

        if adv_test:
            print(f"\nFound target lawyer profile for pending fixture: {adv_test.name} (id: {adv_test.id})")
            adv_test.name = "Adv. Mahmudul Hasan"
            adv_test.bar_council_id = "BD-BAR-2020-1188"
            adv_test.district = "Dhaka"
            adv_test.specialization = "Family Law & Property"
            adv_test.phone = "+8801733445566"
            adv_test.verification_status = "pending"
            adv_test.verification_paid = False

            # Update associated user
            u = db.query(User).filter(User.id == adv_test.user_id).first()
            if u:
                u.full_name = "Adv. Mahmudul Hasan"
                u.email = "pending_lawyer@bdlegal.ai"
                u.password_hash = get_password_hash("Password123!")
                print(f"Updated associated user to: {u.full_name} ({u.email})")
        else:
            print("\n'Advocate Test Profile' not found directly. Checking for pending_lawyer@bdlegal.ai...")
            pending_user = db.query(User).filter(User.email == "pending_lawyer@bdlegal.ai").first()
            if pending_user:
                p_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == pending_user.id).first()
                if p_prof:
                    p_prof.name = "Adv. Mahmudul Hasan"
                    p_prof.bar_council_id = "BD-BAR-2020-1188"
                    p_prof.district = "Dhaka"
                    p_prof.specialization = "Family Law & Property"
                    p_prof.phone = "+8801733445566"
                    p_prof.verification_status = "pending"
                    p_prof.verification_paid = False
                    print(f"Updated profile for pending_lawyer@bdlegal.ai: {p_prof.name}")

        db.commit()
        print("\n=== Cleanup Complete ===")
        print(f"Cleaned {cleaned_users_count} users and {cleaned_profiles_count} lawyer profiles.")

    except Exception as e:
        db.rollback()
        print(f"Error during cleanup: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_cleanup()
