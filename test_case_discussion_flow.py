"""
Verification script for:
1. Bid Privacy (Lawyer A cannot see Lawyer B's fee or bid; only owner sees all bids).
2. Case Discussion Thread (permissions, open/closed rules, notifications).
"""

import sys
import uuid
from fastapi.testclient import TestClient

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.main import app
from app.core.database import SessionLocal
from app.models import Notification, User, CasePost, CaseBid, DirectMessage

client = TestClient(app)
DEMO_PASSWORD = "Password123!"


def get_auth_token(email: str, password: str = DEMO_PASSWORD) -> str:
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


def main():
    print("=" * 70)
    print("   BID PRIVACY & CASE DISCUSSION THREAD VERIFICATION SUITE")
    print("=" * 70)

    # 1. Log in personas
    print("\n[Step 1] Authenticating test users...")
    client_token = get_auth_token("client.pro@bdlegal.ai", "Password123!")
    lawyer_a_token = get_auth_token("adv.nusrat@bdlegal.ai", "Password123!")
    lawyer_b_token = get_auth_token("lawyer@bdlegal.ai", "Lawyer@1234")
    non_bidder_token = get_auth_token("adv.tanvir@bdlegal.ai", "Password123!")
    print("  [✓] Client Pro, Lawyer A, Lawyer B, and Non-bidder Lawyer authenticated.")

    # 2. Client creates a new case
    print("\n[Step 2] Client creating a new case on Case Board...")
    case_res = client.post(
        "/api/cases",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "title": f"Corporate Merger Negotiation {uuid.uuid4().hex[:6]}",
            "category": "Corporate",
            "description": "Seeking expert counsel for cross-border merger and contract drafting.",
            "attachment_asset_ids": [],
        },
    )
    assert case_res.status_code == 201, f"Create case failed: {case_res.text}"
    case_data = case_res.json()
    case_id = case_data["id"]
    print(f"  [✓] Case created: ID={case_id}, Title='{case_data['title']}'")

    # 3. Lawyer A submits bid
    print("\n[Step 3] Lawyer A submits bid (Fee: 15,000 BDT)...")
    bid_a_res = client.post(
        f"/api/cases/{case_id}/bid",
        headers={"Authorization": f"Bearer {lawyer_a_token}"},
        json={
            "proposed_fee": 15000,
            "pitch_message": "Pitch from Lawyer A: 10 years experience in corporate M&A.",
        },
    )
    assert bid_a_res.status_code == 201, f"Bid A failed: {bid_a_res.text}"
    bid_a_data = bid_a_res.json()
    bid_a_id = bid_a_data["id"]
    print(f"  [✓] Bid A submitted: ID={bid_a_id}, Fee={bid_a_data['proposed_fee']}")

    # 4. Lawyer B submits bid
    print("\n[Step 4] Lawyer B submits bid (Fee: 28,000 BDT)...")
    bid_b_res = client.post(
        f"/api/cases/{case_id}/bid",
        headers={"Authorization": f"Bearer {lawyer_b_token}"},
        json={
            "proposed_fee": 28000,
            "pitch_message": "Pitch from Lawyer B: High Court senior advocate advisory.",
        },
    )
    assert bid_b_res.status_code == 201, f"Bid B failed: {bid_b_res.text}"
    bid_b_data = bid_b_res.json()
    bid_b_id = bid_b_data["id"]
    print(f"  [✓] Bid B submitted: ID={bid_b_id}, Fee={bid_b_data['proposed_fee']}")

    # 5. SECURITY CHECK: Lawyer A GET case -> sees my_bid only, bid_count 2, NO trace of Lawyer B's fee or pitch
    print("\n[Step 5] Security Check: Lawyer A GET /api/cases/{case_id}...")
    lawyer_a_get_res = client.get(
        f"/api/cases/{case_id}",
        headers={"Authorization": f"Bearer {lawyer_a_token}"},
    )
    assert lawyer_a_get_res.status_code == 200, f"Lawyer A get case failed: {lawyer_a_get_res.text}"
    la_case = lawyer_a_get_res.json()

    print(f"  -> bids array in response: {la_case.get('bids')}")
    print(f"  -> bid_count: {la_case.get('bid_count')}")
    print(f"  -> my_bid ID: {la_case.get('my_bid', {}).get('id') if la_case.get('my_bid') else None}")
    print(f"  -> my_bid fee: {la_case.get('my_bid', {}).get('proposed_fee') if la_case.get('my_bid') else None}")

    assert la_case.get("bids") is None, "SECURITY VIOLATION: Lawyer A received 'bids' array!"
    assert la_case.get("bid_count") == 2, f"Expected bid_count 2, got {la_case.get('bid_count')}"
    assert la_case.get("my_bid") is not None, "Lawyer A should see my_bid"
    assert la_case["my_bid"]["id"] == bid_a_id, "my_bid does not match Lawyer A's bid"
    assert la_case["my_bid"]["proposed_fee"] == 15000

    # Ensure no trace of Lawyer B's fee (28000) or pitch in Lawyer A's response payload
    raw_response_text = lawyer_a_get_res.text
    assert "28000" not in raw_response_text, "SECURITY VIOLATION: Lawyer B's fee leaked to Lawyer A!"
    assert "High Court senior advocate" not in raw_response_text, "SECURITY VIOLATION: Lawyer B's pitch leaked to Lawyer A!"
    print("  [✓] PASSED: Lawyer A sees only my_bid and bid_count=2. No trace of Lawyer B's fee or pitch.")

    # Also verify lawyer board GET /api/cases
    board_res = client.get(
        "/api/cases",
        headers={"Authorization": f"Bearer {lawyer_a_token}"},
    )
    assert board_res.status_code == 200
    board_cases = board_res.json()
    board_target = next((c for c in board_cases if c["id"] == case_id), None)
    assert board_target is not None
    assert board_target.get("bids") is None, "SECURITY VIOLATION: Lawyer board returned bids array to lawyer"
    assert board_target.get("my_bid") is not None and board_target["my_bid"]["id"] == bid_a_id
    assert "28000" not in board_res.text, "SECURITY VIOLATION: Lawyer B fee in board response"
    print("  [✓] PASSED: Lawyer Board GET /api/cases also enforces bid privacy.")

    # 6. Client GET case -> sees both bids
    print("\n[Step 6] Client GET /api/cases/{case_id}...")
    client_get_res = client.get(
        f"/api/cases/{case_id}",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert client_get_res.status_code == 200
    client_case = client_get_res.json()
    assert client_case.get("bids") is not None, "Case owner must see bids array"
    assert len(client_case["bids"]) == 2, f"Expected 2 bids for owner, got {len(client_case['bids'])}"
    bids_fees = {b["id"]: b["proposed_fee"] for b in client_case["bids"]}
    assert bids_fees.get(bid_a_id) == 15000
    assert bids_fees.get(bid_b_id) == 28000
    print(f"  [✓] PASSED: Client sees both bids: {bids_fees}")

    # 7. Client posts message on Bid A thread -> 201; Lawyer A notified
    print("\n[Step 7] Client posts message on Bid A thread...")
    msg_client_res = client.post(
        f"/api/cases/{case_id}/bids/{bid_a_id}/messages",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "content": "Hello Lawyer A, could you clarify your availability next week?",
            "attachment_asset_ids": [],
        },
    )
    assert msg_client_res.status_code == 201, f"Client msg failed: {msg_client_res.text}"
    msg_client_data = msg_client_res.json()
    assert msg_client_data["content"] == "Hello Lawyer A, could you clarify your availability next week?"
    assert msg_client_data["case_id"] == case_id
    assert msg_client_data["bid_id"] == bid_a_id
    print(f"  [✓] Message created (201): ID={msg_client_data['id']}")

    # Check notification for Lawyer A
    db = SessionLocal()
    try:
        lawyer_a_user = db.query(User).filter(User.email == "adv.nusrat@bdlegal.ai").first()
        notif = (
            db.query(Notification)
            .filter(
                Notification.user_id == lawyer_a_user.id,
                Notification.type == "case_message",
            )
            .order_by(Notification.created_at.desc())
            .first()
        )
        assert notif is not None, "Notification not found for Lawyer A"
        assert notif.title == "New case message"
        assert notif.link == "/lawyer?tab=case-board"
        print(f"  [✓] Lawyer A notified: type={notif.type}, title='{notif.title}', link='{notif.link}'")
    finally:
        db.close()

    # 8. Lawyer B posts on Bid B thread -> 201; Client notified
    print("\n[Step 8] Lawyer B posts on Bid B thread...")
    msg_lawyer_b_res = client.post(
        f"/api/cases/{case_id}/bids/{bid_b_id}/messages",
        headers={"Authorization": f"Bearer {lawyer_b_token}"},
        json={
            "content": "Hello Client, I have handled similar M&A transactions successfully.",
            "attachment_asset_ids": [],
        },
    )
    assert msg_lawyer_b_res.status_code == 201, f"Lawyer B msg failed: {msg_lawyer_b_res.text}"
    msg_b_data = msg_lawyer_b_res.json()
    assert msg_b_data["case_id"] == case_id
    assert msg_b_data["bid_id"] == bid_b_id
    print(f"  [✓] Lawyer B message created (201): ID={msg_b_data['id']}")

    # Check notification for Client
    db = SessionLocal()
    try:
        client_user = db.query(User).filter(User.email == "client.pro@bdlegal.ai").first()
        notif_client = (
            db.query(Notification)
            .filter(
                Notification.user_id == client_user.id,
                Notification.type == "case_message",
            )
            .order_by(Notification.created_at.desc())
            .first()
        )
        assert notif_client is not None, "Notification not found for Client"
        assert notif_client.title == "New case message"
        assert notif_client.link == "/client/cases"
        print(f"  [✓] Client notified: type={notif_client.type}, title='{notif_client.title}', link='{notif_client.link}'")
    finally:
        db.close()

    # 9. GET messages for threads
    print("\n[Step 9] Checking GET /api/cases/{case_id}/bids/{bid_id}/messages...")
    get_msgs_a = client.get(
        f"/api/cases/{case_id}/bids/{bid_a_id}/messages",
        headers={"Authorization": f"Bearer {lawyer_a_token}"},
    )
    assert get_msgs_a.status_code == 200
    assert len(get_msgs_a.json()) >= 1
    print(f"  [✓] Thread A retrieved {len(get_msgs_a.json())} message(s) by Lawyer A.")

    # 10. Client accepts Bid A
    print("\n[Step 10] Client accepts Bid A...")
    accept_res = client.post(
        f"/api/cases/{case_id}/bids/{bid_a_id}/accept",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert accept_res.status_code == 200, f"Accept bid failed: {accept_res.text}"
    print(f"  [✓] Bid A accepted: booking_id={accept_res.json().get('booking_id')}")

    # 11. Lawyer B posts on Bid B thread -> 403 thread_closed
    print("\n[Step 11] Lawyer B attempts to post on Bid B thread after Bid A accepted...")
    msg_after_closed = client.post(
        f"/api/cases/{case_id}/bids/{bid_b_id}/messages",
        headers={"Authorization": f"Bearer {lawyer_b_token}"},
        json={
            "content": "Can we still negotiate?",
        },
    )
    print(f"  -> Status code: {msg_after_closed.status_code}")
    print(f"  -> Response: {msg_after_closed.json()}")
    assert msg_after_closed.status_code == 403, f"Expected 403, got {msg_after_closed.status_code}"
    err_json = msg_after_closed.json()
    assert err_json.get("error") == "thread_closed", f"Expected error='thread_closed', got {err_json}"
    assert err_json.get("message") == "This case discussion is closed."
    print("  [✓] PASSED: Lawyer B received 403 thread_closed ('This case discussion is closed.').")

    # Also verify GET returns thread_closed for closed thread
    get_after_closed = client.get(
        f"/api/cases/{case_id}/bids/{bid_b_id}/messages",
        headers={"Authorization": f"Bearer {lawyer_b_token}"},
    )
    assert get_after_closed.status_code == 403
    assert get_after_closed.json().get("error") == "thread_closed"
    print("  [✓] PASSED: GET on closed thread also returns 403 thread_closed.")

    # Verify that accepted thread (Bid A) remains OPEN
    print("\n[Step 12] Lawyer A posts on accepted Bid A thread (should remain open)...")
    msg_accepted_thread = client.post(
        f"/api/cases/{case_id}/bids/{bid_a_id}/messages",
        headers={"Authorization": f"Bearer {lawyer_a_token}"},
        json={
            "content": "Thank you for accepting! I look forward to working with you.",
        },
    )
    assert msg_accepted_thread.status_code == 201, f"Accepted thread should be open: {msg_accepted_thread.text}"
    print("  [✓] PASSED: Accepted Bid A thread remains open for discussion post-acceptance.")

    # 13. Non-bidder lawyer posts on any thread -> 403
    print("\n[Step 13] Non-bidder Lawyer attempts to post on Bid A thread...")
    non_bidder_post = client.post(
        f"/api/cases/{case_id}/bids/{bid_a_id}/messages",
        headers={"Authorization": f"Bearer {non_bidder_token}"},
        json={
            "content": "Unauthorized intrusion attempt",
        },
    )
    print(f"  -> Status code: {non_bidder_post.status_code}")
    assert non_bidder_post.status_code == 403, f"Expected 403 for non-bidder, got {non_bidder_post.status_code}"
    print("  [✓] PASSED: Non-bidder lawyer received 403 Forbidden.")

    print("\n" + "=" * 70)
    print("   ALL TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)


if __name__ == "__main__":
    main()
