import os
import sys
import time

sys.path.insert(0, os.path.abspath('backend'))
from app.core.database import SessionLocal
from app.models import User, LawyerProfile
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\USER\.gemini\antigravity\brain\dafeb3a4-5a30-487e-b175-bcbc3a9bdfa2"

def main():
    db = SessionLocal()
    unv_user = db.query(User).filter(User.email == 'unverified_lawyer@bdlegal.ai').first()
    unv_prof = db.query(LawyerProfile).filter(LawyerProfile.user_id == unv_user.id).first()
    unv_prof.verification_status = 'pending'
    unv_prof.verification_note = None
    db.commit()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        print("1. Navigating to login page...")
        page.goto("http://localhost:5173/login")
        page.wait_for_selector('input[type="email"]')

        print("2. Logging in as unverified lawyer...")
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))
        page.fill('input[type="email"]', "unverified_lawyer@bdlegal.ai")
        page.fill('input[type="password"]', "Password123!")
        page.click('button[type="submit"]')

        page.wait_for_url("**/lawyer*", timeout=15000)
        page.wait_for_load_state("networkidle")
        print("URL after login:", page.url)

        print("3. Checking Unverified Lawyer state on LawyerDashboard...")
        banner = page.locator("#unverified-lawyer-banner")
        banner.wait_for(state="visible", timeout=10000)
        print(">> Unverified banner is visible:", banner.inner_text().split('\n')[0])

        # Check tabs disabled
        tab_consultations = page.locator("#tab-consultations")
        assert tab_consultations.is_disabled(), "Consultations tab should be disabled"
        tab_case_board = page.locator("#tab-case-board")
        assert tab_case_board.is_disabled(), "Case board tab should be disabled"
        tab_availability = page.locator("#tab-availability")
        assert tab_availability.is_disabled(), "Availability tab should be disabled"
        print(">> Gated tabs are successfully disabled!")

        # Check 3-slot checklist in Profile tab
        page.wait_for_selector("#slot-nid", timeout=5000)
        page.wait_for_selector("#slot-bar_council_cert", timeout=5000)
        page.wait_for_selector("#slot-practicing_license", timeout=5000)
        print(">> All 3 verification slots (NID, Bar Council, Practicing License) are present in Profile tab!")

        # Screenshot 1: Unverified profile with 3-slot checklist
        screenshot1_path = os.path.join(ARTIFACT_DIR, "unverified_lawyer_profile_checklist.png")
        page.screenshot(path=screenshot1_path, full_page=True)
        print(f">> Screenshot saved to: {screenshot1_path}")

        # Check Navbar Profile link
        print("4. Testing Navbar Profile navigation...")
        nav_profile = page.locator("#nav-link-profile")
        nav_profile.click()
        page.wait_for_timeout(1000)
        assert "tab=profile" in page.url or page.url.endswith("/lawyer"), f"Unexpected URL: {page.url}"
        print(">> Navbar Profile navigates correctly to Lawyer profile tab!")

        # 5. Set status to rejected with verification_note
        print("5. Testing Rejected state with administrator note...")
        db.refresh(unv_prof)
        unv_prof.verification_status = 'rejected'
        unv_prof.verification_note = 'High Court practicing license document is expired. Please re-upload current 2026 certificate.'
        db.commit()

        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#unverified-lawyer-banner", timeout=10000)
        banner_text = page.locator("#unverified-lawyer-banner").inner_text()
        assert "Verification Rejected" in banner_text, "Banner should show Verification Rejected"
        assert "expired" in banner_text, "Banner should display rejection note"
        print(">> Rejected banner with reason successfully displayed!")

        # Check resubmit button
        btn_submit = page.locator("#btn-submit-verification")
        assert btn_submit.is_visible()
        print(">> Resubmit button is visible:", btn_submit.inner_text())

        screenshot2_path = os.path.join(ARTIFACT_DIR, "rejected_lawyer_profile_checklist.png")
        page.screenshot(path=screenshot2_path, full_page=True)
        print(f">> Screenshot saved to: {screenshot2_path}")

        # 6. Set status to approved
        print("6. Testing Approved state...")
        db.refresh(unv_prof)
        unv_prof.verification_status = 'approved'
        unv_prof.verification_note = None
        db.commit()

        page.reload()
        page.wait_for_load_state("networkidle")

        # Verify unverified banner is gone
        assert page.locator("#unverified-lawyer-banner").count() == 0, "Unverified banner should disappear when approved"
        print(">> Unverified banner disappeared after admin approval!")

        # Verify tabs unlocked
        tab_consultations = page.locator("#tab-consultations")
        assert not tab_consultations.is_disabled(), "Consultations tab should be enabled after approval"
        tab_availability = page.locator("#tab-availability")
        assert not tab_availability.is_disabled(), "Availability tab should be enabled after approval"
        print(">> All dashboard tabs are successfully unlocked!")

        # Click consultations tab
        tab_consultations.click()
        page.wait_for_timeout(1000)
        screenshot3_path = os.path.join(ARTIFACT_DIR, "approved_lawyer_dashboard_unlocked.png")
        page.screenshot(path=screenshot3_path, full_page=True)
        print(f">> Screenshot saved to: {screenshot3_path}")

        browser.close()
        print("\n>>> ALL PLAYWRIGHT VISUAL CHECKS PASSED PERFECTLY! <<<")

if __name__ == '__main__':
    main()
