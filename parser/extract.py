import fitz
import base64
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)

    if len(text.strip()) >= 80:
        return text.strip()

    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    return extract_text_from_image(img_bytes, "image/png")

def extract_text_from_image(img_bytes: bytes, media_type: str) -> str:
    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_b64
                    }
                },
                {
                    "type": "text",
                    "text": "Transcribe ALL text from this document exactly as written. Include every word, number, date, and code. Do not summarize."
                }
            ]
        }]
    )
    return msg.content[0].text

def extract(file_bytes: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        return extract_text_from_pdf(file_bytes)
    elif content_type in ("image/jpeg", "image/png", "image/jpg"):
        return extract_text_from_image(file_bytes, content_type)
    elif content_type == "text/plain":
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        try:
            return extract_text_from_pdf(file_bytes)
        except Exception:
            return ""