# Sample documents for testing

All names, numbers and organisations in these files are **fictional**. They are safe to
upload and to send to a cloud LLM (Groq).

| File | Type | What it tests |
|---|---|---|
| `1_discharge_summary_digital.pdf` | Digital PDF (real text) | `pypdf` text extraction, 2 pages |
| `1_discharge_summary.docx` | DOCX with a table | `python-docx`, table reading |
| `2_lab_report_scanned.pdf` | Scanned PDF (image only, tilted, noisy) | OCR fallback, 2 pages |
| `3_pharmacy_bill_photo.jpg` | Phone photo of a bill (tilted, blurred) | Image OCR, OCR errors (`15` is read as `1S`) |
| `4_insurance_claim_form.docx` | DOCX form with tables | Label/value fields |

## Questions and expected answers

### 1. Discharge summary (PDF or DOCX)
| Question | Expected answer |
|---|---|
| What was the diagnosis? | Dengue fever with thrombocytopenia (low platelets) |
| What was the lowest platelet count? | 68,000 /uL (on 02/09) |
| Did the platelets improve? | Yes, from 68,000 to 1,42,000 without transfusion |
| Which painkillers should be avoided? | Ibuprofen and aspirin |
| How much water should the patient drink? | At least 3 litres of fluids a day |
| When is the follow up? | After 1 week with Dr. Meera Kulkarni |
| Which liver test was high? | SGPT, 88 U/L (normal 7 - 56) |
| What is the patient's blood group? | Not in the document (the AI should say it couldn't find it) |

### 2. Lab report (scanned PDF)
| Question | Expected answer |
|---|---|
| Is the patient diabetic? | Sugar is high: fasting 148, PP 212, HbA1c 7.9 % (remarks: uncontrolled diabetes) |
| What is the HbA1c? | 7.9 % |
| Which values are low? | Haemoglobin 10.4 g/dL and HDL cholesterol 41 mg/dL |
| Is the thyroid normal? | Yes, TSH 3.2 (range 0.4 - 4.0) |
| What is the LDL cholesterol? | 162 mg/dL (high, should be < 100) |
| Who signed the report? | Dr. P. Nair, MD (Pathology) |

### 3. Pharmacy bill (photo)
| Question | Expected answer |
|---|---|
| What is the total amount paid? | Rs 439.20 |
| How many paracetamol tablets were bought? | 15 (OCR may show "1S") |
| How much discount was given? | 10 %, Rs 48.80 |
| How was the bill paid? | UPI |
| What is the costliest item? | ORS sachets, 210.00 |

### 4. Insurance claim form (DOCX)
| Question | Expected answer |
|---|---|
| What is the policy number? | SLD/HLT/2026/558201 |
| How much is being claimed? | Rs 26,659 |
| What were the room charges? | 10,000 (4 days x 2,500) |
| What type of claim is this? | Reimbursement |
| What is the IFSC code? | DEMO0001234 |
