"""
Extract plain text from uploaded PDF and EPUB files.
No Flask imports; pure logic for easy testing.
Supports single-string output (parse_ebook) and chunked output (parse_ebook_chunks).
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
    _MAX_CHUNK_CHARS = getattr(config, "MAX_CHUNK_CHARS", None)  # None => use GEMINI_MAX_INPUT_CHARS or 30_000
    _PDF_CHUNK_PAGES = getattr(config, "PDF_CHUNK_PAGES", 8)
except ImportError:
    _MAX_TEXT_LENGTH = 300_000
    _MAX_CHUNK_CHARS = 30_000
    _PDF_CHUNK_PAGES = 8

# Fallback for MAX_CHUNK_CHARS when not set in config
try:
    _MAX_CHUNK_CHARS = _MAX_CHUNK_CHARS or getattr(config, "GEMINI_MAX_INPUT_CHARS", 30_000)
except (NameError, AttributeError):
    _MAX_CHUNK_CHARS = _MAX_CHUNK_CHARS or 30_000


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


# --- Chunked extraction (V2) ---


def _truncate_chunk(text: str, max_chars: int) -> str:
    """Truncate a single chunk to max_chars; append note if truncated."""
    if not text or max_chars <= 0:
        return text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Text truncated for length.]"


def _extract_pdf_chunks(path: str, pages_per_chunk: int) -> list[dict]:
    """Extract PDF as chunks by page ranges. Each chunk: {id, title, text}."""
    try:
        reader = PdfReader(path)
        pages = list(reader.pages)
        if not pages:
            raise ParsingError("PDF has no pages.")
        chunks = []
        chunk_id = 1
        for start in range(0, len(pages), pages_per_chunk):
            end = min(start + pages_per_chunk, len(pages))
            parts = []
            for i in range(start, end):
                raw = pages[i].extract_text()
                if raw:
                    parts.append(raw)
            text = _normalize_text("\n".join(parts))
            if not text:
                continue
            title = f"Pages {start + 1}\u2013{end}"
            text = _truncate_chunk(text, _MAX_CHUNK_CHARS)
            chunks.append({"id": chunk_id, "title": title, "text": text})
            chunk_id += 1
        if not chunks:
            raise ParsingError("PDF appears to have no extractable text (e.g. scanned pages).")
        return chunks
    except PdfReadError as e:
        raise ParsingError("Could not read PDF. File may be corrupted or invalid.") from e
    except ParsingError:
        raise
    except Exception as e:
        raise ParsingError("Could not read PDF.") from e


def _toc_links(book: epub.EpubBook) -> list[tuple[str, str]]:
    """Flatten TOC into a list of (href, title). Recursively walks Link and Section."""
    result = []

    def walk(toc):
        if toc is None:
            return
        if isinstance(toc, (list, tuple)):
            for item in toc:
                walk(item)
            return
        if hasattr(toc, "href") and hasattr(toc, "title"):
            # epub.Link
            if getattr(toc, "href", None):
                result.append((toc.href, getattr(toc, "title") or "Untitled"))
            return
        if hasattr(toc, "title") and hasattr(toc, "children"):
            # Section with children
            for child in getattr(toc, "children", []) or []:
                walk(child)
            return
        if hasattr(toc, "title") and hasattr(toc, "__iter__") and not isinstance(toc, str):
            try:
                for child in toc:
                    walk(child)
            except TypeError:
                pass

    walk(getattr(book, "toc", None))
    return result


def _extract_epub_chunks(path: str) -> list[dict]:
    """Extract EPUB as chunks by TOC (chapters). Fallback: one chunk per document or single chunk."""
    try:
        book = epub.read_epub(path)
        # Build href -> item map (file_name and basename for TOC resolution)
        items_by_href = {}
        for item in book.get_items():
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            name = getattr(item, "file_name", None)
            if not name and callable(getattr(item, "get_name", None)):
                name = item.get_name()
            if name:
                items_by_href[name] = item
                if "/" in name:
                    items_by_href[name.split("/")[-1]] = item

        links = _toc_links(book)
        chunks = []
        seen_hrefs = set()
        chunk_id = 1

        for href, title in links:
            # Normalize href: strip fragment, use as key
            base_href = href.split("#")[0].lstrip("/")
            if not base_href or base_href in seen_hrefs:
                continue
            item = None
            if hasattr(book, "get_item_with_href"):
                item = book.get_item_with_href(href) or book.get_item_with_href(base_href)
            if item is None:
                item = items_by_href.get(base_href) or items_by_href.get(href.split("/")[-1] if "/" in href else href) or items_by_href.get(href)
            if item is None:
                continue
            seen_hrefs.add(base_href)
            content = item.get_content()
            if not content:
                continue
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            if not text:
                continue
            text = _normalize_text(text)
            text = _truncate_chunk(text, _MAX_CHUNK_CHARS)
            chunks.append({"id": chunk_id, "title": title or f"Chapter {chunk_id}", "text": text})
            chunk_id += 1

        if chunks:
            return _apply_global_cap(chunks)

        # Fallback: one chunk per document item (spine order or get_items)
        for item in book.get_items():
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            content = item.get_content()
            if not content:
                continue
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            if not text:
                continue
            text = _normalize_text(text)
            text = _truncate_chunk(text, _MAX_CHUNK_CHARS)
            chunks.append({"id": chunk_id, "title": f"Section {chunk_id}", "text": text})
            chunk_id += 1

        if not chunks:
            raise ParsingError("EPUB appears to have no extractable text.")
        return _apply_global_cap(chunks)
    except ParsingError:
        raise
    except Exception as e:
        raise ParsingError("Invalid or corrupted EPUB.") from e


def _apply_global_cap(chunks: list[dict]) -> list[dict]:
    """Trim or drop chunks so total text stays under MAX_TEXT_LENGTH."""
    total = 0
    out = []
    for c in chunks:
        total += len(c["text"])
        if total > _MAX_TEXT_LENGTH:
            # Trim this chunk to fit
            allowance = _MAX_TEXT_LENGTH - (total - len(c["text"]))
            if allowance <= 0:
                break
            c = {**c, "text": _truncate_chunk(c["text"], allowance)}
        out.append(c)
        if total >= _MAX_TEXT_LENGTH:
            break
    return out


def parse_ebook_chunks(file_path: str, filename: str) -> list[dict]:
    """
    Extract eBook as structured chunks. Each chunk: {"id": int, "title": str, "text": str}.
    EPUB: chunk by TOC/chapters; PDF: chunk by fixed page ranges (PDF_CHUNK_PAGES).
    """
    path = Path(file_path)
    if not path.exists():
        raise ParsingError("File not found.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        chunks = _extract_pdf_chunks(str(path), _PDF_CHUNK_PAGES)
    elif ext == "epub":
        chunks = _extract_epub_chunks(str(path))
    else:
        raise ParsingError("Unsupported format. Use PDF or EPUB.")

    if not chunks:
        raise ParsingError("No text could be extracted from the file.")

    return chunks


def parse_ebook(file_path: str, filename: str) -> str:
    """
    Extract plain text from an eBook file (PDF or EPUB).
    Infers type from extension. Truncates to MAX_TEXT_LENGTH if configured.
    Kept for backward compatibility; new code should use parse_ebook_chunks.
    """
    chunks = parse_ebook_chunks(file_path, filename)
    combined = "\n\n".join(c["text"] for c in chunks)
    if len(combined) > _MAX_TEXT_LENGTH:
        combined = combined[:_MAX_TEXT_LENGTH] + "\n\n[Text truncated for length.]"
    return combined
