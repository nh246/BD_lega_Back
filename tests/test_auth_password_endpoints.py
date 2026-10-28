import os
import sys
import uuid
import datetime
from datetime import timedelta, timezone

sys.path.insert(0, os.path.abspath('backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models import User, AuditLog
from app.core.security import get_password_hash, create_password_reset_token

client = TestClient(app)

def test_password_flows():
    db = SessionLocal()
    test_email = f"pwd_test_{uuid.uuid4().hex[:8]}@example.com"
    original_pwd = "InitialPassword123!"
    changed_pwd = "ChangedPassword123!"
    reset_pwd = "ResetFinalPassword123!"

    # 1. Create a test user
    test_user = User(
        id=uuid.uuid4(),
        email=test_email,
        password_hash=get_password_hash(original_pwd),
        full_name="Password Test User",
        role="user",
        status="active",
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)
    print(f"1. Created test user: {test_email}")

    try:
        # 2. Login to get auth token
        login_resp = client.post("/api/auth/login", json={"email": test_email, "password": original_pwd})
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        access_token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        print("2. Logged in successfully and obtained Bearer token.")

        # 3. Test POST /api/auth/change-password with wrong current -> 400
        wrong_resp = client.post(
            "/api/auth/change-password",
            json={"current_password": "WrongPassword!", "new_password": changed_pwd},
            headers=headers,
        )
        print(f"3. Change password with wrong current status: {wrong_resp.status_code}, body: {wrong_resp.json()}")
        assert wrong_resp.status_code == 400, f"Expected 400, got {wrong_resp.status_code}"
        assert wrong_resp.json().get("error") == "current_password_incorrect"

        # 4. Test POST /api/auth/change-password with correct current -> 200 + audit row
        correct_resp = client.post(
            "/api/auth/change-password",
            json={"current_password": original_pwd, "new_password": changed_pwd},
            headers=headers,
        )
        print(f"4. Change password with correct current status: {correct_resp.status_code}, body: {correct_resp.json()}")
        assert correct_resp.status_code == 200, f"Expected 200, got {correct_resp.status_code}"
        assert "successfully" in correct_resp.json().get("message", "").lower()

        # Verify audit row 'password_changed'
        db.expire_all()
        audit_change = (
            db.query(AuditLog)
            .filter(AuditLog.actor_id == test_user.id, AuditLog.action == "password_changed")
            .first()
        )
        assert audit_change is not None, "Audit row for 'password_changed' must exist"
        print(f">> Verified audit log created: id={audit_change.id}, action={audit_change.action}")

        # Verify login with new changed password works
        new_login = client.post("/api/auth/login", json={"email": test_email, "password": changed_pwd})
        assert new_login.status_code == 200, "Login with changed password failed"

        # 5. Test POST /api/auth/forgot-password -> 200 + reset_url returned (demo mode)
        forgot_resp = client.post("/api/auth/forgot-password", json={"email": test_email})
        print(f"5. Forgot password status: {forgot_resp.status_code}, body: {forgot_resp.json()}")
        assert forgot_resp.status_code == 200, f"Expected 200, got {forgot_resp.status_code}"
        data = forgot_resp.json()
        assert "reset_url" in data, f"Demo mode must return reset_url: {data}"
        assert "/reset-password?token=" in data["reset_url"]
        reset_token = data["reset_url"].split("token=")[1]

        # Verify user in DB has reset_token and reset_token_expires_at
        db.expire_all()
        user_in_db = db.query(User).filter(User.id == test_user.id).first()
        assert user_in_db.reset_token == reset_token
        assert user_in_db.reset_token_expires_at is not None
        print(f">> Verified DB reset_token set for user: {user_in_db.reset_token[:20]}...")

        # Verify audit row 'password_reset_requested'
        audit_forgot = (
            db.query(AuditLog)
            .filter(AuditLog.actor_id == test_user.id, AuditLog.action == "password_reset_requested")
            .first()
        )
        assert audit_forgot is not None, "Audit row for 'password_reset_requested' must exist"
        print(f">> Verified audit log created: id={audit_forgot.id}, action={audit_forgot.action}")

        # Non-existing user test: returns 200 without leaking existence
        non_exist_resp = client.post("/api/auth/forgot-password", json={"email": "nonexistent_random_user_999@example.com"})
        assert non_exist_resp.status_code == 200
        assert "reset_url" not in non_exist_resp.json(), "Must not return reset_url for non-existent email"
        print(">> Verified non-existent email does not leak user existence.")

        # 6. Test POST /api/auth/reset-password with expired token -> 400
        expired_token = create_password_reset_token(test_email, expires_delta=timedelta(minutes=-10))
        expired_resp = client.post(
            "/api/auth/reset-password",
            json={"token": expired_token, "new_password": reset_pwd},
        )
        print(f"6. Reset password with expired token status: {expired_resp.status_code}, body: {expired_resp.json()}")
        assert expired_resp.status_code == 400, f"Expected 400, got {expired_resp.status_code}"
        assert expired_resp.json().get("error") == "invalid_or_expired_token"

        # 7. Test POST /api/auth/reset-password with invalid / tampered token -> 400
        invalid_resp = client.post(
            "/api/auth/reset-password",
            json={"token": "invalid.jwt.token.here", "new_password": reset_pwd},
        )
        assert invalid_resp.status_code == 400
        assert invalid_resp.json().get("error") == "invalid_or_expired_token"
        print(">> Verified invalid token correctly returns 400 invalid_or_expired_token.")

        # 8. Test POST /api/auth/reset-password with valid token -> 200 + password updated
        valid_reset_resp = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "new_password": reset_pwd},
        )
        print(f"8. Reset password with valid token status: {valid_reset_resp.status_code}, body: {valid_reset_resp.json()}")
        assert valid_reset_resp.status_code == 200, f"Expected 200, got {valid_reset_resp.status_code}"
        assert "successful" in valid_reset_resp.json().get("message", "").lower()

        # Verify DB: reset_token cleared
        db.expire_all()
        user_after_reset = db.query(User).filter(User.id == test_user.id).first()
        assert user_after_reset.reset_token is None, "reset_token must be cleared after reset"
        print(">> Verified reset_token cleared in DB.")

        # Verify audit row 'password_reset_completed'
        audit_reset = (
            db.query(AuditLog)
            .filter(AuditLog.actor_id == test_user.id, AuditLog.action == "password_reset_completed")
            .first()
        )
        assert audit_reset is not None, "Audit row for 'password_reset_completed' must exist"
        print(f">> Verified audit log created: id={audit_reset.id}, action={audit_reset.action}")

        # Verify user can log in with new reset password
        final_login = client.post("/api/auth/login", json={"email": test_email, "password": reset_pwd})
        assert final_login.status_code == 200, f"Login with reset password failed: {final_login.text}"
        print(">> Verified login succeeds with new reset password!")

        # Verify old password no longer works
        old_login = client.post("/api/auth/login", json={"email": test_email, "password": changed_pwd})
        assert old_login.status_code == 401, "Old password must no longer work"
        print(">> Verified old password no longer works (returns 401).")

        # Verify reusing the same reset token fails (since user.reset_token was cleared)
        reuse_resp = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "new_password": "AnotherPassword123!"},
        )
        assert reuse_resp.status_code == 400
        assert reuse_resp.json().get("error") == "invalid_or_expired_token"
        print(">> Verified reused token is rejected (returns 400).")

        print("\nALL TESTCLIENT VERIFICATIONS PASSED SUCCESSFULLY!")

    finally:
        # Cleanup test user and audit logs
        db.query(AuditLog).filter(AuditLog.actor_id == test_user.id).delete()
        db.query(User).filter(User.id == test_user.id).delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    test_password_flows()

