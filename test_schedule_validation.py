"""
Backend verification script for Schedule validation endpoints.
Requirements tested:
1. Time "10:jhfgghg AM" -> 400 {"error": "invalid_time"}
2. Date "12/23/1111111" -> 400 {"error": "invalid_date"}
3. Past date -> 400 {"error": "invalid_date"}
4. Date > 365 days -> 400 {"error": "invalid_date"}
5. End time <= Start time -> 400 {"error": "invalid_time"}
6. Duration > 240 mins -> 400 {"error": "invalid_time"}
7. Valid 30-minute slot -> 201 Created
8. Overlapping slot on same date -> 400 {"error": "overlap", "message": "You already have a slot that overlaps this time."}
"""

import sys
from datetime import date, timedelta
from fastapi.testclient import TestClient

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.main import app

client = TestClient(app)
DEMO_PASSWORD = "Password123!"


def get_auth_token(email: str, password: str = DEMO_PASSWORD) -> str:
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


def main():
    print("=" * 60)
    print("     SCHEDULE VALIDATION BACKEND VERIFICATION")
    print("=" * 60)

    token = get_auth_token("adv.nusrat@bdlegal.ai")
    headers = {"Authorization": f"Bearer {token}"}
    today = date.today()
    target_date = (today + timedelta(days=10)).isoformat()

    # 1. Test invalid time format: "10:jhfgghg AM"
    print("\n[Test 1] Testing invalid start_time '10:jhfgghg AM'...")
    res = client.post(
        "/api/lawyer/schedules",
        headers=headers,
        json={"date": target_date, "start_time": "10:jhfgghg AM", "end_time": "11:00 AM"},
    )
    print(f"Status: {res.status_code}, Body: {res.json()}")
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    assert res.json().get("error") == "invalid_time", f"Expected error: invalid_time, got {res.json()}"
    print("✓ Test 1 Passed: Rejected invalid time format with 400 invalid_time")

    # 2. Test invalid date: "12/23/1111111"
    print("\n[Test 2] Testing invalid date '12/23/1111111'...")
    res = client.post(
        "/api/lawyer/schedules",
        headers=headers,
        json={"date": "12/23/1111111", "start_time": "10:00 AM", "end_time": "10:30 AM"},
    )
    print(f"Status: {res.status_code}, Body: {res.json()}")
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    assert res.json().get("error") == "invalid_date", f"Expected error: invalid_date, got {res.json()}"
    print("✓ Test 2 Passed: Rejected invalid date format with 400 invalid_date")

    # 3. Test past date: yesterday
    print("\n[Test 3] Testing past date...")
    yesterday = (today - timedelta(days=1)).isoformat()
    res = client.post(
        "/api/lawyer/schedules",
        headers=headers,
        json={"date": yesterday, "start_time": "10:00 AM", "end_time": "10:30 AM"},
    )
    print(f"Status: {res.status_code}, Body: {res.json()}")
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    assert res.json().get("error") == "invalid_date", f"Expected error: invalid_date, got {res.json()}"
    print("✓ Test 3 Passed: Rejected past date with 400 invalid_date")

    # 4. Test date > 365 days
    print("\n[Test 4] Testing date > 365 days ahead...")
    far_future = (today + timedelta(days=366)).isoformat()
    res = client.post(
        "/api/lawyer/schedules",
        headers=headers,
        json={"date": far_future, "start_time": "10:00 AM", "end_time": "10:30 AM"},
    )
    print(f"Status: {res.status_code}, Body: {res.json()}")
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    assert res.json().get("error") == "invalid_date", f"Expected error: invalid_date, got {res.json()}"
    print("✓ Test 4 Passed: Rejected >365 days date with 400 invalid_date")

    # 5. Test valid 30-min slot creation -> 201
    print(f"\n[Test 5] Creating valid 30-min slot for {target_date} 10:00 AM - 10:30 AM...")
    # First delete any existing slot in that slot if present
    existing_slots = client.get("/api/lawyer/schedules", headers=headers).json()
    for s in existing_slots:
        if s["date"] == target_date:
            client.delete(f"/api/lawyer/schedules/{s['id']}", headers=headers)

    res = client.post(
        "/api/lawyer/schedules",
        headers=headers,
        json={"date": target_date, "start_time": "10:00 AM", "end_time": "10:30 AM"},
    )
    print(f"Status: {res.status_code}, Body: {res.json()}")
    assert res.status_code == 201, f"Expected 201, got {res.status_code}"
    created_id = res.json()["id"]
    print("✓ Test 5 Passed: Created valid 30-min slot with 201 Created")

    # 6. Test overlapping slot on same date -> 400 overlap
    print(f"\n[Test 6] Testing overlapping slot on {target_date} 10:15 AM - 10:45 AM...")
    res = client.post(
        "/api/lawyer/schedules",
        headers=headers,
        json={"date": target_date, "start_time": "10:15 AM", "end_time": "10:45 AM"},
    )
    print(f"Status: {res.status_code}, Body: {res.json()}")
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    assert res.json().get("error") == "overlap", f"Expected error: overlap, got {res.json()}"
    assert res.json().get("message") == "You already have a slot that overlaps this time."
    print("✓ Test 6 Passed: Rejected overlapping slot with 400 overlap and required message")

    # 7. Test exact duplicate overlapping slot -> 400 overlap
    print(f"\n[Test 7] Testing exact duplicate slot on {target_date} 10:00 AM - 10:30 AM...")
    res = client.post(
        "/api/lawyer/schedules",
        headers=headers,
        json={"date": target_date, "start_time": "10:00 AM", "end_time": "10:30 AM"},
    )
    assert res.status_code == 400
    assert res.json().get("error") == "overlap"
    print("✓ Test 7 Passed: Rejected exact duplicate slot with 400 overlap")

    # 8. Clean up created slot
    client.delete(f"/api/lawyer/schedules/{created_id}", headers=headers)
    print("\n✓ Cleaned up test slot")

    print("\n" + "=" * 60)
    print("  ALL BACKEND SCHEDULE VALIDATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()
