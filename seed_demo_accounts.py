"""
Seed demo accounts for BD Legal Guide AI.
Creates 2 user accounts and 2 lawyer accounts:
1. free_user@bdlegal.ai (Citizen - Free Plan)
2. pro_user@bdlegal.ai  (Citizen - Pro Plan)
3. free_lawyer@bdlegal.ai (Advocate - Free / Basic Profile)
4. pro_lawyer@bdlegal.ai  (Advocate - Bar Council Verified Pro)

Password for all accounts: Password123!
Idempotent: safe to run multiple times.
"""

from datetime import datetime, timedelta
import uuid
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import User, LawyerProfile, Schedule, Subscription, Plan


DEMO_PASSWORD = "Password123!"

DEMO_ACCOUNTS = [
    {
        "email": "free_user@bdlegal.ai",
        "full_name": "Rahim Ahmed (Free User)",
        "role": "user",
        "is_pro": False,
    },
    {
        "email": "pro_user@bdlegal.ai",
        "full_name": "Karim Chowdhury (Pro User)",
        "role": "user",
        "is_pro": True,
    },
    {
        "email": "free_lawyer@bdlegal.ai",
        "full_name": "Adv. Tanvir Hasan (Free Lawyer)",
        "role": "lawyer",
        "is_pro": False,
        "bar_id": "BC-DH-2019-3321",
        "specialization": "Civil Litigation & Land Disputes",
        "district": "Dhaka",
        "phone": "+8801711002233",
    },
    {
        "email": "pro_lawyer@bdlegal.ai",
        "full_name": "Adv. Nusrat Jahan (Verified Pro)",
        "role": "lawyer",
        "is_pro": True,
        "bar_id": "BC-SC-2015-8842",
        "specialization": "Corporate Law & Criminal Defense",
        "district": "Dhaka",
        "phone": "+8801811445566",
    },
]


def seed_demo_accounts():
    db = SessionLocal()
    try:
        print("=== Seeding BD Legal Guide AI Demo Accounts ===")

        # 1. Fetch or create plans
        user_free_plan = db.query(Plan).filter(Plan.code == "user_free").first()
        user_pro_plan = db.query(Plan).filter(Plan.code == "user_pro").first()
        lawyer_basic_plan = db.query(Plan).filter(Plan.code == "lawyer_basic").first()
        lawyer_verified_plan = db.query(Plan).filter(Plan.code == "lawyer_verified").first()

        if not user_pro_plan:
            user_pro_plan = Plan(
                id=uuid.uuid4(),
                code="user_pro",
                name="Pro Plan",
                price_monthly=299.0,
                features=[
                    "Unlimited AI chat queries and saved sessions",
                    "Extended AI memory (20-turn context vs 5)",
                    "AI confidence score on every answer",
                    "Direct messaging with verified lawyers",
                    "Priority handling of consultation requests",
                ],
            )
            db.add(user_pro_plan)
            db.commit()

        if not lawyer_verified_plan:
            lawyer_verified_plan = Plan(
                id=uuid.uuid4(),
                code="lawyer_verified",
                name="Lawyer Verified Badge",
                price_monthly=999.0,
                features=[
                    "Official Bar Council verified gold badge",
                    "Priority top placement in lawyer directory",
                    "Direct client messaging channel",
                    "Unlimited consultation bookings",
                ],
            )
            db.add(lawyer_verified_plan)
            db.commit()

        # 2. Upsert each account
        hashed_pw = get_password_hash(DEMO_PASSWORD)

        for acc in DEMO_ACCOUNTS:
            email = acc["email"]
            user = db.query(User).filter(User.email == email).first()

            if not user:
                user = User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=hashed_pw,
                    full_name=acc["full_name"],
                    role=acc["role"],
                    status="active",
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"[CREATED] User: {email} ({acc['role']})")
            else:
                user.password_hash = hashed_pw
                user.full_name = acc["full_name"]
                user.role = acc["role"]
                user.status = "active"
                db.commit()
                print(f"[UPDATED] User: {email} ({acc['role']})")

            # Handle subscriptions for Citizen accounts
            if acc["role"] == "user":
                # Clear existing subscriptions if free
                if not acc["is_pro"]:
                    # Ensure no active user_pro subscription
                    active_subs = (
                        db.query(Subscription)
                        .filter(
                            Subscription.user_id == user.id,
                            Subscription.status == "active",
                        )
                        .all()
                    )
                    for s in active_subs:
                        s.status = "expired"
                    db.commit()
                    print(f" -> Free plan confirmed for {email}")
                else:
                    # Give active user_pro subscription for 1 year
                    existing_pro = (
                        db.query(Subscription)
                        .filter(
                            Subscription.user_id == user.id,
                            Subscription.plan_id == user_pro_plan.id,
                            Subscription.status == "active",
                        )
                        .first()
                    )
                    if not existing_pro:
                        new_sub = Subscription(
                            id=uuid.uuid4(),
                            user_id=user.id,
                            plan_id=user_pro_plan.id,
                            status="active",
                            started_at=datetime.utcnow(),
                            expires_at=datetime.utcnow() + timedelta(days=365),
                        )
                        db.add(new_sub)
                        db.commit()
                    else:
                        existing_pro.expires_at = datetime.utcnow() + timedelta(days=365)
                        db.commit()
                    print(f" -> Active Pro subscription confirmed for {email}")

            # Handle LawyerProfile & Schedules for Lawyer accounts
            if acc["role"] == "lawyer":
                profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == user.id).first()
                if not profile:
                    profile = LawyerProfile(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        name=acc["full_name"],
                        bar_council_id=acc["bar_id"],
                        district=acc["district"],
                        specialization=acc["specialization"],
                        phone=acc["phone"],
                        verification_status="approved",
                        verification_paid=acc["is_pro"],
                    )
                    db.add(profile)
                    db.commit()
                    db.refresh(profile)
                    print(f" -> Created LawyerProfile for {email} (verified_paid={acc['is_pro']})")
                else:
                    profile.name = acc["full_name"]
                    profile.bar_council_id = acc["bar_id"]
                    profile.district = acc["district"]
                    profile.specialization = acc["specialization"]
                    profile.phone = acc["phone"]
                    profile.verification_status = "approved"
                    profile.verification_paid = acc["is_pro"]
                    db.commit()
                    print(f" -> Updated LawyerProfile for {email} (verified_paid={acc['is_pro']})")

                # Ensure sample schedules exist so user can immediately test bookings
                sched_count = db.query(Schedule).filter(Schedule.lawyer_id == profile.id).count()
                if sched_count == 0:
                    sample_slots = [
                        {"date": "Mon", "start_time": "10:00 AM", "end_time": "11:00 AM"},
                        {"date": "Tue", "start_time": "02:00 PM", "end_time": "03:00 PM"},
                        {"date": "Wed", "start_time": "11:00 AM", "end_time": "12:00 PM"},
                        {"date": "Thu", "start_time": "04:00 PM", "end_time": "05:00 PM"},
                    ]
                    for s in sample_slots:
                        db.add(
                            Schedule(
                                id=uuid.uuid4(),
                                lawyer_id=profile.id,
                                date=s["date"],
                                start_time=s["start_time"],
                                end_time=s["end_time"],
                                is_booked=False,
                            )
                        )
                    db.commit()
                    print(f" -> Added 4 availability slots for {acc['full_name']}")

        print("\nAll demo accounts seeded successfully!")
        print("Credentials for all 4 accounts:")
        print("  1. Free User:       free_user@bdlegal.ai   | Password123!")
        print("  2. Pro User:        pro_user@bdlegal.ai    | Password123!")
        print("  3. Free Lawyer:     free_lawyer@bdlegal.ai | Password123!")
        print("  4. Verified Lawyer: pro_lawyer@bdlegal.ai  | Password123!")

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_accounts()
