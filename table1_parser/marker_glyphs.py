"""Shared normalization for observed marker glyphs."""

from __future__ import annotations

import unicodedata

from table1_parser.schemas.paper_footnotes import FootnoteGlyphKind


CANONICAL_SYMBOL_KEYS = {
    "†": "dagger",
    "‡": "double_dagger",
    "§": "section",
    "¶": "paragraph",
    "#": "number_sign",
    "|": "vertical_bar",
}


def glyph_fields(glyph_raw: str) -> tuple[FootnoteGlyphKind, str, list[str]]:
    """Return normalized identity fields without deciding marker meaning."""
    glyph = glyph_raw.strip()
    codepoints = [f"U+{ord(char):04X}" for char in glyph]
    if not glyph:
        return "unknown", "unknown:", codepoints
    normalized_key = unicodedata.normalize("NFKC", glyph).strip().casefold()
    if normalized_key.isalpha():
        return "letter", f"letter:{normalized_key}", codepoints
    if normalized_key.isdigit():
        return "number", f"number:{normalized_key}", codepoints
    if normalized_key and all(char == "*" for char in normalized_key):
        return "asterisk", f"asterisk:{len(normalized_key)}", codepoints
    if normalized_key in CANONICAL_SYMBOL_KEYS:
        return "symbol", f"symbol:{CANONICAL_SYMBOL_KEYS[normalized_key]}", codepoints
    if any(not char.isalnum() for char in glyph):
        return "symbol", "symbol:" + ",".join(codepoints), codepoints
    return "unknown", f"unknown:{normalized_key or glyph}", codepoints
