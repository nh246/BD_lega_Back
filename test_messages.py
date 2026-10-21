"""
Integration tests for Pro Direct Messaging Channel.
"""

import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal
from app.core.security import get_password_hash, create_access_token
from app.models import User, LawyerProfile, Plan, Subscription, DirectMessage


def test_direct_messaging():
    print("--- Starting Direct Messaging Channel Integration Tests ---")
    client = TestClient(app)
    db: Session = SessionLocal()

    try:
        # 1. Setup Fixtures
        # Clean up existing test data
        test_emails = [
            "msg_free_user@example.com",
            "msg_pro_user@example.com",
            "msg_lawyer@example.com",
            "msg_unapproved@example.com",
        ]
        existing = db.query(User).filter(User.email.in_(test_emails)).all()
        for u in existing:
            db.query(DirectMessage).filter(DirectMessage.sender_user_id == u.id).delete()
            db.query(DirectMessage).filter(DirectMessage.recipient_user_id == u.id).delete()
            db.query(Subscription).filter(Subscription.user_id == u.id).delete()
            db.query(LawyerProfile).filter(LawyerProfile.user_id == u.id).delete()
            db.delete(u)
        db.commit()

        # Free User
        free_user = User(
            id=uuid.uuid4(),
            email="msg_free_user@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Free Citizen",
            role="user",
            status="active",
        )
        # Pro User
        pro_user = User(
            id=uuid.uuid4(),
            email="msg_pro_user@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Pro Citizen",
            role="user",
            status="active",
        )
        # Lawyer User
        lawyer_user = User(
            id=uuid.uuid4(),
            email="msg_lawyer@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Advocate Test",
            role="lawyer",
            status="active",
        )
        db.add_all([free_user, pro_user, lawyer_user])
        db.flush()

        # Approved Lawyer Profile
        lawyer_profile = LawyerProfile(
            id=uuid.uuid4(),
            user_id=lawyer_user.id,
            name="Advocate Test Profile",
            verification_status="approved",
            verification_paid=True,
        )
        db.add(lawyer_profile)

        # Pro Plan & Subscription for Pro User
        pro_plan = db.query(Plan).filter(Plan.code == "user_pro").first()
        if not pro_plan:
            pro_plan = Plan(code="user_pro", name="Pro Plan", price_monthly=299.0)
            db.add(pro_plan)
            db.flush()

        pro_sub = Subscription(
            id=uuid.uuid4(),
            user_id=pro_user.id,
            plan_id=pro_plan.id,
            status="active",
        )
        db.add(pro_sub)
        db.commit()

        # Tokens
        free_token = create_access_token({"sub": free_user.email, "role": "user"})
        pro_token = create_access_token({"sub": pro_user.email, "role": "user"})
        lawyer_token = create_access_token({"sub": lawyer_user.email, "role": "lawyer"})

        free_headers = {"Authorization": f"Bearer {free_token}"}
        pro_headers = {"Authorization": f"Bearer {pro_token}"}
        lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}

        # 2. Free User Attempts to send message -> 402 Payment Required
        resp = client.post(
            f"/api/messages/lawyer/{lawyer_profile.id}",
            json={"content": "Hello lawyer, I have a query."},
            headers=free_headers,
        )
        assert resp.status_code == 402, f"Expected 402 for free user, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("error") == "pro_required", f"Expected error: pro_required, got {data}"
        assert "Direct messaging with verified lawyers is a Pro feature." in str(data), f"Wrong message: {data}"
        print("[PASS] Free user POST /api/messages/lawyer/{id} -> 402 with pro_required")

        # 3. Unapproved lawyer -> 404
        unapproved_user = User(
            id=uuid.uuid4(),
            email="msg_unapproved@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Pending Lawyer User",
            role="lawyer",
            status="active",
        )
        db.add(unapproved_user)
        db.flush()

        unapproved_profile = LawyerProfile(
            id=uuid.uuid4(),
            user_id=unapproved_user.id,
            name="Pending Lawyer",
            verification_status="pending",
        )
        db.add(unapproved_profile)
        db.commit()

        resp = client.post(
            f"/api/messages/lawyer/{unapproved_profile.id}",
            json={"content": "Hello pending lawyer"},
            headers=pro_headers,
        )
        assert resp.status_code == 404, f"Expected 404 for unapproved lawyer, got {resp.status_code}"
        print("[PASS] Messaging unapproved lawyer -> 404 Not Found")

        # 4. Pro user sends direct message -> 201 Created
        resp = client.post(
            f"/api/messages/lawyer/{lawyer_profile.id}",
            json={"content": "Hello Advocate, I need urgent advice on property law."},
            headers=pro_headers,
        )
        assert resp.status_code == 201, f"Expected 201 for Pro user message, got {resp.status_code}: {resp.text}"
        msg_data = resp.json()
        assert msg_data["content"] == "Hello Advocate, I need urgent advice on property law."
        assert msg_data["sender_user_id"] == str(pro_user.id)
        assert msg_data["is_read"] is False
        print("[PASS] Pro user successfully sent direct message (201)")

        # 5. Lawyer inbox reflects conversation & unread count
        resp = client.get("/api/lawyer/messages", headers=lawyer_headers)
        assert resp.status_code == 200, f"Expected 200 on inbox, got {resp.status_code}"
        inbox = resp.json()
        assert len(inbox) == 1, f"Expected 1 conversation in inbox, got {len(inbox)}"
        assert inbox[0]["user_id"] == str(pro_user.id)
        assert inbox[0]["name"] == "Pro Citizen"
        assert inbox[0]["unread_count"] == 1
        assert "property law" in inbox[0]["last_message"]
        print("[PASS] Lawyer inbox shows citizen conversation with unread badge")

        # 6. Lawyer retrieves thread with citizen -> marks read
        resp = client.get(f"/api/lawyer/messages/{pro_user.id}", headers=lawyer_headers)
        assert resp.status_code == 200, f"Expected 200 on thread, got {resp.status_code}"
        thread = resp.json()
        assert len(thread) == 1
        assert thread[0]["content"] == "Hello Advocate, I need urgent advice on property law."
        print("[PASS] Lawyer retrieved thread and marked incoming message read")

        # Verify unread count is now 0 in inbox
        resp = client.get("/api/lawyer/messages", headers=lawyer_headers)
        assert resp.json()[0]["unread_count"] == 0
        print("[PASS] Lawyer inbox unread count updated to 0")

        # 7. Lawyer replies to citizen
        resp = client.post(
            f"/api/lawyer/messages/{pro_user.id}",
            json={"content": "Please share your title deed and land records for review."},
            headers=lawyer_headers,
        )
        assert resp.status_code == 201, f"Expected 201 on reply, got {resp.status_code}: {resp.text}"
        reply_data = resp.json()
        assert reply_data["content"] == "Please share your title deed and land records for review."
        print("[PASS] Lawyer replied to citizen (201)")

        # 8. Citizen views conversation thread with lawyer
        resp = client.get(f"/api/messages/lawyer/{lawyer_profile.id}", headers=pro_headers)
        assert resp.status_code == 200
        client_thread = resp.json()
        assert len(client_thread) == 2, f"Expected 2 messages in thread, got {len(client_thread)}"
        assert client_thread[0]["sender_user_id"] == str(pro_user.id)
        assert client_thread[1]["sender_user_id"] == str(lawyer_user.id)
        assert client_thread[1]["content"] == "Please share your title deed and land records for review."
        print("[PASS] Citizen thread shows full conversation including lawyer reply")

        print("\n==========================================")
        print(" ALL DIRECT MESSAGING TESTS PASSED (100%) ")
        print("==========================================")

    finally:
        db.close()


if __name__ == "__main__":
    test_direct_messaging()
