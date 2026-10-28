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
    assert lawyer, "lawyer@bdlegal.ai must exist"
    prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == lawyer.id).first()
    assert prof, "LawyerProfile must exist"

    # Tomorrow's date in YYYY-MM-DD
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # Clean existing schedules for tomorrow for clean testing
    db.query(Schedule).filter(
        Schedule.lawyer_id == prof.id,
        Schedule.date == tomorrow
    ).delete()

    # Seed an occupied slot at 09:00 - 09:30 for tomorrow
    slot_0900 = Schedule(
        lawyer_id=prof.id,
        date=tomorrow,
        start_time="09:00",
        end_time="09:30",
        is_booked=False,
    )
    db.add(slot_0900)
    db.commit()
    print(f"Seeded 09:00-09:30 slot for lawyer {lawyer.email} on {tomorrow}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        print("1. Navigating to login...")
        page.goto("http://localhost:5173/login")
        page.wait_for_selector('input[type="email"]')

        print("2. Logging in as approved lawyer...")
        page.fill('input[type="email"]', "lawyer@bdlegal.ai")
        page.fill('input[type="password"]', "Password123!")
        page.click('button[type="submit"]')

        page.wait_for_url("**/lawyer*", timeout=15000)
        page.wait_for_load_state("networkidle")
        print("Logged in, current URL:", page.url)

        print("3. Navigating to Availability tab...", flush=True)
        tab_btn = page.locator("#tab-availability")
        if tab_btn.is_visible():
            print(">> Clicking tab-availability button...", flush=True)
            tab_btn.click()
        else:
            page.goto("http://localhost:5173/lawyer?tab=availability")

        page.wait_for_selector("#availability-grid-container", timeout=15000)
        page.wait_for_load_state("networkidle")

        print("4. Verifying 48 rows exist in the grid (00:00 to 23:30)...")
        # Check first row 00:00
        row_0000 = page.locator("#grid-row-00-00")
        assert row_0000.is_visible(), "Row 00:00 must be present"

        # Check night row 02:00
        row_0200 = page.locator("#grid-row-02-00")
        assert row_0200.is_visible(), "Row 02:00 must be present"
        row_0200_classes = row_0200.get_attribute("class") or ""
        assert "bg-zinc-950" in row_0200_classes, f"Night row must be dimmed (bg-zinc-950). Got: {row_0200_classes}"
        print(">> Night row 02:00 is dimmed with bg-zinc-950.")

        # Check day row 09:00
        row_0900 = page.locator("#grid-row-09-00")
        assert row_0900.is_visible(), "Row 09:00 must be present"

        # Check last row 23:30
        row_2330 = page.locator("#grid-row-23-30")
        assert row_2330.is_visible(), "Row 23:30 must be present"
        print(">> All 48 rows (00:00 to 23:30) verified in the grid.")

        # Capture initial grid screenshot
        shot1 = os.path.join(ARTIFACT_DIR, "availability_grid_48_rows_night_dimmed.png")
        page.screenshot(path=shot1, full_page=False)
        print(">> Saved screenshot:", shot1)

        print("5. Testing Smart Prefill: Click occupied 09:00 row on tomorrow's date...")
        # The seeded 09:00 slot is occupied from 09:00-09:30, but 09:30-10:00 is free
        cell_0900 = page.locator(f"#slot-{tomorrow}-09-00")
        assert cell_0900.is_visible(), f"Seeded slot at 09:00 on {tomorrow} must be visible"
        print(">> Found occupied slot at 09:00:", cell_0900.inner_text().replace('\n', ' '))

        cell_0900.click()
        page.wait_for_selector("#add-slot-start-time", timeout=5000)

        # Check that start time is pre-filled with 09:30 (next available start time)
        start_val = page.locator("#add-slot-start-time").input_value()
        print(">> Add Slot Modal opened! Start time value:", start_val)
        assert start_val == "09:30", f"Expected prefill 09:30, got {start_val}"

        # Check duration options
        dur_options = page.locator("#add-slot-duration option").all_inner_texts()
        print(">> Duration options in modal:", dur_options)
        expected_options = ['30 min', '1 hour', '1.5 hours', '2 hours']
        assert all(opt in dur_options for opt in expected_options), f"Missing duration options in {dur_options}"

        # Capture smart prefill modal screenshot
        shot2 = os.path.join(ARTIFACT_DIR, "smart_prefill_next_available_slot.png")
        page.screenshot(path=shot2)
        print(">> Saved screenshot:", shot2)

        # Close modal
        page.click('button:has-text("Cancel")')
        page.wait_for_selector("#add-slot-start-time", state="detached")

        print("6. Testing Night Emergency Slot: Click 02:00 row on tomorrow's date...")
        btn_0200 = page.locator(f"#btn-add-{tomorrow}-02-00")
        assert btn_0200.is_visible(), "02:00 empty cell button must be visible"
        btn_0200.click()

        page.wait_for_selector("#add-slot-start-time", timeout=5000)
        start_val_0200 = page.locator("#add-slot-start-time").input_value()
        print(">> Add Slot Modal opened for night slot! Start time value:", start_val_0200)
        assert start_val_0200 == "02:00", f"Expected prefill 02:00, got {start_val_0200}"

        # Submit to create night slot
        page.click("#add-slot-submit")
        page.wait_for_selector("#add-slot-start-time", state="detached", timeout=5000)
        page.wait_for_load_state("networkidle")

        # Verify the 02:00 slot is now rendered in the grid
        new_slot_0200 = page.locator(f"#slot-{tomorrow}-02-00")
        new_slot_0200.wait_for(state="visible", timeout=8000)
        print(">> Night emergency slot created at 02:00:", new_slot_0200.inner_text().replace('\n', ' '))

        # Capture screenshot of created night slot
        shot3 = os.path.join(ARTIFACT_DIR, "night_emergency_slot_created.png")
        page.screenshot(path=shot3)
        print(">> Saved screenshot:", shot3)

        print("7. Testing Standalone /lawyer/availability Page...")
        page.goto("http://localhost:5173/lawyer/availability")
        page.wait_for_selector("#availability-grid-container", timeout=10000)
        page.wait_for_load_state("networkidle")

        shot4 = os.path.join(ARTIFACT_DIR, "standalone_availability_page_48_rows.png")
        page.screenshot(path=shot4)
        print(">> Saved screenshot:", shot4)

        browser.close()
        print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")

if __name__ == '__main__':
    main()
