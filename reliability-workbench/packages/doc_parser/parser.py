"""Document parser implementation. Per Gemini critique Round 2 — tightened contract."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal


PARSER_VERSION = "0.1.0"
DEFAULT_MAX_FILE_SIZE_MB = 100


class ParseError(Exception):
    pass


class UnsupportedFormat(ValueError):
    pass


class FileTooLargeError(ValueError):
    pass


class EncodingError(ValueError):
    pass


@dataclass
class Block:
    """Generic block. For tables, prefer TableBlock subclass."""
    kind: Literal["heading", "paragraph", "table", "list", "code"]
    text: str                          # plaintext rendering for LLM consumption
    char_offset: int                   # offset in Document.plaintext (sequential, strictly increasing)
    char_length: int
    depth: int = 0                     # heading level (1-6) or list nesting depth
    html: str | None = None            # source HTML fragment if applicable
    table_data: list[list[str]] | None = None   # populated ONLY when kind=="table"
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentMetadata:
    """Structured metadata. Pulled out of dict per Gemini §8 critique."""
    raw_size_bytes: int
    decoded_chars: int
    detected_encoding: str
    parser_version: str = PARSER_VERSION
    block_count: int = 0
    title: str | None = None
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    # Form type detection — moved from skill regex to parser (per William feedback 2026-04-26)
    form_type: str | None = None        # "10-K" | "10-K/A" | "DEF 14A" | ...
    form_type_source: str | None = None # "sgml-type-tag" | "ixbrl-dei" | "body-form-text" | None


@dataclass
class Document:
    blocks: list[Block]
    plaintext: str                       # NFC-normalized + html.unescape'd
    metadata: DocumentMetadata
    format: Literal["html", "ixbrl", "pem-sgml", "plaintext"]
    raw: bytes
    raw_hash: str                        # SHA-256 hex; for caching/idempotency
    extraction_strategy: str


# ──────────────────────────────────────────
# Format detection
# ──────────────────────────────────────────

def detect_format(content: bytes) -> str:
    """Returns 'html' | 'ixbrl' | 'pem-sgml' | 'plaintext'."""
    head = content[:8000].decode("utf-8", errors="ignore")
    if "BEGIN PRIVACY-ENHANCED MESSAGE" in head[:200]:
        return "pem-sgml"
    if "<SEC-DOCUMENT>" in head[:5000] or "<IMS-DOCUMENT>" in head[:5000]:
        return "pem-sgml"  # SGML envelope, also old format
    if "xmlns:ix=" in head or '<?xml' in head[:200] and "XBRL" in head[:5000]:
        return "ixbrl"
    if re.search(r"<html\b", head, re.IGNORECASE):
        return "html"
    return "plaintext"


# ──────────────────────────────────────────
# Decoding
# ──────────────────────────────────────────

def _decode(content: bytes, requested: str | None = None) -> tuple[str, str]:
    """Returns (decoded_text, encoding_used). Tries requested first, then auto."""
    if requested:
        try:
            return content.decode(requested), requested
        except (UnicodeDecodeError, LookupError) as e:
            raise EncodingError(f"failed to decode with requested {requested!r}: {e}") from e
    # Auto: try chardet if available, else fallback chain
    try:
        import chardet  # type: ignore
        detected = chardet.detect(content[:50000]).get("encoding")
        if detected:
            try:
                return content.decode(detected), detected
            except UnicodeDecodeError:
                pass
    except ImportError:
        pass
    # Hardcoded fallback chain
    for enc in ("utf-8", "latin-1"):
        try:
            return content.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore"), "utf-8-lossy"


# ──────────────────────────────────────────
# PEM/SGML envelope (1990s SEC)
# ──────────────────────────────────────────

def _detect_form_type(raw_text: str, body_text: str, fmt: str) -> tuple[str | None, str | None]:
    """
    Detect SEC form type from authoritative source. Returns (form_type, source).

    Layered preference (most → least authoritative):
      1. SGML <TYPE> tag in raw envelope (1990s SEC, 100% reliable)
      2. iXBRL dei:DocumentType element (modern SEC, 100% reliable)
      3. Body text "FORM 10-K/A" near document top (heuristic, ~95%)

    Examples returned: "10-K", "10-K/A", "10-K405", "DEF 14A", None.
    """
    # 1. SGML envelope (look in raw_text BEFORE envelope stripping — most reliable)
    m = re.search(r"<TYPE>\s*([A-Z0-9\-/]+)", raw_text[:5000])
    if m:
        return m.group(1).strip(), "sgml-type-tag"

    # 2. iXBRL dei:DocumentType
    if fmt == "ixbrl":
        m = re.search(
            r'name=["\']dei:DocumentType["\'][^>]*>\s*([^<\s]+)',
            raw_text[:200000],  # iXBRL header section can be large
        )
        if m:
            return m.group(1).strip(), "ixbrl-dei"

    # 3. Body text fallback — bounded window (NOT full doc — was the Ford 1995 bug)
    m = re.search(
        r"\bFORM\s+(10-K/A|10-K\b|DEF\s+14A|10-K405|10-Q[A-Z]?)",
        body_text[:5000],
        re.IGNORECASE,
    )
    if m:
        return m.group(1).upper().replace(" ", " "), "body-form-text"

    return None, None


def _strip_pem_sgml(text: str) -> tuple[str, str]:
    """
    Returns (body_text, strategy_label).

    Old SEC format:
      -----BEGIN PRIVACY-ENHANCED MESSAGE-----
      ... RSA headers ...
      <SEC-DOCUMENT>...
      <SEC-HEADER>...</SEC-HEADER>
      <DOCUMENT><TYPE>10-K<TEXT>... actual 10-K ...</TEXT></DOCUMENT>
      <DOCUMENT><TYPE>EX-21<TEXT>... exhibit ...</TEXT></DOCUMENT>
      ...
    """
    # 1. Skip PEM header
    m = re.search(r"<(SEC|IMS)-DOCUMENT>", text)
    if m:
        text = text[m.start():]

    # 2. Find first <DOCUMENT><TYPE>10-K...<TEXT>...</TEXT></DOCUMENT>
    doc_re = re.search(
        r"<DOCUMENT>\s*<TYPE>10-K[\s\S]*?<TEXT>([\s\S]*?)</TEXT>\s*</DOCUMENT>",
        text, re.IGNORECASE,
    )
    if doc_re:
        return doc_re.group(1), "pem-sgml-doc-text-block"

    # 3. Fallback: take everything after </SEC-HEADER>
    for tag in ("</SEC-HEADER>", "</IMS-HEADER>"):
        idx = text.find(tag)
        if idx != -1:
            return text[idx + len(tag):], f"pem-sgml-after-{tag.strip('</>').lower()}"

    return text, "pem-sgml-fallback-raw"


# ──────────────────────────────────────────
# Tag stripping (HTML / iXBRL / SGML page markers)
# ──────────────────────────────────────────

def _strip_tags(text: str) -> str:
    """Remove all tags, preserve content. Decode HTML entities. Normalize whitespace + Unicode (NFC)."""
    # SGML page markers (<PAGE>) → newline so content stays separated
    text = re.sub(r"<PAGE>\s*\d*", "\n", text, flags=re.IGNORECASE)
    # All other tags → space (NOT empty — would merge words)
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities (CRITICAL — fixes &#160; bugs)
    text = html.unescape(text)
    # NFC normalization (Gemini Round 2 — handles e.g. accented char composition)
    text = unicodedata.normalize("NFC", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_table_data(table_el) -> list[list[str]] | None:
    """Best-effort 2D table extraction. Merged cells duplicated to maintain grid integrity."""
    try:
        rows = []
        for tr in table_el.find_all("tr"):
            row = []
            for cell in tr.find_all(["td", "th"]):
                text = html.unescape(cell.get_text(" ", strip=True))
                colspan = int(cell.get("colspan", 1))
                row.extend([text] * colspan)
            if row:
                rows.append(row)
        return rows if rows else None
    except Exception:
        return None


# ──────────────────────────────────────────
# Block extraction (best-effort using bs4 if available)
# ──────────────────────────────────────────

def _extract_blocks(text: str, fmt: str) -> tuple[list[Block], list[str]]:
    """Best effort. Returns (blocks, warnings)."""
    warnings: list[str] = []
    if fmt not in ("html", "ixbrl"):
        return [], warnings  # PEM/plaintext — no structured blocks
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        warnings.append("bs4 not installed; block extraction skipped")
        return [], warnings

    try:
        if fmt == "ixbrl" and _has_lxml():
            soup = BeautifulSoup(text, "xml")
        else:
            soup = BeautifulSoup(text, "lxml" if _has_lxml() else "html.parser")
    except Exception as e:
        warnings.append(f"bs4 parse failed: {e}")
        return [], warnings

    blocks: list[Block] = []
    offset = 0
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "ul", "ol"]):
        try:
            inner_text = html.unescape(el.get_text(" ", strip=True))
            inner_text = unicodedata.normalize("NFC", inner_text)
        except Exception:
            continue
        if not inner_text:
            continue
        kind = (
            "heading" if el.name.startswith("h") and el.name[1:].isdigit()
            else "paragraph" if el.name == "p"
            else "table" if el.name == "table"
            else "list"
        )
        depth = int(el.name[1]) if kind == "heading" else 0
        attrs: dict[str, Any] = {}
        table_data = None
        if kind == "table":
            table_data = _extract_table_data(el)
            if table_data is None:
                warnings.append(f"table at offset {offset} could not be parsed; fallback to text")
        blocks.append(Block(
            kind=kind, text=inner_text,
            char_offset=offset, char_length=len(inner_text),
            depth=depth,
            html=str(el)[:5000] if len(str(el)) < 50000 else None,  # cap to avoid bloat
            table_data=table_data,
            attrs=attrs,
        ))
        offset += len(inner_text) + 1
    return blocks, warnings


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


# ──────────────────────────────────────────
# Public API
# ──────────────────────────────────────────

def parse(
    content: bytes,
    *,
    format_hint: Literal["html", "ixbrl", "pem-sgml", "plaintext", "auto"] = "auto",
    encoding: str | None = None,
    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
) -> Document:
    """
    Parse bytes into a Document.

    Args:
      content:           raw bytes
      format_hint:       "auto" (default) | "html" | "ixbrl" | "pem-sgml" | "plaintext"
      encoding:          if None, auto-detect (chardet → utf-8 → latin-1)
      max_file_size_mb:  reject inputs larger than this (OOM guard); 1-500 valid

    Raises:
      ParseError                  empty input or stripped result is empty
      UnsupportedFormat           hint or detected format is unknown
      FileTooLargeError           content exceeds max_file_size_mb
      EncodingError               cannot decode with requested encoding
    """
    if not content:
        raise ParseError("empty content")
    if not 1 <= max_file_size_mb <= 500:
        raise ValueError(f"max_file_size_mb must be 1-500, got {max_file_size_mb}")
    size_mb = len(content) / (1024 * 1024)
    if size_mb > max_file_size_mb:
        raise FileTooLargeError(f"content {size_mb:.1f} MB > limit {max_file_size_mb} MB")

    fmt = format_hint if format_hint != "auto" else detect_format(content)
    if fmt not in ("html", "ixbrl", "pem-sgml", "plaintext"):
        raise UnsupportedFormat(f"unknown format: {fmt}")

    text, used_encoding = _decode(content, encoding)
    raw_hash = hashlib.sha256(content).hexdigest()

    # Envelope handling
    if fmt == "pem-sgml":
        body_text, strategy = _strip_pem_sgml(text)
        plaintext = _strip_tags(body_text)
    else:
        body_text = text
        strategy = f"{fmt}-tags-stripped"
        plaintext = _strip_tags(body_text)

    # Sanity: plaintext must have content
    if not plaintext:
        raise ParseError(f"after stripping ({strategy}), plaintext is empty")

    # Best-effort block extraction
    blocks, warnings = _extract_blocks(body_text, fmt)

    # Detect form type (10-K vs 10-K/A etc.) — uses raw text BEFORE envelope strip
    # so SGML <TYPE> tag is still visible
    form_type, form_type_source = _detect_form_type(text, body_text, fmt)

    metadata = DocumentMetadata(
        raw_size_bytes=len(content),
        decoded_chars=len(text),
        detected_encoding=used_encoding,
        block_count=len(blocks),
        warnings=warnings,
        form_type=form_type,
        form_type_source=form_type_source,
    )

    return Document(
        blocks=blocks,
        plaintext=plaintext,
        metadata=metadata,
        format=fmt,
        raw=content,
        raw_hash=raw_hash,
        extraction_strategy=strategy,
    )
