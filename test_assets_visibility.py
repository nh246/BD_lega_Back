import sys
import uuid
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import User, ProfileAsset, CasePost, CaseBid, LawyerProfile, DirectMessage

client = TestClient(app)

def test_visibility_model():
    db = SessionLocal()
    try:
        # 1. Setup test users
        suffix = uuid.uuid4().hex[:6]
        
        # Owner Lawyer (A)
        user_a = User(
            id=uuid.uuid4(),
            email=f"lawyer_a_{suffix}@test.com",
            password_hash="mockhash",
            full_name=f"Advocate A {suffix}",
            role="lawyer",
            status="active",
        )
        profile_a = LawyerProfile(
            id=uuid.uuid4(),
            user_id=user_a.id,
            name=user_a.full_name,
            bar_council_id=f"BC-A-{suffix}",
            verification_status="approved",
            verification_paid=True,
        )
        
        # Client Owner (B)
        user_b = User(
            id=uuid.uuid4(),
            email=f"client_b_{suffix}@test.com",
            password_hash="mockhash",
            full_name=f"Client B {suffix}",
            role="user",
            status="active",
        )
        
        # Bidding Lawyer (C)
        user_c = User(
            id=uuid.uuid4(),
            email=f"lawyer_c_{suffix}@test.com",
            password_hash="mockhash",
            full_name=f"Advocate C {suffix}",
            role="lawyer",
            status="active",
        )
        profile_c = LawyerProfile(
            id=uuid.uuid4(),
            user_id=user_c.id,
            name=user_c.full_name,
            bar_council_id=f"BC-C-{suffix}",
            verification_status="approved",
            verification_paid=True,
        )
        
        # Non-Bidding / Stranger Lawyer (D)
        user_d = User(
            id=uuid.uuid4(),
            email=f"lawyer_d_{suffix}@test.com",
            password_hash="mockhash",
            full_name=f"Advocate D {suffix}",
            role="lawyer",
            status="active",
        )
        profile_d = LawyerProfile(
            id=uuid.uuid4(),
            user_id=user_d.id,
            name=user_d.full_name,
            bar_council_id=f"BC-D-{suffix}",
            verification_status="approved",
            verification_paid=True,
        )

        # Stranger User (E)
        user_e = User(
            id=uuid.uuid4(),
            email=f"stranger_e_{suffix}@test.com",
            password_hash="mockhash",
            full_name=f"Stranger E {suffix}",
            role="user",
            status="active",
        )

        db.add_all([user_a, profile_a, user_b, user_c, profile_c, user_d, profile_d, user_e])
        db.flush()

        # 2. Setup Assets
        # Asset 1: Lawyer A's verification doc
        verif_doc = ProfileAsset(
            id=uuid.uuid4(),
            owner_user_id=user_a.id,
            kind="verification",
            filename="bar_council_cert.pdf",
            mime_type="application/pdf",
            file_bytes=b"%PDF-1.4 Mock verification certificate for Lawyer A",
            size_bytes=48,
        )

        # Asset 2: Case evidence document uploaded by Client B
        case_evidence = ProfileAsset(
            id=uuid.uuid4(),
            owner_user_id=user_b.id,
            kind="text",
            filename="deed_of_sale.pdf",
            mime_type="application/pdf",
            file_bytes=b"%PDF-1.4 Mock deed of sale evidence",
            size_bytes=35,
        )

        # Asset 3: Discussion attachment uploaded during case negotiation
        discussion_attachment = ProfileAsset(
            id=uuid.uuid4(),
            owner_user_id=user_c.id,
            kind="text",
            filename="counter_proposal.pdf",
            mime_type="application/pdf",
            file_bytes=b"%PDF-1.4 Mock counter proposal",
            size_bytes=32,
        )

        db.add_all([verif_doc, case_evidence, discussion_attachment])
        db.flush()

        # 3. Setup CasePost & Bid
        case_post = CasePost(
            id=uuid.uuid4(),
            user_id=user_b.id,
            title="Property Dispute Evidence Test",
            category="Property Law",
            description="Testing evidence document access rules.",
            status="open",
            attachment_asset_ids=[str(case_evidence.id)],
        )
        db.add(case_post)
        db.flush()

        # Lawyer C places a bid on this case
        bid_c = CaseBid(
            id=uuid.uuid4(),
            case_id=case_post.id,
            lawyer_profile_id=profile_c.id,
            proposed_fee=15000,
            pitch_message="I can handle this property dispute.",
            status="pending",
        )
        db.add(bid_c)
        db.flush()

        # 4. Setup DirectMessage Discussion Thread
        dm_msg = DirectMessage(
            id=uuid.uuid4(),
            sender_user_id=user_c.id,
            recipient_user_id=user_b.id,
            lawyer_profile_id=profile_c.id,
            case_id=case_post.id,
            bid_id=bid_c.id,
            content="Here is the counter proposal document attached.",
            attachments=[str(discussion_attachment.id)],
        )
        db.add(dm_msg)
        db.commit()

        # Helper to generate authorization headers
        def auth_headers(user):
            token = create_access_token(data={"sub": user.email, "role": user.role})
            return {"Authorization": f"Bearer {token}"}

        headers_a = auth_headers(user_a)
        headers_b = auth_headers(user_b)
        headers_c = auth_headers(user_c)
        headers_d = auth_headers(user_d)
        headers_e = auth_headers(user_e)

        print("\n--- Running TestClient Asset Visibility Verifications ---")

        # TEST 1: Unauthenticated fetch -> 401
        res = client.get(f"/api/assets/{verif_doc.id}/file")
        print(f"1. Unauthenticated fetch on verification doc: status = {res.status_code}")
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"

        res_case_unauth = client.get(f"/api/assets/{case_evidence.id}/file")
        print(f"   Unauthenticated fetch on case evidence: status = {res_case_unauth.status_code}")
        assert res_case_unauth.status_code == 401, f"Expected 401, got {res_case_unauth.status_code}"

        # TEST 2: Owner fetches own verification doc -> 200
        res_owner = client.get(f"/api/assets/{verif_doc.id}/file", headers=headers_a)
        print(f"2. Owner (Lawyer A) fetches own verification doc: status = {res_owner.status_code}")
        assert res_owner.status_code == 200, f"Expected 200, got {res_owner.status_code}"
        assert res_owner.content == b"%PDF-1.4 Mock verification certificate for Lawyer A"

        # TEST 3: Case Evidence:
        # - Bidding lawyer (C) fetches case evidence -> 200
        res_c_evidence = client.get(f"/api/assets/{case_evidence.id}/file", headers=headers_c)
        print(f"3a. Bidding lawyer (Lawyer C) fetches case evidence: status = {res_c_evidence.status_code}")
        assert res_c_evidence.status_code == 200, f"Expected 200, got {res_c_evidence.status_code}"

        # - Non-bidding lawyer (D) fetches case evidence -> 404
        res_d_evidence = client.get(f"/api/assets/{case_evidence.id}/file", headers=headers_d)
        print(f"3b. Non-bidding lawyer (Lawyer D) fetches case evidence: status = {res_d_evidence.status_code}")
        assert res_d_evidence.status_code == 404, f"Expected 404, got {res_d_evidence.status_code}"

        # - Stranger user (E) fetches case evidence -> 404
        res_e_evidence = client.get(f"/api/assets/{case_evidence.id}/file", headers=headers_e)
        print(f"3c. Stranger user (User E) fetches case evidence: status = {res_e_evidence.status_code}")
        assert res_e_evidence.status_code == 404, f"Expected 404, got {res_e_evidence.status_code}"

        # TEST 4: Case Discussion Attachment:
        # - Counterparty (Client B) fetches discussion attachment -> 200
        res_b_disc = client.get(f"/api/assets/{discussion_attachment.id}/file", headers=headers_b)
        print(f"4a. Counterparty (Client B) fetches discussion attachment: status = {res_b_disc.status_code}")
        assert res_b_disc.status_code == 200, f"Expected 200, got {res_b_disc.status_code}"

        # - Uploader (Lawyer C) fetches own discussion attachment -> 200
        res_c_disc = client.get(f"/api/assets/{discussion_attachment.id}/file", headers=headers_c)
        print(f"4b. Sender (Lawyer C) fetches discussion attachment: status = {res_c_disc.status_code}")
        assert res_c_disc.status_code == 200, f"Expected 200, got {res_c_disc.status_code}"

        # - Stranger lawyer (Lawyer D) fetches discussion attachment -> 404
        res_d_disc = client.get(f"/api/assets/{discussion_attachment.id}/file", headers=headers_d)
        print(f"4c. Stranger lawyer (Lawyer D) fetches discussion attachment: status = {res_d_disc.status_code}")
        assert res_d_disc.status_code == 404, f"Expected 404, got {res_d_disc.status_code}"

        # - Stranger user (User E) fetches discussion attachment -> 404
        res_e_disc = client.get(f"/api/assets/{discussion_attachment.id}/file", headers=headers_e)
        print(f"4d. Stranger user (User E) fetches discussion attachment: status = {res_e_disc.status_code}")
        assert res_e_disc.status_code == 404, f"Expected 404, got {res_e_disc.status_code}"

        print("\n>>> ALL TESTCLIENT VISIBILITY MODEL TESTS PASSED! <<<")

    finally:
        db.close()

if __name__ == "__main__":
    test_visibility_model()
