import os
import sys
import datetime

sys.path.insert(0, os.path.abspath('backend'))
from app.core.database import SessionLocal
from app.models import User, Schedule, LawyerProfile
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\USER\.gemini\antigravity\brain\dafeb3a4-5a30-487e-b175-bcbc3a9bdfa2"

def main():
    db = SessionLocal()
    lawyer = db.query(User).filter(User.email == 'lawyer@bdlegal.ai').first()
    prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == lawyer.id).first()

    target_date = (datetime.date.today() + datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    db.query(Schedule).filter(Schedule.lawyer_id == prof.id, Schedule.date == target_date).delete()

    # Seed 1-hour slot (09:00 - 10:00)
    s = Schedule(
        lawyer_id=prof.id,
        date=target_date,
        start_time='09:00',
        end_time='10:00',
        is_booked=False,
    )
    db.add(s)
    db.commit()
    print('Seeded 1-hour slot (09:00 - 10:00) on', target_date)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='msedge')
        ctx = browser.new_context(viewport={'width': 1440, 'height': 950})
        page = ctx.new_page()

        page.goto('http://localhost:5173/login')
        page.fill('input[type="email"]', 'lawyer@bdlegal.ai')
        page.fill('input[type="password"]', 'Password123!')
        page.click('button[type="submit"]')
        page.wait_for_url('**/lawyer*')

        page.goto('http://localhost:5173/lawyer?tab=availability')
        page.wait_for_selector('#availability-grid-container')
        page.wait_for_load_state('networkidle')

        # Scroll to row 09:00 so both 09:00 and 09:30 are clearly visible
        page.locator('#grid-row-09-00').scroll_into_view_if_needed()

        shot = os.path.join(ARTIFACT_DIR, 'multi_interval_connected_slot.png')
        page.screenshot(path=shot)
        print('Screenshot saved:', shot)

        browser.close()

if __name__ == '__main__':
    main()

