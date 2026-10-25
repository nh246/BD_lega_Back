"""
Setup test accounts for frontend DM testing:
1. Lawyer: adv.karim@test.com / Password123!
2. Free Client 1 (no booking): client.nobooking@test.com / Password123!
3. Free Client 2 (confirmed booking): client.confirmed@test.com / Password123!
4. Free Client 3 (completed booking): client.completed@test.com / Password123!
"""

import uuid
from datetime import datetime, timezone, timedelta
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import User, LawyerProfile, Booking, Schedule, DirectMessage, ProfileAsset

def setup_data():
    db = SessionLocal()
    try:
        # 1. Lawyer
        lawyer_user = db.query(User).filter(User.email == "adv.karim@test.com").first()
        if not lawyer_user:
            lawyer_user = User(
                id=uuid.uuid4(),
                email="adv.karim@test.com",
                password_hash=get_password_hash("Password123!"),
                full_name="Adv. Karim Uddin",
                role="lawyer",
                status="active",
            )
            db.add(lawyer_user)
            db.flush()
        else:
            lawyer_user.password_hash = get_password_hash("Password123!")
            lawyer_user.status = "active"

        lawyer_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == lawyer_user.id).first()
        if not lawyer_prof:
            lawyer_prof = LawyerProfile(
                id=uuid.uuid4(),
                user_id=lawyer_user.id,
                name="Adv. Karim Uddin",
                verification_status="approved",
                hourly_rate=2500,
                specialization="Corporate & Civil Law",
                district="Dhaka",
            )
            db.add(lawyer_prof)
            db.flush()
        else:
            lawyer_prof.verification_status = "approved"

        # 2. Free User 1 (No booking)
        u1 = db.query(User).filter(User.email == "client.nobooking@test.com").first()
        if not u1:
            u1 = User(
                id=uuid.uuid4(),
                email="client.nobooking@test.com",
                password_hash=get_password_hash("Password123!"),
                full_name="Tanvir (No Booking)",
                role="user",
                status="active",
            )
            db.add(u1)
            db.flush()
        else:
            u1.password_hash = get_password_hash("Password123!")

        # 3. Free User 2 (Confirmed booking)
        u2 = db.query(User).filter(User.email == "client.confirmed@test.com").first()
        if not u2:
            u2 = User(
                id=uuid.uuid4(),
                email="client.confirmed@test.com",
                password_hash=get_password_hash("Password123!"),
                full_name="Rahim (Confirmed Booking)",
                role="user",
                status="active",
            )
            db.add(u2)
            db.flush()
        else:
            u2.password_hash = get_password_hash("Password123!")

        # Ensure schedule + confirmed booking for u2
        b2 = db.query(Booking).filter(Booking.user_id == u2.id, Booking.lawyer_id == lawyer_prof.id, Booking.status == "confirmed").first()
        if not b2:
            s2 = Schedule(
                id=uuid.uuid4(),
                lawyer_id=lawyer_prof.id,
                date=datetime.now().date() + timedelta(days=2),
                start_time="10:00 AM",
                end_time="11:00 AM",
                is_booked=True,
            )
            db.add(s2)
            db.flush()
            b2 = Booking(
                id=uuid.uuid4(),
                user_id=u2.id,
                lawyer_id=lawyer_prof.id,
                schedule_id=s2.id,
                status="confirmed",
            )
            db.add(b2)
            db.flush()

        # 4. Free User 3 (Completed booking)
        u3 = db.query(User).filter(User.email == "client.completed@test.com").first()
        if not u3:
            u3 = User(
                id=uuid.uuid4(),
                email="client.completed@test.com",
                password_hash=get_password_hash("Password123!"),
                full_name="Sultana (Completed Booking)",
                role="user",
                status="active",
            )
            db.add(u3)
            db.flush()
        else:
            u3.password_hash = get_password_hash("Password123!")

        # Ensure schedule + completed booking for u3
        b3 = db.query(Booking).filter(Booking.user_id == u3.id, Booking.lawyer_id == lawyer_prof.id).first()
        if not b3:
            s3 = Schedule(
                id=uuid.uuid4(),
                lawyer_id=lawyer_prof.id,
                date=datetime.now().date() - timedelta(days=3),
                start_time="02:00 PM",
                end_time="03:00 PM",
                is_booked=True,
            )
            db.add(s3)
            db.flush()
            b3 = Booking(
                id=uuid.uuid4(),
                user_id=u3.id,
                lawyer_id=lawyer_prof.id,
                schedule_id=s3.id,
                status="completed",
            )
            db.add(b3)
            db.flush()
        else:
            b3.status = "completed"

        # Create sample direct message between u3 and lawyer so completed thread has content
        dm_completed = db.query(DirectMessage).filter(DirectMessage.sender_user_id == u3.id, DirectMessage.lawyer_profile_id == lawyer_prof.id).first()
        if not dm_completed:
            dm_completed = DirectMessage(
                id=uuid.uuid4(),
                sender_user_id=u3.id,
                lawyer_profile_id=lawyer_prof.id,
                recipient_user_id=lawyer_user.id,
                content="Prior consultation advice regarding contract breach.",
                attachments=[],
                is_read=True,
                created_at=datetime.utcnow() - timedelta(days=3),
            )
            db.add(dm_completed)
            db.flush()

        db.commit()

        print(f"LAWYER_ID={lawyer_prof.id}")
        print(f"LAWYER_EMAIL=adv.karim@test.com")
        print(f"CLIENT_NO_BOOKING_EMAIL=client.nobooking@test.com")
        print(f"CLIENT_CONFIRMED_EMAIL=client.confirmed@test.com")
        print(f"CLIENT_COMPLETED_EMAIL=client.completed@test.com")
        print("SETUP_SUCCESS")

    finally:
        db.close()

if __name__ == "__main__":
    setup_data()
