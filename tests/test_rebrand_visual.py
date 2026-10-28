import os
import sys

backend_dir = os.path.abspath('backend')
os.chdir(backend_dir)
sys.path.insert(0, os.path.join(backend_dir, 'venv', 'Lib', 'site-packages'))
sys.path.insert(0, backend_dir)

from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\USER\.gemini\antigravity\brain\dafeb3a4-5a30-487e-b175-bcbc3a9bdfa2"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        # -------------------------------------------------------------
        # 1. LANDING PAGE & TITLE VERIFICATION
        # -------------------------------------------------------------
        print("1. Loading Landing Page http://localhost:5173/...", flush=True)
        page.goto("http://localhost:5173/")
        page.wait_for_selector("h1:has-text('Legal Bridge')", timeout=10000)

        # Assert document title
        doc_title = page.title()
        print(">> Page Title:", doc_title, flush=True)
        assert "Legal Bridge" in doc_title, f"Document title missing Legal Bridge: {doc_title}"

        # Assert Navbar brand
        navbar_brand = page.locator("nav").text_content()
        assert "Legal" in navbar_brand and "Bridge" in navbar_brand, f"Navbar missing Legal Bridge: {navbar_brand}"

        # Assert Section 1 Hero
        assert page.locator("h1:has-text('Legal Bridge')").is_visible(), "Hero H1 not visible"
        assert page.locator("text='Your bridge to justice.'").first.is_visible(), "Tagline not visible"
        assert page.locator("button:has-text('Start Chatting')").is_visible(), "Start Chatting button not visible"
        assert page.locator("button:has-text('Find a Lawyer')").is_visible(), "Find a Lawyer button not visible"

        # Screenshot 1: Hero & Trust Bar
        shot1 = os.path.join(ARTIFACT_DIR, "rebrand_landing_hero_trust.png")
        page.screenshot(path=shot1)
        print(">> Saved:", shot1, flush=True)

        # Assert Section 2 Trust Bar
        assert page.locator("text='Bar Council Verified'").first.is_visible(), "Trust Bar Chip 1 missing"
        assert page.locator("text='SSLCommerz Secure Payments'").first.is_visible(), "Trust Bar Chip 2 missing"
        assert page.locator("text='Audited Privacy'").first.is_visible(), "Trust Bar Chip 3 missing"

        # Assert Section 3 How It Works
        assert page.locator("h2:has-text('How Legal Bridge Works')").is_visible(), "How It Works heading missing"
        assert page.locator("h3:has-text('Ask the AI')").is_visible(), "Step 1 missing"
        assert page.locator("h3:has-text('Match with a Lawyer')").is_visible(), "Step 2 missing"
        assert page.locator("h3:has-text('Consult & Resolve')").is_visible(), "Step 3 missing"

        # Assert Section 4 Features Grid
        assert page.locator("h2:has-text('Everything You Need for Legal Clarity')").is_visible(), "Features heading missing"
        assert page.locator("h3:has-text('AI Legal Assistant')").is_visible(), "AI Legal Assistant missing"
        assert page.locator("h3:has-text('Case Board Marketplace')").is_visible(), "Case Board Marketplace missing"
        assert page.locator("h3:has-text('Video Consultations')").is_visible(), "Video Consultations missing"
        assert page.locator("h3:has-text('Secure Payments')").is_visible(), "Secure Payments missing"
        assert page.locator("h3:has-text('Verified Lawyers')").is_visible(), "Verified Lawyers missing"
        assert page.locator("h3:has-text('Smart Reviews')").is_visible(), "Smart Reviews missing"
        # Verify Firm Management is gone
        assert not page.locator("h3:has-text('Firm Management')").is_visible(), "Firm Management MUST NOT be present"

        # Scroll to Case Board Spotlight & For Lawyers
        sec_caseboard = page.locator("h2:has-text('Post your case. Let lawyers compete.')")
        sec_caseboard.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        shot2 = os.path.join(ARTIFACT_DIR, "rebrand_landing_caseboard_lawyers.png")
        page.screenshot(path=shot2)
        print(">> Saved:", shot2, flush=True)

        # Assert Section 5 Case Board Spotlight
        assert page.locator("h2:has-text('Post your case. Let lawyers compete.')").is_visible()
        assert page.locator("button:has-text('Post a Case')").is_visible()

        # Assert Section 6 For Lawyers Band
        assert page.locator("h2:has-text('Grow your legal practice')").is_visible()
        assert page.locator("text='Reach clients nationwide'").first.is_visible()
        assert page.locator("text='Gold Verified Badge'").first.is_visible()
        assert page.locator("text='Full schedule control'").first.is_visible()

        # Scroll to Pricing & Testimonials
        sec_pricing = page.locator("h2:has-text('Simple Plans for Every Citizen')")
        sec_pricing.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        shot3 = os.path.join(ARTIFACT_DIR, "rebrand_landing_pricing_testimonials.png")
        page.screenshot(path=shot3)
        print(">> Saved:", shot3, flush=True)

        # Assert Section 7 Pricing Teaser
        assert page.locator("h3:has-text('Free Plan')").is_visible()
        assert page.locator("h3:has-text('Pro Citizen')").is_visible()

        # Assert Section 8 Testimonials
        assert page.locator("p", has_text="Got my property dispute resolved in 2 weeks").is_visible()
        assert page.locator("p", has_text="The AI helped me understand my rights before I hired a lawyer").is_visible()
        assert page.locator("p", has_text="As a lawyer, this platform doubled my caseload").is_visible()

        # Scroll to Final CTA & Footer
        page.locator("footer").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        shot4 = os.path.join(ARTIFACT_DIR, "rebrand_landing_cta_footer.png")
        page.screenshot(path=shot4)
        print(">> Saved:", shot4, flush=True)

        # Assert Section 9 Final CTA Band
        assert page.locator("h2:has-text('Ready to get started?')").is_visible()
        assert page.locator("button:has-text('Sign Up Free')").is_visible()

        # Assert Section 10 Footer
        footer = page.locator("footer")
        assert footer.locator("span", has_text="Bridge").first.is_visible()
        assert footer.locator("text=Your bridge to justice.").is_visible()
        assert footer.locator("text=educational and informational purposes").is_visible()
        assert footer.locator("h4:has-text('Product')").is_visible()
        assert footer.locator("h4:has-text('For Lawyers')").is_visible()
        assert footer.locator("h4:has-text('Legal & Support')").is_visible()
        assert footer.locator("text=2026 Legal Bridge. Made in Bangladesh").is_visible()

        # -------------------------------------------------------------
        # 2. LOGIN PAGE REBRAND
        # -------------------------------------------------------------
        print("2. Testing Login Page http://localhost:5173/login...", flush=True)
        page.goto("http://localhost:5173/login")
        page.wait_for_selector("#login-email", timeout=10000)

        login_title = page.title()
        print(">> Login Title:", login_title, flush=True)
        assert "Legal Bridge" in login_title, f"Login page title missing Legal Bridge: {login_title}"
        assert page.locator("text='Log in to Legal Bridge'").is_visible(), "Login subtitle missing Legal Bridge"

        shot5 = os.path.join(ARTIFACT_DIR, "rebrand_login_page.png")
        page.screenshot(path=shot5)
        print(">> Saved:", shot5, flush=True)

        # -------------------------------------------------------------
        # 3. CITIZEN NAVBAR REBRAND
        # -------------------------------------------------------------
        print("3. Testing Citizen Login & Navbar...", flush=True)
        page.fill("#login-email", "free_user@legalbridge.ai")
        page.fill("#login-password", "Password123!")
        page.wait_for_function("() => !document.querySelector('#login-submit').disabled")
        page.click("#login-submit")
        page.wait_for_selector("text=Rahim Ahmed", timeout=15000)
        print(">> Citizen landed on:", page.url, flush=True)

        nav_text = page.locator("nav").text_content()
        assert "Legal" in nav_text and "Bridge" in nav_text, f"Citizen navbar missing Legal Bridge: {nav_text}"
        shot6 = os.path.join(ARTIFACT_DIR, "rebrand_citizen_dashboard.png")
        page.screenshot(path=shot6)
        print(">> Saved:", shot6, flush=True)

        context.close()

        # -------------------------------------------------------------
        # 4. LAWYER NAVBAR REBRAND
        # -------------------------------------------------------------
        print("4. Testing Lawyer Login & Navbar...", flush=True)
        context2 = browser.new_context(viewport={"width": 1440, "height": 950})
        page2 = context2.new_page()
        page2.goto("http://localhost:5173/login")
        page2.wait_for_selector("#login-email", timeout=10000)
        page2.fill("#login-email", "pro_lawyer@legalbridge.ai")
        page2.fill("#login-password", "Password123!")
        page2.wait_for_function("() => !document.querySelector('#login-submit').disabled")
        page2.click("#login-submit")
        page2.wait_for_url("**/lawyer", timeout=15000)
        page2.locator("nav", has_text="Nusrat").wait_for(timeout=15000)
        print(">> Lawyer landed on:", page2.url, flush=True)

        nav_text_lawyer = page2.locator("nav").text_content()
        assert "Legal" in nav_text_lawyer and "Bridge" in nav_text_lawyer, f"Lawyer navbar missing Legal Bridge: {nav_text_lawyer}"
        shot7 = os.path.join(ARTIFACT_DIR, "rebrand_lawyer_dashboard.png")
        page2.screenshot(path=shot7)
        print(">> Saved:", shot7, flush=True)

        context2.close()

        # -------------------------------------------------------------
        # 5. ADMIN PANEL REBRAND
        # -------------------------------------------------------------
        print("5. Testing Admin Login & Dashboard...", flush=True)
        context3 = browser.new_context(viewport={"width": 1440, "height": 950})
        page3 = context3.new_page()
        page3.goto("http://localhost:5173/login")
        page3.wait_for_selector("#login-email", timeout=10000)
        page3.fill("#login-email", "admin@legalbridge.ai")
        page3.fill("#login-password", "Password123!")
        page3.wait_for_function("() => !document.querySelector('#login-submit').disabled")
        page3.click("#login-submit")
        page3.wait_for_url("**/admin", timeout=15000)
        page3.locator("h1", has_text="Legal Bridge Admin").wait_for(timeout=15000)
        print(">> Admin landed on:", page3.url, flush=True)

        admin_title = page3.title()
        print(">> Admin Title:", admin_title, flush=True)
        assert "Legal Bridge" in admin_title, f"Admin title missing Legal Bridge: {admin_title}"

        # Check Admin sidebar brand & page header
        assert page3.locator("text=Legal Bridge").first.is_visible()
        assert page3.locator("h1:has-text('Legal Bridge Admin')").is_visible()

        shot8 = os.path.join(ARTIFACT_DIR, "rebrand_admin_dashboard.png")
        page3.screenshot(path=shot8)
        print(">> Saved:", shot8, flush=True)

        context3.close()
        browser.close()
        print("\nALL REBRAND VISUAL ASSERTIONS PASSED SUCCESSFULLY!", flush=True)

if __name__ == "__main__":
    main()
