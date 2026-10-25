"""
Verification test script for Consultation Completion Flow and Reviews System.

Covers:
1. Client requests completion -> status "completion_requested".
2. Lawyer confirms -> status "completed".
3. Client submits review (5 stars) -> 201 Created.
4. GET /api/lawyers & GET /api/lawyers/{id} shows avg_rating and review_count.
5. GET /api/lawyers/{id}/reviews returns the review list.
6. Lazy auto-complete: mock a completion_requested_at 49 hours ago -> GET request flips it to "completed".
"""

import sys
import uuid
from datetime import datetime, timezone, timedelta, date
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.models import User, LawyerProfile, Booking, Schedule, Review

client = TestClient(app)


def run_tests():
    db = SessionLocal()
    try:
        print("\n=== STEP 1: Setup Test Accounts & Booking ===")
        # 1. Setup Lawyer
        lawyer_email = f"review_lawyer_{uuid.uuid4().hex[:6]}@example.com"
        lawyer_user = User(
            id=uuid.uuid4(),
            email=lawyer_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Barrister Review Tester",
            role="lawyer",
            status="active",
        )
        db.add(lawyer_user)
        db.flush()

        lawyer_prof = LawyerProfile(
            id=uuid.uuid4(),
            user_id=lawyer_user.id,
            name="Barrister Review Tester",
            verification_status="approved",
            hourly_rate=2500,
            specialization="Corporate Law",
            district="Dhaka",
        )
        db.add(lawyer_prof)
        db.flush()

        lawyer_token = create_access_token({"sub": lawyer_user.email, "role": "lawyer"})
        lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}

        # 2. Setup Client
        client_email = f"review_client_{uuid.uuid4().hex[:6]}@example.com"
        client_user = User(
            id=uuid.uuid4(),
            email=client_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Review Client Tester",
            role="user",
            status="active",
        )
        db.add(client_user)
        db.flush()

        client_token = create_access_token({"sub": client_user.email, "role": "user"})
        client_headers = {"Authorization": f"Bearer {client_token}"}

        # 3. Setup Schedule & Confirmed Booking
        schedule1 = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=date.today(),
            start_time="10:00 AM",
            end_time="10:30 AM",
            is_booked=True,
        )
        db.add(schedule1)
        db.flush()

        booking1 = Booking(
            id=uuid.uuid4(),
            user_id=client_user.id,
            lawyer_id=lawyer_prof.id,
            schedule_id=schedule1.id,
            status="confirmed",
            meeting_started_at=datetime.now(timezone.utc) - timedelta(minutes=45),
            meeting_ended_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        )
        db.add(booking1)
        db.commit()
        print(f"Created confirmed booking: {booking1.id}")

        print("\n=== STEP 2: Client Requests Completion ===")
        res_req = client.post(
            f"/api/bookings/{booking1.id}/request-completion",
            headers=client_headers,
        )
        print(f"Request completion response status: {res_req.status_code}")
        assert res_req.status_code == 200, f"Expected 200, got {res_req.status_code}: {res_req.text}"
        data_req = res_req.json()
        assert data_req["status"] == "completion_requested", f"Expected 'completion_requested', got {data_req['status']}"
        assert data_req["completion_requested_at"] is not None, "completion_requested_at should be set"
        print(f"SUCCESS: status is 'completion_requested', completion_requested_at={data_req['completion_requested_at']}")

        # Verify client cannot confirm their own completion request
        res_self_confirm = client.post(
            f"/api/bookings/{booking1.id}/confirm-completion",
            headers=client_headers,
        )
        assert res_self_confirm.status_code == 400, f"Expected 400 when confirming own request, got {res_self_confirm.status_code}"
        print("SUCCESS: Requester cannot confirm own completion request (400 as expected)")

        print("\n=== STEP 3: Lawyer Confirms Completion ===")
        res_confirm = client.post(
            f"/api/bookings/{booking1.id}/confirm-completion",
            headers=lawyer_headers,
        )
        print(f"Confirm completion response status: {res_confirm.status_code}")
        assert res_confirm.status_code == 200, f"Expected 200, got {res_confirm.status_code}: {res_confirm.text}"
        data_confirm = res_confirm.json()
        assert data_confirm["status"] == "completed", f"Expected 'completed', got {data_confirm['status']}"
        assert data_confirm["completed_at"] is not None, "completed_at should be set"
        print(f"SUCCESS: status is 'completed', completed_at={data_confirm['completed_at']}")

        print("\n=== STEP 4: Client Submits Review (5 Stars) ===")
        review_payload = {
            "booking_id": str(booking1.id),
            "rating": 5,
            "comment": "Outstanding legal consultation! Very thorough and professional.",
        }
        res_rev = client.post(
            "/api/reviews",
            json=review_payload,
            headers=client_headers,
        )
        print(f"Submit review response status: {res_rev.status_code}")
        assert res_rev.status_code == 201, f"Expected 201, got {res_rev.status_code}: {res_rev.text}"
        data_rev = res_rev.json()
        assert data_rev["rating"] == 5, f"Expected rating 5, got {data_rev['rating']}"
        assert data_rev["reviewee_id"] == str(lawyer_user.id), f"Expected reviewee {lawyer_user.id}, got {data_rev['reviewee_id']}"
        assert data_rev["reviewer_name"] == "Review Client Tester"
        print(f"SUCCESS: Review submitted (201 Created): rating={data_rev['rating']}, reviewee={data_rev['reviewee_id']}")

        # Verify duplicate review is rejected
        res_dup = client.post(
            "/api/reviews",
            json=review_payload,
            headers=client_headers,
        )
        assert res_dup.status_code == 400, f"Expected 400 on duplicate review, got {res_dup.status_code}"
        print("SUCCESS: Duplicate review correctly rejected with 400 Bad Request")

        print("\n=== STEP 5: Verify Lawyer Reviews Endpoint ===")
        res_lawyer_revs = client.get(f"/api/lawyers/{lawyer_prof.id}/reviews")
        assert res_lawyer_revs.status_code == 200, f"Expected 200, got {res_lawyer_revs.status_code}"
        revs_list = res_lawyer_revs.json()
        assert len(revs_list) == 1, f"Expected 1 review, got {len(revs_list)}"
        assert revs_list[0]["rating"] == 5
        assert revs_list[0]["comment"] == "Outstanding legal consultation! Very thorough and professional."
        print(f"SUCCESS: GET /api/lawyers/{lawyer_prof.id}/reviews returns {len(revs_list)} review(s)")

        print("\n=== STEP 6: Lawyer Enrichment (GET /api/lawyers & GET /api/lawyers/{id}) ===")
        res_lawyer_detail = client.get(f"/api/lawyers/{lawyer_prof.id}")
        assert res_lawyer_detail.status_code == 200, f"Expected 200, got {res_lawyer_detail.status_code}"
        detail_data = res_lawyer_detail.json()
        assert detail_data["avg_rating"] == 5.0, f"Expected avg_rating 5.0, got {detail_data['avg_rating']}"
        assert detail_data["review_count"] == 1, f"Expected review_count 1, got {detail_data['review_count']}"
        print(f"SUCCESS: GET /api/lawyers/{lawyer_prof.id} shows avg_rating={detail_data['avg_rating']}, review_count={detail_data['review_count']}")

        # Also check public listing
        res_lawyers_list = client.get("/api/lawyers?district=Dhaka")
        assert res_lawyers_list.status_code == 200
        found = [l for l in res_lawyers_list.json() if l["id"] == str(lawyer_prof.id)]
        assert len(found) == 1
        assert found[0]["avg_rating"] == 5.0
        assert found[0]["review_count"] == 1
        print(f"SUCCESS: GET /api/lawyers shows lawyer with avg_rating={found[0]['avg_rating']}, review_count={found[0]['review_count']}")

        print("\n=== STEP 7: Lazy Auto-Complete ===")
        # Create a second booking with completion_requested_at mocked to 49 hours ago
        schedule2 = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=date.today() - timedelta(days=3),
            start_time="02:00 PM",
            end_time="02:30 PM",
            is_booked=True,
        )
        db.add(schedule2)
        db.flush()

        past_req_time = datetime.now(timezone.utc) - timedelta(hours=49)
        booking2 = Booking(
            id=uuid.uuid4(),
            user_id=client_user.id,
            lawyer_id=lawyer_prof.id,
            schedule_id=schedule2.id,
            status="completion_requested",
            completion_requested_at=past_req_time,
        )
        db.add(booking2)
        db.commit()
        print(f"Created booking2 with status='completion_requested' and completion_requested_at={past_req_time.isoformat()}")

        # Call GET /api/bookings/{id}
        res_lazy = client.get(f"/api/bookings/{booking2.id}", headers=client_headers)
        assert res_lazy.status_code == 200, f"Expected 200, got {res_lazy.status_code}: {res_lazy.text}"
        data_lazy = res_lazy.json()
        assert data_lazy["status"] == "completed", f"Expected lazy auto-complete to flip status to 'completed', got {data_lazy['status']}"
        assert data_lazy["completed_at"] is not None, "completed_at should be set after lazy auto-complete"
        print(f"SUCCESS: Lazy auto-complete flipped status to 'completed', completed_at={data_lazy['completed_at']}")

        # Verify persistence in database
        db.expire_all()
        db_booking2 = db.query(Booking).filter(Booking.id == booking2.id).first()
        assert db_booking2.status == "completed", f"DB status expected 'completed', got {db_booking2.status}"
        assert db_booking2.completed_at is not None
        print("SUCCESS: Database persistence confirmed for lazy auto-complete!")

        print("\n==========================================")
        print("ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("==========================================\n")
    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
