"""
Verification script for Case Board endpoints using FastAPI TestClient.
Tests:
1. Free user POST /api/cases -> 403 Pro required
2. Pro user POST /api/cases -> 201 Created
3. Unverified/Free lawyer GET /api/cases -> 403 Verified required
4. Verified Paid lawyer GET /api/cases -> 200 List of open cases
5. Verified Paid lawyer POST /api/cases/{id}/bid -> 201 Created
6. Case details and notification verification
"""

import sys
import json
from fastapi.testclient import TestClient

# Ensure utf-8 output on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.main import app

client = TestClient(app)

DEMO_PASSWORD = "Password123!"


def get_auth_token(email: str, password: str = DEMO_PASSWORD) -> str:
    """Helper to authenticate and return access token."""
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


def run_tests():
    print("\n" + "=" * 65)
    print("      CASE BOARD BACKEND VERIFICATION TEST SUITE")
    print("=" * 65 + "\n")

    # 1. Authenticate test personas
    print("[1/6] Authenticating test personas...")
    free_token = get_auth_token("client.free@bdlegal.ai")
    pro_token = get_auth_token("client.pro@bdlegal.ai")
    standard_lawyer_token = get_auth_token("adv.tanvir@bdlegal.ai")  # Blue / free verification badge
    gold_lawyer_token = get_auth_token("adv.nusrat@bdlegal.ai")      # Gold / paid verified badge
    print("  [✓] All personas authenticated successfully.\n")

    # 2. Test: Free user POST /api/cases -> 403 Pro required
    print("[2/6] Testing Free user POST /api/cases...")
    case_payload = {
        "title": "Commercial Lease Agreement Review",
        "category": "Corporate",
        "description": "Seeking expert review of a 5-year lease contract for our Dhaka office.",
        "attachment_asset_ids": [],
    }
    res_free = client.post(
        "/api/cases",
        headers={"Authorization": f"Bearer {free_token}"},
        json=case_payload,
    )
    print(f"  Status code: {res_free.status_code}")
    print(f"  Response: {res_free.text}")
    assert res_free.status_code == 403, f"Expected 403, got {res_free.status_code}"
    err_body = res_free.json()
    assert err_body.get("error") == "pro_required", f"Expected error 'pro_required', got {err_body}"
    print("  [✓] Free user correctly rejected with 403 Pro required.\n")

    # 3. Test: Pro user POST /api/cases -> 201 Created
    print("[3/6] Testing Pro user POST /api/cases...")
    pro_case_payload = {
        "title": "Dhaka Land Title Dispute & Mutation Appeal",
        "category": "Property",
        "description": "Commercial plot mutation appeal pending before Dhaka Additional Deputy Commissioner (Revenue). Need senior litigation advocate.",
        "attachment_asset_ids": [],
    }
    res_pro = client.post(
        "/api/cases",
        headers={"Authorization": f"Bearer {pro_token}"},
        json=pro_case_payload,
    )
    print(f"  Status code: {res_pro.status_code}")
    assert res_pro.status_code == 201, f"Expected 201, got {res_pro.status_code}: {res_pro.text}"
    case_data = res_pro.json()
    case_id = case_data["id"]
    print(f"  Created Case ID: {case_id}")
    print(f"  Title: {case_data['title']}")
    print(f"  Category: {case_data['category']}")
    print(f"  User Name: {case_data['user_name']}")
    print(f"  Status: {case_data['status']}")
    assert case_data["status"] == "open"
    assert case_data["user_name"] == "Karim Chowdhury (Pro)"
    print("  [✓] Pro user successfully posted case (201 Created).\n")

    # 4. Test: Unverified/Standard Lawyer GET /api/cases -> 403 Verified required
    print("[4/6] Testing Unverified / Standard Lawyer GET /api/cases...")
    res_std_lawyer = client.get(
        "/api/cases",
        headers={"Authorization": f"Bearer {standard_lawyer_token}"},
    )
    print(f"  Status code: {res_std_lawyer.status_code}")
    print(f"  Response: {res_std_lawyer.text}")
    assert res_std_lawyer.status_code == 403, f"Expected 403, got {res_std_lawyer.status_code}"
    std_err = res_std_lawyer.json()
    assert std_err.get("error") == "verified_required", f"Expected error 'verified_required', got {std_err}"
    print("  [✓] Standard (non-gold) lawyer correctly rejected with 403 Verified required.\n")

    # 5. Test: Verified Paid (Gold) Lawyer GET /api/cases -> 200 List of open cases
    print("[5/6] Testing Verified Paid (Gold) Lawyer GET /api/cases...")
    res_gold_lawyer = client.get(
        "/api/cases",
        headers={"Authorization": f"Bearer {gold_lawyer_token}"},
    )
    print(f"  Status code: {res_gold_lawyer.status_code}")
    assert res_gold_lawyer.status_code == 200, f"Expected 200, got {res_gold_lawyer.status_code}: {res_gold_lawyer.text}"
    open_cases = res_gold_lawyer.json()
    print(f"  Total open cases visible to Gold Lawyer: {len(open_cases)}")
    matching_case = next((c for c in open_cases if c["id"] == case_id), None)
    assert matching_case is not None, f"Newly created case {case_id} not found in open cases list"
    print(f"  Found matching case: '{matching_case['title']}' by {matching_case['user_name']}")
    print("  [✓] Gold Verified lawyer successfully retrieved open case board.\n")

    # 6. Test: Verified Paid Lawyer POST /api/cases/{id}/bid -> 201 Created
    print("[6/6] Testing Verified Paid Lawyer POST /api/cases/{id}/bid...")
    bid_payload = {
        "proposed_fee": 18000,
        "pitch_message": "Senior High Court advocate with 12+ years experience in land mutation appeals and land survey tribunal matters in Dhaka.",
    }
    res_bid = client.post(
        f"/api/cases/{case_id}/bid",
        headers={"Authorization": f"Bearer {gold_lawyer_token}"},
        json=bid_payload,
    )
    print(f"  Status code: {res_bid.status_code}")
    assert res_bid.status_code == 201, f"Expected 201, got {res_bid.status_code}: {res_bid.text}"
    bid_data = res_bid.json()
    print(f"  Bid ID: {bid_data['id']}")
    print(f"  Lawyer Name: {bid_data['lawyer_name']}")
    print(f"  Proposed Fee: {bid_data['proposed_fee']} BDT")
    print(f"  Pitch: {bid_data['pitch_message']}")
    print(f"  Avg Rating: {bid_data.get('lawyer_avg_rating')} stars")
    assert bid_data["proposed_fee"] == 18000
    assert bid_data["lawyer_name"] == "Adv. Nusrat Jahan"
    print("  [✓] Gold Verified lawyer successfully submitted bid (201 Created).\n")

    # 7. Additional Verification: View details as Client Pro and verify bid is attached
    print("[7/9] Verifying Case Details GET /api/cases/{id} as Client Pro...")
    res_details = client.get(
        f"/api/cases/{case_id}",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_details.status_code == 200, f"Expected 200, got {res_details.status_code}: {res_details.text}"
    details = res_details.json()
    assert details["bids"] is not None and len(details["bids"]) >= 1
    first_bid = details["bids"][0]
    bid_id = first_bid["id"]
    print(f"  Case has {len(details['bids'])} bid(s)")
    print(f"  Top bid ID: {bid_id} from {first_bid['lawyer_name']} ({first_bid['proposed_fee']} BDT)")
    print("  [✓] Case owner can inspect all bids successfully.\n")

    # 8. Test: Accept Bid Flow
    print("[8/9] Testing POST /api/cases/{case_id}/bids/{bid_id}/accept...")
    # 8a: Unauthorized attempt (Free user trying to accept Pro user's case bid)
    res_unauth = client.post(
        f"/api/cases/{case_id}/bids/{bid_id}/accept",
        headers={"Authorization": f"Bearer {free_token}"},
    )
    assert res_unauth.status_code == 403, f"Expected 403 for non-owner, got {res_unauth.status_code}"
    print("  [✓] Unauthorized user correctly rejected with 403 Forbidden.")

    # 8b: Authorized acceptance by Case Owner
    res_accept = client.post(
        f"/api/cases/{case_id}/bids/{bid_id}/accept",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    print(f"  Status code: {res_accept.status_code}")
    print(f"  Response: {res_accept.text}")
    assert res_accept.status_code == 200, f"Expected 200, got {res_accept.status_code}: {res_accept.text}"
    accept_data = res_accept.json()
    booking_id = accept_data["booking_id"]
    assert accept_data["status"] == "awaiting_payment"
    assert accept_data["case_id"] == case_id
    assert accept_data["bid_id"] == bid_id
    print(f"  Generated Booking ID: {booking_id}")
    print(f"  Booking Status: {accept_data['status']}")

    # 8c: Verify Booking record directly
    res_booking = client.get(
        f"/api/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_booking.status_code == 200, f"Expected 200, got {res_booking.status_code}: {res_booking.text}"
    booking_data = res_booking.json()
    assert booking_data["status"] == "awaiting_payment"
    assert booking_data.get("case_brief") is not None and "Case Acceptance" in booking_data.get("case_brief")
    print(f"  Verified Booking: status='{booking_data['status']}', case_brief='{booking_data.get('case_brief')}'")

    # 8d: Verify Case and Bid statuses updated
    res_details_after = client.get(
        f"/api/cases/{case_id}",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_details_after.status_code == 200
    updated_case = res_details_after.json()
    assert updated_case["status"] == "assigned", f"Expected case status 'assigned', got {updated_case['status']}"
    accepted_bid = next(b for b in updated_case["bids"] if b["id"] == bid_id)
    assert accepted_bid["status"] == "accepted", f"Expected bid status 'accepted', got {accepted_bid['status']}"
    print(f"  Case status: '{updated_case['status']}', Bid status: '{accepted_bid['status']}'")

    # 8e: Attempting to accept again should return 400
    res_reaccept = client.post(
        f"/api/cases/{case_id}/bids/{bid_id}/accept",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_reaccept.status_code == 400, f"Expected 400 on already assigned case, got {res_reaccept.status_code}"
    print("  [✓] Duplicate acceptance correctly rejected with 400 Bad Request.\n")

    # 9. Test: Reject Bid Flow
    print("[9/9] Testing POST /api/cases/{case_id}/bids/{bid_id}/reject...")
    # Create a fresh case and bid to test reject
    case_payload_2 = {
        "title": "Family Inheritance Settlement",
        "category": "Family",
        "description": "Ancestral asset division consultation required.",
        "attachment_asset_ids": [],
    }
    res_case_2 = client.post(
        "/api/cases",
        headers={"Authorization": f"Bearer {pro_token}"},
        json=case_payload_2,
    )
    assert res_case_2.status_code == 201
    case_id_2 = res_case_2.json()["id"]

    res_bid_2 = client.post(
        f"/api/cases/{case_id_2}/bid",
        headers={"Authorization": f"Bearer {gold_lawyer_token}"},
        json={"proposed_fee": 12000, "pitch_message": "Experienced in family succession matters."},
    )
    assert res_bid_2.status_code == 201
    bid_id_2 = res_bid_2.json()["id"]

    # Reject as non-owner -> 403
    res_rej_unauth = client.post(
        f"/api/cases/{case_id_2}/bids/{bid_id_2}/reject",
        headers={"Authorization": f"Bearer {free_token}"},
    )
    assert res_rej_unauth.status_code == 403, f"Expected 403, got {res_rej_unauth.status_code}"

    # Reject as owner -> 200 OK
    res_reject = client.post(
        f"/api/cases/{case_id_2}/bids/{bid_id_2}/reject",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_reject.status_code == 200, f"Expected 200, got {res_reject.status_code}: {res_reject.text}"
    reject_data = res_reject.json()
    assert reject_data["status"] == "rejected"
    assert reject_data["bid_id"] == bid_id_2
    print(f"  Bid ID {bid_id_2} successfully rejected.")

    # Rejecting again -> 400
    res_rereject = client.post(
        f"/api/cases/{case_id_2}/bids/{bid_id_2}/reject",
        headers={"Authorization": f"Bearer {pro_token}"},
    )
    assert res_rereject.status_code == 400, f"Expected 400 on already rejected bid, got {res_rereject.status_code}"
    print("  [✓] Reject flow fully validated with 403, 200, and 400 checks.\n")

    print("=" * 65)
    print("      ALL CASE BOARD ACCEPT & REJECT TESTS PASSED (9/9) !")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_tests()
