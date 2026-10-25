"""
Test suite for consultation meeting flow:
1. Lawyer updates meeting settings -> GET meeting-info returns them.
2. Client clicks 'Start Meeting' -> meeting_started_at is set.
3. Lawyer clicks 'Extend' when next slot is free -> extended_minutes = 30.
4. Lawyer clicks 'Extend' when next slot is booked -> 400 error.
5. Lawyer clicks 'End Meeting' -> meeting_ended_at is set.
6. GET /api/lawyers shows presence_status = 'in_consultation' during active meeting.
"""

import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.models import User, LawyerProfile, Booking, Schedule

client = TestClient(app)

def run_tests():
    db = SessionLocal()
    try:
        # 1. Setup a lawyer user and profile
        lawyer_email = f"meeting_lawyer_{uuid.uuid4().hex[:6]}@example.com"
        lawyer_user = User(
            id=uuid.uuid4(),
            email=lawyer_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Adv. Meeting Tester",
            role="lawyer",
            status="active",
        )
        db.add(lawyer_user)
        db.flush()

        lawyer_prof = LawyerProfile(
            id=uuid.uuid4(),
            user_id=lawyer_user.id,
            name="Adv. Meeting Tester",
            verification_status="approved",
            hourly_rate=2000,
        )
        db.add(lawyer_prof)
        db.commit()

        lawyer_token = create_access_token({"sub": lawyer_user.email, "role": "lawyer"})
        lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}

        # 2. Setup a client user
        client_email = f"meeting_client_{uuid.uuid4().hex[:6]}@example.com"
        client_user = User(
            id=uuid.uuid4(),
            email=client_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Consultation Client",
            role="user",
            status="active",
        )
        db.add(client_user)
        db.commit()

        client_token = create_access_token({"sub": client_user.email, "role": "user"})
        client_headers = {"Authorization": f"Bearer {client_token}"}

        # -------------------------------------------------------------
        # TEST 1: Lawyer updates meeting settings -> GET meeting-info
        # -------------------------------------------------------------
        print("\n--- Test 1: Lawyer updates meeting settings -> GET meeting-info returns them ---")
        settings_payload = {
            "meeting_provider": "Google Meet",
            "meeting_link": "https://meet.google.com/abc-defg-hij",
        }
        res_put = client.put(
            "/api/lawyer/me/meeting-settings",
            json=settings_payload,
            headers=lawyer_headers,
        )
        print("PUT /api/lawyer/me/meeting-settings status:", res_put.status_code)
        print("PUT response body:", res_put.json())
        assert res_put.status_code == 200, f"Expected 200, got {res_put.status_code}"
        assert res_put.json().get("meeting_provider") == "Google Meet"
        assert res_put.json().get("meeting_link") == "https://meet.google.com/abc-defg-hij"

        res_info = client.get(f"/api/lawyers/{lawyer_prof.id}/meeting-info")
        print("GET /api/lawyers/{id}/meeting-info status:", res_info.status_code)
        print("GET response body:", res_info.json())
        assert res_info.status_code == 200, f"Expected 200, got {res_info.status_code}"
        assert res_info.json().get("meeting_provider") == "Google Meet"
        assert res_info.json().get("meeting_link") == "https://meet.google.com/abc-defg-hij"
        print("PASS: Lawyer meeting settings successfully updated and retrieved!")

        # -------------------------------------------------------------
        # Setup confirmed booking and schedule slots
        # -------------------------------------------------------------
        sched_curr = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=datetime.now().date() + timedelta(days=1),
            start_time="10:00 AM",
            end_time="10:30 AM",
            is_booked=True,
        )
        db.add(sched_curr)
        db.flush()

        booking = Booking(
            id=uuid.uuid4(),
            user_id=client_user.id,
            lawyer_id=lawyer_prof.id,
            schedule_id=sched_curr.id,
            status="confirmed",
            meeting_link="https://meet.google.com/abc-defg-hij",
        )
        db.add(booking)
        db.commit()

        # Check presence before meeting starts -> should be "available"
        res_lawyer_init = client.get(f"/api/lawyers/{lawyer_prof.id}")
        assert res_lawyer_init.json().get("presence_status") == "available"
        print("Initial presence_status is 'available'")

        # -------------------------------------------------------------
        # TEST 2: Client clicks "Start Meeting" -> meeting_started_at set
        # -------------------------------------------------------------
        print("\n--- Test 2: Client clicks 'Start Meeting' -> meeting_started_at is set ---")
        res_start = client.post(
            f"/api/bookings/{booking.id}/start-meeting",
            headers=client_headers,
        )
        print("POST start-meeting status:", res_start.status_code)
        print("POST start-meeting body:", res_start.json())
        assert res_start.status_code == 200, f"Expected 200, got {res_start.status_code}"
        started_at = res_start.json().get("meeting_started_at")
        assert started_at is not None, "Expected meeting_started_at to be populated"
        print(f"PASS: meeting_started_at is set to {started_at}")

        # -------------------------------------------------------------
        # TEST 3: Presence status shows "in_consultation" during active meeting
        # -------------------------------------------------------------
        print("\n--- Test 3: GET /api/lawyers shows presence_status = 'in_consultation' ---")
        res_lawyers_list = client.get("/api/lawyers")
        matched = [l for l in res_lawyers_list.json() if l["id"] == str(lawyer_prof.id)]
        assert len(matched) == 1, "Lawyer should be in approved list"
        print("presence_status in listing:", matched[0].get("presence_status"))
        assert matched[0].get("presence_status") == "in_consultation"

        res_lawyer_single = client.get(f"/api/lawyers/{lawyer_prof.id}")
        assert res_lawyer_single.json().get("presence_status") == "in_consultation"
        print("PASS: Lawyer presence_status is 'in_consultation'!")

        # -------------------------------------------------------------
        # TEST 4: Lawyer clicks "Extend" when next slot is free -> extended_minutes = 30
        # -------------------------------------------------------------
        print("\n--- Test 4: Lawyer clicks 'Extend' when next slot is free -> extended_minutes = 30 ---")
        # Add next slot: 10:30 AM to 11:00 AM, is_booked = False
        sched_next = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=sched_curr.date,
            start_time="10:30 AM",
            end_time="11:00 AM",
            is_booked=False,
        )
        db.add(sched_next)
        db.commit()

        res_extend_1 = client.post(
            f"/api/bookings/{booking.id}/extend-meeting",
            headers=lawyer_headers,
        )
        print("POST extend-meeting status:", res_extend_1.status_code)
        print("POST extend-meeting body:", res_extend_1.json())
        assert res_extend_1.status_code == 200, f"Expected 200, got {res_extend_1.status_code}"
        assert res_extend_1.json().get("extended_minutes") == 30
        print("PASS: Meeting extended successfully by 30 minutes!")

        # -------------------------------------------------------------
        # TEST 5: Lawyer clicks "Extend" when next slot is booked -> 400 error
        # -------------------------------------------------------------
        print("\n--- Test 5: Lawyer clicks 'Extend' when next slot is booked -> 400 error ---")
        # Add a subsequent slot: 11:00 AM to 11:30 AM, is_booked = True
        sched_booked = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=sched_curr.date,
            start_time="11:00 AM",
            end_time="11:30 AM",
            is_booked=True,
        )
        db.add(sched_booked)
        db.commit()

        res_extend_2 = client.post(
            f"/api/bookings/{booking.id}/extend-meeting",
            headers=lawyer_headers,
        )
        print("POST extend-meeting status:", res_extend_2.status_code)
        print("POST extend-meeting body:", res_extend_2.json())
        assert res_extend_2.status_code == 400, f"Expected 400, got {res_extend_2.status_code}"
        assert res_extend_2.json().get("error") == "next_slot_booked"
        assert "Cannot extend. Your next client starts at" in res_extend_2.json().get("message", "")
        print("PASS: Extension correctly rejected with 400 next_slot_booked!")

        # -------------------------------------------------------------
        # TEST 6: Lawyer clicks "End Meeting" -> meeting_ended_at is set
        # -------------------------------------------------------------
        print("\n--- Test 6: Lawyer clicks 'End Meeting' -> meeting_ended_at is set ---")
        res_end = client.post(
            f"/api/bookings/{booking.id}/end-meeting",
            headers=lawyer_headers,
        )
        print("POST end-meeting status:", res_end.status_code)
        print("POST end-meeting body:", res_end.json())
        assert res_end.status_code == 200, f"Expected 200, got {res_end.status_code}"
        ended_at = res_end.json().get("meeting_ended_at")
        assert ended_at is not None, "Expected meeting_ended_at to be populated"
        print(f"PASS: meeting_ended_at is set to {ended_at}")

        # Check presence status after meeting ended -> should return back to "available"
        res_lawyer_after = client.get(f"/api/lawyers/{lawyer_prof.id}")
        print("presence_status after meeting ended:", res_lawyer_after.json().get("presence_status"))
        assert res_lawyer_after.json().get("presence_status") == "available"
        print("PASS: Presence reverted to 'available' after meeting ended!")

        print("\n================ ALL TEST SCENARIOS PASSED! ================")

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
