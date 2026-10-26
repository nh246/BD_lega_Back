"""
Verification script for Optional Bid Fee and Case Acceptance logic.
Tests:
1. Bid with fee <= 0 -> 422 Unprocessable Entity
2. Bid without fee (None / missing) -> 201 Created with proposed_fee=None
3. Accept bid without fee -> booking fee equals lawyer hourly_rate (and status awaiting_payment if rate > 0)
4. Bid with fee 25000 -> 201 Created with proposed_fee=25000
5. Accept bid with fee 25000 -> booking fee equals 25000
"""

import sys
from fastapi.testclient import TestClient

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.main import app
from app.core.database import SessionLocal
from app.models import LawyerProfile

client = TestClient(app)
DEMO_PASSWORD = "Password123!"


def get_auth_token(email: str, password: str = DEMO_PASSWORD) -> str:
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


def main():
    print("=" * 65)
    print("      OPTIONAL BID FEE BACKEND VERIFICATION")
    print("=" * 65)

    pro_token = get_auth_token("client.pro@bdlegal.ai")
    gold_token = get_auth_token("adv.nusrat@bdlegal.ai")

    db = SessionLocal()
    try:
        # Get lawyer's profile and hourly rate
        lawyer_profile = (
            db.query(LawyerProfile)
            .filter(LawyerProfile.user_id != None)
            .join(LawyerProfile.user)
            .filter(LawyerProfile.user.has(email="adv.nusrat@bdlegal.ai"))
            .first()
        )
        assert lawyer_profile is not None
        expected_hourly_rate = lawyer_profile.hourly_rate if lawyer_profile.hourly_rate is not None else 0
        print(f"Lawyer hourly_rate in DB: {expected_hourly_rate} BDT")
    finally:
        db.close()

    # 1. Create a test case
    print("\n[Step 1] Creating Case 1 for optional fee test...")
    res_case_1 = client.post(
        "/api/cases",
        headers={"Authorization": f"Bearer {pro_token}"},
        json={
            "title": "Corporate Mergers & Acquisitions Advisory",
            "category": "Corporate",
            "description": "Need legal review on asset purchase agreement and closing deliverables.",
            "attachment_asset_ids": [],
        },
    )
    assert res_case_1.status_code == 201, f"Failed to create case: {res_case_1.text}"
    case_1_id = res_case_1.json()["id"]
    print(f"  Case 1 created: ID {case_1_id}")

    # 2. Test invalid fee <= 0 (e.g. 0 or -500) -> 422
    print("\n[Step 2] Testing bid submission with proposed_fee <= 0...")
    res_invalid_fee = client.post(
        f"/api/cases/{case_1_id}/bid",
        headers={"Authorization": f"Bearer {gold_token}"},
        json={"proposed_fee": 0, "pitch_message": "Experienced in corporate M&A."},
    )
    print(f"  Fee 0 status: {res_invalid_fee.status_code}")
    assert res_invalid_fee.status_code in [400, 422], f"Expected 400 or 422, got {res_invalid_fee.status_code}"
    print("  ✓ Fee 0 rejected correctly.")

    res_negative_fee = client.post(
        f"/api/cases/{case_1_id}/bid",
        headers={"Authorization": f"Bearer {gold_token}"},
        json={"proposed_fee": -100, "pitch_message": "Experienced in corporate M&A."},
    )
    print(f"  Fee -100 status: {res_negative_fee.status_code}")
    assert res_negative_fee.status_code in [400, 422], f"Expected 400 or 422, got {res_negative_fee.status_code}"
    print("  ✓ Negative fee rejected correctly.")

    # 3. Test bid WITHOUT fee -> 201
    print("\n[Step 3] Submitting bid WITHOUT proposed_fee (None / omitted)...")
    res_no_fee_bid = client.post(
        f"/api/cases/{case_1_id}/bid",
        headers={"Authorization": f"Bearer {gold_token}"},
        json={"pitch_message": "Ready to discuss requirements and propose tailored strategy."},
    )
    print(f"  Status code: {res_no_fee_bid.status_code}")
    assert res_no_fee_bid.status_code == 201, f"Expected 201, got {res_no_fee_bid.status_code}: {res_no_fee_bid.text}"
    bid_1 = res_no_fee_bid.json()
    assert bid_1["proposed_fee"] is None, f"Expected None, got {bid_1['proposed_fee']}"
    bid_1_id = bid_1["id"]
    print(f"  ✓ Bid without fee accepted with 201 Created (proposed_fee={bid_1['proposed_fee']})")

    # 4. Accept bid without fee -> booking fee equals lawyer hourly_rate
    print(f"\n[Step 4] Accepting bid without fee (ID: {bid_1_id})...")
    res_accept_1 = client.post(
        f"/api/cases/{case_1_id}/bids/{bid_1_id}/accept",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    print(f"  Status code: {res_accept_1.status_code}")
    assert res_accept_1.status_code == 200, f"Expected 200, got {res_accept_1.status_code}: {res_accept_1.text}"
    accept_1_data = res_accept_1.json()
    booking_1_id = accept_1_data["booking_id"]
    print(f"  Booking 1 ID: {booking_1_id}, status: {accept_1_data['status']}, fee: {accept_1_data.get('fee')}")
    assert accept_1_data.get("fee") == expected_hourly_rate, f"Expected {expected_hourly_rate}, got {accept_1_data.get('fee')}"

    # Also verify via GET /api/bookings/{booking_id}
    res_get_booking_1 = client.get(
        f"/api/bookings/{booking_1_id}",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_get_booking_1.status_code == 200
    booking_1_data = res_get_booking_1.json()
    assert booking_1_data.get("fee") == expected_hourly_rate, f"Expected {expected_hourly_rate}, got {booking_1_data.get('fee')}"
    print(f"  ✓ Verified: Booking fee ({booking_1_data.get('fee')}) equals lawyer hourly_rate ({expected_hourly_rate})")

    # 5. Create Case 2 for fixed fee test
    print("\n[Step 5] Creating Case 2 for 25000 fee test...")
    res_case_2 = client.post(
        "/api/cases",
        headers={"Authorization": f"Bearer {pro_token}"},
        json={
            "title": "Commercial Property Title Verification",
            "category": "Property",
            "description": "Comprehensive title deed verification and vetting of land records in Gulshan.",
            "attachment_asset_ids": [],
        },
    )
    assert res_case_2.status_code == 201
    case_2_id = res_case_2.json()["id"]

    # 6. Submit bid with fee 25000 -> 201
    print(f"\n[Step 6] Submitting bid with fee 25000 on Case {case_2_id}...")
    res_fee_bid = client.post(
        f"/api/cases/{case_2_id}/bid",
        headers={"Authorization": f"Bearer {gold_token}"},
        json={"proposed_fee": 25000, "pitch_message": "Will conduct complete land registration searches."},
    )
    print(f"  Status code: {res_fee_bid.status_code}")
    assert res_fee_bid.status_code == 201
    bid_2 = res_fee_bid.json()
    assert bid_2["proposed_fee"] == 25000
    bid_2_id = bid_2["id"]
    print(f"  ✓ Bid with fee 25000 accepted with 201 Created (proposed_fee={bid_2['proposed_fee']})")

    # 7. Accept bid with fee 25000 -> booking fee equals 25000
    print(f"\n[Step 7] Accepting bid with fee 25000 (ID: {bid_2_id})...")
    res_accept_2 = client.post(
        f"/api/cases/{case_2_id}/bids/{bid_2_id}/accept",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    print(f"  Status code: {res_accept_2.status_code}")
    assert res_accept_2.status_code == 200
    accept_2_data = res_accept_2.json()
    booking_2_id = accept_2_data["booking_id"]
    print(f"  Booking 2 ID: {booking_2_id}, status: {accept_2_data['status']}, fee: {accept_2_data.get('fee')}")
    assert accept_2_data.get("fee") == 25000
    assert accept_2_data["status"] == "awaiting_payment"

    # Also verify via GET /api/bookings/{booking_id}
    res_get_booking_2 = client.get(
        f"/api/bookings/{booking_2_id}",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_get_booking_2.status_code == 200
    booking_2_data = res_get_booking_2.json()
    assert booking_2_data.get("fee") == 25000
    print(f"  ✓ Verified: Booking fee ({booking_2_data.get('fee')}) equals 25000")

    # 8. Test fee == 0 rule -> booking status 'confirmed' (free consultation)
    print("\n[Step 8] Testing fee == 0 rule (free consultation -> status 'confirmed')...")
    db = SessionLocal()
    try:
        lp = db.query(LawyerProfile).filter(LawyerProfile.id == lawyer_profile.id).first()
        lp.hourly_rate = 0
        db.commit()

        res_case_3 = client.post(
            "/api/cases",
            headers={"Authorization": f"Bearer {pro_token}"},
            json={
                "title": "Pro Bono Legal Inquiry",
                "category": "Civil",
                "description": "Inquiry regarding public interest litigation.",
                "attachment_asset_ids": [],
            },
        )
        assert res_case_3.status_code == 201
        case_3_id = res_case_3.json()["id"]

        res_zero_bid = client.post(
            f"/api/cases/{case_3_id}/bid",
            headers={"Authorization": f"Bearer {gold_token}"},
            json={"pitch_message": "Happy to provide free initial guidance."},
        )
        assert res_zero_bid.status_code == 201
        bid_3_id = res_zero_bid.json()["id"]

        res_accept_3 = client.post(
            f"/api/cases/{case_3_id}/bids/{bid_3_id}/accept",
            headers={"Authorization": f"Bearer {pro_token}"},
        )
        assert res_accept_3.status_code == 200
        accept_3_data = res_accept_3.json()
        print(f"  Booking 3 ID: {accept_3_data['booking_id']}, status: {accept_3_data['status']}, fee: {accept_3_data.get('fee')}")
        assert accept_3_data.get("fee") == 0
        assert accept_3_data["status"] == "confirmed"
        print("  ✓ Verified: When fee == 0, booking status is 'confirmed' (free consultation)")
    finally:
        # Restore lawyer's original hourly_rate
        lp = db.query(LawyerProfile).filter(LawyerProfile.id == lawyer_profile.id).first()
        if lp:
            lp.hourly_rate = expected_hourly_rate
            db.commit()
        db.close()

    print("\n" + "=" * 65)
    print("  ALL OPTIONAL BID FEE TESTS PASSED (100% GREEN)!")
    print("=" * 65)


if __name__ == "__main__":
    main()
