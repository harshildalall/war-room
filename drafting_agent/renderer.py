from pathlib import Path
from datetime import date
from docxtpl import DocxTemplate, RichText
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import pdfrw
import io

TEMPLATE_PATH = Path("templates/appeal_letter_tpl.docx")
UHC_FORM_PATH = Path("templates/UHC-Single-Paper-Claim-Reconsideration-Form.pdf")

REASON_MAP = {
    "medical_necessity":    (8,  182),
    "prior_auth":           (6,  218),
    "coding_error":         (5,  236),
    "lack_of_information":  (2,  290),
    "out_of_network":       (8,  182),
    "experimental":         (8,  182),
    "exhausted_benefits":   (8,  182),
    "other":                (8,  182),
}


def render_docx(strategy: dict, drafted: dict, output_path: Path) -> None:
    tpl = DocxTemplate(TEMPLATE_PATH)

    body_rt = RichText()
    paragraphs = drafted["appeal_letter"].split("\n\n")
    for i, para in enumerate(paragraphs):
        body_rt.add(para)
        if i < len(paragraphs) - 1:
            body_rt.add("\n\n")

    context = {
        "appeal_date":              date.today().strftime("%B %d, %Y"),
        "insurer_name":             strategy.get("insurer", ""),
        "insurer_address":          strategy.get("insurer_address", ""),
        "patient_name":             strategy.get("patient_name", ""),
        "patient_dob":              strategy.get("patient_dob", ""),
        "member_id":                strategy.get("member_id", ""),
        "claim_number":             strategy.get("case_id", ""),
        "date_of_service":          strategy.get("date_of_service", ""),
        "denial_reason_summary":    strategy.get("denial_reason_text", ""),
        "appeal_level":             strategy.get("appeal_level", "first_internal"),
        "medical_necessity_argument": body_rt,
        "personal_evidence":        strategy.get("personal_evidence", []),
        "external_evidence":        drafted.get("citations_footnoted", []),
        "missing_info_note":        strategy.get("missing_info_note", ""),
        "submitter_name":           strategy.get("submitter_name", ""),
    }

    tpl.render(context)
    tpl.save(str(output_path))
    print(f"[drafting_agent] .docx saved → {output_path}")


def render_pdf(docx_path: Path, pdf_path: Path) -> None:
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        print(f"[drafting_agent] .pdf saved → {pdf_path}")
    except ImportError:
        from subprocess import run as sp_run
        sp_run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(pdf_path.parent), str(docx_path)],
            check=True
        )
        print(f"[drafting_agent] .pdf saved via LibreOffice → {pdf_path}")


def render_uhc_form(strategy: dict, drafted: dict, output_path: Path) -> None:
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.setFont("Helvetica", 9)

    # Page 1 — member info
    c.drawString(180, 713, date.today().strftime("%m/%d/%Y"))
    c.drawString(420, 713, strategy.get("member_id", ""))
    c.drawString(180, 695, strategy.get("case_id", ""))
    c.drawString(420, 695, strategy.get("date_of_service", ""))
    c.drawString(180, 677, strategy.get("billed_amount", ""))

    patient = strategy.get("patient_name", "")
    name_parts = patient.split(" ", 1)
    c.drawString(72,  659, name_parts[-1] if len(name_parts) > 1 else patient)
    c.drawString(300, 659, name_parts[0] if len(name_parts) > 1 else "")

    # Page 2 — reason checkbox + comments
    c.showPage()
    c.setFont("Helvetica", 10)

    denial_category = strategy.get("denial_reason_category", "other")
    _, y_pos = REASON_MAP.get(denial_category, (8, 182))
    c.drawString(58, y_pos, "X")

    c.setFont("Helvetica", 8)
    comments = drafted.get("appeal_letter", "")[:800]
    text_obj = c.beginText(72, 140)
    for line in comments.split("\n"):
        text_obj.textLine(line)
    c.drawText(text_obj)

    c.save()
    packet.seek(0)

    overlay = pdfrw.PdfReader(packet)
    base = pdfrw.PdfReader(str(UHC_FORM_PATH))
    writer = pdfrw.PdfWriter()

    for i, page in enumerate(base.pages):
        merger = pdfrw.PageMerge(page)
        if i < len(overlay.pages):
            merger.add(overlay.pages[i]).render()
        writer.addpage(page)

    writer.write(str(output_path))
    print(f"[drafting_agent] UHC form saved → {output_path}")