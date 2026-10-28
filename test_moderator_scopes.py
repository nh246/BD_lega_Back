import sys
import uuid
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.models import User

client = TestClient(app)

def run_tests():
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:6]
        
        # 1. Setup Admin user
        admin_user = User(
            id=uuid.uuid4(),
            email=f"admin_{suffix}@test.com",
            password_hash=get_password_hash("Password123!"),
            full_name=f"Admin {suffix}",
            role="admin",
            status="active",
            scopes=[],
        )
        db.add(admin_user)

        # 2. Setup Moderator user with [users:view, lawyers:view]
        mod_user = User(
            id=uuid.uuid4(),
            email=f"mod_{suffix}@test.com",
            password_hash=get_password_hash("Password123!"),
            full_name=f"Moderator {suffix}",
            role="moderator",
            status="active",
            scopes=["users:view", "lawyers:view"],
        )
        db.add(mod_user)

        # 3. Setup Target Moderator to test demote
        target_mod = User(
            id=uuid.uuid4(),
            email=f"target_mod_{suffix}@test.com",
            password_hash=get_password_hash("Password123!"),
            full_name=f"Target Mod {suffix}",
            role="moderator",
            status="active",
            scopes=["users:view"],
        )
        db.add(target_mod)
        db.commit()

        # Generate tokens (sub = email as used in auth)
        admin_token = create_access_token({"sub": admin_user.email})
        mod_token = create_access_token({"sub": mod_user.email})

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        mod_headers = {"Authorization": f"Bearer {mod_token}"}

        print("--- Running TestClient Moderator Scope & Security Verifications ---")

        # Test 1: Moderator with [users:view, lawyers:view] GET /api/admin/moderators -> 403
        res = client.get("/api/admin/moderators", headers=mod_headers)
        print(f"1. Moderator GET /api/admin/moderators: status = {res.status_code}")
        assert res.status_code == 403, f"Expected 403, got {res.status_code}"

        # Test 2: Moderator POST /api/admin/moderators/{id}/demote -> 403
        res = client.post(f"/api/admin/moderators/{target_mod.id}/demote", headers=mod_headers)
        print(f"2. Moderator POST /api/admin/moderators/{{id}}/demote: status = {res.status_code}")
        assert res.status_code == 403, f"Expected 403, got {res.status_code}"

        # Test 3a: Moderator with [users:view, lawyers:view] GET /api/admin/users -> 200
        res = client.get("/api/admin/users", headers=mod_headers)
        print(f"3a. Moderator GET /api/admin/users (has users:view): status = {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"

        # Test 3b: Moderator without queries:view GET /api/admin/queries -> 403
        res = client.get("/api/admin/queries", headers=mod_headers)
        print(f"3b. Moderator GET /api/admin/queries (missing queries:view): status = {res.status_code}")
        assert res.status_code == 403, f"Expected 403, got {res.status_code}"

        # Test 4: Admin GET /api/admin/moderators -> 200
        res = client.get("/api/admin/moderators", headers=admin_headers)
        print(f"4. Admin GET /api/admin/moderators: status = {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"

        # Cleanup
        db.delete(admin_user)
        db.delete(mod_user)
        db.delete(target_mod)
        db.commit()

        print("\n>>> ALL TESTCLIENT MODERATOR SCOPE TESTS PASSED! <<<")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
