import uuid
import os
from datetime import datetime
from app.core.database import SessionLocal
from app.models import ProfileAsset, LawyerProfile, User

female_img_path = r"C:\Users\USER\.gemini\antigravity-ide\brain\dafeb3a4-5a30-487e-b175-bcbc3a9bdfa2\advocate_female_1792845784988.jpg"
male_img_path = r"C:\Users\USER\.gemini\antigravity-ide\brain\dafeb3a4-5a30-487e-b175-bcbc3a9bdfa2\advocate_male_1792845804939.jpg"

with open(female_img_path, "rb") as f:
    female_bytes = f.read()

with open(male_img_path, "rb") as f:
    male_bytes = f.read()

db = SessionLocal()
lawyers = db.query(LawyerProfile).all()

for l in lawyers:
    if "Nusrat" in l.name:
        l.hourly_rate = 2500
        l.years_exp = 11
        l.languages = "Bangla, English"
        img_bytes = female_bytes
    elif "Sarah" in l.name:
        l.hourly_rate = 1800
        l.years_exp = 8
        l.languages = "Bangla, English"
        img_bytes = female_bytes
    elif "Rafiqul" in l.name:
        l.hourly_rate = 2200
        l.years_exp = 11
        l.languages = "Bangla, English"
        img_bytes = male_bytes
    elif "Tanvir" in l.name:
        l.hourly_rate = 1500
        l.years_exp = 7
        l.languages = "Bangla, English"
        img_bytes = male_bytes
    else:
        continue

    # Check existing avatar asset
    asset = db.query(ProfileAsset).filter(
        ProfileAsset.owner_user_id == l.user_id,
        ProfileAsset.kind == "avatar"
    ).first()

    clean_name = l.name.replace(" ", "_")
    if not asset:
        asset = ProfileAsset(
            id=uuid.uuid4(),
            owner_user_id=l.user_id,
            kind="avatar",
            filename=f"{clean_name}.jpg",
            mime_type="image/jpeg",
            file_bytes=img_bytes,
            size_bytes=len(img_bytes),
            created_at=datetime.utcnow(),
        )
        db.add(asset)
        print(f" [+] Created avatar asset for: {l.name}")
    else:
        asset.file_bytes = img_bytes
        asset.size_bytes = len(img_bytes)
        asset.mime_type = "image/jpeg"
        print(f" [.] Updated avatar asset for: {l.name}")

db.commit()
print("Finished seeding lawyer avatars & decision attributes.")
