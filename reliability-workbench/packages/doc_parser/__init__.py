"""
Document Parser — turn raw bytes into structured Document, format-agnostic.

WHAT I DO:
  - Detect format: html | ixbrl | pem-sgml (1990s SEC) | plaintext
  - Strip envelopes (PEM RSA wrapper, SGML headers, iXBRL tags)
  - Decode HTML entities (`&#160;` → real space) — fixes the PFE bug
  - Produce plaintext + a list of Block (heading/paragraph/table/list/code)
  - Report extraction strategy for trace/audit

WHAT I DON'T DO:
  - I don't extract SEC items (that's apps/sec10k-extractor)
  - I don't classify content semantically
  - I don't cache / persist
  - I don't know what year the filing is from (caller can use metadata)

IO CONTRACT:
  parse(content: bytes, format_hint="auto") → Document
  detect_format(content: bytes) → str

  Document(blocks, plaintext, metadata, format, raw, extraction_strategy)
  Block(kind, text, char_offset, char_length, attrs)

HIDDEN FACTS:
  - Encoding: tries utf-8, falls back to latin-1 (1990s SEC sometimes used latin-1)
  - PEM detection: starts with "-----BEGIN PRIVACY-ENHANCED MESSAGE-----"
  - SGML detection: contains `<SEC-DOCUMENT>` or `<IMS-DOCUMENT>`
  - iXBRL detection: contains "XBRL" + xmlns:ix
  - For PEM/SGML: tries to find <DOCUMENT><TYPE>10-K block first (preserves only 10-K body, drops exhibits)
  - plaintext is ALWAYS html.unescape()'d (mandatory — fixes &#160; bugs across providers)
  - Block extraction is best-effort; on failure, returns plaintext-only Document

DECOUPLING:
  - bs4 + lxml optional (fallback to html.parser if missing)
  - Doesn't import from packages/*
"""

from .parser import (
    parse, detect_format,
    Document, DocumentMetadata, Block,
    ParseError, UnsupportedFormat, FileTooLargeError, EncodingError,
    PARSER_VERSION,
)

__all__ = [
    "parse", "detect_format",
    "Document", "DocumentMetadata", "Block",
    "ParseError", "UnsupportedFormat", "FileTooLargeError", "EncodingError",
    "PARSER_VERSION",
]
