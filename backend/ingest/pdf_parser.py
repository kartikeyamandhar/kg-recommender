import fitz  # pymupdf

MAX_CHARS = 6000


def extract_pdf_text(file_bytes: bytes) -> tuple[str, bool]:
    """
    Extract text from PDF bytes.
    Returns (text, truncated) where truncated=True if content exceeded MAX_CHARS.
    Strips likely headers/footers: first and last lines of each page if < 80 chars.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []

    for page in doc:
        raw = page.get_text("text")
        lines = raw.splitlines()
        # Strip header (first line) and footer (last line) if short
        if len(lines) > 2:
            if len(lines[0].strip()) < 80:
                lines = lines[1:]
            if lines and len(lines[-1].strip()) < 80:
                lines = lines[:-1]
        pages.append("\n".join(lines))

    doc.close()
    full_text = "\n\n".join(pages).strip()

    if len(full_text) > MAX_CHARS:
        return full_text[:MAX_CHARS], True

    return full_text, False