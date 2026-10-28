import os
import sys
import uuid
import io

sys.path.insert(0, os.path.abspath('backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models import User, LawyerProfile, Notification, ProfileAsset
from app.core.security import create_access_token

def run_tests():
    db = SessionLocal()
    client = TestClient(app)

    # 1. Find or create unverified lawyer
    unverified_user = db.query(User).filter(User.email == 'unverified_lawyer@bdlegal.ai').first()
    if not unverified_user:
        unverified_user = User(
            id=uuid.uuid4(),
            email='unverified_lawyer@bdlegal.ai',
            role='lawyer',
            full_name='Unverified Advocate',
            password_hash='x',
            status='active'
        )
        db.add(unverified_user)
        db.commit()

    unverified_profile = db.query(LawyerProfile).filter(LawyerProfile.user_id == unverified_user.id).first()
    if not unverified_profile:
        unverified_profile = LawyerProfile(
            id=uuid.uuid4(),
            user_id=unverified_user.id,
            name='Unverified Advocate',
            verification_status='pending',
            verification_paid=False,
            verification_checklist={}
        )
        db.add(unverified_profile)
        db.commit()
    else:
        unverified_profile.verification_status = 'pending'
        unverified_profile.verification_checklist = {}
        db.commit()

    # Clear previous assets for test user
    db.query(ProfileAsset).filter(ProfileAsset.owner_user_id == unverified_user.id).delete()
    db.commit()

    token_unverified = create_access_token(data={'sub': unverified_user.email, 'role': 'lawyer'})
    auth_headers_unverified = {'Authorization': f'Bearer {token_unverified}'}

    # Test unverified lawyer gates:
    # a) availability slots
    res = client.post('/api/availability/slots', headers=auth_headers_unverified, json={'date': '2026-11-01', 'start_time': '10:00', 'end_time': '11:00'})
    print('Unverified POST /api/availability/slots:', res.status_code, res.json())
    assert res.status_code == 403
    assert res.json().get('error') == 'unverified_lawyer'

    # b) consultations
    res = client.get('/api/lawyer/consultations', headers=auth_headers_unverified)
    print('Unverified GET /api/lawyer/consultations:', res.status_code, res.json())
    assert res.status_code == 403
    assert res.json().get('error') == 'unverified_lawyer'

    # c) profile update
    res = client.put('/api/lawyer/me', headers=auth_headers_unverified, json={
        'full_name': 'Advocate Test Name',
        'bio': 'Specialist in Bangladesh Supreme Court litigation.',
        'district': 'Dhaka',
        'specialization': 'Civil Litigation',
        'years_exp': 10,
        'hourly_rate': 2500,
        'payment_methods': [{'method': 'bKash', 'number': '01711223344', 'type': 'Personal'}],
        'payment_instructions': 'Send with booking reference',
        'meeting_provider': 'Google Meet',
        'meeting_link': 'https://meet.google.com/test-meet'
    })
    print('Unverified PUT /api/lawyer/me:', res.status_code)
    assert res.status_code == 200
    data = res.json()
    assert data['bio'] == 'Specialist in Bangladesh Supreme Court litigation.'
    assert data['meeting_provider'] == 'Google Meet'

    # d) upload slot 1 (nid)
    f1 = io.BytesIO(b'%PDF-1.4 test nid content')
    res = client.post('/api/profile/assets', headers=auth_headers_unverified, data={'kind': 'verification', 'slot': 'nid'}, files={'file': ('nid.pdf', f1, 'application/pdf')})
    print('Upload nid status:', res.status_code, res.json())
    assert res.status_code == 201

    # e) submit verification should fail when slots missing
    res = client.post('/api/lawyer/verification/submit', headers=auth_headers_unverified)
    print('Incomplete submit status:', res.status_code, res.json())
    assert res.status_code == 400

    # f) upload remaining slots
    f2 = io.BytesIO(b'%PDF-1.4 test bar council')
    res = client.post('/api/profile/assets', headers=auth_headers_unverified, data={'kind': 'verification', 'slot': 'bar_council_cert'}, files={'file': ('bar_council.pdf', f2, 'application/pdf')})
    assert res.status_code == 201

    f3 = io.BytesIO(b'%PDF-1.4 test license')
    res = client.post('/api/profile/assets', headers=auth_headers_unverified, data={'kind': 'verification', 'slot': 'practicing_license'}, files={'file': ('license.pdf', f3, 'application/pdf')})
    assert res.status_code == 201

    # g) submit verification succeeds
    res = client.post('/api/lawyer/verification/submit', headers=auth_headers_unverified)
    print('Complete submit status:', res.status_code, res.json())
    assert res.status_code == 200
    assert res.json()['verification_status'] == 'pending'

    # Check admin notification
    notif = db.query(Notification).filter(Notification.type == 'lawyer_verification_submitted').order_by(Notification.created_at.desc()).first()
    assert notif is not None
    print('Admin notification created:', notif.title, notif.message)

    # h) Verified lawyer can access availability and consultations
    verified_user = db.query(User).filter(User.email == 'lawyer@bdlegal.ai').first()
    if verified_user:
        v_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == verified_user.id).first()
        if v_prof:
            v_prof.verification_status = 'approved'
            db.commit()
            token_verified = create_access_token(data={'sub': verified_user.email, 'role': 'lawyer'})
            auth_headers_verified = {'Authorization': f'Bearer {token_verified}'}

            res = client.post('/api/availability/slots', headers=auth_headers_verified, json={'date': '2026-11-05', 'start_time': '10:00 AM', 'end_time': '11:00 AM'})
            print('Verified POST /api/availability/slots:', res.status_code, res.json())
            assert res.status_code in (200, 201)

            res = client.get('/api/lawyer/consultations', headers=auth_headers_verified)
            print('Verified GET /api/lawyer/consultations:', res.status_code)
            assert res.status_code == 200

    print('>>> ALL VERIFICATION TESTS PASSED SUCCESSFULLY! <<<')

if __name__ == '__main__':
    run_tests()
