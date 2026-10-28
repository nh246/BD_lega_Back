import os
import sys
sys.path.insert(0, os.path.abspath('backend'))
from app.core.database import SessionLocal
from app.models import User, LawyerProfile
from app.core.security import get_password_hash

db = SessionLocal()
lawyers = db.query(User).filter(User.role == 'lawyer').all()
for l in lawyers:
    prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == l.id).first()
    print(f'Email: {l.email}, Name: {l.full_name}, Status: {prof.verification_status if prof else None}, Paid: {prof.verification_paid if prof else None}')

# Set password for unverified_lawyer@bdlegal.ai to 'Password123!'
unv = db.query(User).filter(User.email == 'unverified_lawyer@bdlegal.ai').first()
if unv:
    unv.password_hash = get_password_hash('Password123!')
    db.commit()
    print('Set unverified_lawyer@bdlegal.ai password to Password123!')

# Also ensure lawyer@bdlegal.ai has 'Password123!'
l1 = db.query(User).filter(User.email == 'lawyer@bdlegal.ai').first()
if l1:
    l1.password_hash = get_password_hash('Password123!')
    db.commit()
    print('Set lawyer@bdlegal.ai password to Password123!')

