# Every page is classified into one document type. Types are grouped into
# categories, which become the tabs in the UI (like "Medical Documents (70)").
#
# "description" is written the way you'd describe the page to someone who can't
# read it. The image model (SigLIP) compares a page image with these sentences.

CATEGORIES = {
    "insurance": "Insurance Documents",
    "medical": "Medical Documents",
    "financial": "Financial Documents",
    "kyc": "KYC Documents",
    "other": "Other Documents",
}

DOC_TYPES = {
    # Insurance
    "claim_form": {
        "category": "insurance",
        "label": "Claim form",
        "description": "a health insurance claim form with policy number, patient and hospital details",
    },
    "policy_document": {
        "category": "insurance",
        "label": "Policy document",
        "description": "a health insurance policy schedule with sum insured, premium and policy period",
    },
    "preauth_form": {
        "category": "insurance",
        "label": "Pre-authorization form",
        "description": "a cashless pre-authorization request form for hospital admission",
    },
    "health_card": {
        "category": "insurance",
        "label": "Health card / e-card",
        "description": "a small health insurance member ID card",
    },
    # Medical
    "discharge_summary": {
        "category": "medical",
        "label": "Discharge summary",
        "description": "a hospital discharge summary with diagnosis, treatment and advice on discharge",
    },
    "lab_report": {
        "category": "medical",
        "label": "Lab report",
        "description": "a medical laboratory test report with results, units and reference ranges",
    },
    "prescription": {
        "category": "medical",
        "label": "Prescription",
        "description": "a doctor's prescription with medicines and dosage",
    },
    "radiology_report": {
        "category": "medical",
        "label": "Radiology report",
        "description": "an X-ray, CT, MRI or ultrasound report with findings and impression",
    },
    "consultation_notes": {
        "category": "medical",
        "label": "Consultation notes",
        "description": "a doctor's consultation or OPD notes with complaints and examination",
    },
    # Financial
    "hospital_bill": {
        "category": "financial",
        "label": "Hospital bill",
        "description": "a hospital final bill with itemised charges and total amount",
    },
    "pharmacy_bill": {
        "category": "financial",
        "label": "Pharmacy bill",
        "description": "a pharmacy or chemist bill listing medicines with quantity and price",
    },
    "payment_receipt": {
        "category": "financial",
        "label": "Payment receipt",
        "description": "a payment receipt acknowledging money received",
    },
    "cancelled_cheque": {
        "category": "financial",
        "label": "Cancelled cheque",
        "description": "a bank cheque crossed and marked cancelled",
    },
    # KYC
    "aadhaar": {
        "category": "kyc",
        "label": "Aadhaar card",
        "description": "an Indian Aadhaar identity card with a 12 digit number",
    },
    "pan_card": {
        "category": "kyc",
        "label": "PAN card",
        "description": "an Indian PAN card for income tax with a 10 character number",
    },
    "passport": {
        "category": "kyc",
        "label": "Passport",
        "description": "a passport data page with photo and machine readable lines",
    },
    "driving_licence": {
        "category": "kyc",
        "label": "Driving licence",
        "description": "a driving licence card",
    },
    "voter_id": {
        "category": "kyc",
        "label": "Voter ID",
        "description": "an election voter identity card",
    },
    # Other
    "other": {
        "category": "other",
        "label": "Other",
        "description": "a general document such as a letter, resume or notice, not medical, financial or an ID",
    },
}

# Pages that couldn't be read at all (blank, too blurred, OCR found nothing).
# Decided by rules, not by the models, and shown in the "Failed pages" tab.
FAILED = "failed"


def category_of(doc_type: str) -> str:
    return DOC_TYPES[doc_type]["category"] if doc_type in DOC_TYPES else "other"
