from io import BytesIO

import fitz
from docx import Document


def extract_pdf_text(file_bytes: bytes) -> str:
    document = fitz.open(
        stream=file_bytes,
        filetype="pdf",
    )

    pages = []

    for page in document:
        pages.append(page.get_text())

    document.close()

    return "\n".join(pages).strip()


def extract_docx_text(file_bytes: bytes) -> str:
    document = Document(
        BytesIO(file_bytes)
    )

    paragraphs = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    return "\n".join(paragraphs).strip()


def extract_resume_text(
    file_name: str,
    file_bytes: bytes,
) -> str:
    extension = file_name.lower().split(".")[-1]

    if extension == "pdf":
        return extract_pdf_text(file_bytes)

    if extension == "docx":
        return extract_docx_text(file_bytes)

    raise ValueError(
        "Only PDF and DOCX resumes are supported."
    )