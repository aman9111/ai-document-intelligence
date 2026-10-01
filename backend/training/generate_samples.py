"""Generate fictional page images for training and testing the page classifier.

Every page is fake: made-up names, numbers and organisations, and every ID card
carries a SPECIMEN watermark. Nothing here is a real person or a real document.

    python training/generate_samples.py              # default counts
    python training/generate_samples.py --train 60 --test 15

Output (not committed to git, re-create it any time with the same seed):

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

def title(text): return ("title", text)
def heading(text): return ("heading", text)
def kv(pairs): return ("kv", pairs)
def table(header, rows): return ("table", header, rows)
def para(text): return ("para", text)
def sign(text): return ("sign", text)
def footer(text): return ("footer", text)


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


def policy_document(rng):
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
    ]


def payment_receipt(rng):
    org = hospital(rng)
    return org, [
        title(rng.choice(["PAYMENT RECEIPT", "RECEIPT", "ADVANCE RECEIPT", "MONEY RECEIPT"])),
        kv([("Receipt no.", f"R-{digits(rng, 6)}"), ("Date", date(rng)), ("Received from", name(rng)),
            ("Amount", f"Rs {amount(rng, 500, 100000)}"), ("Payment mode", rng.choice(["Cash", "UPI", "Card", "NEFT", "Cheque"])),
            ("Towards", rng.choice(["Advance deposit", "Final settlement", "OPD charges", "Lab charges"]))]),
        para("Received with thanks."),
        sign("Cashier"),
    ]


def other(rng):
    kind = rng.choice(OTHER_KINDS)
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
    for split, count, fonts, seed in [("train", args.train, TRAIN_FONTS, args.seed), ("test", args.test, TEST_FONTS, args.seed + 1000)]:
        rng = random.Random(seed)
        for doc_type in DOC_TYPES:
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
