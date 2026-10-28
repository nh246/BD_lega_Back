import os
import sys
import uuid
import datetime

backend_dir = os.path.abspath('backend')
os.chdir(backend_dir)
sys.path.insert(0, os.path.join(backend_dir, 'venv', 'Lib', 'site-packages'))
sys.path.insert(0, backend_dir)
from app.core.database import SessionLocal
from app.models import User, AuditLog
from app.core.security import get_password_hash
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\USER\.gemini\antigravity\brain\dafeb3a4-5a30-487e-b175-bcbc3a9bdfa2"

def main():
    db = SessionLocal()
    test_email = f"e2e_pwd_{uuid.uuid4().hex[:8]}@bdlegal.ai"
    initial_pwd = "OldPassword123!"
    reset_new_pwd = "BrandNewPassword123!"
    final_updated_pwd = "UpdatedAgainPassword123!"

    # Create test user
    user = User(
        id=uuid.uuid4(),
        email=test_email,
        password_hash=get_password_hash(initial_pwd),
        full_name="E2E Password Citizen",
        role="user",
        status="active",
    )
    db.add(user)
    db.commit()
    print(f">> Created test user: {test_email}", flush=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="msedge")
            context = browser.new_context(viewport={"width": 1440, "height": 950})
            page = context.new_page()
            page.on("console", lambda msg: print("BROWSER LOG:", msg.text, flush=True))
            page.on("response", lambda res: print("API RESP:", res.url, res.status, flush=True) if "auth" in res.url else None)

            # -----------------------------------------------------------------
            # FLOW 1: Forgot Password Modal & Reset Password E2E Flow
            # -----------------------------------------------------------------
            print("1. Navigating to /login...", flush=True)
            page.goto("http://localhost:5173/login")
            page.wait_for_selector("#login-email", timeout=10000)

            print("2. Clicking 'Forgot Password?' link...", flush=True)
            page.click("#link-forgot-password")
            page.wait_for_selector("#forgot-email", timeout=5000)

            print("3. Entering email into forgot password modal...", flush=True)
            page.fill("#forgot-email", test_email)
            page.click("#btn-send-reset-link")

            # Wait for demo mode box
            page.wait_for_selector("#demo-reset-link-input", timeout=8000)
            demo_link = page.locator("#demo-reset-link-input").input_value()
            print(">> Demo reset link generated:", demo_link, flush=True)

            shot1 = os.path.join(ARTIFACT_DIR, "forgot_password_modal_demo_box.png")
            page.screenshot(path=shot1)
            print(">> Saved screenshot:", shot1, flush=True)

            print("4. Testing 'Copy Link' button...", flush=True)
            page.click("#btn-copy-reset-link")
            page.wait_for_selector("button:has-text('Copied')", timeout=3000)

            print("5. Clicking 'Open Reset Page'...", flush=True)
            page.click("#btn-open-reset-page")

            # Wait for ResetPasswordPage form
            page.wait_for_selector("#reset-new-password", timeout=8000)
            page.wait_for_load_state("networkidle")
            print(">> Landed on Reset Password Page. URL:", page.url, flush=True)

            # Fill new password with strength & match hints
            page.fill("#reset-new-password", reset_new_pwd)
            page.fill("#reset-confirm-password", reset_new_pwd)

            shot2 = os.path.join(ARTIFACT_DIR, "reset_password_page_form.png")
            page.screenshot(path=shot2)
            print(">> Saved screenshot:", shot2, flush=True)

            print("6. Submitting Reset Password form...", flush=True)
            page.click("#btn-submit-reset-password")

            # Wait for success card
            page.wait_for_selector("h2:has-text('Password Reset Successful!')", timeout=6000)
            shot3 = os.path.join(ARTIFACT_DIR, "reset_password_success.png")
            page.screenshot(path=shot3)
            print(">> Saved screenshot:", shot3, flush=True)

            # Wait for automatic redirect to /login
            page.wait_for_url("**/login*", timeout=8000)
            page.wait_for_load_state("networkidle")
            print(">> Successfully redirected to /login after password reset!", flush=True)

            # -----------------------------------------------------------------
            # FLOW 2: Login with New Password & Test Security Card on Client Profile
            # -----------------------------------------------------------------
            print("7. Logging in with NEW reset password...", flush=True)
            page.fill("#login-email", test_email)
            page.fill("#login-password", reset_new_pwd)
            page.click("#login-submit")

            page.wait_for_url("**/client*", timeout=10000)
            page.wait_for_load_state("networkidle")
            print(">> Logged in successfully with new password! Landed on:", page.url, flush=True)

            # Scroll to SecurityCard
            sec_card = page.locator("#security-current-password")
            sec_card.wait_for(state="visible", timeout=8000)
            sec_card.scroll_into_view_if_needed()

            # Test Wrong Current Password
            print("8. Testing wrong current password on Security Card...", flush=True)
            page.fill("#security-current-password", "WrongCurrentPassword123!")
            page.fill("#security-new-password", final_updated_pwd)
            page.fill("#security-confirm-password", final_updated_pwd)
            page.click("#btn-update-password")

            page.wait_for_selector("text='Current password is incorrect'", timeout=5000)
            shot4 = os.path.join(ARTIFACT_DIR, "security_card_wrong_password_toast.png")
            page.screenshot(path=shot4)
            print(">> Saved screenshot:", shot4, flush=True)

            # Test Correct Current Password
            print("9. Testing correct current password on Security Card...", flush=True)
            page.fill("#security-current-password", reset_new_pwd)
            page.fill("#security-new-password", final_updated_pwd)
            page.fill("#security-confirm-password", final_updated_pwd)
            page.click("#btn-update-password")

            page.wait_for_selector("text='Password updated successfully'", timeout=5000)
            page.wait_for_timeout(1000)

            # Verify inputs cleared
            assert page.locator("#security-current-password").input_value() == "", "Current password input must be cleared"
            assert page.locator("#security-new-password").input_value() == "", "New password input must be cleared"
            assert page.locator("#security-confirm-password").input_value() == "", "Confirm password input must be cleared"
            print(">> Verified all password inputs cleared upon success!", flush=True)

            shot5 = os.path.join(ARTIFACT_DIR, "security_card_success_cleared.png")
            page.screenshot(path=shot5)
            print(">> Saved screenshot:", shot5, flush=True)

            # -----------------------------------------------------------------
            # FLOW 3: Lawyer Profile Security Card
            # -----------------------------------------------------------------
            print("10. Testing Lawyer Profile Security Card...", flush=True)
            page.goto("http://localhost:5173/login")
            page.fill("#login-email", "lawyer@bdlegal.ai")
            page.fill("#login-password", "Password123!")
            page.click("#login-submit")
            page.wait_for_url("**/lawyer*", timeout=10000)

            page.goto("http://localhost:5173/lawyer?tab=profile")
            page.wait_for_selector("#security-current-password", timeout=10000)
            page.locator("#security-current-password").scroll_into_view_if_needed()

            shot6 = os.path.join(ARTIFACT_DIR, "lawyer_profile_security_card.png")
            page.screenshot(path=shot6)
            print(">> Saved screenshot:", shot6, flush=True)

            # -----------------------------------------------------------------
            # FLOW 4: Invalid / Expired Token Edge Cases
            # -----------------------------------------------------------------
            print("11. Testing missing token on /reset-password (fresh clean tab)...", flush=True)
            page.close()
            page = context.new_page()
            page.goto("http://localhost:5173/reset-password")
            page.wait_for_selector("h2:has-text('Invalid reset link')", timeout=10000)
            shot7 = os.path.join(ARTIFACT_DIR, "reset_password_missing_token.png")
            page.screenshot(path=shot7)
            print(">> Saved screenshot:", shot7, flush=True)

            print("12. Testing expired / invalid token on /reset-password?token=expired.dummy...", flush=True)
            page.goto("http://localhost:5173/reset-password?token=expired.dummy.token")
            page.wait_for_selector("#reset-new-password", timeout=10000)
            page.fill("#reset-new-password", "SomePassword123!")
            page.fill("#reset-confirm-password", "SomePassword123!")
            page.click("#btn-submit-reset-password")

            page.wait_for_selector("h2:has-text('Link Invalid or Expired')", timeout=8000)
            shot8 = os.path.join(ARTIFACT_DIR, "reset_password_expired_token_card.png")
            page.screenshot(path=shot8)
            print(">> Saved screenshot:", shot8, flush=True)

            browser.close()
            print("\nALL E2E PASSWORD VISUAL FLOWS COMPLETED SUCCESSFULLY!", flush=True)

    finally:
        db.query(AuditLog).filter(AuditLog.actor_id == user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    main()
