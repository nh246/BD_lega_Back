"""
Idempotent Database Seed Script for BD Legal Guide AI.
Run with:
    python -m app.seed
from the backend root directory (E:\\Law_Project\\backend).
"""

import sys
import uuid
import bcrypt
from datetime import datetime, timedelta

from app.core.database import Base, engine, SessionLocal
from app.models import (
    User,
    LawyerProfile,
    LawFirm,
    Schedule,
    Booking,
    ChatSession,
    ChatMessage,
    LlmConfig,
    Plan,
    Subscription,
    Payment,
    AuditLog,
)


def hash_password(password: str) -> str:
    """Hash plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def seed_database():
    print("=" * 60)
    print("BD Legal Guide AI — Database Seeding")
    print("=" * 60)

    # 1. Ensure all tables are created
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # ---------------------------------------------------------
        # 2. Seed Plans (4 plans)
        # ---------------------------------------------------------
        plans_data = [
            {
                "code": "user_free",
                "name": "Free Plan",
                "price_monthly": 0.0,
                "duration_days": None,
                "features": [
                    "Standard Gemini AI Chat (15 msgs/mo)",
                    "3-turn chat memory",
                    "Browse Lawyer Directory",
                    "Book Consultations",
                    "Basic Session History",
                ],
            },
            {
                "code": "user_pro_monthly",
                "name": "Pro Monthly",
                "price_monthly": 299.0,
                "duration_days": 30,
                "features": [
                    "Standard Gemini AI Chat (Unlimited)",
                    "20-turn chat memory",
                    "Direct messaging with verified lawyers",
                    "Browse Lawyer Directory",
                    "Book Consultations",
                    "Basic Session History",
                    "RAG-Verified Citations (BD Penal Code)",
                    "Document Analysis (PDF/Docx)",
                    "Priority Lawyer Matching",
                ],
            },
            {
                "code": "user_pro_6m",
                "name": "Pro 6 Months",
                "price_monthly": 1499.0,
                "duration_days": 180,
                "features": [
                    "All Pro features for 6 months",
                    "Standard Gemini AI Chat (Unlimited)",
                    "20-turn chat memory",
                    "Direct messaging with verified lawyers",
                    "Priority Lawyer Matching",
                ],
            },
            {
                "code": "user_pro_1y",
                "name": "Pro 1 Year",
                "price_monthly": 2499.0,
                "duration_days": 365,
                "features": [
                    "All Pro features for 1 full year",
                    "Standard Gemini AI Chat (Unlimited)",
                    "20-turn chat memory",
                    "Direct messaging with verified lawyers",
                    "Priority Lawyer Matching",
                    "Maximum savings",
                ],
            },
            {
                "code": "user_pro",
                "name": "Pro Plan",
                "price_monthly": 299.0,
                "duration_days": 30,
                "features": [
                    "Standard Gemini AI Chat",
                    "Browse Lawyer Directory",
                    "Book Consultations",
                    "Basic Session History",
                    "RAG-Verified Citations (BD Penal Code)",
                    "Document Analysis (PDF/Docx)",
                    "Priority Lawyer Matching",
                    "Unlimited AI Queries",
                ],
            },
            {
                "code": "lawyer_basic",
                "name": "Lawyer Basic",
                "price_monthly": 0.0,
                "duration_days": None,
                "features": [
                    "Directory Listing",
                    "Receive Consultation Requests",
                    "Manual Schedule Management",
                ],
            },
            {
                "code": "lawyer_verified",
                "name": "Lawyer Verified Badge",
                "price_monthly": 999.0,
                "duration_days": None,
                "features": [
                    "Bar Council Verified Badge",
                    "Priority Search & Directory Ranking",
                    "Instant Meeting Link Generation",
                    "Direct Client Video Consultation",
                    "Priority Payouts",
                ],
            },
        ]

        plans_map = {}
        for p in plans_data:
            existing_plan = db.query(Plan).filter(Plan.code == p["code"]).first()
            if not existing_plan:
                new_plan = Plan(
                    id=uuid.uuid4(),
                    code=p["code"],
                    name=p["name"],
                    price_monthly=p["price_monthly"],
                    duration_days=p.get("duration_days"),
                    features=p["features"],
                )
                db.add(new_plan)
                db.flush()
                plans_map[p["code"]] = new_plan
                print(f" [+] Plan created: {p['code']} ({p['name']})")
            else:
                existing_plan.name = p["name"]
                existing_plan.price_monthly = p["price_monthly"]
                if hasattr(existing_plan, "duration_days"):
                    existing_plan.duration_days = p.get("duration_days")
                existing_plan.features = p["features"]
                plans_map[p["code"]] = existing_plan
                print(f" [.] Plan exists: {p['code']}")

        # ---------------------------------------------------------
        # 3. Seed Users & Lawyer Profiles
        # ---------------------------------------------------------
        def get_or_create_user(email, password, full_name, role, status="active", scopes=None):
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password(password),
                    full_name=full_name,
                    role=role,
                    status=status,
                    scopes=scopes,
                    created_at=datetime.utcnow(),
                )
                db.add(user)
                db.flush()
                print(f" [+] User created: {email} [{role}]")
            else:
                print(f" [.] User exists: {email}")
            return user

        # Required Users
        admin_user = get_or_create_user(
            email="admin@bdlegal.ai",
            password="Admin@1234",
            full_name="System Administrator",
            role="admin",
            scopes=["admin:all"],
        )

        moderator_user = get_or_create_user(
            email="moderator@bdlegal.ai",
            password="Mod@1234",
            full_name="Lead Moderator",
            role="moderator",
            scopes=[
                "users:view",
                "users:moderate",
                "lawyers:view",
                "lawyers:verify",
                "firms:view",
                "firms:verify",
                "queries:view",
                "audit:view",
            ],
        )

        lawyer_sarah = get_or_create_user(
            email="lawyer@bdlegal.ai",
            password="Lawyer@1234",
            full_name="Adv. Sarah Ahmed",
            role="lawyer",
        )

        regular_user = get_or_create_user(
            email="user@bdlegal.ai",
            password="User@1234",
            full_name="Kamal Hossain",
            role="user",
        )

        # 3 Extra Users
        client_1 = get_or_create_user(
            email="client1@bdlegal.ai",
            password="User@1234",
            full_name="Tariqul Islam",
            role="user",
        )
        client_2 = get_or_create_user(
            email="client2@bdlegal.ai",
            password="User@1234",
            full_name="Nusrat Jahan",
            role="user",
        )
        client_3 = get_or_create_user(
            email="client3@bdlegal.ai",
            password="User@1234",
            full_name="Farhan Kabir",
            role="user",
        )

        # 1 Extra Moderator
        mod_2 = get_or_create_user(
            email="mod2@bdlegal.ai",
            password="Mod@1234",
            full_name="Audit Moderator",
            role="moderator",
            scopes=["users:view", "lawyers:view", "firms:view", "audit:view"],
        )

        # 3 Extra Lawyers: 1 approved, 1 pending, 1 rejected
        lawyer_rafiq = get_or_create_user(
            email="lawyer_approved@bdlegal.ai",
            password="Lawyer@1234",
            full_name="Adv. Rafiqul Haque",
            role="lawyer",
        )
        lawyer_tanvir = get_or_create_user(
            email="lawyer_pending@bdlegal.ai",
            password="Lawyer@1234",
            full_name="Adv. Tanvir Chowdhury",
            role="lawyer",
        )
        lawyer_mizan = get_or_create_user(
            email="lawyer_rejected@bdlegal.ai",
            password="Lawyer@1234",
            full_name="Adv. Mizanur Rahman",
            role="lawyer",
        )

        # Lawyer Profiles
        def get_or_create_profile(user, name, bar_id, district, spec, phone, status, paid):
            profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == user.id).first()
            if not profile:
                profile = LawyerProfile(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    name=name,
                    bar_council_id=bar_id,
                    district=district,
                    specialization=spec,
                    phone=phone,
                    verification_status=status,
                    verification_paid=paid,
                    created_at=datetime.utcnow(),
                )
                db.add(profile)
                db.flush()
                print(f" [+] LawyerProfile created: {name} ({status})")
            else:
                print(f" [.] LawyerProfile exists: {name}")
            return profile

        sarah_profile = get_or_create_profile(
            lawyer_sarah,
            name="Adv. Sarah Ahmed",
            bar_id="BD-BAR-2018-4921",
            district="Dhaka",
            spec="Civil Law & Property",
            phone="+8801711223344",
            status="approved",
            paid=True,
        )

        rafiq_profile = get_or_create_profile(
            lawyer_rafiq,
            name="Adv. Rafiqul Haque",
            bar_id="BD-BAR-2015-1029",
            district="Chittagong",
            spec="Criminal Defense & Constitutional Law",
            phone="+8801811334455",
            status="approved",
            paid=True,
        )

        tanvir_profile = get_or_create_profile(
            lawyer_tanvir,
            name="Adv. Tanvir Chowdhury",
            bar_id="BD-BAR-2022-7782",
            district="Sylhet",
            spec="Family Law & Corporate",
            phone="+8801911445566",
            status="pending",
            paid=False,
        )

        mizan_profile = get_or_create_profile(
            lawyer_mizan,
            name="Adv. Mizanur Rahman",
            bar_id="BD-BAR-0000-FAIL",
            district="Rajshahi",
            spec="Taxation & Commercial",
            phone="+8801611556677",
            status="rejected",
            paid=False,
        )

        # ---------------------------------------------------------
        # 4. Seed Law Firms (2 firms)
        # ---------------------------------------------------------
        firms_data = [
            {
                "name": "Rahman & Partners Law Chambers",
                "contact_person": "Adv. Mahbubur Rahman",
                "email": "contact@rahmanpartners.com",
                "phone": "+88029876543",
                "address": "Gulshan-2, Dhaka 1212",
                "status": "approved",
            },
            {
                "name": "Chowdhury & Associates Legal Consultants",
                "contact_person": "Adv. Farhana Chowdhury",
                "email": "info@chowdhurylegal.com",
                "phone": "+88029554321",
                "address": "Agrabad Commercial Area, Chittagong 4100",
                "status": "pending",
            },
        ]

        for f in firms_data:
            existing_firm = db.query(LawFirm).filter(LawFirm.name == f["name"]).first()
            if not existing_firm:
                new_firm = LawFirm(
                    id=uuid.uuid4(),
                    name=f["name"],
                    contact_person=f["contact_person"],
                    email=f["email"],
                    phone=f["phone"],
                    address=f["address"],
                    status=f["status"],
                    created_at=datetime.utcnow(),
                )
                db.add(new_firm)
                print(f" [+] LawFirm created: {f['name']} ({f['status']})")
            else:
                print(f" [.] LawFirm exists: {f['name']}")

        # ---------------------------------------------------------
        # 5. Seed 6 Schedule Slots in 2026 for Approved Lawyers
        # ---------------------------------------------------------
        schedules_list = []
        slots_def = [
            (sarah_profile.id, "2026-10-25", "10:00 AM", "11:00 AM", True),
            (sarah_profile.id, "2026-10-25", "02:00 PM", "03:00 PM", True),
            (sarah_profile.id, "2026-10-26", "11:00 AM", "12:00 PM", False),
            (rafiq_profile.id, "2026-10-27", "09:00 AM", "10:00 AM", False),
            (rafiq_profile.id, "2026-10-27", "03:00 PM", "04:00 PM", False),
            (rafiq_profile.id, "2026-10-28", "10:00 AM", "11:00 AM", False),
        ]

        for lawyer_id, s_date, start_t, end_t, is_b in slots_def:
            parsed_s_date = datetime.strptime(s_date, "%Y-%m-%d").date()
            slot = (
                db.query(Schedule)
                .filter(
                    Schedule.lawyer_id == lawyer_id,
                    Schedule.date == parsed_s_date,
                    Schedule.start_time == start_t,
                )
                .first()
            )
            if not slot:
                slot = Schedule(
                    id=uuid.uuid4(),
                    lawyer_id=lawyer_id,
                    date=parsed_s_date,
                    start_time=start_t,
                    end_time=end_t,
                    is_booked=is_b,
                )
                db.add(slot)
                db.flush()
                print(f" [+] Schedule slot created: {s_date} {start_t} for lawyer {lawyer_id}")
            else:
                print(f" [.] Schedule slot exists: {s_date} {start_t}")
            schedules_list.append(slot)

        # ---------------------------------------------------------
        # 6. Seed 2 Bookings (1 confirmed, 1 pending)
        # ---------------------------------------------------------
        # Booking 1: Confirmed (Kamal Hossain with Adv. Sarah)
        b1 = db.query(Booking).filter(Booking.schedule_id == schedules_list[0].id).first()
        if not b1:
            b1 = Booking(
                id=uuid.uuid4(),
                user_id=regular_user.id,
                lawyer_id=sarah_profile.id,
                schedule_id=schedules_list[0].id,
                status="confirmed",
                created_at=datetime.utcnow() - timedelta(days=2),
            )
            db.add(b1)
            print(" [+] Booking created: Confirmed (User Kamal -> Adv. Sarah)")
        else:
            print(" [.] Booking 1 exists")

        # Booking 2: Pending (Tariqul Islam with Adv. Sarah)
        b2 = db.query(Booking).filter(Booking.schedule_id == schedules_list[1].id).first()
        if not b2:
            b2 = Booking(
                id=uuid.uuid4(),
                user_id=client_1.id,
                lawyer_id=sarah_profile.id,
                schedule_id=schedules_list[1].id,
                status="pending",
                created_at=datetime.utcnow() - timedelta(hours=6),
            )
            db.add(b2)
            print(" [+] Booking created: Pending (User Tariqul -> Adv. Sarah)")
        else:
            print(" [.] Booking 2 exists")

        # ---------------------------------------------------------
        # 7. Seed 1 Chat Session with 2 Messages
        # ---------------------------------------------------------
        existing_session = db.query(ChatSession).filter(ChatSession.user_id == regular_user.id).first()
        if not existing_session:
            chat_session = ChatSession(
                id=uuid.uuid4(),
                user_id=regular_user.id,
                created_at=datetime.utcnow() - timedelta(days=1),
            )
            db.add(chat_session)
            db.flush()

            msg_1 = ChatMessage(
                id=uuid.uuid4(),
                session_id=chat_session.id,
                role="user",
                content="What is the penalty for cyber defamation under Bangladesh Cyber Security Act 2023?",
                provider=None,
                model=None,
                created_at=datetime.utcnow() - timedelta(days=1, minutes=5),
            )
            msg_2 = ChatMessage(
                id=uuid.uuid4(),
                session_id=chat_session.id,
                role="assistant",
                content=(
                    "Under the Cyber Security Act 2023 of Bangladesh, offenses related to sending offensive, "
                    "false, or defamatory information digitally carry rigorous imprisonment and substantial fines. "
                    "Section 25 provides penalties for first-time offenders of up to 2–3 years imprisonment or fines "
                    "up to BDT 300,000. Repeated offenses incur enhanced sentences. "
                    "For formal legal advice or initiating proceedings with the Cyber Tribunal, consultation with a verified advocate is advised."
                ),
                provider="gemini",
                model="gemini-1.5-flash",
                created_at=datetime.utcnow() - timedelta(days=1, minutes=4),
            )
            db.add(msg_1)
            db.add(msg_2)
            print(" [+] Chat session & 2 messages created for user Kamal Hossain")
        else:
            print(" [.] Chat session exists for user Kamal Hossain")

        # ---------------------------------------------------------
        # 8. Seed 1 Active LLM Config
        # ---------------------------------------------------------
        existing_llm = db.query(LlmConfig).filter(LlmConfig.provider == "gemini", LlmConfig.model_name == "gemini-1.5-flash").first()
        if not existing_llm:
            llm_config = LlmConfig(
                id=uuid.uuid4(),
                provider="gemini",
                model_name="gemini-1.5-flash",
                temperature=0.3,
                max_tokens=2048,
                system_prompt=(
                    "You are BD Legal Guide AI, an authoritative, helpful legal information assistant "
                    "specializing in Bangladesh law (Penal Code 1860, Code of Criminal Procedure 1898, "
                    "Civil Law, and Special Statutory Acts)."
                ),
                disclaimer=(
                    "This is general legal information and does not constitute formal attorney-client legal "
                    "representation. For specific legal counsel, please book a consultation with a verified advocate."
                ),
                is_active=True,
                created_at=datetime.utcnow(),
            )
            db.add(llm_config)
            print(" [+] LLM Config created: gemini-1.5-flash (Active)")
        else:
            print(" [.] LLM Config exists: gemini-1.5-flash")

        # ---------------------------------------------------------
        # 9. Seed 2 Payments (Status: paid)
        # ---------------------------------------------------------
        # Create an active subscription for regular_user (Pro plan)
        sub_pro = db.query(Subscription).filter(Subscription.user_id == regular_user.id).first()
        if not sub_pro:
            sub_pro = Subscription(
                id=uuid.uuid4(),
                user_id=regular_user.id,
                plan_id=plans_map["user_pro"].id,
                status="active",
                started_at=datetime.utcnow() - timedelta(days=5),
                expires_at=datetime.utcnow() + timedelta(days=25),
            )
            db.add(sub_pro)
            db.flush()
            print(" [+] Subscription created: User Pro for Kamal Hossain")
        else:
            print(" [.] Subscription exists for Kamal Hossain")

        # Payment 1: Subscription payment
        pay_sub = db.query(Payment).filter(Payment.external_ref == "ch_stripe_sub_demo_001").first()
        if not pay_sub:
            pay_sub = Payment(
                id=uuid.uuid4(),
                subscription_id=sub_pro.id,
                lawyer_profile_id=None,
                type="subscription",
                amount=299.0,
                provider="stripe",
                external_ref="ch_stripe_sub_demo_001",
                status="paid",
                created_at=datetime.utcnow() - timedelta(days=5),
            )
            db.add(pay_sub)
            print(" [+] Payment 1 created: Subscription $299 (Paid)")
        else:
            print(" [.] Payment 1 exists")

        # Payment 2: Lawyer Verification One-Time payment
        pay_verif = db.query(Payment).filter(Payment.external_ref == "ch_stripe_verif_demo_002").first()
        if not pay_verif:
            pay_verif = Payment(
                id=uuid.uuid4(),
                subscription_id=None,
                lawyer_profile_id=sarah_profile.id,
                type="verification_one_time",
                amount=999.0,
                provider="stripe",
                external_ref="ch_stripe_verif_demo_002",
                status="paid",
                created_at=datetime.utcnow() - timedelta(days=10),
            )
            db.add(pay_verif)
            print(" [+] Payment 2 created: Lawyer Verification $999 (Paid)")
        else:
            print(" [.] Payment 2 exists")

        # ---------------------------------------------------------
        # 10. Seed 5 Sample Audit Logs
        # ---------------------------------------------------------
        audit_records = [
            {
                "actor_id": admin_user.id,
                "action": "system_bootstrap",
                "target_type": "system",
                "target_id": "core_engine",
                "details": {"version": "2.0.0", "module": "Module 1 - Core Database"},
            },
            {
                "actor_id": admin_user.id,
                "action": "user_role_assigned",
                "target_type": "user",
                "target_id": str(moderator_user.id),
                "details": {"email": "moderator@bdlegal.ai", "assigned_role": "moderator"},
            },
            {
                "actor_id": moderator_user.id,
                "action": "lawyer_verification_approved",
                "target_type": "lawyer_profile",
                "target_id": str(sarah_profile.id),
                "details": {"bar_council_id": "BD-BAR-2018-4921", "result": "approved"},
            },
            {
                "actor_id": regular_user.id,
                "action": "subscription_started",
                "target_type": "subscription",
                "target_id": str(sub_pro.id),
                "details": {"plan_code": "user_pro", "price": 299.0},
            },
            {
                "actor_id": regular_user.id,
                "action": "booking_requested",
                "target_type": "booking",
                "target_id": str(b1.id if b1 else "booking_slot_1"),
                "details": {"lawyer": "Adv. Sarah Ahmed", "slot_date": "2026-10-25"},
            },
        ]

        # Only insert sample audit logs if audit_logs table has less than 5 rows
        existing_audit_count = db.query(AuditLog).count()
        if existing_audit_count < 5:
            for log_data in audit_records:
                log_entry = AuditLog(
                    id=uuid.uuid4(),
                    actor_id=log_data["actor_id"],
                    action=log_data["action"],
                    target_type=log_data["target_type"],
                    target_id=log_data["target_id"],
                    details=log_data["details"],
                    created_at=datetime.utcnow(),
                )
                db.add(log_entry)
            print(" [+] 5 Sample Audit Logs created")
        else:
            print(f" [.] Audit logs exist ({existing_audit_count} entries)")

        # Commit all changes
        db.commit()
        print("=" * 60)
        print("Database seeding completed successfully!")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f" [!] Seeding error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
