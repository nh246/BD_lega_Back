"""
Verification test script for Real-Time Notification System.

Covers:
1. Setup client and lawyer users and slot.
2. Client books slot and submits payment proof -> Lawyer receives 'payment_submitted' notification.
3. Lawyer confirms payment -> Client receives 'payment_confirmed' notification.
4. Client calls GET /api/notifications -> returns 'Payment Confirmed' with unread_count >= 1.
5. Client marks single notification as read (POST /api/notifications/{id}/read) -> is_read = True.
6. Client marks all as read (POST /api/notifications/read-all) -> unread_count becomes 0.
7. Message notification: Lawyer replies to client -> Client receives 'new_message' notification.
8. Review notification: Client completes and reviews consultation -> Lawyer receives 'review_received' notification.
"""

import sys
import uuid
from datetime import datetime, timezone, timedelta, date
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.models import User, LawyerProfile, Booking, Schedule, Notification

client = TestClient(app)


def run_tests():
    db = SessionLocal()
    try:
        print("\n=== STEP 1: Setup Test Accounts & Booking ===")
        # 1. Setup Lawyer
        lawyer_email = f"notif_lawyer_{uuid.uuid4().hex[:6]}@example.com"
        lawyer_user = User(
            id=uuid.uuid4(),
            email=lawyer_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Adv. Notification Tester",
            role="lawyer",
            status="active",
        )
        db.add(lawyer_user)
        db.flush()

        lawyer_prof = LawyerProfile(
            id=uuid.uuid4(),
            user_id=lawyer_user.id,
            name="Adv. Notification Tester",
            verification_status="approved",
            hourly_rate=3000,
            specialization="Civil Litigation",
            district="Dhaka",
        )
        db.add(lawyer_prof)
        db.flush()

        lawyer_token = create_access_token({"sub": lawyer_user.email, "role": "lawyer"})
        lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}

        # 2. Setup Client
        client_email = f"notif_client_{uuid.uuid4().hex[:6]}@example.com"
        client_user = User(
            id=uuid.uuid4(),
            email=client_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Client Notif User",
            role="user",
            status="active",
        )
        db.add(client_user)
        db.flush()

        client_token = create_access_token({"sub": client_user.email, "role": "user"})
        client_headers = {"Authorization": f"Bearer {client_token}"}

        # 3. Create Schedule Slot
        slot_date = (date.today() + timedelta(days=2)).isoformat()
        slot = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=slot_date,
            start_time="10:00 AM",
            end_time="11:00 AM",
            is_booked=False,
        )
        db.add(slot)
        db.commit()

        print(f"Created Lawyer ({lawyer_email}) and Client ({client_email}) and Slot ({slot.id})")

        print("\n=== STEP 2: Client Books Slot & Submits Payment ===")
        # Client creates booking
        book_res = client.post(
            "/api/bookings",
            headers=client_headers,
            json={
                "schedule_id": str(slot.id),
                "case_brief": "Legal counsel required regarding property registration.",
            },
        )
        assert book_res.status_code == 201, f"Booking creation failed: {book_res.text}"
        booking_id = book_res.json()["id"]
        print(f"Booking created successfully: {booking_id}")

        # Client submits payment proof
        pay_res = client.post(
            f"/api/bookings/{booking_id}/submit-payment",
            headers=client_headers,
            json={"trx_id": "BKASH-TEST-998877"},
        )
        assert pay_res.status_code == 200, f"Submit payment failed: {pay_res.text}"
        assert pay_res.json()["status"] == "payment_submitted"
        print("Payment proof submitted with status: payment_submitted")

        # Verify Lawyer received 'payment_submitted' notification
        lawyer_notifs_res = client.get("/api/notifications", headers=lawyer_headers)
        assert lawyer_notifs_res.status_code == 200, f"Get lawyer notifs failed: {lawyer_notifs_res.text}"
        lawyer_notifs_data = lawyer_notifs_res.json()
        assert any(n["type"] == "payment_submitted" for n in lawyer_notifs_data["notifications"]), (
            f"Expected payment_submitted notification for lawyer, got: {lawyer_notifs_data}"
        )
        print("Lawyer received 'payment_submitted' notification: SUCCESS")

        print("\n=== STEP 3: Lawyer Confirms Payment -> Client Receives Notification ===")
        confirm_res = client.post(
            f"/api/bookings/{booking_id}/confirm-payment",
            headers=lawyer_headers,
        )
        assert confirm_res.status_code == 200, f"Confirm payment failed: {confirm_res.text}"
        assert confirm_res.json()["status"] == "confirmed"
        print("Payment confirmed by lawyer with status: confirmed")

        # Client fetches notifications
        client_notifs_res = client.get("/api/notifications", headers=client_headers)
        assert client_notifs_res.status_code == 200, f"Get client notifs failed: {client_notifs_res.text}"
        client_notifs_data = client_notifs_res.json()
        print(f"Client notifications response: unread_count={client_notifs_data['unread_count']}, count={len(client_notifs_data['notifications'])}")

        payment_confirmed_notif = next(
            (n for n in client_notifs_data["notifications"] if n["type"] == "payment_confirmed"),
            None,
        )
        assert payment_confirmed_notif is not None, f"Payment Confirmed notification missing: {client_notifs_data}"
        assert payment_confirmed_notif["title"] == "Payment Confirmed"
        assert payment_confirmed_notif["is_read"] is False
        assert client_notifs_data["unread_count"] >= 1
        print("Client GET /api/notifications returns 'Payment Confirmed' with unread_count >= 1: SUCCESS")

        print("\n=== STEP 4: Mark Notification as Read & Mark All as Read ===")
        notif_id = payment_confirmed_notif["id"]

        # Mark single notification as read
        read_single_res = client.post(
            f"/api/notifications/{notif_id}/read",
            headers=client_headers,
        )
        assert read_single_res.status_code == 200, f"Mark single read failed: {read_single_res.text}"
        assert read_single_res.json()["is_read"] is True
        print(f"Notification {notif_id} marked as read: SUCCESS")

        # Add another notification and then call read-all
        from app.services.notifications import trigger_notification
        trigger_notification(
            db=db,
            user_id=client_user.id,
            type="booking_confirmed",
            title="Booking Confirmed",
            message="Your consultation is scheduled.",
            link="/client/bookings",
        )

        before_read_all = client.get("/api/notifications", headers=client_headers).json()
        assert before_read_all["unread_count"] >= 1
        print(f"Before read-all unread_count: {before_read_all['unread_count']}")

        read_all_res = client.post("/api/notifications/read-all", headers=client_headers)
        assert read_all_res.status_code == 200, f"Read all failed: {read_all_res.text}"
        assert read_all_res.json()["unread_count"] == 0

        after_read_all = client.get("/api/notifications", headers=client_headers).json()
        assert after_read_all["unread_count"] == 0
        print("POST /api/notifications/read-all -> unread_count is now 0: SUCCESS")

        print("\n=== STEP 5: New Message Notification ===")
        msg_reply_res = client.post(
            f"/api/messages/lawyer/reply/{client_user.id}",
            headers=lawyer_headers,
            json={"content": "Hello! I received your consultation request."},
        )
        assert msg_reply_res.status_code == 201, f"Lawyer reply failed: {msg_reply_res.text}"

        client_msgs_notifs = client.get("/api/notifications", headers=client_headers).json()
        new_msg_notif = next((n for n in client_msgs_notifs["notifications"] if n["type"] == "new_message"), None)
        assert new_msg_notif is not None, f"Expected new_message notification for client, got: {client_msgs_notifs}"
        assert new_msg_notif["title"] == "New Message"
        print("Lawyer message -> Client received 'new_message' notification: SUCCESS")

        print("\n=== STEP 6: Review Received Notification ===")
        # Fast-forward booking to completed
        bk = db.query(Booking).filter(Booking.id == uuid.UUID(booking_id)).first()
        bk.status = "completed"
        bk.completed_at = datetime.now(timezone.utc)
        db.commit()

        review_res = client.post(
            "/api/reviews",
            headers=client_headers,
            json={
                "booking_id": booking_id,
                "rating": 5,
                "comment": "Excellent consultation, very helpful!",
            },
        )
        assert review_res.status_code == 201, f"Review submit failed: {review_res.text}"

        lawyer_reviews_notifs = client.get("/api/notifications", headers=lawyer_headers).json()
        review_notif = next((n for n in lawyer_reviews_notifs["notifications"] if n["type"] == "review_received"), None)
        assert review_notif is not None, f"Expected review_received notification for lawyer, got: {lawyer_reviews_notifs}"
        assert review_notif["title"] == "New Review"
        assert "5-star" in review_notif["message"]
        print("Client review -> Lawyer received 'review_received' notification: SUCCESS")

        print("\nALL NOTIFICATION TESTS PASSED SUCCESSFULLY! (6/6 checks passed)")

    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
