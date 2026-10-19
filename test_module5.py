"""
Comprehensive integration test suite for Module 5: Schedules & Bookings.
Tests live database connectivity, validation, roles, booking lifecycle,
schedule availability toggling, and audit logging.
"""

import sys
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal, engine, Base
from app.core.security import get_password_hash, create_access_token
from app.models import User, LawyerProfile, Schedule, Booking, AuditLog


def run_tests():
    print("--- Starting Module 5 Integration Tests ---")
    client = TestClient(app)

    db: Session = SessionLocal()
    try:
        # 1. Verify health check
        health_resp = client.get("/health")
        assert health_resp.status_code == 200, f"Health check failed: {health_resp.text}"
        assert health_resp.json()["db"] == "connected"
        print("[PASS] Database and health check connected")

        # 2. Setup Test Fixtures in DB
        # Clean up any leftover test data
        test_emails = [
            "m5_client@example.com",
            "m5_lawyer@example.com",
            "m5_fake_lawyer@example.com",
            "m5_other_lawyer@example.com",
        ]
        users = db.query(User).filter(User.email.in_(test_emails)).all()
        user_ids = [u.id for u in users]
        if user_ids:
            db.query(Booking).filter(Booking.user_id.in_(user_ids)).delete(synchronize_session=False)
            profiles = db.query(LawyerProfile).filter(LawyerProfile.user_id.in_(user_ids)).all()
            profile_ids = [p.id for p in profiles]
            if profile_ids:
                db.query(Booking).filter(Booking.lawyer_id.in_(profile_ids)).delete(synchronize_session=False)
                db.query(Schedule).filter(Schedule.lawyer_id.in_(profile_ids)).delete(synchronize_session=False)
            for u in users:
                db.delete(u)
            db.commit()

        # Create Client User
        client_user = User(
            email="m5_client@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M5 Test Client",
            role="user",
            status="active",
        )
        db.add(client_user)

        # Create Lawyer 1 User & Profile
        lawyer_user = User(
            email="m5_lawyer@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Advocate M5 Lawyer",
            role="lawyer",
            status="active",
        )
        db.add(lawyer_user)
        db.flush()

        lawyer_profile = LawyerProfile(
            user_id=lawyer_user.id,
            name="Advocate M5 Lawyer",
            district="Dhaka",
            specialization="Corporate Law",
            phone="01700000001",
            verification_status="approved",
        )
        db.add(lawyer_profile)

        # Create Lawyer 2 User & Profile (for cross-lawyer access check)
        other_lawyer_user = User(
            email="m5_other_lawyer@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Advocate Other",
            role="lawyer",
            status="active",
        )
        db.add(other_lawyer_user)
        db.flush()

        other_profile = LawyerProfile(
            user_id=other_lawyer_user.id,
            name="Advocate Other",
            district="Chittagong",
            verification_status="approved",
        )
        db.add(other_profile)

        # Create Fake Lawyer User (role="lawyer" but no lawyer_profile row)
        fake_lawyer_user = User(
            email="m5_fake_lawyer@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Fake Lawyer Without Profile",
            role="lawyer",
            status="active",
        )
        db.add(fake_lawyer_user)
        db.commit()

        # Generate JWT tokens
        client_token = create_access_token({"sub": client_user.email, "role": "user"})
        lawyer_token = create_access_token({"sub": lawyer_user.email, "role": "lawyer"})
        other_lawyer_token = create_access_token({"sub": other_lawyer_user.email, "role": "lawyer"})
        fake_lawyer_token = create_access_token({"sub": fake_lawyer_user.email, "role": "lawyer"})

        client_headers = {"Authorization": f"Bearer {client_token}"}
        lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}
        other_lawyer_headers = {"Authorization": f"Bearer {other_lawyer_token}"}
        fake_headers = {"Authorization": f"Bearer {fake_lawyer_token}"}

        print("[PASS] Test fixtures created (Client, Approved Lawyer, Other Lawyer, Lawyer without profile)")

        # 3. Test Schedule Creation Permission Checks
        # Regular user tries to create lawyer schedule -> 403
        resp = client.post(
            "/api/lawyer/schedules",
            json={"date": "2026-11-10", "start_time": "10:00 AM", "end_time": "11:00 AM"},
            headers=client_headers,
        )
        assert resp.status_code == 403, f"Expected 403 for client creating schedule, got {resp.status_code}"
        print("[PASS] Client denied from creating schedule slot (403)")

        # Fake lawyer without profile -> 403
        resp = client.post(
            "/api/lawyer/schedules",
            json={"date": "2026-11-10", "start_time": "10:00 AM", "end_time": "11:00 AM"},
            headers=fake_headers,
        )
        assert resp.status_code == 403, f"Expected 403 for lawyer without profile row, got {resp.status_code}"
        print("[PASS] Lawyer without lawyer_profiles row denied with 403")

        # Legitimate lawyer creates schedule slot -> 201
        resp = client.post(
            "/api/lawyer/schedules",
            json={"date": "2026-11-10", "start_time": "10:00 AM", "end_time": "11:00 AM"},
            headers=lawyer_headers,
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        schedule_data = resp.json()
        schedule_id = schedule_data["id"]
        assert schedule_data["is_booked"] is False
        assert schedule_data["lawyer_id"] == str(lawyer_profile.id)
        assert schedule_data["date"] == "2026-11-10"
        print(f"[PASS] Lawyer successfully created schedule slot ({schedule_id})")

        # 4. Public querying of lawyer's available schedules
        resp = client.get(f"/api/lawyers/{lawyer_profile.id}/schedules")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        schedules = resp.json()
        assert len(schedules) >= 1
        assert any(s["id"] == schedule_id and s["is_booked"] is False for s in schedules)
        print("[PASS] Public GET /api/lawyers/{id}/schedules returned unbooked slot")

        # 5. Client Booking Creation
        # Lawyer cannot book as client -> 403
        resp = client.post(
            "/api/bookings",
            json={"schedule_id": schedule_id},
            headers=lawyer_headers,
        )
        assert resp.status_code == 403, f"Expected 403 for lawyer booking, got {resp.status_code}"
        print("[PASS] Lawyer forbidden from booking as client (403)")

        # Client books the slot -> 201
        resp = client.post(
            "/api/bookings",
            json={"schedule_id": schedule_id},
            headers=client_headers,
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        booking_data = resp.json()
        booking_id = booking_data["id"]
        assert booking_data["status"] == "pending"
        assert booking_data["schedule_id"] == schedule_id
        assert booking_data["user_id"] == str(client_user.id)
        assert booking_data["lawyer_id"] == str(lawyer_profile.id)
        assert booking_data["lawyer_name"] == "Advocate M5 Lawyer"
        assert booking_data["user_name"] == "M5 Test Client"
        print(f"[PASS] Client successfully booked slot ({booking_id}) with lawyer_name joined")

        # Verify schedule is_booked is now True in DB and public endpoint returns 0 available slots
        resp = client.get(f"/api/lawyers/{lawyer_profile.id}/schedules")
        assert resp.status_code == 200
        available_slots = [s for s in resp.json() if s["id"] == schedule_id]
        assert len(available_slots) == 0, "Booked slot should not appear in available schedules"
        print("[PASS] Booked slot is immediately hidden from available schedules")

        # 6. Double booking prevention (400 Bad Request)
        resp = client.post(
            "/api/bookings",
            json={"schedule_id": schedule_id},
            headers=client_headers,
        )
        assert resp.status_code == 400, f"Expected 400 for double booking, got {resp.status_code}"
        print("[PASS] Double-booking prevented with 400 Bad Request")

        # Verify audit log for booking_created
        db.expire_all()
        audit_entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "booking_created", AuditLog.target_id == booking_id)
            .first()
        )
        assert audit_entry is not None, "Audit log for booking_created was not created"
        assert audit_entry.actor_id == client_user.id
        print("[PASS] Audit log entry verified: booking_created")

        # 7. Listing Bookings
        # GET /api/bookings/mine for user
        resp = client.get("/api/bookings/mine", headers=client_headers)
        assert resp.status_code == 200
        my_bookings = resp.json()
        assert any(b["id"] == booking_id and b["lawyer_name"] == "Advocate M5 Lawyer" for b in my_bookings)
        print("[PASS] GET /api/bookings/mine returned user's booking with lawyer_name")

        # GET /api/lawyer/bookings for lawyer
        resp = client.get("/api/lawyer/bookings", headers=lawyer_headers)
        assert resp.status_code == 200
        lawyer_bookings = resp.json()
        assert any(b["id"] == booking_id and b["user_name"] == "M5 Test Client" for b in lawyer_bookings)
        print("[PASS] GET /api/lawyer/bookings returned lawyer's booking with user_name")

        # GET /api/lawyer/requests alias for frontend
        resp = client.get("/api/lawyer/requests", headers=lawyer_headers)
        assert resp.status_code == 200
        assert any(b["id"] == booking_id for b in resp.json())
        print("[PASS] GET /api/lawyer/requests alias verified")

        # 8. Lawyer Confirming & Cancelling Booking
        # Other lawyer attempts to update booking -> 403
        resp = client.patch(
            f"/api/lawyer/bookings/{booking_id}",
            json={"status": "confirmed"},
            headers=other_lawyer_headers,
        )
        assert resp.status_code == 403, f"Expected 403 for unauthorized lawyer, got {resp.status_code}"
        print("[PASS] Non-assigned lawyer prevented from updating booking (403)")

        # Assigned lawyer confirms booking
        resp = client.patch(
            f"/api/lawyer/bookings/{booking_id}",
            json={"status": "confirmed"},
            headers=lawyer_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"
        print("[PASS] Assigned lawyer confirmed booking")

        # Verify audit log for booking_confirmed
        db.expire_all()
        audit_entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "booking_confirmed", AuditLog.target_id == booking_id)
            .first()
        )
        assert audit_entry is not None, "Audit log for booking_confirmed was not found"
        print("[PASS] Audit log entry verified: booking_confirmed")

        # Assigned lawyer cancels booking -> Schedule slot reopened!
        resp = client.patch(
            f"/api/lawyer/bookings/{booking_id}",
            json={"status": "cancelled"},
            headers=lawyer_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        print("[PASS] Assigned lawyer cancelled booking")

        # Verify schedule is_booked is now reset to False
        db.expire_all()
        slot = db.query(Schedule).filter(Schedule.id == uuid.UUID(schedule_id)).first()
        assert slot.is_booked is False, f"Schedule is_booked should be False, got {slot.is_booked}"
        print("[PASS] Schedule slot is_booked reset to False upon cancellation")

        # Verify public available slots now shows the slot again
        resp = client.get(f"/api/lawyers/{lawyer_profile.id}/schedules")
        assert resp.status_code == 200
        available_slots = [s for s in resp.json() if s["id"] == schedule_id]
        assert len(available_slots) == 1, "Slot should be available again after cancellation"
        print("[PASS] Slot is visible again in available schedules")

        # Verify audit log for booking_cancelled
        db.expire_all()
        audit_entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "booking_cancelled", AuditLog.target_id == booking_id)
            .first()
        )
        assert audit_entry is not None, "Audit log for booking_cancelled was not found"
        print("[PASS] Audit log entry verified: booking_cancelled")

        # 9. Clean up test records
        db.query(Booking).filter(Booking.id == uuid.UUID(booking_id)).delete(synchronize_session=False)
        db.query(Schedule).filter(Schedule.id == uuid.UUID(schedule_id)).delete(synchronize_session=False)
        for u in [client_user, lawyer_user, other_lawyer_user, fake_lawyer_user]:
            db.delete(u)
        db.commit()
        print("[PASS] Test cleanup completed")

        print("\n==========================================")
        print(" ALL MODULE 5 TESTS PASSED SUCCESSFULLY! ")
        print("==========================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
