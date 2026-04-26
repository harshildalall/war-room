from pathlib import Path
from datetime import date
from docxtpl import DocxTemplate, RichText

TEMPLATE_PATH = Path("templates/appeal_letter_tpl.docx")

def render_docx(strategy: dict, drafted: dict, output_path: Path) -> None:
    tpl = DocxTemplate(TEMPLATE_PATH)

    body_rt = RichText()
    paragraphs = drafted["appeal_letter"].split("\n\n")
    for i, para in enumerate(paragraphs):
        body_rt.add(para)
        if i < len(paragraphs) - 1:
            body_rt.add("\n\n")

    context = {
        "appeal_date": date.today().strftime("%B %d, %Y"),
        "insurer_name": strategy.get("insurer", ""),
        "insurer_address": strategy.get("insurer_address", ""),
        "patient_name": strategy.get("patient_name", ""),
        "patient_dob": strategy.get("patient_dob", ""),
        "member_id": strategy.get("member_id", ""),
        "claim_number": strategy.get("case_id", ""),
        "date_of_service": strategy.get("date_of_service", ""),
        "denial_reason_summary": strategy.get("denial_reason_text", ""),
        "appeal_level": strategy.get("appeal_level", "first_internal"),
        "medical_necessity_argument": drafted["appeal_letter"],
        "personal_evidence": strategy.get("personal_evidence", []),
        "external_evidence": drafted.get("citations_footnoted", []),
        "missing_info_note": strategy.get("missing_info_note", ""),
        "submitter_name": strategy.get("submitter_name", ""),
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