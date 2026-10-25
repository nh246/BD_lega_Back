"""
Test suite for direct messaging permissions, read-only threads, and attachments.
"""

import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.models import User, LawyerProfile, Booking, Schedule, ProfileAsset, Plan, Subscription

client = TestClient(app)

def run_tests():
    db = SessionLocal()
    try:
        # Ensure plans exist
        from app.core.plans import ensure_plans_exist
        ensure_plans_exist(db)

        # 1. Fetch or create an approved lawyer
        lawyer_prof = (
            db.query(LawyerProfile)
            .filter(LawyerProfile.verification_status == "approved")
            .first()
        )
        if not lawyer_prof:
            lawyer_user = User(
                id=uuid.uuid4(),
                email=f"test_lawyer_{uuid.uuid4().hex[:6]}@example.com",
                password_hash=get_password_hash("Password123!"),
                full_name="Adv. Test Approved",
                role="lawyer",
                status="active",
            )
            db.add(lawyer_user)
            db.flush()
            lawyer_prof = LawyerProfile(
                id=uuid.uuid4(),
                user_id=lawyer_user.id,
                name="Adv. Test Approved",
                verification_status="approved",
                hourly_rate=2000,
            )
            db.add(lawyer_prof)
            db.commit()

        lawyer_user = db.query(User).filter(User.id == lawyer_prof.user_id).first()
        lawyer_token = create_access_token({"sub": lawyer_user.email, "role": "lawyer"})
        lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}

        # 2. Free user with no booking
        free_user_1 = User(
            id=uuid.uuid4(),
            email=f"free_no_booking_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=get_password_hash("Password123!"),
            full_name="Free User No Booking",
            role="user",
            status="active",
        )
        db.add(free_user_1)
        db.commit()

        free_token_1 = create_access_token({"sub": free_user_1.email, "role": "user"})
        free_headers_1 = {"Authorization": f"Bearer {free_token_1}"}

        print("\n--- Test 1: Free user with no booking -> POST /api/messages/lawyer/{id} -> 403 ---")
        res1 = client.post(
            f"/api/messages/lawyer/{lawyer_prof.id}",
            json={"content": "Hello without booking"},
            headers=free_headers_1,
        )
        print("Status code:", res1.status_code)
        print("Response body:", res1.json())
        assert res1.status_code == 403, f"Expected 403, got {res1.status_code}"
        assert res1.json().get("error") == "no_booking", f"Expected error 'no_booking', got {res1.json()}"
        print("PASS: Free user without booking was rejected with 403 no_booking")

        # 3. Free user with confirmed booking
        free_user_2 = User(
            id=uuid.uuid4(),
            email=f"free_confirmed_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=get_password_hash("Password123!"),
            full_name="Free User Confirmed",
            role="user",
            status="active",
        )
        db.add(free_user_2)
        db.flush()

        sched_1 = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=datetime.now().date() + timedelta(days=2),
            start_time="10:00 AM",
            end_time="10:30 AM",
            is_booked=True,
        )
        db.add(sched_1)
        db.flush()

        booking_confirmed = Booking(
            id=uuid.uuid4(),
            user_id=free_user_2.id,
            lawyer_id=lawyer_prof.id,
            schedule_id=sched_1.id,
            status="confirmed",
        )
        db.add(booking_confirmed)
        db.commit()

        free_token_2 = create_access_token({"sub": free_user_2.email, "role": "user"})
        free_headers_2 = {"Authorization": f"Bearer {free_token_2}"}

        print("\n--- Test 2: Free user with confirmed booking -> POST succeeds (201) ---")
        res2 = client.post(
            f"/api/messages/lawyer/{lawyer_prof.id}",
            json={"content": "Consultation question for our confirmed booking"},
            headers=free_headers_2,
        )
        print("Status code:", res2.status_code)
        print("Response body:", res2.json())
        assert res2.status_code == 201, f"Expected 201, got {res2.status_code}"
        assert res2.json().get("content") == "Consultation question for our confirmed booking"
        print("PASS: Free user with confirmed booking successfully sent message (201)")

        # 4. Pro user -> POST succeeds (no booking needed)
        pro_user = User(
            id=uuid.uuid4(),
            email=f"pro_user_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=get_password_hash("Password123!"),
            full_name="Pro User Test",
            role="user",
            status="active",
        )
        db.add(pro_user)
        db.flush()

        pro_plan = db.query(Plan).filter(Plan.code == "user_pro_monthly").first()
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=pro_user.id,
            plan_id=pro_plan.id,
            status="active",
            started_at=datetime.now(timezone.utc) - timedelta(days=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=29),
        )
        db.add(sub)
        db.commit()

        pro_token = create_access_token({"sub": pro_user.email, "role": "user"})
        pro_headers = {"Authorization": f"Bearer {pro_token}"}

        print("\n--- Test 3: Pro user -> POST succeeds (no booking needed) ---")
        res3 = client.post(
            f"/api/messages/lawyer/{lawyer_prof.id}",
            json={"content": "Hello, I am a Pro member reaching out directly."},
            headers=pro_headers,
        )
        print("Status code:", res3.status_code)
        print("Response body:", res3.json())
        assert res3.status_code == 201, f"Expected 201, got {res3.status_code}"
        print("PASS: Pro user without booking successfully sent message (201)")

        # 5. Completed booking -> POST returns 403 (read-only)
        free_user_completed = User(
            id=uuid.uuid4(),
            email=f"completed_user_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=get_password_hash("Password123!"),
            full_name="Completed Booking User",
            role="user",
            status="active",
        )
        db.add(free_user_completed)
        db.flush()

        sched_completed = Schedule(
            id=uuid.uuid4(),
            lawyer_id=lawyer_prof.id,
            date=datetime.now().date() - timedelta(days=5),
            start_time="02:00 PM",
            end_time="02:30 PM",
            is_booked=True,
        )
        db.add(sched_completed)
        db.flush()

        booking_comp = Booking(
            id=uuid.uuid4(),
            user_id=free_user_completed.id,
            lawyer_id=lawyer_prof.id,
            schedule_id=sched_completed.id,
            status="completed",
        )
        db.add(booking_comp)
        db.commit()

        completed_token = create_access_token({"sub": free_user_completed.email, "role": "user"})
        completed_headers = {"Authorization": f"Bearer {completed_token}"}

        print("\n--- Test 4: Completed booking -> POST returns 403 (read-only) ---")
        res4 = client.post(
            f"/api/messages/lawyer/{lawyer_prof.id}",
            json={"content": "Follow-up question after consultation was completed"},
            headers=completed_headers,
        )
        print("Status code:", res4.status_code)
        print("Response body:", res4.json())
        assert res4.status_code == 403, f"Expected 403, got {res4.status_code}"
        assert res4.json().get("error") == "booking_completed", f"Expected error 'booking_completed', got {res4.json()}"
        print("PASS: Completed booking thread returned 403 booking_completed")

        # 6. Message with 5 attachments -> 400
        # Create 5 assets owned by pro_user
        assets = []
        for i in range(5):
            a = ProfileAsset(
                id=uuid.uuid4(),
                owner_user_id=pro_user.id,
                kind="image" if i % 2 == 0 else "text",
                filename=f"doc_{i}.png",
                mime_type="image/png",
                file_bytes=b"fakebytes",
                size_bytes=9,
            )
            db.add(a)
            assets.append(a)
        db.commit()

        print("\n--- Test 5: Message with 5 attachments -> 400 ---")
        res5 = client.post(
            f"/api/messages/lawyer/{lawyer_prof.id}",
            json={
                "content": "Message with 5 attachments",
                "attachment_asset_ids": [str(a.id) for a in assets],
            },
            headers=pro_headers,
        )
        print("Status code:", res5.status_code)
        print("Response body:", res5.json())
        assert res5.status_code == 400, f"Expected 400, got {res5.status_code}"
        print("PASS: Message with 5 attachments was rejected with 400")

        # 7. Message with 2 attachments -> 201, attachments field populated
        print("\n--- Test 6: Message with 2 attachments -> 201, attachments field populated ---")
        chosen_ids = [str(assets[0].id), str(assets[1].id)]
        res6 = client.post(
            f"/api/messages/lawyer/{lawyer_prof.id}",
            json={
                "content": "Message with 2 attachments",
                "attachment_asset_ids": chosen_ids,
            },
            headers=pro_headers,
        )
        print("Status code:", res6.status_code)
        print("Response body:", res6.json())
        assert res6.status_code == 201, f"Expected 201, got {res6.status_code}"
        returned_attachments = res6.json().get("attachments")
        assert returned_attachments == chosen_ids, f"Expected {chosen_ids}, got {returned_attachments}"
        print("PASS: Message with 2 attachments created (201) and attachments field populated!")

        # 8. Thread retrieval includes attachments field
        print("\n--- Test 7: GET endpoints include attachments field ---")
        res7 = client.get(
            f"/api/messages/lawyer/{lawyer_prof.id}",
            headers=pro_headers,
        )
        print("Status code:", res7.status_code)
        thread = res7.json()
        assert len(thread) >= 2, "Expected messages in thread"
        last_msg = thread[-1]
        assert "attachments" in last_msg, "attachments field must be in serialized message"
        assert last_msg["attachments"] == chosen_ids
        print("PASS: Thread retrieval contains attachments:", last_msg["attachments"])

        # 9. Task 3: Asset Visibility
        print("\n--- Test 8: Asset Visibility in GET /api/assets/{id}/file ---")
        attached_asset_id = chosen_ids[0]

        # 9a. Sender (pro_user) can view file -> 200
        res_sender = client.get(f"/api/assets/{attached_asset_id}/file", headers=pro_headers)
        print("Sender access status:", res_sender.status_code)
        assert res_sender.status_code == 200, f"Sender should have access, got {res_sender.status_code}"

        # 9b. Recipient lawyer can view file -> 200
        res_lawyer = client.get(f"/api/assets/{attached_asset_id}/file", headers=lawyer_headers)
        print("Lawyer recipient access status:", res_lawyer.status_code)
        assert res_lawyer.status_code == 200, f"Lawyer should have access, got {res_lawyer.status_code}"

        # 9c. Third-party user cannot view file -> 404
        res_third = client.get(f"/api/assets/{attached_asset_id}/file", headers=free_headers_1)
        print("Third party access status:", res_third.status_code)
        assert res_third.status_code == 404, f"Third party should get 404, got {res_third.status_code}"

        # 9d. Unauthenticated cannot view file -> 404
        res_unauth = client.get(f"/api/assets/{attached_asset_id}/file")
        print("Unauthenticated access status:", res_unauth.status_code)
        assert res_unauth.status_code == 404, f"Unauthenticated should get 404, got {res_unauth.status_code}"

        print("PASS: Asset visibility rules verified successfully!")

        # 10. Lawyer reply permissions (POST /api/lawyer/messages/{user_id})
        print("\n--- Test 9: Lawyer reply with no booking -> 403 no_active_booking ---")
        res_lawyer_no_bk = client.post(
            f"/api/lawyer/messages/{free_user_1.id}",
            json={"content": "Reply with no booking"},
            headers=lawyer_headers,
        )
        print("Status code:", res_lawyer_no_bk.status_code)
        print("Response body:", res_lawyer_no_bk.json())
        assert res_lawyer_no_bk.status_code == 403, f"Expected 403, got {res_lawyer_no_bk.status_code}"
        assert res_lawyer_no_bk.json().get("error") == "no_active_booking"
        print("PASS: Lawyer reply with no active booking was rejected with 403 no_active_booking")

        print("\n--- Test 10: Lawyer reply with completed booking -> 403 booking_completed ---")
        res_lawyer_completed = client.post(
            f"/api/lawyer/messages/{free_user_completed.id}",
            json={"content": "Reply to completed booking"},
            headers=lawyer_headers,
        )
        print("Status code:", res_lawyer_completed.status_code)
        print("Response body:", res_lawyer_completed.json())
        assert res_lawyer_completed.status_code == 403, f"Expected 403, got {res_lawyer_completed.status_code}"
        assert res_lawyer_completed.json().get("error") == "booking_completed"
        print("PASS: Lawyer reply to completed booking returned 403 booking_completed")

        print("\n--- Test 11: Lawyer reply with confirmed booking -> 201 ---")
        res_lawyer_confirmed = client.post(
            f"/api/lawyer/messages/{free_user_2.id}",
            json={"content": "Thank you for confirming the booking. I look forward to speaking with you."},
            headers=lawyer_headers,
        )
        print("Status code:", res_lawyer_confirmed.status_code)
        print("Response body:", res_lawyer_confirmed.json())
        assert res_lawyer_confirmed.status_code == 201, f"Expected 201, got {res_lawyer_confirmed.status_code}"
        print("PASS: Lawyer reply with confirmed booking succeeded (201)")

        print("\n================ ALL TEST SUITE CHECKS PASSED! ================")

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
