"""
Extract plain text from uploaded PDF and EPUB files.
No Flask imports; pure logic for easy testing.
"""
import re
from pathlib import Path

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

# Optional: use config for max length; avoid circular import by defaulting
try:
    import config
    _MAX_TEXT_LENGTH = getattr(config, "MAX_TEXT_LENGTH", 300_000)
except ImportError:
    _MAX_TEXT_LENGTH = 300_000


class ParsingError(Exception):
    """Raised when file cannot be parsed (corrupted or unreadable)."""
    pass


def _normalize_text(text: str) -> str:
    """Collapse whitespace and trim."""
    if not text or not text.strip():
        return ""
    return re.sub(r"\s+", " ", text.strip())


def _extract_pdf(path: str) -> str:
    """Extract text from a PDF file using PyPDF2."""
    try:
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            raw = page.extract_text()
            if raw:
                parts.append(raw)
        combined = "\n".join(parts)
        if not combined.strip():
            raise ParsingError("PDF appears to have no extractable text (e.g. scanned pages).")
        return _normalize_text(combined)
    except PdfReadError as e:
        raise ParsingError("Could not read PDF. File may be corrupted or invalid.") from e
    except Exception as e:
        if isinstance(e, ParsingError):
            raise
        raise ParsingError("Could not read PDF.") from e


def _extract_epub(path: str) -> str:
    """Extract text from an EPUB using ebooklib and BeautifulSoup."""
    try:
        book = epub.read_epub(path)
        parts = []
        for item in book.get_items():
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            content = item.get_content()
            if not content:
                continue
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            if text:
                parts.append(text)
        combined = " ".join(parts)
        if not combined.strip():
            raise ParsingError("EPUB appears to have no extractable text.")
        return _normalize_text(combined)
    except ParsingError:
        raise
    except Exception as e:
        raise ParsingError("Invalid or corrupted EPUB.") from e


def parse_ebook(file_path: str, filename: str) -> str:
    """
    Extract plain text from an eBook file (PDF or EPUB).
    Infers type from extension. Truncates to MAX_TEXT_LENGTH if configured.
    """
    path = Path(file_path)
    if not path.exists():
        raise ParsingError("File not found.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        text = _extract_pdf(str(path))
    elif ext == "epub":
        text = _extract_epub(str(path))
    else:
        raise ParsingError("Unsupported format. Use PDF or EPUB.")

    if not text:
        raise ParsingError("No text could be extracted from the file.")

    # Truncate to avoid context limit for LLM
    if len(text) > _MAX_TEXT_LENGTH:
        text = text[: _MAX_TEXT_LENGTH] + "\n\n[Text truncated for length.]"

    return text
