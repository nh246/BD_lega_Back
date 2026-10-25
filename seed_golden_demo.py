"""
Seed script: Golden Demo State (Chapter 7 Freeze)
File: backend/seed_golden_demo.py

UPSERT (update if exists, create if not) key accounts and test fixtures:
- Admin: admin@bdlegal.ai (Password: Password123!)
- Lawyer 1 (Gold): adv.nusrat@bdlegal.ai (Verified, Gold Badge, Fee: 2500, 5.0 stars)
- Lawyer 2 (Standard): adv.tanvir@bdlegal.ai (Verified, Blue Badge, Fee: 1500, 4.8 stars)
- Lawyer 3 (Pending): adv.pending@bdlegal.ai (Status: pending, for admin demo)
- Client Pro: client.pro@bdlegal.ai (Active Pro Monthly Sub, 14/15 messages used, confirmed booking with Lawyer 1, 2 unread notifs)
- Client Free: client.free@bdlegal.ai (No sub, 5/15 messages used, awaiting_payment booking with Lawyer 2)
"""

import sys
import uuid
from datetime import datetime, timezone, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func

# Ensure utf-8 encoding for Windows terminals
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import (
    User,
    LawyerProfile,
    Schedule,
    Booking,
    Review,
    Notification,
    MonthlyUsage,
    Subscription,
    Plan,
    ProfileAsset,
)
from app.core.plans import ensure_plans_exist

DEMO_PASSWORD = "Password123!"


def get_or_create_user(db: Session, email: str, role: str, name: str, status: str = "active") -> User:
    """Helper to ensure user exists with consistent demo password and role."""
    normalized_email = email.lower().strip()
    hashed_pw = get_password_hash(DEMO_PASSWORD)

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email=normalized_email,
            password_hash=hashed_pw,
            full_name=name,
            role=role,
            status=status,
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"  [+] Created User: {normalized_email} ({role})")
    else:
        user.password_hash = hashed_pw
        user.full_name = name
        user.role = role
        user.status = status
        db.commit()
        db.refresh(user)
        print(f"  [*] Updated User: {normalized_email} ({role})")

    return user


def _ensure_lawyer_avatar(db: Session, user: User, preferred_filename_match: str):
    """Ensure lawyer user has an avatar asset attached."""
    existing_avatar = (
        db.query(ProfileAsset)
        .filter(ProfileAsset.owner_user_id == user.id, ProfileAsset.kind == "avatar")
        .first()
    )
    if existing_avatar:
        return existing_avatar

    # Find a sample avatar to copy file_bytes from
    sample_avatar = (
        db.query(ProfileAsset)
        .filter(ProfileAsset.kind == "avatar", ProfileAsset.filename.ilike(f"%{preferred_filename_match}%"))
        .first()
    )
    if not sample_avatar:
        sample_avatar = (
            db.query(ProfileAsset)
            .filter(ProfileAsset.kind == "avatar")
            .first()
        )

    if sample_avatar:
        new_asset = ProfileAsset(
            id=uuid.uuid4(),
            owner_user_id=user.id,
            kind="avatar",
            filename=sample_avatar.filename,
            mime_type=sample_avatar.mime_type,
            file_bytes=sample_avatar.file_bytes,
            size_bytes=sample_avatar.size_bytes,
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_asset)
        db.commit()
        db.refresh(new_asset)
        print(f"  [+] Attached Avatar Asset ({new_asset.filename}) to {user.email}")
        return new_asset

    return None


def _ensure_lawyer_reviews(db: Session, lawyer: LawyerProfile, target_rating: float, reviewer_user: User):
    """
    Ensure the lawyer has completed bookings and reviews yielding the target average rating.
    - If target_rating == 5.0: 2 reviews with rating 5.
    - If target_rating == 4.8: 5 reviews (four 5-star, one 4-star = 24 / 5 = 4.8).
    """
    existing_reviews = (
        db.query(Review)
        .filter(Review.reviewee_id == lawyer.user_id)
        .all()
    )

    if target_rating == 5.0:
        ratings = [5, 5]
        comments = [
            "Adv. Nusrat provided exceptional clarity on corporate compliance and contract drafting. Highly recommended!",
            "Outstanding service. Very professional, responsive, and punctual video consultation.",
        ]
    elif target_rating == 4.8:
        ratings = [5, 5, 5, 5, 4]
        comments = [
            "Great guidance on land dispute resolution. Thorough knowledge of BD property acts.",
            "Adv. Tanvir explained civil litigation steps in simple terms. Very helpful.",
            "Prompt response and clear advice on documentation required for our case.",
            "Very knowledgeable and attentive advocate. Addressed all our concerns.",
            "Helpful consultation session. Clear action plan provided for court filing.",
        ]
    else:
        ratings = [int(round(target_rating))]
        comments = ["Good consultation."]

    # If already seeded with matching count and exact average, keep them
    if len(existing_reviews) == len(ratings):
        current_avg = sum(r.rating for r in existing_reviews) / len(existing_reviews)
        if round(current_avg, 1) == round(target_rating, 1):
            return

    # Delete existing reviews and their mock completed bookings to reset cleanly
    for r in existing_reviews:
        db.delete(r)
    db.commit()

    # Create past completed schedules & bookings to anchor each review
    base_date = date.today() - timedelta(days=20)
    for idx, (star, comment) in enumerate(zip(ratings, comments)):
        sched_date = base_date + timedelta(days=idx * 3)
        schedule = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer.id,
            date=sched_date,
            start_time="11:00 AM",
            end_time="12:00 PM",
            is_booked=True,
        )
        db.add(schedule)
        db.flush()

        booking = Booking(
            id=uuid.uuid4(),
            user_id=reviewer_user.id,
            lawyer_id=lawyer.id,
            schedule_id=schedule.id,
            status="completed",
            meeting_link="https://meet.google.com/completed-demo",
            meeting_started_at=datetime.now(timezone.utc) - timedelta(days=20 - idx * 3, hours=2),
            meeting_ended_at=datetime.now(timezone.utc) - timedelta(days=20 - idx * 3, hours=1),
            completed_at=datetime.now(timezone.utc) - timedelta(days=20 - idx * 3, hours=1),
            created_at=datetime.now(timezone.utc) - timedelta(days=25 - idx * 3),
        )
        db.add(booking)
        db.flush()

        review = Review(
            id=uuid.uuid4(),
            booking_id=booking.id,
            reviewer_id=reviewer_user.id,
            reviewee_id=lawyer.user_id,
            rating=star,
            comment=comment,
            created_at=datetime.now(timezone.utc) - timedelta(days=20 - idx * 3, minutes=30),
        )
        db.add(review)

    db.commit()
    print(f"  [+] Seeded {len(ratings)} Reviews for {lawyer.name} -> Target Avg: {target_rating} stars")


def ensure_lawyer(
    db: Session,
    email: str,
    name: str,
    is_verified: bool,
    rating: float,
    hourly_rate: int,
    is_gold: bool = False,
    bar_council_id: str = None,
    district: str = "Dhaka",
    specialization: str = None,
    reviewer_user: User = None,
) -> LawyerProfile:
    """Helper to ensure lawyer profile and stats exist."""
    user = get_or_create_user(db, email, "lawyer", name, status="active")

    verif_status = "approved" if is_verified else "pending"
    default_bar_id = bar_council_id or ("BC-SC-2015-8842" if is_gold else "BC-DH-2019-3321")
    default_spec = specialization or ("Corporate Law & Criminal Defense" if is_gold else "Civil Litigation & Land Disputes")

    profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == user.id).first()
    if not profile:
        profile = LawyerProfile(
            id=uuid.uuid4(),
            user_id=user.id,
            name=name,
            bar_council_id=default_bar_id,
            district=district,
            specialization=default_spec,
            phone="+8801712345678",
            verification_status=verif_status,
            verification_paid=is_gold,
            hourly_rate=hourly_rate,
            years_exp=12 if is_gold else 8,
            languages="Bangla, English",
            payment_methods=[{"provider": "bKash", "number": "01712345678", "type": "personal"}],
            meeting_provider="Google Meet",
            meeting_link="https://meet.google.com/abc-defg-hij",
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        print(f"  [+] Created Lawyer Profile: {name} (Verified: {is_verified}, Gold: {is_gold})")
    else:
        profile.name = name
        profile.bar_council_id = default_bar_id
        profile.district = district
        profile.specialization = default_spec
        profile.verification_status = verif_status
        profile.verification_paid = is_gold
        profile.hourly_rate = hourly_rate
        profile.payment_methods = [{"provider": "bKash", "number": "01712345678", "type": "personal"}]
        profile.meeting_provider = "Google Meet"
        profile.meeting_link = "https://meet.google.com/abc-defg-hij"
        db.commit()
        db.refresh(profile)
        print(f"  [*] Updated Lawyer Profile: {name} (Verified: {is_verified}, Gold: {is_gold})")

    # 5) Ensure avatar asset is attached
    filename_hint = "Nusrat" if "nusrat" in email else ("Tanvir" if "tanvir" in email else "avatar")
    _ensure_lawyer_avatar(db, user, filename_hint)

    # Setup reviews for verified lawyers
    if is_verified and rating is not None and reviewer_user:
        _ensure_lawyer_reviews(db, profile, rating, reviewer_user)

    # Ensure 2 future open slots for appointment booking
    today = date.today()
    for offset, (stime, etime) in [(1, ("10:00 AM", "11:00 AM")), (2, ("03:00 PM", "04:00 PM"))]:
        slot_date = today + timedelta(days=offset)
        existing_slot = (
            db.query(Schedule)
            .filter(
                Schedule.lawyer_id == profile.id,
                Schedule.date == slot_date,
                Schedule.start_time == stime,
            )
            .first()
        )
        if not existing_slot:
            open_slot = Schedule(
                id=uuid.uuid4(),
                lawyer_id=profile.id,
                date=slot_date,
                start_time=stime,
                end_time=etime,
                is_booked=False,
            )
            db.add(open_slot)
    db.commit()

    return profile


def run_seed():
    db = SessionLocal()
    try:
        print("\n" + "=" * 60)
        print("   SEEDING GOLDEN DEMO STATE FOR CHAPTER 7 SCREENSHOTS")
        print("=" * 60 + "\n")

        # 0. Ensure Plans exist
        ensure_plans_exist(db)
        pro_plan = db.query(Plan).filter(Plan.code.in_(["user_pro_monthly", "user_pro"])).first()

        # Step 1: Admin
        print("\n--- 1. Admin Account ---")
        admin = get_or_create_user(db, "admin@bdlegal.ai", "admin", "System Administrator", status="active")

        # Step 2: Clients (Free & Pro)
        print("\n--- 2. Client Accounts ---")
        client_pro = get_or_create_user(db, "client.pro@bdlegal.ai", "user", "Karim Chowdhury (Pro)", status="active")
        client_free = get_or_create_user(db, "client.free@bdlegal.ai", "user", "Rahim Ahmed (Free)", status="active")

        # Step 3: Lawyers
        print("\n--- 3. Lawyer Accounts ---")
        # Lawyer 1 (Gold): adv.nusrat@bdlegal.ai (Verified, Gold Badge, Fee: 2500, 5.0 stars)
        lawyer_1 = ensure_lawyer(
            db=db,
            email="adv.nusrat@bdlegal.ai",
            name="Adv. Nusrat Jahan",
            is_verified=True,
            rating=5.0,
            hourly_rate=2500,
            is_gold=True,
            bar_council_id="BC-SC-2015-8842",
            district="Dhaka",
            specialization="Corporate Law & Criminal Defense",
            reviewer_user=client_free,
        )

        # Lawyer 2 (Standard): adv.tanvir@bdlegal.ai (Verified, Blue Badge, Fee: 1500, 4.8 stars)
        lawyer_2 = ensure_lawyer(
            db=db,
            email="adv.tanvir@bdlegal.ai",
            name="Adv. Tanvir Hasan",
            is_verified=True,
            rating=4.8,
            hourly_rate=1500,
            is_gold=False,
            bar_council_id="BC-DH-2019-3321",
            district="Dhaka",
            specialization="Civil Litigation & Land Disputes",
            reviewer_user=client_free,
        )

        # Lawyer 3 (Pending): adv.pending@bdlegal.ai (Status: pending, for admin demo)
        lawyer_3 = ensure_lawyer(
            db=db,
            email="adv.pending@bdlegal.ai",
            name="Adv. Kazi Mahmudul",
            is_verified=False,
            rating=None,
            hourly_rate=1800,
            is_gold=False,
            bar_council_id="BC-DH-2023-9911",
            district="Chittagong",
            specialization="Family Law & Property",
            reviewer_user=None,
        )

        # Step 4: Client Pro State & Fixtures
        print("\n--- 4. Client Pro State (Sub, Messages, Booking, Notifs) ---")
        # 4a. Active Pro Monthly Subscription
        if pro_plan:
            active_sub = (
                db.query(Subscription)
                .filter(Subscription.user_id == client_pro.id)
                .first()
            )
            if not active_sub:
                active_sub = Subscription(
                    id=uuid.uuid4(),
                    user_id=client_pro.id,
                    plan_id=pro_plan.id,
                    status="active",
                    started_at=datetime.now(timezone.utc) - timedelta(days=5),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=25),
                )
                db.add(active_sub)
            else:
                active_sub.plan_id = pro_plan.id
                active_sub.status = "active"
                active_sub.expires_at = datetime.now(timezone.utc) + timedelta(days=25)
            db.commit()
            print("  [+] Confirmed Active Pro Monthly Subscription for client.pro@bdlegal.ai")

        # 4b. 14/15 messages used this month
        now_utc = datetime.now(timezone.utc)
        usage_pro = (
            db.query(MonthlyUsage)
            .filter(
                MonthlyUsage.user_id == client_pro.id,
                MonthlyUsage.year == now_utc.year,
                MonthlyUsage.month == now_utc.month,
            )
            .first()
        )
        if not usage_pro:
            usage_pro = MonthlyUsage(
                id=uuid.uuid4(),
                user_id=client_pro.id,
                year=now_utc.year,
                month=now_utc.month,
                messages_used=14,
            )
            db.add(usage_pro)
        else:
            usage_pro.messages_used = 14
        db.commit()
        print("  [+] Confirmed 14/15 Messages Used for client.pro@bdlegal.ai")

        # 4c. Confirmed Booking with Lawyer 1 (Meeting Link: "https://meet.google.com/demo")
        booking_pro = (
            db.query(Booking)
            .filter(Booking.user_id == client_pro.id, Booking.lawyer_id == lawyer_1.id)
            .first()
        )
        if booking_pro:
            booking_pro.status = "confirmed"
            booking_pro.meeting_link = "https://meet.google.com/demo"
            if booking_pro.schedule:
                booking_pro.schedule.is_booked = True
        else:
            tomorrow = date.today() + timedelta(days=1)
            sched_pro = Schedule(
                id=uuid.uuid4(),
                lawyer_id=lawyer_1.id,
                date=tomorrow,
                start_time="04:00 PM",
                end_time="05:00 PM",
                is_booked=True,
            )
            db.add(sched_pro)
            db.flush()

            booking_pro = Booking(
                id=uuid.uuid4(),
                user_id=client_pro.id,
                lawyer_id=lawyer_1.id,
                schedule_id=sched_pro.id,
                status="confirmed",
                meeting_link="https://meet.google.com/demo",
                created_at=datetime.now(timezone.utc) - timedelta(hours=3),
            )
            db.add(booking_pro)
        db.commit()
        print("  [+] Confirmed Booking Created/Updated: client.pro -> Adv. Nusrat Jahan (https://meet.google.com/demo)")

        # 4d. 2 UNREAD Notifications ("Payment Confirmed", "New Review")
        db.query(Notification).filter(Notification.user_id == client_pro.id).delete()
        notif1 = Notification(
            id=uuid.uuid4(),
            user_id=client_pro.id,
            type="payment_confirmed",
            title="Payment Confirmed",
            message="Your consultation payment with Adv. Nusrat Jahan was approved. Meeting link is ready.",
            link="/client/bookings",
            is_read=False,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        notif2 = Notification(
            id=uuid.uuid4(),
            user_id=client_pro.id,
            type="review_received",
            title="New Review",
            message="Adv. Nusrat Jahan left feedback regarding your recent corporate legal consultation.",
            link="/client/bookings",
            is_read=False,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        db.add(notif1)
        db.add(notif2)
        db.commit()
        print("  [+] Created 2 Unread Notifications for client.pro@bdlegal.ai")

        # Step 5: Client Free State & Fixtures
        print("\n--- 5. Client Free State (Usage, Awaiting Payment Booking) ---")
        # Expire any active subscriptions
        for s in db.query(Subscription).filter(Subscription.user_id == client_free.id).all():
            s.status = "expired"

        # 5/15 messages used
        usage_free = (
            db.query(MonthlyUsage)
            .filter(
                MonthlyUsage.user_id == client_free.id,
                MonthlyUsage.year == now_utc.year,
                MonthlyUsage.month == now_utc.month,
            )
            .first()
        )
        if not usage_free:
            usage_free = MonthlyUsage(
                id=uuid.uuid4(),
                user_id=client_free.id,
                year=now_utc.year,
                month=now_utc.month,
                messages_used=5,
            )
            db.add(usage_free)
        else:
            usage_free.messages_used = 5
        db.commit()
        print("  [+] Confirmed 5/15 Messages Used for client.free@bdlegal.ai")

        # Awaiting Payment Booking with Lawyer 2
        booking_free = (
            db.query(Booking)
            .filter(Booking.user_id == client_free.id, Booking.lawyer_id == lawyer_2.id)
            .first()
        )
        if booking_free:
            booking_free.status = "awaiting_payment"
            if booking_free.schedule:
                booking_free.schedule.is_booked = True
        else:
            day_after = date.today() + timedelta(days=3)
            sched_free = Schedule(
                id=uuid.uuid4(),
                lawyer_id=lawyer_2.id,
                date=day_after,
                start_time="02:00 PM",
                end_time="03:00 PM",
                is_booked=True,
            )
            db.add(sched_free)
            db.flush()

            booking_free = Booking(
                id=uuid.uuid4(),
                user_id=client_free.id,
                lawyer_id=lawyer_2.id,
                schedule_id=sched_free.id,
                status="awaiting_payment",
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
            db.add(booking_free)
        db.commit()
        print("  [+] Awaiting Payment Booking Created/Updated: client.free -> Adv. Tanvir Hasan")

        # Step 6: Print Summary of Golden State
        print("\n" + "=" * 60)
        print("         GOLDEN DEMO STATE SUMMARY (READY FOR CHAPTER 7)")
        print("=" * 60)

        # Query stats to print
        l1_reviews = db.query(func.avg(Review.rating), func.count(Review.id)).filter(Review.reviewee_id == lawyer_1.user_id).first()
        l2_reviews = db.query(func.avg(Review.rating), func.count(Review.id)).filter(Review.reviewee_id == lawyer_2.user_id).first()
        pro_notifs = db.query(Notification).filter(Notification.user_id == client_pro.id, Notification.is_read == False).count()

        summary_rows = [
            ("Admin", "admin@bdlegal.ai", "Password123!", "Admin", "Full platform access, review pending lawyers"),
            ("Lawyer 1 (Gold)", "adv.nusrat@bdlegal.ai", "Password123!", "Verified Gold", f"Fee: 2500 BDT, {round(float(l1_reviews[0] or 5), 1)} stars ({l1_reviews[1]} reviews)"),
            ("Lawyer 2 (Standard)", "adv.tanvir@bdlegal.ai", "Password123!", "Verified Blue", f"Fee: 1500 BDT, {round(float(l2_reviews[0] or 4.8), 1)} stars ({l2_reviews[1]} reviews)"),
            ("Lawyer 3 (Pending)", "adv.pending@bdlegal.ai", "Password123!", "Pending Review", "Hidden from public directory; visible in Admin review"),
            ("Client Pro", "client.pro@bdlegal.ai", "Password123!", "Pro Monthly", f"14/15 msgs used, Confirmed Booking, {pro_notifs} Unread Notifs"),
            ("Client Free", "client.free@bdlegal.ai", "Password123!", "Free Tier", "5/15 msgs used, Awaiting Payment Booking"),
        ]

        print(f"{'Role / Account':<22} | {'Email':<24} | {'Password':<14} | {'Status / Details'}")
        print("-" * 85)
        for role, email, pw, badge, details in summary_rows:
            print(f"{role:<22} | {email:<24} | {pw:<14} | {badge} ({details})")
        print("=" * 85 + "\n")

    except Exception as e:
        db.rollback()
        print(f"\n[!] Error seeding golden demo: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
