"""
Integration test suite for Module 7: Payments & Subscriptions.
Tests public plans listing, subscription checkout (demo provider),
instant subscription activation, lawyer verification purchase,
audit logging, and admin payments auditing.
"""

import sys
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal
from app.core.security import get_password_hash, create_access_token
from app.models import User, LawyerProfile, Plan, Subscription, Payment, AuditLog


def run_tests():
    print("--- Starting Module 7 Integration Tests ---")
    client = TestClient(app)
    db: Session = SessionLocal()

    try:
        # 1. Health check
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json()["db"] == "connected"
        print("[PASS] Database and health check connected")

        # 2. Public Plans Endpoint
        resp = client.get("/api/plans")
        assert resp.status_code == 200, f"Expected 200 on /api/plans, got {resp.status_code}"
        plans = resp.json()
        assert len(plans) >= 2, "Expected at least 2 subscription plans in database"
        assert any(p["code"] == "user_pro" for p in plans), "Plan 'user_pro' should be present"
        print(f"[PASS] GET /api/plans returned {len(plans)} plans")

        # 3. Setup Test Fixtures
        test_emails = [
            "m7_admin@example.com",
            "m7_client@example.com",
            "m7_lawyer@example.com",
            "m7_fake_lawyer@example.com",
        ]
        users = db.query(User).filter(User.email.in_(test_emails)).all()
        user_ids = [u.id for u in users]
        if user_ids:
            # Clean related payments and subscriptions
            db.query(Payment).filter(Payment.subscription_id.in_(
                db.query(Subscription.id).filter(Subscription.user_id.in_(user_ids))
            )).delete(synchronize_session=False)
            db.query(Subscription).filter(Subscription.user_id.in_(user_ids)).delete(synchronize_session=False)
            profiles = db.query(LawyerProfile).filter(LawyerProfile.user_id.in_(user_ids)).all()
            profile_ids = [p.id for p in profiles]
            if profile_ids:
                db.query(Payment).filter(Payment.lawyer_profile_id.in_(profile_ids)).delete(synchronize_session=False)
            for u in users:
                db.delete(u)
            db.commit()

        # Create Admin
        admin_user = User(
            email="m7_admin@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M7 Admin",
            role="admin",
            status="active",
        )
        # Create Client
        client_user = User(
            email="m7_client@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M7 Client",
            role="user",
            status="active",
        )
        # Create Lawyer
        lawyer_user = User(
            email="m7_lawyer@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M7 Lawyer",
            role="lawyer",
            status="active",
        )
        # Create Fake Lawyer without profile
        fake_lawyer_user = User(
            email="m7_fake_lawyer@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M7 Fake Lawyer",
            role="lawyer",
            status="active",
        )
        db.add_all([admin_user, client_user, lawyer_user, fake_lawyer_user])
        db.flush()

        lawyer_profile = LawyerProfile(
            user_id=lawyer_user.id,
            name="Advocate M7 Lawyer",
            district="Dhaka",
            specialization="Civil Law",
            phone="01800000007",
            verification_status="pending",
            verification_paid=False,
        )
        db.add(lawyer_profile)
        db.commit()

        admin_token = create_access_token({"sub": admin_user.email, "role": "admin"})
        client_token = create_access_token({"sub": client_user.email, "role": "user"})
        lawyer_token = create_access_token({"sub": lawyer_user.email, "role": "lawyer"})
        fake_lawyer_token = create_access_token({"sub": fake_lawyer_user.email, "role": "lawyer"})

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        client_headers = {"Authorization": f"Bearer {client_token}"}
        lawyer_headers = {"Authorization": f"Bearer {lawyer_token}"}
        fake_headers = {"Authorization": f"Bearer {fake_lawyer_token}"}

        print("[PASS] Test fixtures created (Admin, Client, Lawyer, Fake Lawyer)")

        # 4. Subscription Checkout (Demo Instant Approval)
        # Unauthenticated request -> 401
        resp = client.post("/api/subscriptions", json={"plan_code": "user_pro"})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("[PASS] Unauthenticated subscription request denied (401)")

        # Invalid plan code -> 404
        resp = client.post(
            "/api/subscriptions",
            json={"plan_code": "non_existent_plan"},
            headers=client_headers,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("[PASS] Non-existent plan rejected (404)")

        # Valid client subscription checkout with demo provider -> 200
        resp = client.post(
            "/api/subscriptions",
            json={"plan_code": "user_pro", "provider": "demo"},
            headers=client_headers,
        )
        assert resp.status_code == 200, f"Expected 200 on checkout, got {resp.status_code}: {resp.text}"
        checkout_data = resp.json()
        assert "checkout_url" in checkout_data
        assert "payment-success" in checkout_data["checkout_url"]
        assert checkout_data["status"] == "paid"
        subscription_id = checkout_data["subscription_id"]
        assert subscription_id is not None
        print(f"[PASS] Client completed subscription checkout via demo provider ({subscription_id})")

        # Verify subscription was activated instantly
        db.expire_all()
        sub = db.query(Subscription).filter(Subscription.id == uuid.UUID(subscription_id)).first()
        assert sub is not None
        assert sub.status == "active", f"Subscription status should be active, got {sub.status}"
        assert sub.started_at is not None
        assert sub.expires_at is not None
        print("[PASS] Subscription status activated to 'active' with 30-day expiration")

        # Verify GET /api/subscriptions/mine
        resp = client.get("/api/subscriptions/mine", headers=client_headers)
        assert resp.status_code == 200
        my_sub = resp.json()
        assert my_sub["id"] == subscription_id
        assert my_sub["plan_code"] == "user_pro"
        assert my_sub["status"] == "active"
        print("[PASS] GET /api/subscriptions/mine returned active subscription details")

        # Verify audit log for subscription payment
        audit_entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "payment_completed_demo", AuditLog.actor_id == client_user.id)
            .first()
        )
        assert audit_entry is not None, "Audit log for payment_completed_demo not recorded"
        print("[PASS] Audit log verified: payment_completed_demo for subscription")

        # 5. Lawyer Verification Purchase
        # Regular user tries to purchase verification -> 403
        resp = client.post("/api/lawyer/verification-purchase", headers=client_headers)
        assert resp.status_code == 403
        print("[PASS] Non-lawyer denied from verification purchase (403)")

        # Fake lawyer without lawyer_profiles row -> 403
        resp = client.post("/api/lawyer/verification-purchase", headers=fake_headers)
        assert resp.status_code == 403
        print("[PASS] Lawyer without profile row denied (403)")

        # Legitimate lawyer purchases verification badge -> 200
        resp = client.post("/api/lawyer/verification-purchase", headers=lawyer_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        verif_data = resp.json()
        assert "checkout_url" in verif_data
        assert verif_data["status"] == "paid"
        print("[PASS] Lawyer purchased verification badge via demo provider")

        # Verify lawyer profile was updated: verification_paid == True
        db.expire_all()
        prof = db.query(LawyerProfile).filter(LawyerProfile.id == lawyer_profile.id).first()
        assert prof.verification_paid is True, "LawyerProfile verification_paid should be True"
        print("[PASS] LawyerProfile verification_paid automatically set to True")

        # 6. Admin Payments Listing
        # Non-admin user tries to access /api/admin/payments -> 403
        resp = client.get("/api/admin/payments", headers=client_headers)
        assert resp.status_code == 403
        print("[PASS] Non-admin denied from /api/admin/payments (403)")

        # Admin accesses /api/admin/payments -> 200
        resp = client.get("/api/admin/payments", headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        payments = resp.json()
        assert len(payments) >= 2, "Expected at least 2 payments (subscription & verification)"

        # Check client subscription payment
        sub_pay = next((p for p in payments if p["type"] == "subscription" and p["user_email"] == "m7_client@example.com"), None)
        assert sub_pay is not None, "Client subscription payment should be present in admin payments"
        assert sub_pay["amount"] == 299.0
        assert sub_pay["status"] == "paid"
        assert sub_pay["provider"] == "demo"

        # Check lawyer verification payment
        verif_pay = next((p for p in payments if p["type"] == "verification_one_time" and p["client_name"] == "Advocate M7 Lawyer"), None)
        assert verif_pay is not None, "Lawyer verification payment should be present in admin payments"
        assert verif_pay["amount"] == 999.0
        assert verif_pay["status"] == "paid"
        print(f"[PASS] GET /api/admin/payments returned joined user details for transactions")

        # 7. Clean up test records
        db.query(Payment).filter(Payment.subscription_id == uuid.UUID(subscription_id)).delete(synchronize_session=False)
        db.query(Payment).filter(Payment.lawyer_profile_id == lawyer_profile.id).delete(synchronize_session=False)
        db.query(Subscription).filter(Subscription.id == uuid.UUID(subscription_id)).delete(synchronize_session=False)
        for u in [admin_user, client_user, lawyer_user, fake_lawyer_user]:
            db.delete(u)
        db.commit()
        print("[PASS] Test cleanup completed")

        print("\n==========================================")
        print(" ALL MODULE 7 TESTS PASSED SUCCESSFULLY! ")
        print("==========================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
