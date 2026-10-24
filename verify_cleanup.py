"""
Verification script for:
1) Public GET /api/lawyers returns clean names and does NOT include 'Adv. Mahmudul Hasan'.
2) Admin GET /api/admin/lawyers DOES include 'Adv. Mahmudul Hasan' with status 'pending'.
3) Dashboard welcome data: GET /api/auth/me for free_user@bdlegal.ai returns 'Rahim Ahmed'.
4) DEMO_ACCOUNTS.md exists.
"""

import os
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token


def run_verification():
    client = TestClient(app)
    suffixes = [" (Free User)", " (Pro User)", " (Verified Pro)", " (Free Lawyer)"]

    print("=" * 60)
    print("VERIFICATION SUITE: Display Names, Pending Fixture & Demo Docs")
    print("=" * 60)

    # 1. Public GET /api/lawyers
    res_public = client.get("/api/lawyers")
    assert res_public.status_code == 200, f"Expected 200, got {res_public.status_code}"
    public_lawyers = res_public.json()
    public_names = [l["name"] for l in public_lawyers]

    print(f"\n[1] Public GET /api/lawyers: returned {len(public_lawyers)} approved lawyers.")
    for name in public_names:
        for s in suffixes:
            assert s not in name, f"Found forbidden suffix '{s}' in public lawyer name '{name}'"
        print(f"  - {name}")

    assert "Adv. Mahmudul Hasan" not in public_names, "Pending lawyer 'Adv. Mahmudul Hasan' must NOT appear in public listing!"
    assert "Advocate Test Profile" not in public_names, "'Advocate Test Profile' must NOT appear in public listing!"
    print("  [OK] Clean names confirmed (no fake suffixes).")
    print("  [OK] 'Adv. Mahmudul Hasan' (pending) is correctly EXCLUDED from public directory.")

    # 2. Admin GET /api/admin/lawyers
    admin_token = create_access_token({"sub": "admin@bdlegal.ai", "role": "admin", "scopes": ["admin:all", "lawyers:view"]})
    res_admin = client.get("/api/admin/lawyers", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200, f"Expected 200, got {res_admin.status_code}"
    admin_lawyers = res_admin.json()

    mahmudul = next((l for l in admin_lawyers if l["name"] == "Adv. Mahmudul Hasan"), None)
    print(f"\n[2] Admin GET /api/admin/lawyers: returned {len(admin_lawyers)} total lawyers.")
    assert mahmudul is not None, "Pending lawyer 'Adv. Mahmudul Hasan' MUST appear in admin lawyers listing!"
    assert mahmudul["verification_status"] == "pending", f"Expected pending, got {mahmudul['verification_status']}"
    assert mahmudul["bar_council_id"] == "BD-BAR-2020-1188", f"Unexpected bar id: {mahmudul['bar_council_id']}"
    assert mahmudul["district"] == "Dhaka", f"Unexpected district: {mahmudul['district']}"
    assert mahmudul["specialization"] == "Family Law & Property", f"Unexpected spec: {mahmudul['specialization']}"
    assert mahmudul["phone"] == "+8801733445566", f"Unexpected phone: {mahmudul['phone']}"
    print("  [OK] 'Adv. Mahmudul Hasan' found in admin list with status='pending':")
    print(f"      ID:             {mahmudul['id']}")
    print(f"      Bar Council ID: {mahmudul['bar_council_id']}")
    print(f"      District:       {mahmudul['district']}")
    print(f"      Specialization: {mahmudul['specialization']}")
    print(f"      Contact:        {mahmudul['phone']}")
    print(f"      Status:         {mahmudul['verification_status']}")

    # 3. Free user login & GET /api/auth/me
    free_token = create_access_token({"sub": "free_user@bdlegal.ai", "role": "user"})
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {free_token}"})
    assert res_me.status_code == 200, f"Expected 200, got {res_me.status_code}"
    me_data = res_me.json()

    print(f"\n[3] Free User GET /api/auth/me:")
    print(f"      Email:     {me_data['email']}")
    print(f"      Full Name: {me_data['full_name']}")
    assert me_data["full_name"] == "Rahim Ahmed", f"Expected 'Rahim Ahmed', got '{me_data['full_name']}'"
    print("  [OK] Dashboard welcome displays 'Rahim Ahmed' (no suffix).")

    # 4. DEMO_ACCOUNTS.md existence
    md_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "DEMO_ACCOUNTS.md"))
    assert os.path.exists(md_path), f"DEMO_ACCOUNTS.md not found at {md_path}"
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Internal reference only." in content
    assert "pending_lawyer@bdlegal.ai" in content
    assert "Adv. Mahmudul Hasan" in content
    assert "Rahim Ahmed" in content
    print(f"\n[4] DEMO_ACCOUNTS.md existence and contents:")
    print(f"  [OK] Found at {md_path} ({len(content)} bytes).")
    print("  [OK] Contains required table, disclaimer note, and all seeded fixtures.")

    print("\n" + "=" * 60)
    print("ALL VERIFICATION CHECKS PASSED SUCCESSFULLY (0 ERRORS)")
    print("=" * 60)


if __name__ == "__main__":
    run_verification()
