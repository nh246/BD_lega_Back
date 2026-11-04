import os
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_documents"))
os.makedirs(OUT_DIR, exist_ok=True)
print(f"Generating test documents in: {OUT_DIR}")

# -------------------------------------------------------------
# 1. GENERATE NATIONAL ID CARD (01_National_ID_Card.png)
# -------------------------------------------------------------
def generate_nid():
    width, height = 850, 520
    img = Image.new("RGB", (width, height), color="#f8fafc")
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rounded_rectangle([10, 10, width - 10, height - 10], radius=24, outline="#0284c7", width=3)

    # Top Header banner (Green)
    draw.rounded_rectangle([15, 15, width - 15, 95], radius=16, fill="#047857")
    # Red circle emblem
    draw.ellipse([35, 25, 95, 85], fill="#dc2626")

    # Header texts
    draw.text((120, 24), "Government of the People's Republic of Bangladesh", fill="#ffffff")
    draw.text((120, 48), "National Identity Card / জাতীয় পরিচয়পত্র", fill="#fef08a")

    # Smart card chip outline
    draw.rounded_rectangle([45, 125, 155, 215], radius=8, fill="#e2e8f0", outline="#94a3b8", width=2)
    draw.line([45, 170, 155, 170], fill="#94a3b8", width=2)
    draw.line([100, 125, 100, 215], fill="#94a3b8", width=2)

    # Photo Box
    draw.rounded_rectangle([45, 235, 175, 410], radius=10, fill="#cbd5e1", outline="#64748b", width=2)
    draw.text((80, 310), "PHOTO", fill="#475569")

    # Details
    draw.text((210, 125), "Name: MD. NAZMUL HOSSAIN", fill="#0f172a")
    draw.text((210, 160), "Father: Late Rafiqul Hossain", fill="#334155")
    draw.text((210, 195), "Mother: Begum Rokeya", fill="#334155")
    draw.text((210, 230), "Date of Birth: 14 Aug 1988", fill="#334155")
    draw.text((210, 265), "Blood Group: B+", fill="#dc2626")

    # NID Number Bar
    draw.rounded_rectangle([210, 310, width - 40, 365], radius=8, fill="#f1f5f9", outline="#0284c7", width=2)
    draw.text((225, 325), "NID NO: 19882691234567890", fill="#0369a1")

    # Signature & Watermark
    draw.text((210, 385), "Signature: M. N. Hossain", fill="#1e293b")
    draw.line([210, 410, 380, 410], fill="#64748b", width=1)

    # Bottom footer security bar
    draw.rectangle([15, height - 55, width - 15, height - 15], fill="#0f172a")
    draw.text((30, height - 42), "<<BGD19882691234567890<<<<04<<<<<HOSSAIN<<NAZMUL<<<<<<<<<<<", fill="#38bdf8")

    out_path = os.path.join(OUT_DIR, "01_National_ID_Card.png")
    img.save(out_path, "PNG")
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 2. GENERATE BAR COUNCIL SANAD (02_Bar_Council_Sanad.png)
# -------------------------------------------------------------
def generate_sanad():
    width, height = 850, 1150
    img = Image.new("RGB", (width, height), color="#fffbeb")
    draw = ImageDraw.Draw(img)

    # Vintage Ornate Double Border
    draw.rectangle([20, 20, width - 20, height - 20], outline="#78350f", width=4)
    draw.rectangle([30, 30, width - 30, height - 30], outline="#92400e", width=2)
    draw.rectangle([38, 38, width - 38, height - 38], outline="#b45309", width=1)

    # Top Emblem
    draw.ellipse([width//2 - 45, 55, width//2 + 45, 145], outline="#78350f", width=3, fill="#fef3c7")
    draw.text((width//2 - 25, 90), "SEAL", fill="#78350f")

    # Titles
    draw.text((width//2 - 180, 165), "BANGLADESH BAR COUNCIL", fill="#78350f")
    draw.text((width//2 - 210, 205), "BAR COUNCIL BHABAN, SHAHBAGH, DHAKA", fill="#92400e")
    draw.line([150, 235, width - 150, 235], fill="#b45309", width=2)

    draw.text((width//2 - 220, 260), "CERTIFICATE OF ENROLLMENT AS AN ADVOCATE", fill="#1e1b4b")
    draw.text((width//2 - 60, 290), "(SANAD)", fill="#b45309")

    # Certificate Body Text
    lines = [
        "This is to certify that",
        "MR. NAZMUL HOSSAIN",
        "Son of Late Rafiqul Hossain and Begum Rokeya",
        "having fulfilled all the conditions prescribed by the Legal Practitioners",
        "and Bar Council Order, 1972 (President's Order No. 46 of 1972)",
        "and the rules framed thereunder, has this day been duly admitted",
        "and enrolled as an",
        "ADVOCATE",
        "of the Supreme Court of Bangladesh / District Courts.",
        "",
        "Sanad / Registration No: BC-SC-2015-8842",
        "Date of Enrollment: 12th day of May, 2015",
        "Roll No: 1489/HC/2015",
        "Place of Practice: Dhaka & High Court Division, Supreme Court",
    ]

    y = 350
    for line in lines:
        if line == "MR. NAZMUL HOSSAIN":
            draw.text((width//2 - 130, y), line, fill="#0f172a")
            draw.line([width//2 - 140, y + 25, width//2 + 140, y + 25], fill="#0f172a", width=1)
            y += 50
        elif line == "ADVOCATE":
            draw.text((width//2 - 65, y), line, fill="#047857")
            y += 45
        else:
            w_est = len(line) * 4
            draw.text((max(80, width//2 - w_est), y), line, fill="#1e293b")
            y += 35

    # Gold Foil Seal Stamp simulation
    draw.ellipse([80, 850, 200, 970], outline="#b45309", width=4, fill="#fde68a")
    draw.text((105, 900), "OFFICIAL SEAL\nBAR COUNCIL", fill="#78350f")

    # Signatures
    draw.line([100, 1050, 280, 1050], fill="#334155", width=2)
    draw.text((120, 1060), "Secretary, Bar Council", fill="#475569")

    draw.line([width - 300, 1050, width - 120, 1050], fill="#334155", width=2)
    draw.text((width - 280, 1060), "Chairman, Enrollment Committee", fill="#475569")

    out_path = os.path.join(OUT_DIR, "02_Bar_Council_Sanad.png")
    img.save(out_path, "PNG")
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 3. GENERATE PRACTICING LICENSE (03_High_Court_Practicing_License.png)
# -------------------------------------------------------------
def generate_license():
    width, height = 850, 520
    img = Image.new("RGB", (width, height), color="#0f172a")
    draw = ImageDraw.Draw(img)

    # Gold Border
    draw.rounded_rectangle([15, 15, width - 15, height - 15], radius=20, outline="#eab308", width=3)
    draw.rounded_rectangle([25, 25, width - 25, height - 25], radius=15, outline="#ca8a04", width=1)

    # Header
    draw.rounded_rectangle([25, 25, width - 25, 105], radius=12, fill="#1e293b")
    draw.text((45, 38), "SUPREME COURT BAR ASSOCIATION, BANGLADESH", fill="#fbbf24")
    draw.text((45, 68), "HIGH COURT DIVISION PRACTICING PERMIT — 2026/2027", fill="#e2e8f0")

    # Photo box
    draw.rounded_rectangle([50, 130, 185, 310], radius=10, fill="#1e293b", outline="#eab308", width=2)
    draw.text((85, 210), "PHOTO", fill="#94a3b8")

    # Lawyer Details
    draw.text((220, 135), "ADVOCATE NAZMUL HOSSAIN", fill="#f8fafc")
    draw.text((220, 175), "SCBA Member No: 4421", fill="#fbbf24")
    draw.text((220, 210), "Bar Council Sanad: BC-SC-2015-8842", fill="#cbd5e1")
    draw.text((220, 245), "Specialization: Civil & Constitutional Litigation", fill="#cbd5e1")
    draw.text((220, 280), "Enrolled Date: 12-05-2015", fill="#cbd5e1")
    draw.text((220, 315), "Status: ACTIVE PRACTICING ADVOCATE", fill="#34d399")

    # Validity badge
    draw.rounded_rectangle([50, 350, width - 50, 420], radius=10, fill="#1e293b", outline="#34d399", width=2)
    draw.text((70, 375), "PERMIT VALID TILL: 31 DECEMBER 2027", fill="#34d399")
    draw.text((width - 250, 375), "SECURITY CODE: HC-9984", fill="#e2e8f0")

    # Footer
    draw.text((50, 455), "Authorized by Supreme Court Bar Association & Bangladesh Bar Council", fill="#64748b")

    out_path = os.path.join(OUT_DIR, "03_High_Court_Practicing_License.png")
    img.save(out_path, "PNG")
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 4. GENERATE COMMERCIAL TENANCY AGREEMENT (04_Commercial_Tenancy_Agreement.pdf)
# -------------------------------------------------------------
def generate_tenancy_pdf():
    out_path = os.path.join(OUT_DIR, "04_Commercial_Tenancy_Agreement.pdf")
    doc = SimpleDocTemplate(out_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=15,
    )
    h2_style = ParagraphStyle(
        "DocH2",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0369a1"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=8,
    )

    story = []
    story.append(Paragraph("<b>COMMERCIAL SHOP LEASE & TENANCY AGREEMENT</b>", title_style))
    story.append(Paragraph("Governed under the Transfer of Property Act, 1882 and Premises Rent Control Act, 1991", ParagraphStyle("Sub", parent=body_style, alignment=1, textColor=colors.HexColor("#64748b"))))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=15))

    story.append(Paragraph("<b>THIS DEED OF COMMERCIAL LEASE</b> is made on this 1st day of November, 2026 between:", body_style))
    story.append(Paragraph("<b>FIRST PARTY (LANDLORD):</b> Hajee Abdul Karim, S/O Late Shamsul Karim, residing at House 14, Road 5, Gulshan-2, Dhaka-1212.", body_style))
    story.append(Paragraph("<b>SECOND PARTY (TENANT):</b> TechVision Solutions Ltd., represented by its Managing Director, Karim Chowdhury, having corporate office at Banani, Dhaka.", body_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>TERMS AND CONDITIONS:</b>", h2_style))
    terms = [
        "<b>1. Rented Premises:</b> Commercial space measuring 1,450 sq. ft. situated at Shop No. 4B, 3rd Floor, Concord Tower, Gulshan-2, Dhaka.",
        "<b>2. Monthly Rent:</b> The monthly rental is mutually agreed at <b>BDT 65,000/- (Sixty Five Thousand Taka only)</b>, payable within the 7th day of each calendar month.",
        "<b>3. Security Advance:</b> The Tenant has deposited an interest-free advance of <b>BDT 3,00,000/- (Three Lakh Taka)</b> refundable upon expiry of the tenancy after adjusting any utility dues.",
        "<b>4. Lease Period:</b> The lease shall be in force for a period of <b>3 (Three) years</b> starting from November 1, 2026 to October 31, 2029.",
        "<b>5. Subletting Restriction:</b> Under no circumstances shall the Tenant sublet, transfer, or assign the premises to any third party without express written consent from the Landlord.",
        "<b>6. Termination Notice:</b> Either party may terminate this agreement by serving <b>3 (Three) months prior written notice</b>.",
        "<b>7. Dispute Resolution:</b> Any dispute arising out of this agreement shall be settled through arbitration under the Arbitration Act, 2001 or referred to the Rent Controller Court in Dhaka.",
    ]
    for t in terms:
        story.append(Paragraph(t, body_style))

    story.append(Spacer(1, 20))
    sig_data = [
        ["_________________________", "_________________________"],
        ["FIRST PARTY (LANDLORD)", "SECOND PARTY (TENANT)"],
        ["Hajee Abdul Karim", "Karim Chowdhury (MD, TechVision)"],
    ]
    sig_table = Table(sig_data, colWidths=[250, 250])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#1e293b")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
    ]))
    story.append(sig_table)

    doc.build(story)
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 5. GENERATE EMPLOYMENT AND NDA AGREEMENT (05_Employment_and_NDA_Agreement.pdf)
# -------------------------------------------------------------
def generate_nda_pdf():
    out_path = os.path.join(OUT_DIR, "05_Employment_and_NDA_Agreement.pdf")
    doc = SimpleDocTemplate(out_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=17,
        leading=21,
        alignment=1,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=15,
    )
    h2_style = ParagraphStyle(
        "DocH2",
        parent=styles["Heading2"],
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#4338ca"),
        spaceBefore=10,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=7,
    )

    story = []
    story.append(Paragraph("<b>EMPLOYMENT CONTRACT & PROPRIETARY INFORMATION AGREEMENT</b>", title_style))
    story.append(Paragraph("In accordance with Bangladesh Labor Act, 2006 (as amended) and The Contract Act, 1872", ParagraphStyle("Sub", parent=body_style, alignment=1, textColor=colors.HexColor("#64748b"))))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#4f46e5"), spaceAfter=12))

    story.append(Paragraph("<b>PARTIES:</b>", h2_style))
    story.append(Paragraph("<b>Employer:</b> Apex Digital Innovations Bangladesh Ltd., Plot 7, Block B, Niketan, Gulshan-1, Dhaka.", body_style))
    story.append(Paragraph("<b>Employee:</b> Mr. Tanvir Hasan, NID: 19912693847291029, residing at Dhanmondi, Dhaka.", body_style))

    story.append(Paragraph("<b>KEY COVENANTS:</b>", h2_style))
    covenants = [
        "<b>1. Position and Scope:</b> The Employee is appointed as <i>Principal AI Software Engineer</i> responsible for platform architecture and algorithmic intelligence systems.",
        "<b>2. Compensation & Benefits:</b> Monthly gross salary of <b>BDT 1,40,000/-</b> plus festival bonuses, provident fund, and medical insurance in compliance with Chapter XI of the Labor Act.",
        "<b>3. Confidentiality (NDA):</b> The Employee shall not at any time, during or following employment, disclose trade secrets, source code, client records, or proprietary models to any third party.",
        "<b>4. Intellectual Property Assignment:</b> All software code, algorithms, inventions, and patentable assets developed during working hours belong exclusively to the Employer.",
        "<b>5. Non-Compete Evaluation:</b> Any clause restricting the Employee from lawful profession after termination is subject to Section 27 of the Contract Act, 1872 (Restraint of Trade void).",
        "<b>6. Notice Period:</b> Either party may terminate with <b>60 (Sixty) days written notice</b> or payment of equivalent salary in lieu thereof under Section 26 of the Labor Act, 2006.",
    ]
    for c in covenants:
        story.append(Paragraph(c, body_style))

    story.append(Spacer(1, 25))
    sig_data = [
        ["_________________________", "_________________________"],
        ["FOR EMPLOYER", "EMPLOYEE SIGNATURE"],
        ["Director, Human Resources", "Mr. Tanvir Hasan"],
    ]
    sig_table = Table(sig_data, colWidths=[250, 250])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#1e293b")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
    ]))
    story.append(sig_table)

    doc.build(story)
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 6. GENERATE LAND DISPUTE LEGAL NOTICE (06_Land_Boundary_Dispute_Legal_Notice.pdf)
# -------------------------------------------------------------
def generate_legal_notice_pdf():
    out_path = os.path.join(OUT_DIR, "06_Land_Boundary_Dispute_Legal_Notice.pdf")
    doc = SimpleDocTemplate(out_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        "AdvHeader",
        parent=styles["Normal"],
        fontSize=11,
        alignment=1,
        leading=15,
        textColor=colors.HexColor("#0f172a"),
    )
    title_style = ParagraphStyle(
        "NoticeTitle",
        parent=styles["Heading2"],
        fontSize=14,
        alignment=1,
        textColor=colors.HexColor("#b91c1c"),
        spaceBefore=12,
        spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "NoticeBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14.5,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=8,
    )

    story = []
    story.append(Paragraph("<b>ADV. MD. RAFIQUL ISLAM</b><br/>LL.B (Hons), LL.M (DU)<br/>Advocate, Supreme Court of Bangladesh<br/>Chamber: Room 402, Supreme Court Bar Association Bhaban, Dhaka.", header_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0f172a"), spaceAfter=10))

    story.append(Paragraph("<b>DATE: 3rd November, 2026</b>", ParagraphStyle("Date", parent=body_style, alignment=2)))
    story.append(Paragraph("<b>TO:</b><br/>Md. Delwar Hossain<br/>Son of Late Habibur Rahman<br/>Plot No. 18, Block-C, Bashundhara R/A, Dhaka-1229.", body_style))

    story.append(Paragraph("<b><u>SUBJECT: FINAL LEGAL NOTICE DEMANDING DEMOLITION OF ILLEGAL BOUNDARY WALL ENCROACHING ON CS/RS DAG NO. 402, KHATIAN NO. 115</u></b>", title_style))

    story.append(Paragraph("Under instructions from and on behalf of my client, <b>Mr. Nazmul Hossain</b>, I hereby serve upon you this formal Legal Notice as follows:", body_style))

    paras = [
        "1. That my client is the lawful owner and title-holder of 6.5 (six point five) decimals of freehold land situated at Mouza: Vatara, CS & RS Dag No. 402, Khatian No. 115, purchased via Registered Deed No. 4882/2012 with mutation completed.",
        "2. That on 22nd October 2026, taking undue advantage of my client's temporary absence, you and your agents unlawfully encroached upon 1.2 decimals of my client's southern boundary by erecting a brick wall without any color of right.",
        "3. That such encroachment constitutes an actionable wrong of criminal trespass under Section 447 of the Penal Code 1860 and civil encroachment under the Specific Relief Act, 1877.",
        "4. <b>DEMAND:</b> You are hereby demanded to demolish the encroaching boundary wall and restore peaceful vacant possession to my client within <b>15 (Fifteen) days</b> from receipt of this notice.",
        "5. Take notice that failing compliance, my client has given me strict instructions to institute a Suit for Permanent Injunction, Declaration of Title, and Recovery of Possession in the competent Civil Court of Dhaka at your full costs and risks.",
    ]
    for p in paras:
        story.append(Paragraph(p, body_style))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Yours faithfully,<br/><br/><b>(Adv. Md. Rafiqul Islam)</b><br/>Advocate, Supreme Court of Bangladesh", body_style))

    doc.build(story)
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 7. GENERATE MUSLIM FAMILY LAW NOTICE (07_Divorce_Notice_Muslim_Family_Laws.txt)
# -------------------------------------------------------------
def generate_family_txt():
    content = """LEGAL NOTICE OF TALAQ / DIVORCE
Under Section 7(1) of the Muslim Family Laws Ordinance, 1961

Date: 28 October 2026

To:
1. The Chairman / Mayor
   Dhaka North City Corporation, Zone-3, Gulshan, Dhaka.
2. Mst. Farhana Yasmin
   Daughter of Late Shamsuddin Ahmed
   House 22, Road 4, Sector 7, Uttara, Dhaka.

Subject: Formal Notice of Pronouncement of Talaq under Muslim Family Laws Ordinance, 1961

Sir / Madam,

Under instructions from my client, Mr. Asifur Rahman, S/O Dr. M. Rahman, residing at Banani, Dhaka, I do hereby issue this Notice as follows:

1. That my client was married to Mst. Farhana Yasmin on 14th January 2021 according to Muslim Sharia law with solemnization recorded in the Register of Nikah Registrar (Kazi).
2. That owing to irreconcilable differences, emotional incompatibility, and failure of multiple domestic mediation attempts, my client has on 27th October 2026 pronounced single Talaq upon his wife.
3. In strict compliance with Section 7(1) of the Muslim Family Laws Ordinance, 1961, written notice of said pronouncement is hereby delivered to the Chairman of the Local Arbitration Council and a copy served upon the respondent wife.
4. The Chairman is requested to constitute an Arbitration Council within 30 days to facilitate mediation if possible, failing which the Talaq shall become effective upon expiration of ninety (90) days from receipt of this notice.
5. My client confirms readiness to clear all outstanding Dower (Mehr) of BDT 5,00,000/- and maintain the respondent during the statutory Iddat period.

Yours faithfully,

Adv. Md. Khorshed Alam
Advocate, Dhaka Bar Association
Chamber: Court House Street, Kotwali, Dhaka.
"""
    out_path = os.path.join(OUT_DIR, "07_Divorce_Notice_Muslim_Family_Laws.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 8. GENERATE PARTNERSHIP DEED (08_Partnership_Deed.md)
# -------------------------------------------------------------
def generate_partnership_md():
    content = """# DEED OF PARTNERSHIP
**Under The Partnership Act, 1932 (Act IX of 1932)**

**Date:** 1st October, 2026  
**Place:** Dhaka, Bangladesh  

---

## 1. PARTIES
This Deed of Partnership is executed between:
1. **Partner 1:** Mr. Rafiqul Haque, S/O M. Haque, residing at Dhanmondi, Dhaka (Managing Partner - 60% Share).
2. **Partner 2:** Mr. Nazmul Hossain, S/O Late R. Hossain, residing at Uttara, Dhaka (Technical Partner - 40% Share).

---

## 2. FIRM NAME & BUSINESS
* **Firm Name:** *BridgeTech Legal Consultants & Co.*
* **Business Activity:** Legal technology consulting, corporate regulatory compliance, and legal audit advisory services in Bangladesh.
* **Registered Office:** Level 8, Navana Tower, Gulshan-1, Dhaka-1212.

---

## 3. CAPITAL & PROFIT SHARING RATIO
* **Initial Capital:** BDT 10,00,000/- (Ten Lakh Taka) contributed as:
  * Partner 1: BDT 6,00,000 (60%)
  * Partner 2: BDT 4,00,000 (40%)
* **Net Profit / Loss:** Distributed strictly in 60:40 proportion at the close of every financial year (June 30).

---

## 4. BANKING & OPERATIONS
* Bank accounts with Dutch-Bangla Bank Ltd. shall be operated under joint signatures of both partners.
* No partner shall pledge or mortgage partnership assets without prior written consent.

---

## 5. RETIREMENT & DISSOLUTION
* A partner wishing to retire must provide **6 (six) months advance notice** in writing.
* In the event of death or bankruptcy of a partner, the firm shall not automatically dissolve; the surviving partner holds right of first refusal to acquire the deceased partner's shares at audited book value.
* Disputes shall be resolved under the Arbitration Act, 2001 in Dhaka jurisdiction.

---
**IN WITNESS WHEREOF** the partners have signed this deed on the date and year mentioned above.
"""
    out_path = os.path.join(OUT_DIR, "08_Partnership_Deed.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    generate_nid()
    generate_sanad()
    generate_license()
    generate_tenancy_pdf()
    generate_nda_pdf()
    generate_legal_notice_pdf()
    generate_family_txt()
    generate_partnership_md()
    print("\nAll 8 test documents generated successfully!")

