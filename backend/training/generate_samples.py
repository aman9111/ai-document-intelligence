"""Generate fictional page images for training and testing the page classifier.

Every page is fake: made-up names, numbers and organisations, and every ID card
carries a SPECIMEN watermark. Nothing here is a real person or a real document.

    python training/generate_samples.py              # default counts
    python training/generate_samples.py --train 60 --test 15

Output (not committed to git, re-create it any time with the same seed; every
type has its own random sequence, so editing one type changes only its pages):

    training/data/train/<doc_type>/<n>.jpg
    training/data/test/<doc_type>/<n>.jpg
    training/data/failed/<n>.jpg              blank / unreadable pages
    training/data/bundles/bundle_<n>.pdf      multi-page files mixing types
    training/data/manifest.csv                one row per page with its label

The test set uses fonts and settings that never appear in the train set, so the
evaluation shows whether a model learned what a page *is*, not what our training
pages happen to look like.
"""

import argparse
import csv
import json
import random
import string
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from classification.labels import DOC_TYPES  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "data"
PAGE_SIZE = (1240, 1754)  # A4 at 150 dpi
CARD_SIZE = (1012, 638)  # ID card ratio (85.6 x 54 mm)

FONT_DIR = Path("/usr/share/fonts/truetype")
# (regular, bold) pairs. The test set only uses TEST_FONTS.
TRAIN_FONTS = [
    ("dejavu/DejaVuSans.ttf", "dejavu/DejaVuSans-Bold.ttf"),
    ("dejavu/DejaVuSerif.ttf", "dejavu/DejaVuSerif-Bold.ttf"),
    ("dejavu/DejaVuSansCondensed.ttf", "dejavu/DejaVuSansCondensed-Bold.ttf"),
    ("freefont/FreeSans.ttf", "freefont/FreeSansBold.ttf"),
    ("freefont/FreeSerif.ttf", "freefont/FreeSerifBold.ttf"),
    ("liberation/LiberationSans-Regular.ttf", "liberation/LiberationSans-Bold.ttf"),
    ("freefont/FreeMono.ttf", "freefont/FreeMonoBold.ttf"),
]
TEST_FONTS = [
    ("ubuntu/Ubuntu-R.ttf", "ubuntu/Ubuntu-B.ttf"),
    ("liberation2/LiberationSerif-Regular.ttf", "liberation2/LiberationSerif-Bold.ttf"),
    ("liberation2/LiberationMono-Regular.ttf", "liberation2/LiberationMono-Bold.ttf"),
]


# ---------------------------------------------------------------- fake data

FIRST_NAMES = ["Rohan", "Anita", "Vikram", "Priya", "Arjun", "Sneha", "Rahul", "Kavya", "Amit", "Neha",
               "Suresh", "Pooja", "Karan", "Meera", "Imran", "Fatima", "Joseph", "Mary", "Harpreet", "Lakshmi"]
LAST_NAMES = ["Demo", "Testwala", "Sampleson", "Fakeer", "Dummy", "Placeholder", "Mockrao", "Specimen"]
HOSPITAL_A = ["Sunrise", "Lotus", "CityCare", "Greenfield", "Silverline", "Harmony", "Lifeline", "Bluebell", "Unity"]
HOSPITAL_B = ["Demo Hospital", "Test Medical Centre", "Sample Multispeciality Hospital", "Mock Nursing Home",
              "Demo Diagnostics", "Specimen Health Clinic"]
INSURERS = ["SafeLife Demo Insurance Co.", "Trust Sample General Insurance", "Shield Mock Health Insurance",
            "Assure Test Insurance Ltd"]
BANKS = ["Demo National Bank", "Sample Co-operative Bank", "Test Bank of India", "Mock Federal Bank"]
CITIES = ["Mumbai", "Pune", "Delhi", "Bengaluru", "Chennai", "Hyderabad", "Kolkata", "Jaipur", "Lucknow", "Indore"]
STREETS = ["MG Road", "Station Road", "Ring Road", "Link Road", "Park Street", "Lake View Road", "Market Lane"]
DIAGNOSES = ["Dengue fever with thrombocytopenia", "Acute appendicitis", "Type 2 diabetes mellitus",
             "Community acquired pneumonia", "Acute gastroenteritis", "Fracture of right radius",
             "Viral fever", "Urinary tract infection", "Hypertension", "Kidney stone (right ureter)"]
MEDICINES = ["Tab Paracetamol 650 mg", "Tab Pantoprazole 40 mg", "Cap Amoxicillin 500 mg", "Tab Metformin 500 mg",
             "Syp Cough Relief 10 ml", "Tab Cetirizine 10 mg", "Inj Ceftriaxone 1 g", "Tab Azithromycin 500 mg",
             "Tab Vitamin D3 60K", "ORS sachet", "Tab Ondansetron 4 mg", "Tab Atorvastatin 10 mg"]
DOSES = ["1-0-1 after food", "0-0-1 at night", "1-1-1 for 5 days", "once daily before breakfast", "SOS if fever",
         "BD for 7 days", "TDS for 5 days", "OD for 30 days"]
LAB_TESTS = [("Haemoglobin", "g/dL", (9, 17), "12.0 - 17.0"), ("WBC count", "/uL", (3500, 15000), "4,000 - 11,000"),
             ("Platelet count", "lakh/uL", (0.6, 4.5), "1.5 - 4.5"), ("Fasting blood sugar", "mg/dL", (70, 220), "70 - 100"),
             ("HbA1c", "%", (4.5, 10), "< 5.7"), ("Serum creatinine", "mg/dL", (0.5, 2.5), "0.6 - 1.2"),
             ("Total cholesterol", "mg/dL", (140, 280), "< 200"), ("TSH", "uIU/mL", (0.3, 8), "0.4 - 4.0"),
             ("SGPT", "U/L", (10, 150), "7 - 56"), ("Vitamin D", "ng/mL", (8, 60), "30 - 100"),
             ("Serum sodium", "mmol/L", (128, 148), "135 - 145")]
SCANS = [("X-ray chest PA view", "lung fields are clear. No consolidation. Heart size is normal."),
         ("Ultrasound abdomen", "liver is normal in size and echotexture. A 6 mm calculus is seen in the right kidney."),
         ("CT scan brain (plain)", "no acute intracranial haemorrhage. Ventricles are normal."),
         ("MRI lumbar spine", "mild disc bulge at L4-L5 indenting the thecal sac. No cord compression."),
         ("X-ray right wrist AP/lateral", "undisplaced fracture of the distal radius is noted.")]
BILL_ITEMS = ["Room charges (General ward)", "Doctor consultation", "Nursing charges", "Laboratory investigations",
              "Radiology", "Pharmacy and consumables", "OT charges", "Anaesthesia charges", "ICU charges",
              "Registration", "Ambulance", "Physiotherapy"]
CONSUMABLES = ["IV Cannula 20G", "Syringe 2 ml", "Syringe 10 ml", "Gloves exam nitrile", "Gloves surgical 7.0",
               "Alcohol swabs", "Cotton roll", "Micropore tape 1 inch", "IV set", "Normal saline 500 ml",
               "Ringer lactate 500 ml", "Dextrose 5% 500 ml", "Bed sheet disposable", "Face mask", "ECG electrodes",
               "Surgical blade", "Suture vicryl 2-0", "Gauze swab", "Urine bag", "Foley catheter 16Fr",
               "Inj Paracetamol 1 g", "Inj Pantoprazole 40 mg", "Inj Ondansetron 4 mg", "Inj Ceftriaxone 1 g",
               "Oxygen per hour", "Nebulisation", "Dressing pad", "Crepe bandage", "Blood glucose strip"]
BILL_SECTIONS = ["Room charges", "Medication", "Consumables", "Pathology", "Radiology", "Professional fees",
                 "OT charges", "Nursing", "Procedures"]
OTHER_KINDS = ["letter", "resume", "notice", "minutes", "certificate", "menu"]


def name(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def hospital(rng):
    return f"{rng.choice(HOSPITAL_A)} {rng.choice(HOSPITAL_B)}"


def doctor(rng):
    return f"Dr. {rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def date(rng):
    return f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.choice([2024, 2025, 2026])}"


def address(rng):
    return f"{rng.randint(1, 250)}, {rng.choice(STREETS)}, {rng.choice(CITIES)} - {rng.randint(400001, 560099)}"


def amount(rng, low=100, high=50000):
    return f"{rng.randint(low, high):,}.{rng.choice(['00', '50'])}"


def digits(rng, n):
    return "".join(rng.choice(string.digits) for _ in range(n))


def letters(rng, n):
    return "".join(rng.choice(string.ascii_uppercase) for _ in range(n))


def phone(rng):
    return f"{rng.choice('6789')}{digits(rng, 4)} {digits(rng, 5)}"


# ---------------------------------------------------------------- page content
# A page is a list of blocks; the renderer decides how each block looks.

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def in_words(n):
    """Rupees in words, Indian style: 1890 -> "One Thousand Eight Hundred And Ninety"."""
    def below_hundred(x):
        return ONES[x] if x < 20 else (TENS[x // 10] + (" " + ONES[x % 10] if x % 10 else ""))

    parts = []
    for size, word in [(100000, "Lakh"), (1000, "Thousand"), (100, "Hundred")]:
        if n >= size:
            parts.append(f"{below_hundred(n // size)} {word}")
            n %= size
    if n:
        parts.append(("And " if parts else "") + below_hundred(n))
    return " ".join(parts) or "Zero"


def contact_line(rng, org="demo"):
    # Real bills and receipts often end with a website, email and phone number.
    # Without these, the model learnt that "contact details" mean a letter or resume.
    slug = "".join(c for c in org.lower() if c.isalnum())[:14] or "demo"
    return rng.choice([
        f"Visit our website www.{slug}-demo.in  |  Email: care@{slug}-demo.in",
        f"Helpline: {phone(rng)}  |  www.{slug}-demo.in",
        f"For home sample collection call {phone(rng)}  |  Email: help@{slug}-demo.in",
        f"Customer care {phone(rng)}  |  Reports online at www.{slug}-demo.in",
    ])


LAB_RECEIPT_TESTS = ["Haemogram (CBC)", "SGPT (ALT)", "SGOT (AST)", "Bilirubin total", "Bilirubin direct",
                     "Lipid profile", "Thyroid profile (T3 T4 TSH)", "HbA1c", "Vitamin B12", "Vitamin D (25-OH)",
                     "Serum creatinine", "Blood urea", "Urine routine and microscopy", "Fasting blood sugar",
                     "Post prandial blood sugar", "ESR", "CRP", "Dengue NS1 antigen", "Widal test", "Serum calcium",
                     "Liver function test", "Kidney function test", "Iron studies", "Malaria antigen"]
PAY_MODES = ["Paytm POS", "UPI", "PhonePe", "GPay", "Card POS", "Cash", "Credit card", "Debit card", "NEFT"]


def lab_receipt(rng):
    """Diagnostic lab bill-cum-receipt: tests with report time and price, totals,
    a payment history table and the amount in words."""
    org = f"{rng.choice(HOSPITAL_A)} {rng.choice(['Demo Diagnostics', 'Sample Pathology Lab', 'Test Clinical Laboratories', 'Mock Path Labs'])}"
    tests = rng.sample(LAB_RECEIPT_TESTS, rng.randint(2, 7))
    prices = [rng.choice([90, 120, 150, 190, 230, 280, 350, 450, 600, 850, 1200]) for _ in tests]
    gross = sum(prices)
    discount = rng.choice([0, 0, 0, round(gross * 0.1)])
    net = gross - discount
    when = date(rng)
    if rng.random() < 0.6:
        rows = [(t, f"{when} {rng.choice(['02:30 PM', '04:30 PM', '06:00 PM', '11:00 AM'])}",
                 rng.choice(["", "", "TAT is for working days", "Fasting sample"]), f"{p:.2f}") for t, p in zip(tests, prices)]
        header = ["Test Name", "Expected Report Time", "Remarks", "Amount"]
    else:
        rows = [(str(i + 1), t, f"{p:.2f}") for i, (t, p) in enumerate(zip(tests, prices))]
        header = ["Sr.", "Investigation", "Amount (Rs)"]
    blocks = [
        title(rng.choice(["RECEIPT", "BILL CUM RECEIPT", "PATIENT RECEIPT", "INVOICE", "CASH RECEIPT", "BILL"])),
        kv([("Name", name(rng)), ("Invoice No / Date", f"{digits(rng, 11)} / {when}"),
            ("Age / Gender", f"{rng.randint(1, 85)} Yrs / {rng.choice(['Male', 'Female'])}"),
            ("Branch", f"{rng.choice(CITIES)} Lab"), ("Doctor", doctor(rng)), ("Contact No", phone(rng))]),
        table(header, rows),
        kv([("Gross Bill Amount", f"{gross:.2f}"), ("Discount", f"{discount:.2f}"), ("Net Amount", f"{net:.2f}"),
            ("Paid Amount", f"{net:.2f}"), ("Balance to Pay", "0.00")]),
    ]
    if rng.random() < 0.7:
        blocks.append(heading("Payment History"))
        blocks.append(table(["Receipt No", "Receipt Date", "Amount", "Mode", "Received By"],
                            [(digits(rng, 8), when, f"{net:.2f}", rng.choice(PAY_MODES), name(rng).split()[0])]))
    blocks.append(para(f"Amount Paid in Words : {in_words(net)} Only"))
    if rng.random() < 0.8:
        blocks.append(footer(contact_line(rng, org)))
    return org, blocks


def title(text): return ("title", text)
def heading(text): return ("heading", text)
def kv(pairs): return ("kv", pairs)
def table(header, rows): return ("table", header, rows)
def para(text): return ("para", text)
def sign(text): return ("sign", text)
def footer(text): return ("footer", text)
def qr(): return ("qr",)


def pick(rng, items, low, high):
    return rng.sample(items, rng.randint(low, min(high, len(items))))


def patient_fields(rng):
    fields = [("Patient name", name(rng)), ("Age / Sex", f"{rng.randint(1, 85)}Y / {rng.choice(['Male', 'Female'])}"),
              ("UHID", f"{letters(rng, 3)}-{digits(rng, 2)}-{digits(rng, 6)}"), ("Date", date(rng)),
              ("Consultant", doctor(rng)), ("Ward / Bed", f"{rng.choice(['General', 'Private', 'ICU'])} / Bed-{rng.randint(1, 40)}"),
              ("Mobile", phone(rng))]
    return pick(rng, fields, 3, 6)


def claim_form(rng):
    org = rng.choice(INSURERS)
    return org, [
        title(rng.choice(["HEALTH INSURANCE CLAIM FORM", "CLAIM FORM - PART A", "REIMBURSEMENT CLAIM FORM"])),
        heading("Details of primary insured"),
        kv([("Policy number", f"{letters(rng, 3)}/HLT/{rng.randint(2024, 2026)}/{digits(rng, 6)}"), ("Name of insured", name(rng)),
            ("Address", address(rng)), ("Mobile", phone(rng))]),
        heading("Details of hospitalisation"),
        kv([("Hospital name", hospital(rng)), ("Date of admission", date(rng)), ("Date of discharge", date(rng)),
            ("Diagnosis", rng.choice(DIAGNOSES)), ("Type of claim", rng.choice(["Reimbursement", "Cashless"]))]),
        heading("Claim amount"),
        table(["Expense", "Amount (Rs)"], [(i, amount(rng, 500, 40000)) for i in pick(rng, BILL_ITEMS, 3, 6)]),
        para("I hereby declare that the information furnished in this claim form is true and correct."),
        sign("Signature of insured"),
    ]


HEALTH_PRODUCTS = ["Health Insurance Policy Schedule", "Group Mediclaim Policy Schedule cum Tax Invoice",
                   "Family Health Protector Policy Schedule cum Tax Invoice", "Individual Medishield Policy Schedule",
                   "Critical Illness Policy Schedule cum Tax Invoice", "Personal Accident Policy Schedule"]
OTHER_PRODUCTS = ["Marine Inland Specific Voyage Policy Schedule cum Tax Invoice", "Private Car Package Policy Schedule cum Tax Invoice",
                  "Two Wheeler Liability Policy Schedule", "Standard Fire and Special Perils Policy Schedule cum Tax Invoice",
                  "Shopkeepers Insurance Policy Schedule", "Marine Open Cover Policy Schedule"]


def policy_schedule(rng, health=True):
    """Policy schedule cum tax invoice: QR code, client and invoice details, a few grey
    tables and a digital signature block. Health products are policy documents; marine,
    motor and fire products are "other" (this app is about health documents)."""
    org = rng.choice(INSURERS)
    product = rng.choice(HEALTH_PRODUCTS if health else OTHER_PRODUCTS)
    blocks = [qr()] if rng.random() < 0.7 else []
    blocks += [
        title(product),
        para(f"Regd. Office: {address(rng)}   Corporate Identification Number (CIN): U{digits(rng, 5)}DL{digits(rng, 4)}PLC{digits(rng, 6)}   UIN: {letters(rng, 3).upper()}{digits(rng, 6)}"),
        kv([("Client Name", name(rng).upper()), ("Address", address(rng)), ("Contact No", phone(rng)),
            ("Email", f"{rng.choice(['client', 'accounts', 'user'])}@example.com"),
            ("GSTIN", f"{digits(rng, 2)}{letters(rng, 5).upper()}{digits(rng, 4)}{letters(rng, 1).upper()}1Z{digits(rng, 1)}")]),
        kv([("Unique Invoice Number", f"{letters(rng, 1).upper()}-{letters(rng, 3).upper()}-{digits(rng, 8)}-{digits(rng, 2)}"),
            ("Policy Number", digits(rng, 8)), ("Incepted On Or After", date(rng)),
            ("Expiry", rng.choice([date(rng), "Till the End of the Voyage" if not health else date(rng)])),
            ("Issuing Office", f"{org}, {rng.choice(CITIES)}")]),
        heading("Intermediary Details"),
        table(["Name", "Code", "Contact Number"], [(f"{rng.choice(['Secure', 'Prime', 'Trust'])} Demo Insurance Broker", digits(rng, 8), phone(rng))]),
    ]
    if health:
        members = [(name(rng), date(rng), rng.choice(["Self", "Spouse", "Son", "Daughter", "Father", "Mother"]),
                    f"{amount(rng, 200000, 1000000)}", rng.choice(["None", "Diabetes", "Hypertension", "None"])) for _ in range(rng.randint(1, 4))]
        blocks += [heading("Insured Persons Details"),
                   table(["Name", "Date of Birth", "Relationship", "Sum Insured (Rs)", "Pre-existing Disease"], members),
                   kv([("Plan", rng.choice(["Family Floater", "Individual", "Group"])), ("Room rent limit", "1% of Sum Insured per day"),
                       ("Co-payment", rng.choice(["Nil", "10%", "20%"])), ("TPA", f"{rng.choice(['Medi', 'Health', 'Care'])} Demo TPA Ltd")])]
    elif "Marine" in product:
        blocks += [heading("Risk Details"),
                   kv([("Policy Type", rng.choice(["Inland Rail/Road", "Inland Transit", "Import"])), ("Hypothecation", ""),
                       ("Commodity Category", rng.choice(["Second Hand Vehicles", "Machinery", "Textiles", "Electronic goods"])),
                       ("Nature of Packaging", rng.choice(["Pure Car Containers", "Wooden crates", "Cartons"]))]),
                   heading("Transit Details"),
                   kv([("Voyage From", rng.choice(CITIES).upper()), ("Voyage To", rng.choice(CITIES).upper()), ("Mode of Transit", "Rail/Road")]),
                   heading("Consignment Bill Details"),
                   table(["Bill Type", "Bill Number", "Bill Date"], [("Invoice", digits(rng, 12), date(rng))])]
    elif "Car" in product or "Wheeler" in product:
        blocks += [heading("Vehicle Details"),
                   table(["Make / Model", "Registration No.", "Engine No.", "Chassis No.", "IDV (Rs)"],
                         [(rng.choice(["Demo Motors Sedan", "Sample Auto Hatch", "Mock Bikes 150"]), f"{letters(rng, 2).upper()}{digits(rng, 2)}{letters(rng, 2).upper()}{digits(rng, 4)}",
                           digits(rng, 10), f"{letters(rng, 3).upper()}{digits(rng, 11)}", f"{amount(rng, 50000, 900000)}")])]
    else:
        blocks += [heading("Risk Location and Sum Insured"),
                   table(["Location", "Occupancy", "Sum Insured (Rs)"], [(address(rng), rng.choice(["Shop", "Godown", "Office"]), f"{amount(rng, 100000, 5000000)}")])]
    premium = rng.randint(500, 40000)
    blocks += [heading("Premium Details"),
               table(["Description", "Amount (Rs)"], [("Basic Premium", f"{premium}"), ("CGST @ 9%", f"{premium * 0.09:.2f}"),
                                                     ("SGST @ 9%", f"{premium * 0.09:.2f}"), ("Total Premium", f"{premium * 1.18:.2f}")]),
               para(f"Signature Not Verified\nDigitally signed by {name(rng).upper()}\nDate: {date(rng)} IST\nReason: Valid Policy Copy"),
               footer(f"Page 1 of {rng.randint(2, 4)}")]
    return org, blocks


def motor_claim(rng):
    """Motor claim form (vehicle, driver, accident): an insurance form, but not health, so "other"."""
    blank = rng.random() < 0.6
    v = lambda text: "______________________" if blank else text
    org = rng.choice(INSURERS)
    return org, [
        title(rng.choice(["MOTOR CLAIM FORM", "MOTOR INSURANCE CLAIM FORM", "CLAIM FORM - PRIVATE CAR / TWO WHEELER"])),
        para(f"Regd. Office: {address(rng)}"),
        para("1. THE ISSUE OF THIS FORM IS NOT TO BE TAKEN AS AN ADMISSION OF LIABILITY. 2. PLEASE ANSWER ALL RELEVANT QUESTIONS FULLY. "
             "3. PLEASE CARRY THE FOLLOWING ORIGINAL DOCUMENTS AT THE TIME OF SURVEY OF THE VEHICLE: A) Estimate of Repairs "
             "B) Registration Certificate C) Driving Licence D) F.I.R., If Applicable"),
        kv([("COVER NOTE / POLICY NO.", v(digits(rng, 10))), ("CLAIM NO.", v(digits(rng, 9))),
            ("Policy Period From", v(date(rng))), ("To", v(date(rng)))]),
        heading("1. INSURED"),
        kv([("(a) Name", v(name(rng))), ("(b) Address for correspondence", v(address(rng))), ("(c) Occupation", v("Business")),
            ("(d) Telephone / Mobile No.", v(phone(rng))), ("(e) Email", v("owner@example.com"))]),
        heading("2. THE INSURED VEHICLE"),
        table(["MAKE", "YEAR OF MANUFACTURE", "ENGINE NO.", "CHASSIS NO.", "REGISTRATION NO."],
              [("", "", "", "", "")] if blank else [("Demo Motors", str(rng.randint(2010, 2025)), digits(rng, 10), f"{letters(rng, 3).upper()}{digits(rng, 9)}",
                                                       f"{letters(rng, 2).upper()}{digits(rng, 2)}{letters(rng, 2).upper()}{digits(rng, 4)}")]),
        kv([("(i) Was the vehicle in proper working condition", v("Yes")),
            ("(ii) For what purpose was the vehicle being used at the time of accident?", v("Private")),
            ("(iii) No. of Occupants & their Names", v("2")),
            ("Registered laden weight", v("NA")), ("Nature of permit", v("NA")), ("Was the vehicle plying for hire?", v("No"))]),
        heading("3. DRIVER AT THE TIME OF ACCIDENT"),
        kv([("(a) Name", v(name(rng))), ("(b) Age", v(str(rng.randint(19, 70)))), ("(c) Address", v(address(rng))),
            ("(d) Is the Driver: Owner / Paid driver / Owner's relative or friend", v("Owner")),
            ("(f) Was he under the influence of intoxicating liquor or drugs?", v("No")),
            ("(g) Driving Licence Number", v(f"{letters(rng, 2).upper()}{digits(rng, 13)}")), ("(h) Issuing authority", v("RTO")),
            ("(i) Date of Expiry", v(date(rng))), ("(j) Type of vehicles authorised to drive", v("LMV")),
            ("(k) Was the licence temporary / permanent?", v("Permanent")), ("(l) Has he been involved in any accident before", v("No"))]),
        heading("4. ACCIDENT"),
        kv([("Date and time of accident", v(date(rng))), ("Place of accident", v(rng.choice(CITIES))), ("Speed of the vehicle", v("30 km/h")),
            ("Description of the accident", v("Hit from behind at signal"))]),
        footer("Contd...2"),
    ]


def policy_document(rng):
    if rng.random() < 0.5:
        return policy_schedule(rng, health=True)
    org = rng.choice(INSURERS)
    members = [(name(rng), rng.choice(["Self", "Spouse", "Son", "Daughter"]), str(rng.randint(2, 70))) for _ in range(rng.randint(1, 4))]
    return org, [
        title(rng.choice(["POLICY SCHEDULE", "HEALTH INSURANCE POLICY CERTIFICATE", "SCHEDULE OF BENEFITS"])),
        kv([("Policy number", f"{digits(rng, 4)}/{digits(rng, 8)}"), ("Plan", rng.choice(["Family Floater", "Individual", "Senior Citizen"])),
            ("Policy period", f"{date(rng)} to {date(rng)}"), ("Sum insured", f"Rs {amount(rng, 200000, 1000000)}"),
            ("Premium (incl. GST)", f"Rs {amount(rng, 5000, 40000)}")]),
        heading("Insured members"),
        table(["Name", "Relation", "Age"], members),
        heading("Key benefits"),
        para("In-patient hospitalisation up to sum insured. Pre-hospitalisation 30 days and post-hospitalisation 60 days. "
             "Day care procedures covered. Room rent limit 1% of sum insured per day."),
        sign("Authorised signatory"),
    ]


def preauth_form(rng):
    org = hospital(rng)
    return org, [
        title(rng.choice(["REQUEST FOR CASHLESS HOSPITALISATION", "PRE-AUTHORIZATION REQUEST FORM", "CASHLESS AUTHORISATION REQUEST"])),
        para(f"To: {rng.choice(INSURERS)} / Third Party Administrator"),
        kv([("Name of patient", name(rng)), ("Policy / card number", f"{letters(rng, 2)}{digits(rng, 10)}"),
            ("Treating doctor", doctor(rng)), ("Provisional diagnosis", rng.choice(DIAGNOSES)),
            ("Proposed line of treatment", rng.choice(["Medical management", "Surgical", "Intensive care"])),
            ("Expected date of admission", date(rng)), ("Expected length of stay", f"{rng.randint(1, 10)} days")]),
        heading("Estimated cost"),
        table(["Head", "Amount (Rs)"], [(i, amount(rng, 1000, 60000)) for i in pick(rng, BILL_ITEMS, 3, 5)]),
        sign("Signature and seal of hospital"),
    ]


def discharge_summary(rng):
    org = hospital(rng)
    blocks = [title("DISCHARGE SUMMARY"), kv(patient_fields(rng)), heading("Diagnosis"), para(rng.choice(DIAGNOSES)),
              heading("History and presenting complaints"),
              para(rng.choice(["Fever with chills and body ache for 4 days.", "Pain in right lower abdomen since morning.",
                               "Breathlessness and cough for one week.", "Fall at home with pain and swelling of the wrist."])),
              heading("Hospital course"),
              para("The patient was treated with IV fluids, antibiotics and supportive care. Responded well to treatment "
                   "and was discharged in a stable condition."),
              heading("Medicines on discharge"),
              table(["Medicine", "Dose"], [(m, rng.choice(DOSES)) for m in pick(rng, MEDICINES, 2, 5)]),
              heading("Advice"), para(f"Review in OPD after {rng.randint(1, 3)} weeks. Return immediately if symptoms worsen."),
              sign(f"{doctor(rng)}, Consultant")]
    return org, blocks


def lab_report(rng):
    org = hospital(rng).replace("Hospital", "Diagnostics")
    rows = []
    for test_name, unit, (low, high), ref in pick(rng, LAB_TESTS, 4, 8):
        value = rng.uniform(low, high)
        rows.append((test_name, f"{value:.1f}" if value < 100 else f"{value:,.0f}", unit, ref))
    return org, [
        title(rng.choice(["LABORATORY REPORT", "TEST REPORT", "PATHOLOGY REPORT", "BIOCHEMISTRY REPORT"])),
        kv([("Patient", name(rng)), ("Lab no.", f"{letters(rng, 3)}/{digits(rng, 5)}"), ("Referred by", doctor(rng)),
            ("Sample collected", date(rng))]),
        table(["Test", "Result", "Unit", "Reference range"], rows),
        para("Results should be correlated clinically."),
        sign(f"{doctor(rng)}, MD (Pathology)"),
    ]


def prescription(rng):
    org = f"{doctor(rng)}, MBBS, MD"
    return org, [
        para(f"{rng.choice(['Clinic', 'OPD'])}: {hospital(rng)}  |  Reg. no. {digits(rng, 6)}"),
        kv([("Patient", name(rng)), ("Age", f"{rng.randint(1, 85)} yrs"), ("Date", date(rng))]),
        title("Rx"),
        table(["Medicine", "Dosage", "Duration"], [(m, rng.choice(DOSES), f"{rng.randint(3, 30)} days") for m in pick(rng, MEDICINES, 2, 5)]),
        para(rng.choice(["Plenty of fluids. Light diet.", "Avoid oily food.", "Review after one week with reports."])),
        sign("Signature"),
    ]


def radiology_report(rng):
    org = hospital(rng).replace("Hospital", "Imaging Centre")
    scan, finding = rng.choice(SCANS)
    return org, [
        title(rng.choice(["RADIOLOGY REPORT", "IMAGING REPORT", scan.upper()])),
        kv([("Patient", name(rng)), ("Study", scan), ("Date", date(rng)), ("Referred by", doctor(rng))]),
        heading("Findings"), para(f"The {finding}"),
        heading("Impression"), para(rng.choice(["Study within normal limits.", "Findings as described above.", "Clinical correlation advised."])),
        sign(f"{doctor(rng)}, Radiologist"),
    ]


def consultation_notes(rng):
    org = hospital(rng)
    return org, [
        title(rng.choice(["OPD CONSULTATION", "OUTPATIENT NOTES", "CLINICAL NOTES"])),
        kv(patient_fields(rng)),
        heading("Chief complaints"), para(rng.choice(["Headache for 3 days.", "Cough and cold.", "Joint pain in both knees.", "Burning micturition."])),
        heading("Examination"), para(f"BP {rng.randint(100, 160)}/{rng.randint(60, 100)} mmHg, pulse {rng.randint(60, 110)}/min, temp {rng.uniform(97, 102):.1f} F."),
        heading("Plan"), para(rng.choice(["Investigations advised: CBC, blood sugar.", "Started on medicines. Review in 5 days.", "Refer to orthopaedics."])),
        sign(doctor(rng)),
    ]


def itemized_rows(rng, start=1, sections=True):
    rows, sn = [], start
    for section in rng.sample(BILL_SECTIONS, rng.randint(2, 4)):
        if sections:
            rows.append((section,))  # a one-cell row is drawn as a section heading
        for item in rng.sample(CONSUMABLES + BILL_ITEMS, rng.randint(3, 8)):
            qty = rng.choice([1, 1, 1, 2, 3, 5, 10])
            rate = rng.uniform(5, 3000)
            gross = qty * rate
            rows.append((date(rng), str(sn), item, f"{qty}.00", f"{rate:.2f}", f"{gross:.2f}", "0.00", f"{gross:.2f}"))
            sn += 1
    return rows


ITEMIZED_HEADER = ["Date", "SN", "Description", "Qty", "Rate", "Gross", "Disc.", "Net"]


def hospital_bill(rng):
    org = hospital(rng)
    kind = rng.choice(["summary", "itemized", "itemized", "continuation", "tests"])
    if rng.random() < 0.2:
        return lab_receipt(rng)
    if rng.random() < 0.35:
        return rng.choice([bill_provisional, bill_us_statement, bill_receipt_template, bill_clinic_invoice])(rng)
    patient = kv([("Bill no.", f"{letters(rng, 2)}{digits(rng, 6)}"), ("Patient", name(rng)), ("Admission date", date(rng)),
                  ("Discharge date", date(rng))])
    total_labels = rng.choice([("Gross amount", "Discount", "Net payable"), ("Total bill amount", "Discount", "Net amount"),
                               ("Total amount", "Advance paid", "Balance amount"), ("Bill amount", "Insurance amount", "Patient amount")])
    totals = kv([(total_labels[0], amount(rng, 10000, 200000)), (total_labels[1], amount(rng, 0, 50000)),
                 (total_labels[2], amount(rng, 1000, 200000))])
    pages = rng.randint(2, 8)
    if kind == "summary":
        rows = [(str(i + 1), item, amount(rng, 200, 60000)) for i, item in enumerate(pick(rng, BILL_ITEMS, 4, 9))]
        return org, [title(rng.choice(["FINAL BILL", "IN-PATIENT BILL", "HOSPITAL BILL", "INTERIM BILL", "BILL SUMMARY"])),
                     patient, table(["Sr", "Particulars", "Amount (Rs)"], rows), totals, sign("Billing executive")]
    if kind == "tests":
        # Diagnostic centre / lab bill: test names with a price each
        tests = [t[0].upper() if rng.random() < 0.5 else t[0] for t in rng.sample(LAB_TESTS, rng.randint(3, 7))]
        tests += rng.sample(["Dengue NS1 antigen", "Malaria parasite test", "Widal test", "Urine routine",
                             "Lipid profile", "Thyroid profile", "X-ray chest", "ECG", "USG abdomen"], rng.randint(1, 3))
        rows = [(str(i + 1), test, amount(rng, 100, 3000)) for i, test in enumerate(tests)]
        return org, [patient, kv([("Ref. doctor", doctor(rng)), ("Regn. date", date(rng))]),
                     table(["Sr. No.", "Service particulars", "Amount"], rows), totals,
                     para(rng.choice(["This is an electronically generated bill.", "Thank you!", "Subject to local jurisdiction."]))]
    if kind == "itemized":
        return org, [title(rng.choice(["INPATIENT STATEMENT", "DETAILED BILL", "ITEMISED BILL", "IP BILL - DETAILS"])),
                     kv([("Admission no.", f"IP {digits(rng, 2)}/{digits(rng, 4)}"), ("Invoice date", date(rng)), ("Patient", name(rng)),
                         ("Billing category", rng.choice(["General ward", "Semi private", "Single private", "Insurance"])),
                         ("Insurance", rng.choice(INSURERS + ["Cash"]))]),
                     table(ITEMIZED_HEADER, itemized_rows(rng)),
                     footer(f"Page 1 of {pages}")]
    # A middle page of a long bill: often the letterhead again, then only the table
    page = rng.randint(2, pages)
    rows = itemized_rows(rng, start=rng.randint(12, 80), sections=rng.random() < 0.7)
    blocks = [table(ITEMIZED_HEADER, rows)]
    if page == pages:
        blocks.append(totals)
    blocks.append(footer(f"Page {page} of {pages}"))
    return (org if rng.random() < 0.7 else None), blocks


def bill_provisional(rng):
    """Indian hospital bill: a provisional summary by service code, then a detailed
    breakup with dated rows per section and subtotals."""
    org = hospital(rng)
    sections = {"Room/Bed Charges": [("Bed Charges - GENERAL", 2000, "1 1/4")],
                "Nursing Charges": [("Nursing Fees - GENERAL", 200, "1"), ("Nebulization - GENERAL", 150, "1"),
                                    ("Injection Charges - GENERAL", 50, "1"), ("Blood Transfusion Charges", 500, "1")],
                "OT Charges": [("Major OT Charges - GENERAL", 1500, "1"), ("Minor OT Charges", 800, "1")],
                "Professional Fees": [(doctor(rng), 600, "1"), ("Visit Charges", 400, "2")],
                "Pharmacy": [(m, rng.randint(20, 400), str(rng.randint(1, 10))) for m in rng.sample(MEDICINES, 3)]}
    chosen = rng.sample(list(sections), rng.randint(3, 5))
    codes = {section: f"{rng.randint(100, 399)}{rng.randint(0, 9):03d}" for section in chosen}
    breakup, summary, total = [], [], 0
    for section in chosen:
        breakup.append((section,))
        subtotal = 0
        for particular, rate, units in rng.sample(sections[section], rng.randint(1, len(sections[section]))):
            amount_value = rate * (1 if "/" in units else int(units))
            subtotal += amount_value
            breakup.append((codes[section], f"{date(rng)} {rng.randint(1, 12):02d}:{rng.randint(0, 59):02d} PM", particular,
                            f"{rate:.2f}", units, f"{amount_value:.2f}"))
        breakup.append(("", "", "Subtotal:", "", "", f"{subtotal:.2f}"))
        summary.append((codes[section], section.upper() if rng.random() < 0.3 else section, f"{subtotal:.2f}"))
        total += subtotal
    paid = rng.choice([0, total, round(total * 0.5)])
    return org, [
        para(f"Reg. No. {letters(rng, 3).upper()}{digits(rng, 6)}   Ph: {phone(rng)}   Timings: AVAILABLE 24 HOURS AND 7 DAYS"),
        kv([("Patient UHID", digits(rng, 6)), ("Admission No", f"IP{digits(rng, 5)}"), ("Patient Name", name(rng).upper()),
            ("Admission Date", date(rng)), ("Age / Gender", f"{rng.randint(1, 85)} years / {rng.choice(['Male', 'Female'])}"),
            ("Discharge Date", ""), ("Payer Details", rng.choice(["SELF", "CASH", "INSURANCE"])),
            ("Bed No.", f"{rng.choice(['GENERAL', 'SEMI PVT', 'ICU'])}-{rng.randint(1, 40)}"), ("Consulting Doctors", doctor(rng))]),
        title(rng.choice(["PROVISIONAL BILL", "INTERIM BILL", "PROVISIONAL BILL CUM RECEIPT"])),
        table(["Primary Code", "Particulars", "Amount"], summary),
        kv([("Total Bill Amount", f"{total:.2f}"), ("Amount Payable", f"{total:.2f}"), ("Amount Paid", f"{paid:.2f}"),
            ("Balance Refund", "0.00"), ("Amount paid in words", f"{in_words(paid)} Only" if paid else "Zero")]),
        title("DETAILED BREAKUP"),
        table(["Code", "Date & Time", "Particulars", "Rate", "Units", "Amount"], breakup),
    ]


def bill_us_statement(rng):
    """US style hospital statement: remittance stub, a short letter, charges and payments."""
    org = f"{rng.choice(['Lakeside', 'Riverview', 'Hillcrest', 'Pinewood'])} {rng.choice(['Demo Hospital', 'Sample Medical Center', 'Mock Health System'])}"
    account = digits(rng, 8)
    charges = [(item, f"$ {rng.randint(20, 1500)}.{rng.randint(0, 99):02d}") for item in
               rng.sample(["Pharmacy", "Emergency Room", "EKG/ECG", "Laboratory", "Radiology", "Room and Board", "Physician Services"], rng.randint(3, 5))]
    patient = name(rng)
    return org, [
        kv([("Statement Date", date(rng)), ("Amount Due", f"$ {rng.randint(50, 3000)}.00"), ("Account Number", account),
            ("Show Amount Paid Here", "$ ________")]),
        para("IF PAYING BY CREDIT CARD, FILL OUT BELOW.  Card Number ____________  Exp. Date ______  Signature ____________  "
             "Make checks payable to the hospital. Please detach and return this portion with your payment."),
        para(f"{patient.upper()}\n{address(rng)}"),
        title("INVOICE"),
        para(f"{date(rng)}\n\nDear {patient.split()[0]},\nThank you for selecting {org} for your health care needs. For your records, "
             f"below is a summary of the charges for this account. If you have questions about your bill, please call Patient "
             f"Financial Services at {phone(rng)}."),
        kv([("Patient Name", patient), ("Account", account), ("Date of Service", date(rng)), ("Patient Service", rng.choice(["ER Acute", "Outpatient", "Inpatient"])),
            ("Primary Insurance Plan", rng.choice(["WPS Demo", "Blue Sample", "None"])), ("Amount Due", f"$ {rng.randint(50, 3000)}.00")]),
        table(["Service", "Charges"], charges),
        kv([("Total Charges", f"$ {rng.randint(500, 5000)}.00"), ("Total Payments", f"$ -{rng.randint(0, 900)}.00"),
            ("Total Adjustments", f"$ -{rng.randint(0, 300)}.00"), ("Please Pay This Amount", f"$ {rng.randint(50, 3000)}.00")]),
        para("Please mail payment in full today or contact Patient Financial Services to arrange payment. Physician charges will be billed separately."),
        sign("Sincerely,\nPatient Financial Services"),
    ]


def bill_receipt_template(rng):
    """Medical bill receipt form: institution, practitioner, patient, an itemised table and totals."""
    blank = rng.random() < 0.5
    v = lambda text: "____________________" if blank else text
    rows = [("", "", "", "", "")] * rng.randint(6, 10) if blank else [
        (digits(rng, 4), item, str(rng.randint(1, 3)), f"{rng.randint(10, 400)}.00", f"{rng.randint(10, 900)}.00")
        for item in pick(rng, BILL_ITEMS + MEDICINES, 3, 7)]
    return None, [
        title(rng.choice(["MEDICAL BILL RECEIPT", "MEDICAL RECEIPT", "CLINIC BILL RECEIPT"])),
        kv([("Receipt Number", v(digits(rng, 6))), ("Date", v(date(rng)))]),
        kv([("Name of Medical Institution", v(hospital(rng))), ("Practitioner Name", v(doctor(rng))), ("License Number", v(digits(rng, 7))),
            ("Address", v(address(rng))), ("City/State/ZIP", v(rng.choice(CITIES)))]),
        heading("Patient Information"),
        kv([("Name", v(name(rng))), ("Street Address", v(address(rng))), ("City/State/ZIP", v(rng.choice(CITIES)))]),
        table(["Code", "Description of Services/Medicine/Products", "Qty", "Rate", "Line Total"], rows),
        kv([("Subtotal", v("1,250.00")), ("Tax Rate", v("5%")), ("Total", v("1,312.50")), ("Amount Paid", v("1,312.50"))]),
        kv([("Payment Method", v(rng.choice(["Cash", "Card", "UPI", "Cheque"]))), ("Card/Check No.", v(digits(rng, 6)))]),
        footer("Page 1 of 1"),
    ]


def bill_clinic_invoice(rng):
    """Modern clinic invoice: patient and physician blocks, invoice number and due date,
    services with prices, totals and a notes box."""
    org = f"{rng.choice(['Harbor', 'Summit', 'Meadow', 'Orchid'])} {rng.choice(['Demo Health', 'Sample Clinic', 'Mock Care'])}"
    currency = rng.choice(["$", "Rs", "₹"])
    items = rng.sample([("Full Check Up", "Full body check up"), ("Ear & Throat Examination", "Infection check due inflammation"),
                        ("Office Visit", "Consultation"), ("Blood Draw", "Sample collection"), ("Vaccine", "Seasonal flu vaccine"),
                        ("Immunization", "Booster dose"), ("X-Ray", "Chest PA view"), ("Dressing", "Wound dressing")], rng.randint(3, 6))
    return org, [
        title(rng.choice(["Medical Invoice", "MEDICAL INVOICE", "Clinic Invoice", "Patient Invoice"])),
        kv([("Patient Information", name(rng)), ("Phone", phone(rng)), ("Address", address(rng)),
            ("Prescribing Physician's Information", doctor(rng)), ("Physician Phone", phone(rng))]),
        table(["INVOICE NUMBER", "DATE", "INVOICE DUE DATE", "PRICE"],
              [(digits(rng, 3), date(rng), date(rng), f"{currency} {rng.randint(100, 5000)}")]),
        table(["ITEM", "DESCRIPTION", "PRICE"], [(i, d, f"{currency} {rng.randint(50, 3000)}") for i, d in items]),
        heading("Notes"),
        para(rng.choice(["Online service for monitoring your health!", "Please pay within 15 days.", "Thank you for visiting."])),
        kv([("SUBTOTAL", f"{currency} {rng.randint(500, 9000)}"), ("DISCOUNT", f"{rng.choice([0, 5, 10])} %"),
            ("TAX RATE", f"{rng.choice([0, 5, 9, 18])} %"), ("TOTAL", f"{currency} {rng.randint(500, 9000)}")]),
        footer(rng.choice(["Online consultations 24/7  |  Laboratories  |  Delivery of medicines", contact_line(rng, org)])),
    ]


MEDICAL_STORES = ["Sanjeevani Demo Medical Store", "Shree Sample Medical Hall", "Jan Seva Mock Chemist",
                  "New Demo Pharmacy & General Store", "Arogya Test Medicos", "Om Sample Medical Agency"]
HINDI_LINES = ["बिका हुआ माल वापस नहीं होगा।", "डॉक्टर की पर्ची के बिना दवा नहीं दी जाएगी।", "कृपया दवा की समाप्ति तिथि जांच लें।"]
HINDI_FONT = FONT_DIR / "lohit-devanagari" / "Lohit-Devanagari.ttf"


def render_memo(style, rng):
    """A small printed cash memo pad from a local medical store, blank or filled in by hand."""
    width, height = 700, 1000
    ink = rng.choice([(0, 110, 90), (20, 60, 150), (150, 20, 40), (40, 40, 40)])
    hand = (25, 45, 160)
    img = Image.new("RGB", (width, height), rng.choice([(255, 255, 255), (250, 248, 240), (255, 252, 235)]))
    draw = ImageDraw.Draw(img)
    s = rng.randint(15, 19)
    regular, bold, small = font(style.regular, s), font(style.bold, s), font(style.regular, s - 3)
    filled = rng.random() < 0.5
    m, y = 30, 28

    def centre(text, fnt, colour):
        draw.text(((width - draw.textlength(text, font=fnt)) / 2, y), text, font=fnt, fill=colour)

    dl = f"DL No. {rng.randint(10, 99)}/{digits(rng, 4)}"
    draw.text((m, y), dl, font=small, fill=ink)
    mobile = f"Mo. {phone(rng)}"
    draw.text((width - m - draw.textlength(mobile, font=small), y), mobile, font=small, fill=ink)
    y += s
    draw.text((m, y), f"DL No. {rng.randint(10, 99)}/{digits(rng, 4)}", font=small, fill=ink)
    if rng.random() < 0.5:
        gst = f"GSTIN {digits(rng, 2)}{letters(rng, 5).upper()}{digits(rng, 4)}"
        draw.text((width - m - draw.textlength(gst, font=small), y), gst, font=small, fill=ink)
    y += int(s * 1.8)
    store = rng.choice(MEDICAL_STORES).upper()
    size = s + 14
    while draw.textlength(store, font=font(style.bold, size)) > width - 2 * m:
        size -= 1
    centre(store, font(style.bold, size), ink)
    y += size + 8
    centre(f"{rng.choice(['Ward No.', 'Shop No.', 'Near Bus Stand,'])} {rng.randint(1, 40)}, {rng.choice(STREETS)}, {rng.choice(CITIES)}", regular, ink)
    y += int(s * 2)
    draw.text((m, y), "No.", font=bold, fill=ink)
    draw.text((m + 40, y), str(rng.randint(100, 999)), font=bold, fill=(200, 30, 30))
    draw.text((width - 260, y), "Date ................", font=regular, fill=ink)
    if filled:
        draw.text((width - 200, y - 4), date(rng), font=regular, fill=hand)
    y += int(s * 1.9)
    for label, value_text in [("Sold to Shree", name(rng)), ("Add & Mo.", rng.choice(CITIES)), ("Prescribed By Dr.", doctor(rng))]:
        draw.text((m, y), f"{label} " + "." * 60, font=regular, fill=ink)
        if filled:
            draw.text((m + draw.textlength(label, font=regular) + 20, y - 5), value_text, font=regular, fill=hand)
        y += int(s * 1.8)
    # Table with vertical lines down to the total
    header = ["No.", "Particulars", "Company Name", "Batch No. / Ex. Date", "Amount"]
    weights = [0.6, 3, 1.4, 1.5, 1.1]
    edges = [m]
    for w in weights:
        edges.append(edges[-1] + (width - 2 * m) * w / sum(weights))
    top, head_h = y, int(s * 2.6)
    bottom = height - 150
    draw.rectangle([m, top, width - m, bottom], outline=ink, width=2)
    draw.line([m, top + head_h, width - m, top + head_h], fill=ink, width=2)
    for c, label in enumerate(header):
        lines = wrap(draw, label, small, edges[c + 1] - edges[c] - 6)
        for i, line in enumerate(lines[:2]):
            draw.text((edges[c] + 4, top + 4 + i * s), line, font=small, fill=ink)
        if c:
            draw.line([edges[c], top, edges[c], bottom], fill=ink, width=1)
    if filled:
        row_y = top + head_h + 8
        for i, medicine in enumerate(pick(rng, MEDICINES, 2, 6), start=1):
            cells = [str(i), medicine, rng.choice(["Cipla", "Sun", "Mankind", "Alkem", "Demo"]),
                     f"{letters(rng, 2).upper()}{digits(rng, 3)} {rng.randint(1, 12):02d}/{rng.randint(26, 29)}", f"{rng.randint(20, 600)}"]
            for c, cell in enumerate(cells):
                text = cell
                while draw.textlength(text, font=regular) > edges[c + 1] - edges[c] - 8 and len(text) > 2:
                    text = text[:-1]
                draw.text((edges[c] + 4, row_y), text, font=regular, fill=hand)
            row_y += int(s * 1.9)
    draw.line([m, bottom - int(s * 1.8), width - m, bottom - int(s * 1.8)], fill=ink, width=1)
    draw.text((edges[3] + 6, bottom - int(s * 1.6)), "Total", font=bold, fill=ink)
    y = bottom + 20
    draw.text((width - m - 120, y), "Proprietor", font=regular, fill=ink)
    draw.text((width - m - 120, y + s + 4), name(rng), font=small, fill=ink)
    if HINDI_FONT.exists():
        draw.text((m, y + 10), rng.choice(HINDI_LINES), font=ImageFont.truetype(str(HINDI_FONT), s), fill=ink)
    return img


def pharmacy_bill(rng):
    org = f"{rng.choice(['Goodhealth', 'MediPlus', 'Care', 'Apollo-like', 'Wellness'])} Demo Pharmacy"
    rows = []
    for medicine in pick(rng, MEDICINES, 2, 7):
        qty, rate = rng.randint(1, 30), rng.uniform(2, 250)
        rows.append((medicine, str(qty), f"{rate:.2f}", f"{qty * rate:.2f}"))
    if rng.random() < 0.5:
        header = ["Item", "Batch", "Exp", "Qty", "MRP", "Amount"]
        rows = [(m, f"{letters(rng, 2)}{digits(rng, 4)}", f"{rng.randint(1, 12):02d}/{rng.randint(26, 29)}", r[1], r[2], r[3])
                for m, r in zip([r[0] for r in rows], rows)]
    else:
        header = ["Item", "Qty", "Rate", "Amount"]
    return org, [
        para(f"{address(rng)}  |  GSTIN: {digits(rng, 2)}{letters(rng, 5)}{digits(rng, 4)}{letters(rng, 1)}1Z{digits(rng, 1)}"),
        title(rng.choice(["TAX INVOICE", "CASH MEMO", "PHARMACY BILL", "RETAIL INVOICE"])),
        kv([("Bill no.", f"{digits(rng, 5)}"), ("Date", date(rng)), ("Patient", name(rng)), ("Doctor", doctor(rng))]),
        table(header, rows),
        kv([("Net payable", f"Rs {amount(rng, 100, 6000)}"), ("Paid by", rng.choice(["Cash", "UPI", "Card"]))]),
    ] + ([footer(contact_line(rng, org))] if rng.random() < 0.4 else [])


def payment_receipt(rng):
    org = hospital(rng)
    if rng.random() < 0.35:
        paid = rng.randint(3, 400) * 10
        return org, [
            title(rng.choice(["PAYMENT RECEIPT", "RECEIPT", "E-RECEIPT", "PAYMENT ACKNOWLEDGEMENT"])),
            kv([("Receipt No", digits(rng, 9)), ("Receipt Date", date(rng)), ("Patient Name", name(rng)),
                ("Invoice No", digits(rng, 11)), ("Contact No", phone(rng))]),
            table(["Receipt No", "Receipt Date", "Amount", "Mode", "Received By"],
                  [(digits(rng, 8), date(rng), f"{paid:.2f}", rng.choice(PAY_MODES), name(rng).split()[0])]),
            kv([("Paid Amount", f"{paid:.2f}"), ("Balance to Pay", "0.00")]),
            para(f"Amount Paid in Words : {in_words(paid)} Only"),
            footer(contact_line(rng, org)),
        ]
    return org, [
        title(rng.choice(["PAYMENT RECEIPT", "RECEIPT", "ADVANCE RECEIPT", "MONEY RECEIPT"])),
        kv([("Receipt no.", f"R-{digits(rng, 6)}"), ("Date", date(rng)), ("Received from", name(rng)),
            ("Amount", f"Rs {amount(rng, 500, 100000)}"), ("Payment mode", rng.choice(["Cash", "UPI", "Card", "NEFT", "Cheque"])),
            ("Towards", rng.choice(["Advance deposit", "Final settlement", "OPD charges", "Lab charges"]))]),
        para("Received with thanks."),
        sign("Cashier"),
    ]


def other(rng):
    # Insurance papers that are not about health (motor claims, marine / fire policies)
    # are "other" too; they get extra weight because they look like our insurance types
    kind = rng.choice(OTHER_KINDS + ["motor_claim", "motor_claim", "non_health_policy", "non_health_policy"])
    if kind == "motor_claim":
        return motor_claim(rng)
    if kind == "non_health_policy":
        return policy_schedule(rng, health=False)
    org = f"{rng.choice(['Bright', 'Prime', 'Northstar', 'Evergreen'])} {rng.choice(['Solutions', 'School', 'Housing Society', 'Cafe', 'Technologies'])}"
    if kind == "letter":
        blocks = [para(date(rng)), para(f"To,\n{name(rng)}\n{address(rng)}"), heading(f"Subject: {rng.choice(['Offer of employment', 'Rent agreement renewal', 'Meeting invitation', 'Change of address'])}"),
                  para("Dear Sir/Madam, this is to inform you about the matter mentioned above. Please contact us for any further details. "
                       "We look forward to your reply at the earliest."), sign(f"Regards,\n{name(rng)}")]
    elif kind == "resume":
        blocks = [title(name(rng).upper()), para(f"{phone(rng)}  |  {rng.choice(['dev', 'mail', 'user'])}@example.com"),
                  heading("Experience"), para(f"Software engineer at {org}, {rng.randint(2015, 2022)} - present. Built web applications."),
                  heading("Education"), para("B.Tech in Computer Science"), heading("Skills"), para("Python, React, SQL, Docker")]
    elif kind == "notice":
        blocks = [title("NOTICE"), para(date(rng)), para(f"All residents are informed that the {rng.choice(['water supply', 'lift', 'parking area'])} will be under maintenance "
                                                         f"on {date(rng)} from 10 am to 4 pm. Kindly co-operate."), sign("Secretary")]
    elif kind == "minutes":
        blocks = [title("MINUTES OF MEETING"), kv([("Date", date(rng)), ("Venue", "Conference room"), ("Chair", name(rng))]),
                  heading("Points discussed"), para("1. Review of last quarter. 2. Budget for events. 3. Any other business."), sign("Prepared by")]
    elif kind == "certificate":
        blocks = [title(rng.choice(["CERTIFICATE OF PARTICIPATION", "CERTIFICATE OF ACHIEVEMENT"])),
                  para(f"This is to certify that {name(rng)} has participated in the annual {rng.choice(['sports meet', 'coding contest', 'science fair'])}."), sign("Principal")]
    else:
        blocks = [title("MENU"), table(["Item", "Price"], [(i, f"{rng.randint(50, 400)}") for i in rng.sample(
            ["Masala dosa", "Paneer tikka", "Veg biryani", "Cold coffee", "Gulab jamun", "Tea", "Sandwich"], 5)])]
    return org, blocks


def cancelled_cheque(rng):
    return None, None  # drawn separately, see render_cheque


PAGE_BUILDERS = {
    "claim_form": claim_form, "policy_document": policy_document, "preauth_form": preauth_form,
    "discharge_summary": discharge_summary, "lab_report": lab_report, "prescription": prescription,
    "radiology_report": radiology_report, "consultation_notes": consultation_notes,
    "hospital_bill": hospital_bill, "pharmacy_bill": pharmacy_bill, "payment_receipt": payment_receipt,
    "other": other,
}
CARD_TYPES = {"health_card", "aadhaar", "pan_card", "passport", "driving_licence", "voter_id"}


# ---------------------------------------------------------------- rendering

@dataclass
class Style:
    regular: str
    bold: str
    size: int
    accent: tuple
    margin: int
    header: str  # "band", "line" or "plain"


def make_style(rng, fonts):
    regular, bold = rng.choice(fonts)
    accent = rng.choice([(20, 60, 120), (120, 20, 40), (20, 100, 70), (60, 60, 60), (150, 80, 0), (0, 0, 0)])
    return Style(str(FONT_DIR / regular), str(FONT_DIR / bold), rng.randint(22, 30), accent,
                 rng.randint(70, 120), rng.choice(["band", "line", "plain"]))


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if draw.textlength(candidate, font=fnt) <= width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def render_page(org, blocks, style, rng):
    page = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(page)
    s = style.size
    regular, bold = font(style.regular, s), font(style.bold, s)
    left, right = style.margin, PAGE_SIZE[0] - style.margin
    width = right - left
    y = style.margin

    # Letterhead with the organisation name
    if org:
        org_font = font(style.bold, int(s * 1.5))
        if style.header == "band":
            draw.rectangle([0, 0, PAGE_SIZE[0], y + int(s * 3.2)], fill=style.accent)
            draw.text((left, y), org, font=org_font, fill="white")
            draw.text((left, y + int(s * 1.9)), address(rng), font=font(style.regular, int(s * 0.8)), fill="white")
            y += int(s * 4.2)
        else:
            if rng.random() < 0.6:
                draw.ellipse([left, y, left + s * 2, y + s * 2], outline=style.accent, width=4)
                text_x = left + s * 3
            else:
                text_x = left
            draw.text((text_x, y), org, font=org_font, fill=style.accent)
            draw.text((text_x, y + int(s * 1.8)), f"{address(rng)}  |  Ph: {phone(rng)}", font=font(style.regular, int(s * 0.75)), fill=(80, 80, 80))
            y += int(s * 3.2)
            if style.header == "line":
                draw.line([left, y, right, y], fill=style.accent, width=3)
            y += s

    for block in blocks:
        if y > PAGE_SIZE[1] - style.margin - s * 3:
            break
        kind = block[0]
        if kind == "title":
            title_font = font(style.bold, int(s * 1.35))
            text_width = draw.textlength(block[1], font=title_font)
            x = left if rng.random() < 0.3 else left + (width - text_width) / 2
            draw.text((x, y), block[1], font=title_font, fill="black")
            y += int(s * 2.2)
        elif kind == "heading":
            draw.text((left, y), block[1], font=bold, fill=style.accent)
            y += int(s * 1.6)
        elif kind == "para":
            for line in wrap(draw, block[1], regular, width):
                draw.text((left, y), line, font=regular, fill=(20, 20, 20))
                y += int(s * 1.35)
            y += int(s * 0.6)
        elif kind == "kv":
            columns = 2 if len(block[1]) > 3 and rng.random() < 0.5 else 1
            col_width = width // columns
            for i, (key, value) in enumerate(block[1]):
                x = left + (i % columns) * col_width
                label = f"{key}:"
                draw.text((x, y), label, font=bold, fill="black")
                value_x = x + int(draw.textlength(label, font=bold)) + s // 2
                # Shorten the value so it never runs into the next column
                room = x + col_width - s - value_x
                while draw.textlength(value, font=regular) > room and len(value) > 4:
                    value = value[:-2]
                draw.text((value_x, y), value, font=regular, fill=(20, 20, 20))
                if i % columns == columns - 1 or i == len(block[1]) - 1:
                    y += int(s * 1.5)
            y += int(s * 0.5)
        elif kind == "table":
            header, rows = block[1], block[2]
            # Many columns (itemized bills) need a smaller font
            cell_font = font(style.regular, int(s * 0.72)) if len(header) >= 6 else regular
            head_font = font(style.bold, int(s * 0.72)) if len(header) >= 6 else bold
            # The description column gets more room than the number columns
            weights = [3 if h.lower() in ("description", "particulars", "item", "medicine", "test", "name", "expense", "head") else 1
                       for h in header]
            edges = [left]
            for weight in weights:
                edges.append(edges[-1] + width * weight / sum(weights))
            grid = rng.random() < 0.6
            row_height = int(s * (1.25 if len(header) >= 6 else 1.6))
            table_top = y
            draw.rectangle([left, y, right, y + row_height], fill=(235, 235, 235) if grid else None)
            for c, cell in enumerate(header):
                draw.text((edges[c] + 6, y + 4), cell, font=head_font, fill="black")
            y += row_height
            for row in rows:
                if y > PAGE_SIZE[1] - style.margin - s * 3:
                    break
                if len(row) == 1:  # section heading inside the table
                    draw.text((left + 6, y + 4), row[0], font=head_font, fill=style.accent)
                else:
                    for c, cell in enumerate(row):
                        text = cell
                        while draw.textlength(text, font=cell_font) > edges[c + 1] - edges[c] - 12 and len(text) > 3:
                            text = text[:-2]
                        draw.text((edges[c] + 6, y + 4), text, font=cell_font, fill=(20, 20, 20))
                if grid:
                    draw.line([left, y, right, y], fill=(150, 150, 150), width=1)
                y += row_height
            if grid:
                draw.rectangle([left, table_top, right, y], outline=(120, 120, 120), width=2)
            y += s
        elif kind == "qr":
            # A QR-like square of random modules at the right edge (policy schedules, invoices)
            cells, cell = 25, 6
            qx = right - cells * cell
            draw.rectangle([qx - 6, y - 6, qx + cells * cell + 6, y + cells * cell + 6], fill="white")
            for row_i in range(cells):
                for col_i in range(cells):
                    corner = (row_i < 7 and col_i < 7) or (row_i < 7 and col_i >= cells - 7) or (row_i >= cells - 7 and col_i < 7)
                    on = (row_i in (0, 6) or col_i in (0, 6) or 2 <= row_i <= 4 and 2 <= col_i <= 4) if corner else rng.random() < 0.5
                    if corner and (row_i >= cells - 7 or col_i >= cells - 7):
                        r2, c2 = row_i % (cells - 7) if row_i >= cells - 7 else row_i, col_i % (cells - 7) if col_i >= cells - 7 else col_i
                        on = r2 in (0, 6) or c2 in (0, 6) or 2 <= r2 <= 4 and 2 <= c2 <= 4
                    if on:
                        draw.rectangle([qx + col_i * cell, y + row_i * cell, qx + col_i * cell + cell - 1, y + row_i * cell + cell - 1], fill="black")
        elif kind == "footer":
            small = font(style.regular, int(s * 0.75))
            text_width = draw.textlength(block[1], font=small)
            draw.text((right - text_width, PAGE_SIZE[1] - style.margin), block[1], font=small, fill=(80, 80, 80))
        elif kind == "sign":
            y += s * 2
            x = right - int(s * 12) if rng.random() < 0.7 else left
            draw.line([x, y, x + s * 10, y], fill="black", width=2)
            for line in block[1].split("\n"):
                draw.text((x, y + 6), line, font=regular, fill="black")
                y += int(s * 1.3)
    return page


# ---------- Box-style insurance forms (claim form part A / part B, pre-authorization) ----------
# Real Indian health insurance forms are dense grids: coloured section bars, one box
# per letter, D D M M Y Y date boxes, Yes/No checkboxes. Field names and their order
# vary between insurers, so they are picked from synonyms here.

FORM_ACCENTS = [(0, 150, 70), (0, 115, 60), (20, 80, 150), (130, 25, 45), (80, 80, 80), (0, 120, 140), (190, 90, 0)]


def fake_value(rng, kind):
    makers = {
        "name": lambda: name(rng).upper(),
        "address": lambda: address(rng).upper(),
        "policy": lambda: f"{digits(rng, 2)}-{digits(rng, 8)}-{digits(rng, 2)}",
        "id": lambda: digits(rng, rng.randint(6, 10)),
        "phone": lambda: phone(rng).replace(" ", ""),
        "email": lambda: f"{rng.choice(['user', 'mail', 'demo'])}{digits(rng, 3)}@example.com",
        "pin": lambda: digits(rng, 6),
        "city": lambda: rng.choice(CITIES).upper(),
        "amount": lambda: str(amount(rng, 500, 90000)),
        "hospital": lambda: hospital(rng).upper(),
        "doctor": lambda: doctor(rng).upper(),
        "diagnosis": lambda: rng.choice(DIAGNOSES).upper(),
        "icd": lambda: f"{rng.choice('ABCEIJKNR')}{rng.randint(0, 99):02d}.{rng.randint(0, 9)}",
        "text": lambda: rng.choice(["NA", "NIL", "SELF", "AS PER BILL", "NOT APPLICABLE"]),
        "number": lambda: str(rng.randint(1, 30)),
        "yn": lambda: rng.choice(["Y", "N", "N"]),
    }
    return makers[kind]()


def syn(rng, *options):
    return rng.choice(options)


def claim_form_part_a(rng):
    insured = (syn(rng, "DETAILS OF PRIMARY INSURED", "PRIMARY INSURED DETAILS", "SECTION A - DETAILS OF PRIMARY INSURED"), [
        ("line", [(syn(rng, "a) Policy No", "Policy Number", "Policy / Certificate No"), "policy", 2),
                  (syn(rng, "b) Sl. No / Certificate No", "Certificate No"), "id", 1),
                  (syn(rng, "c) Member / Client ID No", "Member ID", "TPA ID Card No"), "id", 1)]),
        ("line", [(syn(rng, "d) Name", "Name of Primary Insured", "Name of Proposer"), "name", 1)]),
        ("line", [(syn(rng, "e) Address", "Address"), "address", 1)]),
        ("line", [("City", "city", 1), ("State", "city", 1), ("Pin Code", "pin", 1)]),
        ("line", [(syn(rng, "Phone No", "Mobile No"), "phone", 1), ("Email ID", "email", 1)]),
        ("checks", syn(rng, "f) Policy Type", "Type of Policy"), ["Individual", "Corporate", "Family Floater"]),
    ])
    history = (syn(rng, "DETAILS OF INSURANCE HISTORY", "INSURANCE HISTORY", "SECTION B - INSURANCE HISTORY"), [
        ("checks", syn(rng, "a) Currently covered by any other Mediclaim / Health Insurance", "Any other health insurance policy"), ["Yes", "No"]),
        ("line", [("b) If yes, company name", "text", 2), ("Sum Insured (Rs.)", "amount", 1)]),
        ("date", syn(rng, "c) Date of commencement of first Insurance without break", "First insurance start date")),
        ("checks", syn(rng, "d) Have you been hospitalized in the last 4 years?", "Hospitalized in last 4 years"), ["Yes", "No"]),
        ("line", [("Diagnosis", "diagnosis", 1)]),
    ])
    patient = (syn(rng, "DETAILS OF INSURED PERSON HOSPITALIZED", "PATIENT DETAILS", "SECTION C - DETAILS OF INSURED PERSON HOSPITALISED"), [
        ("line", [(syn(rng, "a) Name", "Name of Patient"), "name", 1)]),
        ("checks", "b) Gender", ["Male", "Female", "Other"]),
        ("date", syn(rng, "d) Date of Birth", "Date of Birth")),
        ("checks", syn(rng, "e) Relationship with Primary insured", "Relationship to Insured"), ["Self", "Spouse", "Child", "Father", "Mother", "Other"]),
        ("checks", "f) Occupation", ["Service", "Self Employed", "Homemaker", "Student", "Retired", "Other"]),
    ])
    hospitalisation = (syn(rng, "DETAILS OF HOSPITALIZATION", "HOSPITALISATION DETAILS", "SECTION D - DETAILS OF HOSPITALISATION"), [
        ("line", [(syn(rng, "a) Name of Hospital where Admitted", "Hospital Name"), "hospital", 1)]),
        ("checks", syn(rng, "b) Room Category occupied", "Room Type"), ["Day Care", "Single occupancy", "Twin sharing", "3 or more beds"]),
        ("checks", "c) Hospitalization due to", ["Injury", "Illness", "Maternity"]),
        ("date", syn(rng, "e) Date of Admission", "Date of Admission")),
        ("date", syn(rng, "g) Date of Discharge", "Date of Discharge")),
        ("checks", syn(rng, "i) If injury give cause", "Cause of injury"), ["Self inflicted", "Road Traffic Accident", "Substance Abuse / Alcohol"]),
        ("checks", "Medico legal / MLC Report & Police FIR attached", ["Yes", "No"]),
        ("line", [(syn(rng, "Intimation No. & date", "Claim Intimation No"), "id", 1), ("System of Medicine", "text", 1)]),
    ])
    claim = (syn(rng, "DETAILS OF CLAIM", "CLAIM DETAILS", "SECTION E - DETAILS OF CLAIM"), [
        ("line", [("i. Pre-hospitalization Expenses: Rs.", "amount", 1), ("ii. Hospitalization Expenses: Rs.", "amount", 1)]),
        ("line", [("iii. Post-hospitalization expenses: Rs.", "amount", 1), ("iv. Health-Check up Cost: Rs.", "amount", 1)]),
        ("line", [("v. Ambulance Charges: Rs.", "amount", 1), ("Total Rs.", "amount", 1)]),
        ("line", [("Pre-hospitalization period: days", "number", 1), ("Post hospitalization period: days", "number", 1)]),
        ("checks", "Claim for Domiciliary Hospitalization", ["Yes", "No"]),
        ("line", [("Hospital Daily Cash: Rs.", "amount", 1), ("Surgical Cash: Rs.", "amount", 1), ("Critical Illness Benefit: Rs.", "amount", 1)]),
        ("checks", syn(rng, "Claim Documents Submitted - Check List", "Documents enclosed"),
         ["Claim Form Duly signed", "Hospital Main Bill", "Hospital Break-up Bill", "Discharge Summary", "Pharmacy Bill",
          "Investigation Reports", "Doctor's Prescriptions", "ECG"]),
    ])
    bills = (syn(rng, "DETAILS OF BILLS ENCLOSED", "BILLS ENCLOSED (use separate sheet if required)"), [
        ("grid", ["Sl No.", "Bill No.", "Date", "Issued By", "Towards", "Amount (Rs)"], rng.randint(5, 10),
         ["number", "id", "date", "hospital", "text", "amount"]),
    ])
    bank = (syn(rng, "DETAILS OF PRIMARY INSURED'S BANK ACCOUNT", "BANK DETAILS FOR NEFT (attach cancelled cheque)"), [
        ("chars", "a) PAN", 10, "id"),
        ("line", [("b) Account Number", "id", 1), ("e) IFSC Code", "id", 1)]),
        ("line", [("c) Bank Name and Branch", "text", 1)]),
    ])
    declaration = (syn(rng, "DECLARATION BY THE INSURED", "DECLARATION"), [
        ("note", "I hereby declare that the information furnished in this claim form is true & correct to the best of my "
                 "knowledge and belief. If I have made any false or untrue statement, suppression or concealment of any "
                 "material fact, my right to claim reimbursement shall be forfeited. I also consent & authorize TPA / "
                 "Insurance company to seek necessary medical information / documents from any hospital."),
        ("line", [("Date", "text", 1), ("Place", "city", 1), ("Signature of the Insured", "text", 2)]),
    ])
    sections = [insured, history, patient, hospitalisation, claim, bills, bank, declaration]
    # Some insurers leave sections out or put them on a second page
    sections = [sec for i, sec in enumerate(sections) if i in (0, 3, 4) or rng.random() < 0.75]
    titles = [syn(rng, "CLAIM FORM - PART A", "HEALTH INSURANCE CLAIM FORM - PART A", "REIMBURSEMENT CLAIM FORM (PART A)"),
              syn(rng, "TO BE FILLED IN BY THE INSURED", "TO BE FILLED BY THE INSURED / CLAIMANT"),
              "The issue of this Form is not to be taken as an admission of liability (To be filled in block letters)"]
    return titles, sections


def claim_form_part_b(rng):
    hospital_details = (syn(rng, "A. DETAILS OF HOSPITAL", "DETAILS OF HOSPITAL"), [
        ("line", [("a) Name of the Hospital", "hospital", 1)]),
        ("chars", "b) Hospital ID", 10, "id"),
        ("checks", "c) Type of Hospital", ["Network", "Non Network"]),
        ("line", [("d) Name of the treating doctor", "doctor", 2), ("e) Qualification", "text", 1)]),
        ("line", [("f) Registration No. with State Code", "id", 1), ("g) Phone No.", "phone", 1)]),
    ])
    patient = (syn(rng, "B. DETAILS OF THE PATIENT ADMITTED", "DETAILS OF PATIENT ADMITTED"), [
        ("line", [("a) Name of the Patient", "name", 1)]),
        ("line", [("b) IP Registration Number", "id", 1), ("c) Gender", "text", 1), ("d) Age: Years", "number", 1)]),
        ("date", "f) Date of Admission"),
        ("date", "h) Date of Discharge"),
        ("checks", "j) Type of Admission", ["Emergency", "Planned", "Day Care", "Maternity"]),
        ("checks", "l) Status at time of discharge", ["Discharge to home", "Discharge to another hospital", "Deceased"]),
        ("line", [("m) Total Claimed Amount: Rs.", "amount", 1)]),
    ])
    ailment = (syn(rng, "C. DETAILS OF AILMENT DIAGNOSED (PRIMARY)", "DIAGNOSIS AND PROCEDURE DETAILS"), [
        ("grid", ["", "ICD 10 Codes", "Description", "Procedure", "ICD 10 PCS", "Description"], 4,
         ["text", "icd", "diagnosis", "text", "icd", "text"]),
        ("checks", "c) Present ailment is a complication of PED?", ["Yes", "No"]),
        ("checks", "d) Pre-authorization obtained", ["Yes", "No"]),
        ("line", [("e) Pre-authorization Number", "id", 1)]),
        ("checks", "g) Hospitalization due to Injury", ["Yes", "No", "Road Traffic Accident", "Self-inflicted"]),
        ("line", [("v. FIR no.", "id", 1), ("vi. If not reported to police give reason", "text", 2)]),
    ])
    checklist = (syn(rng, "D. CLAIM DOCUMENTS SUBMITTED - CHECK LIST", "DOCUMENTS CHECK LIST"), [
        ("checks", "", ["Claim Form duly signed", "Original Pre-authorization request", "Copy of the Pre-authorization approval letter"]),
        ("checks", "", ["Hospital main bill", "Hospital break-up bill", "Investigation reports", "Hospital Discharge summary"]),
        ("checks", "", ["Operation Theatre notes", "Pharmacy bills", "MLC report & Police FIR", "Any other, please specify"]),
    ])
    non_network = (syn(rng, "E. ADDITIONAL DETAILS IN CASE OF NON NETWORK HOSPITAL", "NON NETWORK HOSPITAL DETAILS"), [
        ("line", [("a) Address of the Hospital", "address", 1)]),
        ("line", [("City", "city", 1), ("State", "city", 1), ("Pin Code", "pin", 1)]),
        ("line", [("c) Registration No.", "id", 1), ("Name of the Registering Authority", "text", 1)]),
        ("line", [("e) Number of Inpatient beds", "number", 1), ("f) Facilities: OT / ICU", "text", 1)]),
    ])
    declaration = (syn(rng, "F. DECLARATION BY THE HOSPITAL (PLEASE READ VERY CAREFULLY)", "DECLARATION BY THE HOSPITAL"), [
        ("note", "We hereby declare that the information furnished in this Claim Form is true & correct to the best of our "
                 "knowledge and belief. Hospital has required infrastructure to fulfill the hospital definition as per IRDA "
                 "guideline: at least 10 inpatient beds, fully qualified nursing staff and doctors round the clock, a fully "
                 "equipped operation theatre, and daily medical records of patients."),
        ("line", [("Date", "text", 1), ("Place", "city", 1)]),
        ("line", [("Signature of Insured / Claimant", "text", 1), ("Signature and Seal of the Hospital Authority", "text", 1)]),
    ])
    sections = [hospital_details, patient, ailment, checklist, non_network, declaration]
    sections = [sec for i, sec in enumerate(sections) if i in (0, 1, 2) or rng.random() < 0.75]
    titles = [syn(rng, "CLAIM FORM - PART B", "HEALTH INSURANCE CLAIM FORM - PART B", "CLAIM FORM (PART B)"),
              syn(rng, "TO BE FILLED IN BY THE HOSPITAL", "TO BE FILLED BY THE HOSPITAL"),
              "Please include the original preauthorization request form in lieu of PART A"]
    return titles, sections


def preauth_form_boxes(rng):
    hospital_part = (syn(rng, "DETAILS OF THE HOSPITAL", "TO BE FILLED BY THE HOSPITAL"), [
        ("line", [("Name of the Hospital", "hospital", 2), ("Rohini ID", "id", 1)]),
        ("line", [("Contact No", "phone", 1), ("Email ID", "email", 1)]),
    ])
    patient = (syn(rng, "TO BE FILLED BY INSURED / PATIENT", "DETAILS OF THE PATIENT"), [
        ("line", [("Name of the Patient", "name", 1)]),
        ("checks", "Gender", ["Male", "Female", "Third gender"]),
        ("date", "Date of Birth"),
        ("line", [("Contact number", "phone", 1), ("Insured card ID number", "id", 1)]),
        ("line", [("Policy number / Name of corporate", "policy", 1), ("Employee ID", "id", 1)]),
        ("checks", "Currently do you have any other Mediclaim / Health insurance", ["Yes", "No"]),
    ])
    doctor_part = (syn(rng, "TO BE FILLED BY THE TREATING DOCTOR / HOSPITAL", "DETAILS OF THE TREATING DOCTOR"), [
        ("line", [("Name of the treating doctor", "doctor", 1), ("Contact No", "phone", 1)]),
        ("line", [("Nature of illness / disease with presenting complaints", "diagnosis", 1)]),
        ("line", [("Relevant critical findings", "text", 1)]),
        ("line", [("Duration of the present ailment (days)", "number", 1), ("Provisional diagnosis", "diagnosis", 2)]),
        ("line", [("ICD 10 code", "icd", 1), ("Proposed line of treatment", "text", 2)]),
        ("checks", "Proposed line of treatment", ["Medical management", "Surgical management", "Intensive care", "Investigation", "Non allopathic"]),
        ("line", [("Name of surgery", "text", 2), ("ICD 10 PCS code", "icd", 1)]),
    ])
    admission = (syn(rng, "DETAILS OF THE PATIENT ADMITTED", "ADMISSION DETAILS"), [
        ("date", "Date of admission"),
        ("checks", "Is this an emergency / planned hospitalisation", ["Emergency", "Planned"]),
        ("line", [("Expected no. of days stay in hospital", "number", 1), ("Days in ICU", "number", 1), ("Room type", "text", 1)]),
    ])
    cost = (syn(rng, "ESTIMATED COST OF HOSPITALIZATION", "EXPECTED COST OF TREATMENT"), [
        ("line", [("Per day room rent + nursing & service charges + patient's diet: Rs.", "amount", 1)]),
        ("line", [("Expected cost for investigation + diagnostics: Rs.", "amount", 1)]),
        ("line", [("ICU charges: Rs.", "amount", 1), ("OT charges: Rs.", "amount", 1)]),
        ("line", [("Professional fees surgeon + anesthetist fees + consultation charges: Rs.", "amount", 1)]),
        ("line", [("Medicines + consumables + cost of implants: Rs.", "amount", 1)]),
        ("line", [("Sum total expected cost of hospitalization: Rs.", "amount", 1)]),
    ])
    declaration = (syn(rng, "DECLARATION", "DECLARATION BY THE PATIENT / REPRESENTATIVE"), [
        ("note", "I agree to allow the hospital to submit all original documents pertaining to hospitalization to the "
                 "Insurer / TPA after discharge. I agree to sign on the final bill and the discharge summary before discharge. "
                 "Payment to the hospital is governed by the terms and conditions of the policy."),
        ("line", [("Patient / Insured name", "name", 1), ("Contact number", "phone", 1), ("Signature", "text", 1)]),
        ("line", [("Hospital seal", "text", 1), ("Doctor's signature", "text", 1), ("Date", "text", 1)]),
    ])
    sections = [hospital_part, patient, doctor_part, admission, cost, declaration]
    sections = [sec for i, sec in enumerate(sections) if i in (1, 2, 4) or rng.random() < 0.75]
    titles = [syn(rng, "REQUEST FOR CASHLESS HOSPITALISATION FOR HEALTH INSURANCE POLICY", "PRE-AUTHORIZATION REQUEST FORM",
                  "CASHLESS AUTHORIZATION REQUEST - PART C"),
              syn(rng, "TO BE FILLED BY THE HOSPITAL", "(To be filled in block letters)"),
              "Pre-authorization is subject to policy terms and conditions"]
    return titles, sections


def claim_form_continuation(rng):
    """The second page of a claim form: document check list, non-network hospital details,
    declaration and signatures."""
    checklist = (syn(rng, "CLAIM DOCUMENTS SUBMITTED - CHECK LIST", "D. CLAIM DOCUMENTS SUBMITTED - CHECK LIST"), [
        ("checks", "", ["Claim Form duly signed", "Operation Theatre Notes", "Doctor's reference slip for investigation"]),
        ("checks", "", ["Original Pre-authorization request", "Hospital main bill", "ECG"]),
        ("checks", "", ["Copy of the Pre-authorization approval letter", "Hospital break-up bill", "Pharmacy bills"]),
        ("checks", "", ["Copy of photo ID card of patient verified by hospital", "Investigation reports", "MLC report & Police FIR"]),
        ("checks", "", ["Hospital Discharge summary", "CT/MR/USG/HPE investigation reports", "Original death summary"]),
        ("line", [("Any other, please specify", "text", 1)]),
    ])
    non_network = (syn(rng, "ADDITIONAL DETAILS IN CASE OF NON NETWORK HOSPITAL (Only fill in case of non-network hospital)",
                       "E. ADDITIONAL DETAILS IN CASE OF NON NETWORK HOSPITAL"), [
        ("line", [("a) Address of the Hospital", "address", 1)]),
        ("line", [("City", "city", 1)]),
        ("line", [("State", "city", 1), ("Pin Code", "pin", 1)]),
        ("line", [("b) Phone No.", "phone", 1), ("c) Registration No.", "id", 1)]),
        ("date", "Date of Registration"),
        ("date", "Expiry date of Registration"),
        ("line", [("Name of the Registering Authority", "text", 1)]),
        ("chars", "d) PAN", 10, "id"),
        ("line", [("e) Number of Inpatient beds", "number", 1), ("f) Facilities available in the hospital: OT / ICU", "text", 1)]),
        ("line", [("iii. Others", "text", 1)]),
    ])
    declaration = (syn(rng, "DECLARATION BY THE HOSPITAL (PLEASE READ VERY CAREFULLY)", "F. DECLARATION BY THE HOSPITAL"), [
        ("note", "We hereby declare that the information furnished in this Claim Form is true & correct to the best of our "
                 "knowledge and belief. If we have made any false or untrue statement, suppression or concealment of any "
                 "material fact, our right to claim under this claim shall be forfeited. The signature of the insured is "
                 "taken on this form after Claim Form B is fully filled up by us."),
        ("note", "Hospital has required infrastructure to fulfill the hospital definition as per IRDA guideline: has at least "
                 "10 inpatient beds; has fully qualified nursing staff under its employment round the clock; has fully "
                 "qualified doctor(s) in charge round the clock; has a fully equipped operation theatre; maintains daily "
                 "medical records of patients."),
        ("line", [("Place", "city", 1), ("Date", "text", 1)]),
        ("line", [("Signature of Insured / Claimant", "text", 1), ("Signature and Seal of the Hospital Authority", "text", 1)]),
    ])
    sections = [checklist, non_network, declaration]
    if rng.random() < 0.3:
        sections = sections[1:]
    titles = [syn(rng, "CLAIM FORM - PART B (contd.)", "CLAIM FORM - PART B", "CLAIM FORM (continued)"),
              syn(rng, "TO BE FILLED IN BY THE HOSPITAL", "TO BE FILLED BY THE HOSPITAL"),
              "The issue of this Form is not to be taken as an admission of liability"]
    return titles, sections


CHRONIC = ["(a) Diabetes", "(b) Hypertension", "(c) Heart Disease", "(d) Br. Asthma/COPD", "(e) Osteo Arthritis",
           "(f) Cancer", "(g) Any Other Ailment", "(h) Any h/o Alcohol", "(i) Any HIV or STD", "(j) Any Other Ailment"]
ESTIMATES = ["Per Day Room Rent+Nursing", "Consultation Charges", "Investigation + diagnostics", "Medicines + Consumables",
             "Surgeon fees", "OT expenses", "Implants (if any)", "Any Others (pl. specify)", "All incl. Package (if applicable)", "TOTAL"]


def preauth_form_cashless(rng):
    """Cashless request form: one dense table of label / value cells, with Y/N columns."""
    patient = (syn(rng, "TO BE FILLED BY THE INSURED / PATIENT", "PART A - INSURED / PATIENT DETAILS"), [
        ("line", [("Name of Patient", "name", 2), ("Age", "number", 1), ("Sex: M / F", "text", 1)]),
        ("line", [("Contact Number", "phone", 2), ("Email", "email", 2)]),
        ("line", [("Name of Proposer", "name", 2), ("Relation to Proposer", "text", 2)]),
        ("line", [("Address", "address", 1)]),
        ("line", [("Policy Type: Indv / Group (GROUP NAME)", "text", 1)]),
        ("line", [("Card ID No.", "id", 2), ("Policy No.", "policy", 2), ("Emp.ID", "id", 1)]),
        ("line", [("Any Past Policy (Y/N)", "yn", 1), ("If Y, attach copies", "text", 1)]),
        ("line", [("Are you presently covered under any other similar type of scheme? Give details", "text", 1)]),
    ])
    doctor_part = (syn(rng, "TO BE FILLED BY THE TREATING DOCTOR / HOSPITAL", "PART B - TREATING DOCTOR DETAILS"), [
        ("line", [("Doctor (Name & Mobile No)", "doctor", 2), ("Qualification", "text", 1), ("Reg.No.", "id", 1)]),
        ("line", [("Presenting complaints with duration", "diagnosis", 1)]),
        ("line", [("Relevant Clinical Findings", "text", 1)]),
        ("line", [("Earlier history of the present ailment if any", "text", 1)]),
        ("line", [("Date of First Consultation (Fax Prescription)", "text", 1)]),
        ("line", [("Rx / Tests done so far (FAX documents)", "text", 1)]),
        ("line", [("Provisional Diagnosis", "diagnosis", 2), ("ICD - 10 CM Code", "icd", 1)]),
        ("checks", "Proposed Line of Treatment", ["Investigation", "Intensive Care", "Medical Management", "Surgical"]),
        ("line", [("(b) If Surgical, name of the Surgery & its details", "text", 1)]),
        ("line", [("(c) For other treatments, furnish details", "text", 2), ("ICD 10 PCS Code", "icd", 1)]),
        ("line", [("Likely DOA", "text", 1), ("Likely length of stay", "number", 1), ("Room Type", "text", 1), ("Room No.", "number", 1)]),
        ("line", [("In Case of ACCIDENTS: Is it RTA Y / N", "yn", 1), ("MLC Y / N", "yn", 1), ("Date of injury", "text", 1)]),
        ("line", [("FIR Attached: Y / N", "yn", 1), ("Alcohol / Drug Intoxication Y / N", "yn", 1)]),
    ])
    hospital_part = (syn(rng, "HOSPITAL DETAILS", "PART C - HOSPITAL DETAILS"), [
        ("line", [("Hospital name", "hospital", 2), ("Hosp ID", "id", 1), ("E-Mail", "email", 1)]),
        ("line", [("Hospital Address", "address", 2), ("Pin Code", "pin", 1)]),
        ("line", [("Key Contact Person", "name", 2), ("Mobile", "phone", 1)]),
    ])
    estimates = (syn(rng, "ESTIMATED EXPENSES DETAILS", "ESTIMATED EXPENSES / PAST HISTORY OF CHRONIC ILLNESS"), [
        ("grid", ["Estimated expenses", "Amount (Rs)", "Past History of chronic illness", "Y / N", "If Y, Duration"], 10,
         ["text", "amount", "text", "yn", "number"], {0: ESTIMATES, 2: CHRONIC}),
        ("note", "*We confirm having read understood and agreed to the Declaration on the reverse of this form"),
    ])
    titles = [syn(rng, "FORM 1: CASHLESS REQUEST FORM", "CASHLESS REQUEST FORM", "REQUEST FOR CASHLESS TREATMENT"),
              syn(rng, "(To be sent to TPA / Insurer by fax or email)", "TO BE FILLED BY THE INSURED / PATIENT AND HOSPITAL"),
              "Cashless facility is subject to policy terms and conditions"]
    return titles, [patient, doctor_part, hospital_part, estimates]


FORM_BUILDERS = {"claim_form": lambda rng: rng.choice([claim_form_part_a, claim_form_part_a, claim_form_part_b, claim_form_continuation])(rng),
                 "preauth_form": lambda rng: rng.choice([preauth_form_boxes, preauth_form_cashless])(rng)}


def render_form(org, titles, sections, style, rng, look=None):
    """Draw a box-style form. look: "bars" (coloured section bars, a box per field),
    "letters" (grey bars, a box per letter, DD / MM / YYYY dates) or "cells" (the whole
    form is one table of bordered label / value cells)."""
    look = look or rng.choice(["bars", "letters", "cells"])
    page = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(page)
    s = rng.randint(14, 18) if look == "cells" else rng.randint(15, 19)
    regular, bold = font(style.regular, s), font(style.bold, s)
    small = font(style.regular, max(11, s - 3))
    accent = rng.choice(FORM_ACCENTS)
    fill = rng.choices(["blank", "typed", "hand"], weights=[0.4, 0.4, 0.2])[0]
    ink = (25, 45, 150) if fill == "hand" else (15, 15, 15)
    value_font = font(style.bold if fill == "typed" else style.regular, s)
    left, right = 60, PAGE_SIZE[0] - 60
    bottom = PAGE_SIZE[1] - 90
    box_h = int(s * 1.45)
    row_h = box_h + 2 if look == "cells" else int(s * 2.0)
    line_colour = (40, 40, 40) if look == "cells" else (60, 60, 60)
    y = top = 60

    def fit(text, fnt, room):
        while text and draw.textlength(text, font=fnt) > room:
            text = text[:-1]
        return text

    def value(kind):
        return fake_value(rng, kind) if fill != "blank" else ""

    def date_text():
        if fill == "blank":
            return "DD / MM / YYYY"
        day, month, year = date(rng).split("/")
        return f"{day} / {month} / {year}"

    # Header
    if look == "letters":
        draw.rectangle([left, y, left + 210, y + 90], outline=accent, width=4)
        draw.text((left + 14, y + 30), org.split()[0].upper()[:11], font=font(style.bold, s + 6), fill=accent)
        big = font(style.bold, s + 14)
        draw.text((left + 240, y + 10), fit(org, big, right - left - 250), font=big, fill="black")
        draw.rectangle([left + 240, y + 60, right, y + 60 + box_h], fill=(225, 225, 225))
        draw.text(((left + 240 + right - draw.textlength(titles[0], font=bold)) / 2, y + 62), titles[0], font=bold, fill="black")
        y += 110
        draw.rectangle([left, y, right, y + box_h + 4], fill=(10, 10, 10))
        draw.text(((left + right - draw.textlength(titles[1], font=bold)) / 2, y + 3), titles[1], font=bold, fill="white")
        y += box_h + 12
        for line in titles[2:]:
            line = fit(line, small, right - left)
            draw.text(((left + right - draw.textlength(line, font=small)) / 2, y), line, font=small, fill="black")
            y += int(s * 1.2)
        y += 8
    else:
        draw.rectangle([left + 12, y + 10, left + 190, y + 78], outline=accent, width=3)
        draw.text((left + 24, y + 30), org.split()[0].upper()[:11], font=font(style.bold, s + 4), fill=accent)
        title_y = y + 6
        for i, line in enumerate([titles[0], org.upper(), f"CIN: U{digits(rng, 5)}{letters(rng, 2).upper()}{digits(rng, 4)}PLC{digits(rng, 6)}"] + titles[1:]):
            fnt = bold if i < 2 else small
            line = fit(line, fnt, right - left - 420)
            draw.text(((left + right - draw.textlength(line, font=fnt)) / 2, title_y), line, font=fnt, fill="black")
            title_y += int(s * 1.25)
        y = max(title_y, y + 90) + 6

    for title, rows in sections:
        if y > bottom - row_h * 2:
            break
        bar_h = int(s * 1.45)
        if look == "bars":
            draw.rectangle([left, y, right, y + bar_h], fill=accent)
            colour, text = "white", f"{title}:"
        else:
            draw.rectangle([left, y, right, y + bar_h], fill=(215, 215, 215) if look == "cells" else (228, 228, 228),
                           outline=(40, 40, 40), width=1)
            colour, text = "black", title
        text = fit(text, bold, right - left - 20)
        draw.text(((left + right - draw.textlength(text, font=bold)) / 2, y + 2), text, font=bold, fill=colour)
        y += bar_h + (0 if look == "cells" else 8)
        for row in rows:
            if y > bottom - row_h:
                break
            kind = row[0]
            if kind == "line":
                fields = row[1]
                total = sum(f[2] for f in fields)
                x = left + (0 if look == "cells" else 8)
                width = right - left - (0 if look == "cells" else 16)
                for label, value_kind, weight in fields:
                    end = x + width * weight / total
                    if look == "cells":
                        # One bordered cell: "Label : value"
                        draw.rectangle([x, y, end, y + row_h], outline=line_colour, width=1)
                        label = fit(label + " :", regular, (end - x) * 0.7)
                        draw.text((x + 5, y + 3), label, font=regular, fill="black")
                        value_x = x + 10 + draw.textlength(label, font=regular)
                        text = fit(value(value_kind), value_font, end - value_x - 6)
                        if text:
                            draw.text((value_x, y + 3), text, font=value_font, fill=ink)
                    else:
                        label = fit(label + ("" if look == "letters" else ":"), regular, (end - x) * 0.55)
                        draw.text((x, y + 4), label, font=regular, fill="black")
                        box_x = x + draw.textlength(label, font=regular) + 8
                        text = value(value_kind)
                        if look == "letters":
                            # A row of letter boxes up to the end of the field
                            cell, i = box_h * 0.95, 0
                            while box_x + cell <= end - 8:
                                draw.rectangle([box_x, y, box_x + cell, y + box_h], outline=line_colour, width=1)
                                if i < len(text):
                                    draw.text((box_x + cell * 0.22, y + 3), text[i], font=value_font, fill=ink)
                                box_x += cell
                                i += 1
                        else:
                            draw.rectangle([box_x, y, end - 10, y + box_h], outline=line_colour, width=1)
                            text = fit(text, value_font, end - 10 - box_x - 10)
                            if text:
                                draw.text((box_x + 6, y + 3), text, font=value_font, fill=ink)
                    x = end
                y += row_h
            elif kind == "chars":
                label, count, value_kind = row[1], row[2], row[3]
                draw.text((left + 8, y + 4), label + ":", font=regular, fill="black")
                x = left + 8 + max(220, draw.textlength(label + ":", font=regular) + 12)
                text = value(value_kind).replace(" ", "")
                for i in range(count):
                    draw.rectangle([x, y, x + box_h, y + box_h], outline=line_colour, width=1)
                    if i < len(text):
                        draw.text((x + box_h * 0.25, y + 3), text[i], font=value_font, fill=ink)
                    x += box_h + (0 if look == "letters" else 3)
                if look == "cells":
                    draw.rectangle([left, y - 1, right, y + row_h], outline=line_colour, width=1)
                y += row_h
            elif kind == "date":
                label = row[1]
                if look == "cells":
                    draw.rectangle([left, y, right, y + row_h], outline=line_colour, width=1)
                draw.text((left + 8, y + 4), label + ":", font=regular, fill="black")
                x = left + 8 + max(360, draw.textlength(label + ":", font=regular) + 12)
                if look == "bars":
                    digits_text = "" if fill == "blank" else date(rng).replace("/", "")[:4] + date(rng)[-2:]
                    for i, placeholder in enumerate("DDMMYY"):
                        draw.rectangle([x, y, x + box_h, y + box_h], outline=line_colour, width=1)
                        char, colour = (digits_text[i], ink) if digits_text else (placeholder, (175, 175, 175))
                        draw.text((x + box_h * 0.25, y + 3), char, font=small if not digits_text else value_font, fill=colour)
                        x += box_h + (14 if i % 2 else 2)
                else:
                    text = date_text()
                    colour = (150, 150, 150) if fill == "blank" else ink
                    draw.text((x, y + 3), text, font=value_font if fill != "blank" else small, fill=colour)
                    draw.line([x, y + box_h, x + draw.textlength("DD / MM / YYYY", font=regular) + 10, y + box_h], fill=(120, 120, 120))
                    x += draw.textlength("DD / MM / YYYY", font=regular) + 30
                if rng.random() < 0.4:
                    x += 30
                    draw.text((x, y + 4), "Time:", font=regular, fill="black")
                    x += draw.textlength("Time:", font=regular) + 8
                    if look == "bars":
                        for placeholder in "HH:MM":
                            if placeholder == ":":
                                draw.text((x, y + 2), ":", font=bold, fill="black")
                                x += 12
                                continue
                            draw.rectangle([x, y, x + box_h, y + box_h], outline=line_colour, width=1)
                            draw.text((x + box_h * 0.25, y + 3), placeholder, font=small, fill=(175, 175, 175))
                            x += box_h + 2
                    else:
                        draw.text((x, y + 3), "HH : MM" if fill == "blank" else f"{rng.randint(0, 23):02d} : {rng.randint(0, 59):02d}",
                                  font=small if fill == "blank" else value_font, fill=(150, 150, 150) if fill == "blank" else ink)
                y += row_h
            elif kind == "checks":
                label, options = row[1], row[2]
                row_top = y
                x = left + 8
                if label:
                    label = fit(label + ":", regular, (right - left) * 0.45)
                    draw.text((x, y + 4), label, font=regular, fill="black")
                    x += draw.textlength(label, font=regular) + 16
                chosen = rng.randrange(len(options)) if fill != "blank" else -1
                mark = int(box_h * (0.7 if look == "cells" else 1))
                for i, option in enumerate(options):
                    need = draw.textlength(option, font=regular) + mark + 22
                    if x + need > right - 8:
                        y += row_h
                        x = left + 40
                    if look == "cells":
                        # "□ Option": the box comes first
                        draw.rectangle([x, y + (box_h - mark) / 2, x + mark, y + (box_h + mark) / 2], outline=line_colour, width=1)
                        box_x, x = x, x + mark + 6
                        draw.text((x, y + 3), option, font=regular, fill="black")
                        x += draw.textlength(option, font=regular) + 20
                    else:
                        draw.text((x, y + 4), option, font=regular, fill="black")
                        x += draw.textlength(option, font=regular) + 6
                        draw.rectangle([x, y, x + mark, y + mark], outline=line_colour, width=1)
                        box_x, x = x, x + mark + 16
                    if i == chosen:
                        my = y + (box_h - mark) / 2 if look == "cells" else y
                        draw.line([box_x + 3, my + mark / 2, box_x + mark / 2, my + mark - 3], fill=ink, width=3)
                        draw.line([box_x + mark / 2, my + mark - 3, box_x + mark - 2, my + 2], fill=ink, width=3)
                if look == "cells":
                    draw.rectangle([left, row_top, right, y + row_h], outline=line_colour, width=1)
                y += row_h
            elif kind == "grid":
                header, count, kinds = row[1], row[2], row[3]
                fixed = row[4] if len(row) > 4 else {}
                edges = [left + (right - left) * i / len(header) for i in range(len(header) + 1)]
                cell_h = int(s * 1.5)
                filled = rng.randint(1, count) if fill != "blank" else 0
                for r in range(count + 1):
                    if y + cell_h > bottom:
                        break
                    for c in range(len(header)):
                        draw.rectangle([edges[c], y, edges[c + 1], y + cell_h], outline=(90, 90, 90), width=1)
                        if r == 0:
                            text, fnt, colour = header[c], bold, "black"
                        elif c in fixed:
                            text, fnt, colour = fixed[c][(r - 1) % len(fixed[c])], small, "black"
                        elif c == 0 and not header[0]:
                            text, fnt, colour = ["i. Primary Diagnosis", "ii. Additional Diagnosis", "iii. Co-morbidities", "iv. Co-morbidities"][(r - 1) % 4], small, "black"
                        elif c == 0:
                            text, fnt, colour = str(r), regular, "black"
                        elif kinds[c] == "yn":
                            text = f": {fake_value(rng, 'yn')}" if r <= filled else ": Y / N"
                            fnt, colour = (value_font, ink) if r <= filled else (small, "black")
                        elif r <= filled:
                            text = date(rng) if kinds[c] == "date" else fake_value(rng, kinds[c])
                            fnt, colour = value_font, ink
                        else:
                            text, fnt, colour = ("D D M M Y Y" if kinds[c] == "date" else ""), small, (175, 175, 175)
                        draw.text((edges[c] + 6, y + 3), fit(text, fnt, edges[c + 1] - edges[c] - 10), font=fnt, fill=colour)
                    y += cell_h
                y += 8
            elif kind == "note":
                for line in wrap(draw, row[1], small, right - left - 16):
                    if y > bottom - row_h:
                        break
                    draw.text((left + 8, y), line, font=small, fill="black")
                    y += int(s * 1.05)
                y += 8
        y += 0 if look == "cells" else 4
    draw.rectangle([left - 4, top - 4, right + 4, min(y + 4, bottom + 20)], outline="black", width=2)
    if look == "letters" or rng.random() < 0.3:
        slug = "".join(c for c in org.lower() if c.isalnum())[:12]
        foot = f"Registered Office: {address(rng)}  |  http://www.{slug}-demo.in  |  email: support@{slug}-demo.in"
        draw.text((left, PAGE_SIZE[1] - 60), fit(foot, small, right - left - 120), font=small, fill=(60, 60, 60))
        draw.text((right - 90, PAGE_SIZE[1] - 60), f"Page {rng.randint(1, 2)} of {rng.randint(2, 4)}", font=small, fill=(60, 60, 60))
    return page


def silhouette(draw, box):
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=(210, 210, 210), outline=(120, 120, 120), width=2)
    cx, w = (x0 + x1) // 2, x1 - x0
    draw.ellipse([cx - w // 5, y0 + w // 6, cx + w // 5, y0 + w // 6 + w * 2 // 5], fill=(160, 160, 160))
    draw.pieslice([x0 + w // 8, y1 - w // 2, x1 - w // 8, y1 + w // 3], 180, 360, fill=(160, 160, 160))


def render_card(doc_type, style, rng):
    card = Image.new("RGB", CARD_SIZE, rng.choice([(250, 250, 245), (235, 245, 255), (255, 245, 230), (240, 255, 240)]))
    draw = ImageDraw.Draw(card)
    w, h = CARD_SIZE
    s = 30
    bold, regular, small = font(style.bold, s), font(style.regular, int(s * 0.85)), font(style.regular, int(s * 0.7))
    person = name(rng)
    dob = date(rng)

    headers = {
        "aadhaar": ("SAMPLE UNIQUE ID AUTHORITY", (200, 100, 20)),
        "pan_card": ("INCOME TAX DEPARTMENT (SPECIMEN)", (30, 60, 140)),
        "passport": ("REPUBLIC OF SAMPLELAND - PASSPORT", (40, 40, 110)),
        "driving_licence": ("DRIVING LICENCE - DEMO TRANSPORT DEPT", (20, 100, 60)),
        "voter_id": ("ELECTION COMMISSION (SPECIMEN)", (110, 30, 90)),
        "health_card": (rng.choice(INSURERS), style.accent),
    }
    header_text, colour = headers[doc_type]
    draw.rectangle([0, 0, w, 90], fill=colour)
    draw.text((30, 28), header_text, font=bold, fill="white")
    silhouette(draw, (30, 120, 250, 400))

    fields = {
        "aadhaar": [("Name", person), ("DOB", dob), ("Gender", rng.choice(["Male", "Female"])),
                    ("", f"{digits(rng, 4)} {digits(rng, 4)} {digits(rng, 4)}")],
        "pan_card": [("Name", person.upper()), ("Father's name", name(rng).upper()), ("Date of birth", dob),
                     ("Permanent Account Number", f"{letters(rng, 5)}{digits(rng, 4)}{letters(rng, 1)}")],
        "passport": [("Surname", person.split()[1].upper()), ("Given name", person.split()[0].upper()), ("Date of birth", dob),
                     ("Passport no.", f"{letters(rng, 1)}{digits(rng, 7)}"), ("Date of expiry", date(rng))],
        "driving_licence": [("Name", person), ("DL no.", f"{letters(rng, 2)}{digits(rng, 2)} {digits(rng, 11)}"), ("DOB", dob),
                            ("Valid till", date(rng)), ("Class", rng.choice(["LMV", "MCWG, LMV"]))],
        "voter_id": [("Elector's name", person), ("Father's name", name(rng)), ("Gender", rng.choice(["Male", "Female"])),
                     ("EPIC no.", f"{letters(rng, 3)}{digits(rng, 7)}")],
        "health_card": [("Member", person), ("Member ID", f"{letters(rng, 3)}{digits(rng, 9)}"), ("Policy no.", f"{digits(rng, 4)}/{digits(rng, 8)}"),
                        ("Valid till", date(rng)), ("TPA helpline", phone(rng))],
    }
    y = 125
    for key, value in fields[doc_type]:
        if key:
            draw.text((280, y), key, font=small, fill=(90, 90, 90))
            y += int(s * 0.8)
        draw.text((280, y), value, font=bold if not key else regular, fill="black")
        y += int(s * 1.3)

    if doc_type == "passport":
        mrz_font = font(str(FONT_DIR / "dejavu/DejaVuSansMono.ttf"), 26)
        draw.text((30, h - 110), f"P<SPL{person.split()[1].upper()}<<{person.split()[0].upper()}".ljust(44, "<")[:44], font=mrz_font, fill="black")
        draw.text((30, h - 70), f"{letters(rng, 1)}{digits(rng, 7)}<{digits(rng, 1)}SPL{digits(rng, 7)}".ljust(44, "<")[:44], font=mrz_font, fill="black")

    # Watermarks: these are training pictures, not usable documents. A light one
    # across the card and a solid strip at the bottom, away from the fields.
    mark = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(mark).text((140, 250), "SPECIMEN - NOT A REAL ID", font=font(style.bold, 60), fill=(220, 0, 0, 45))
    card = Image.alpha_composite(card.convert("RGBA"), mark.rotate(18)).convert("RGB")
    draw = ImageDraw.Draw(card)
    strip_top = h - 150 if doc_type == "passport" else h - 48
    draw.rectangle([0, strip_top, w, strip_top + 40], fill=(200, 30, 30))
    draw.text((30, strip_top + 6), "SPECIMEN - NOT A REAL ID - FOR SOFTWARE TESTING ONLY", font=font(style.bold, 24), fill="white")
    return card


def render_cheque(style, rng):
    cheque = Image.new("RGB", (1240, 560), rng.choice([(235, 245, 255), (245, 240, 230), (240, 250, 240)]))
    draw = ImageDraw.Draw(cheque)
    bold, regular = font(style.bold, 30), font(style.regular, 26)
    draw.text((40, 30), rng.choice(BANKS), font=font(style.bold, 40), fill=(20, 50, 120))
    draw.text((40, 85), f"{rng.choice(CITIES)} branch  |  IFSC: DEMO0{digits(rng, 6)}", font=regular, fill=(60, 60, 60))
    draw.text((900, 40), f"Date  {date(rng)}", font=regular, fill="black")
    draw.text((40, 170), "Pay", font=bold, fill="black")
    draw.line([120, 205, 1000, 205], fill=(80, 80, 80), width=2)
    draw.text((40, 240), "Rupees", font=bold, fill="black")
    draw.line([170, 275, 1000, 275], fill=(80, 80, 80), width=2)
    draw.rectangle([1020, 230, 1200, 290], outline="black", width=2)
    draw.text((40, 330), f"A/c No. {digits(rng, 12)}", font=bold, fill="black")
    draw.text((40, 380), f"{name(rng).upper()}", font=regular, fill="black")
    draw.text((850, 420), "Authorised signatory", font=regular, fill="black")
    mono = font(str(FONT_DIR / "dejavu/DejaVuSansMono.ttf"), 34)
    draw.text((200, 490), f"\"{digits(rng, 6)}\" {digits(rng, 9)}: {digits(rng, 6)}\" {digits(rng, 2)}", font=mono, fill="black")
    # The two crossing lines and the word that make it a cancelled cheque
    draw.line([300, 120, 520, 520], fill=(20, 20, 20), width=6)
    draw.line([380, 120, 600, 520], fill=(20, 20, 20), width=6)
    draw.text((560, 300), "CANCELLED", font=font(style.bold, 80), fill=(30, 30, 30))
    return cheque


def place_on_page(item, rng):
    # Cards and cheques are usually photocopied or scanned on a full page
    page = Image.new("RGB", PAGE_SIZE, "white")
    scale = rng.uniform(0.75, 1.0)
    item = item.resize((int(item.width * scale), int(item.height * scale)))
    x = rng.randint(60, max(61, PAGE_SIZE[0] - item.width - 60))
    y = rng.randint(80, PAGE_SIZE[1] // 2)
    page.paste(item, (x, y))
    return page


# ---------------------------------------------------------------- scan / photo effects

def degrade(page, rng, mode):
    if mode == "digital":
        return page
    if mode == "scan":
        page = page.convert("L")
        page = page.rotate(rng.uniform(-3, 3), expand=False, fillcolor=255, resample=Image.BICUBIC)
        noise = Image.effect_noise(page.size, rng.uniform(8, 25))
        page = Image.blend(page, noise, rng.uniform(0.04, 0.12))
        page = page.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.2)))
        return page.convert("RGB")
    # phone photo: page on a darker background, tilted, softer focus, uneven light
    background = Image.new("RGB", (page.width + 240, page.height + 240), tuple(rng.randint(60, 140) for _ in range(3)))
    background.paste(page, (120, 120))
    page = background.rotate(rng.uniform(-7, 7), expand=False, fillcolor=(90, 90, 90), resample=Image.BICUBIC)
    page = page.filter(ImageFilter.GaussianBlur(rng.uniform(0.6, 1.6)))
    shade = Image.linear_gradient("L").resize(page.size).rotate(rng.choice([0, 90, 180, 270]))
    page = Image.composite(page, Image.new("RGB", page.size, (40, 40, 40)), shade.point(lambda v: 160 + v * 95 // 255))
    return page


def failed_page(rng):
    kind = rng.choice(["blank", "near_blank", "blur", "dark"])
    page = Image.new("RGB", PAGE_SIZE, "white")
    if kind == "near_blank":
        draw = ImageDraw.Draw(page)
        for _ in range(rng.randint(1, 4)):
            x, y = rng.randint(0, 1100), rng.randint(0, 1600)
            draw.line([x, y, x + rng.randint(5, 60), y + rng.randint(-5, 5)], fill=(180, 180, 180), width=2)
    elif kind == "blur":
        style = make_style(rng, TRAIN_FONTS)
        org, blocks = PAGE_BUILDERS[rng.choice(list(PAGE_BUILDERS))](rng)
        page = render_page(org, blocks, style, rng).filter(ImageFilter.GaussianBlur(rng.uniform(9, 16)))
    elif kind == "dark":
        page = Image.new("RGB", PAGE_SIZE, tuple(rng.randint(5, 40) for _ in range(3)))
    noise = Image.effect_noise(PAGE_SIZE, 20).convert("RGB")
    return Image.blend(page, noise, rng.uniform(0.02, 0.08)), kind


# ---------------------------------------------------------------- main

def make_page(doc_type, rng, fonts):
    style = make_style(rng, fonts)
    if doc_type in CARD_TYPES:
        item = render_card(doc_type, style, rng)
        page = item if rng.random() < 0.3 else place_on_page(item, rng)
    elif doc_type == "cancelled_cheque":
        item = render_cheque(style, rng)
        page = item if rng.random() < 0.3 else place_on_page(item, rng)
    elif doc_type == "pharmacy_bill" and rng.random() < 0.35:
        # Printed cash memo pad of a local medical store, often photographed
        memo = render_memo(style, rng)
        page = Image.new("RGB", PAGE_SIZE, "white")
        scale = rng.uniform(1.0, 1.6)
        memo = memo.resize((int(memo.width * scale), int(memo.height * scale)))
        page.paste(memo, ((PAGE_SIZE[0] - memo.width) // 2, rng.randint(40, max(41, PAGE_SIZE[1] - memo.height - 40))))
    elif doc_type in FORM_BUILDERS and rng.random() < 0.6:
        titles, sections = FORM_BUILDERS[doc_type](rng)
        page = render_form(rng.choice(INSURERS), titles, sections, style, rng)
    else:
        org, blocks = PAGE_BUILDERS[doc_type](rng)
        page = render_page(org, blocks, style, rng)
    mode = rng.choices(["digital", "scan", "photo"], weights=[0.35, 0.45, 0.2])[0]
    return degrade(page, rng, mode), mode


def save(page, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if max(page.size) > 1400:
        page.thumbnail((1400, 1400))
    page.save(path, "JPEG", quality=82)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train", type=int, default=40, help="pages per type in the train set")
    parser.add_argument("--test", type=int, default=12, help="pages per type in the test set")
    parser.add_argument("--failed", type=int, default=30, help="unreadable pages")
    parser.add_argument("--bundles", type=int, default=3, help="multi-page mixed PDFs")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rows = []
    for split, count, fonts in [("train", args.train, TRAIN_FONTS), ("test", args.test, TEST_FONTS)]:
        for doc_type in DOC_TYPES:
            # Each type gets its own random sequence, so changing one type's generator
            # leaves every other type's pages exactly the same (and their OCR / embeddings
            # cached, see build_dataset.py)
            rng = random.Random(f"{args.seed}-{split}-{doc_type}")
            for n in range(count):
                page, mode = make_page(doc_type, rng, fonts)
                path = OUT_DIR / split / doc_type / f"{n:03d}.jpg"
                save(page, path)
                rows.append({"path": str(path.relative_to(OUT_DIR)), "split": split, "doc_type": doc_type,
                             "category": DOC_TYPES[doc_type]["category"], "mode": mode, "source": "synthetic"})
            print(f"{split:5} {doc_type:20} {count} pages")

    rng = random.Random(args.seed + 2000)
    for n in range(args.failed):
        page, kind = failed_page(rng)
        path = OUT_DIR / "failed" / f"{n:03d}.jpg"
        save(page, path)
        rows.append({"path": str(path.relative_to(OUT_DIR)), "split": "failed", "doc_type": "failed", "category": "failed",
                     "mode": kind, "source": "synthetic"})
    print(f"failed {args.failed} pages")

    # Mixed bundles, like one PDF uploaded for a whole insurance claim
    rng = random.Random(args.seed + 3000)
    for n in range(args.bundles):
        types = ["claim_form", "aadhaar", "pan_card", "discharge_summary", "lab_report", "lab_report",
                 "hospital_bill", "pharmacy_bill", "payment_receipt", "cancelled_cheque", "prescription", "other"]
        rng.shuffle(types)
        pages = [make_page(t, rng, TEST_FONTS)[0].convert("RGB") for t in types]
        path = OUT_DIR / "bundles" / f"bundle_{n}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        pages[0].save(path, save_all=True, append_images=pages[1:], resolution=150)
        (OUT_DIR / "bundles" / f"bundle_{n}.json").write_text(json.dumps(types, indent=2))
        print(f"bundle {path.name}: {len(types)} pages")

    with (OUT_DIR / "manifest.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "split", "doc_type", "category", "mode", "source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} pages written to {OUT_DIR}")


if __name__ == "__main__":
    main()
