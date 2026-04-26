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
        "case_id":                  strategy["case_id"],
        "date_today":               date.today().strftime("%B %d, %Y"),
        "recommended_remedy":       strategy["recommended_remedy"],
        "confidence_score":         f"{strategy['confidence_score']:.0%}",
        "strongest_arguments":      strategy["strongest_arguments"],
        "contract_violations":      strategy["contract_violations"],
        "letter_body":              body_rt,
        "citations_footnoted":      drafted["citations_footnoted"],
        "exhibits_checklist":       drafted["exhibits_checklist"],
        "submission_instructions":  drafted["submission_instructions"],
        "deadline":                 drafted["deadline"],
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