"""Extraction backends and helpers."""

from table1_parser.extract.base import BaseExtractor


def build_extractor(backend_name: str = "pymupdf") -> BaseExtractor:
    """Create an extraction backend from its configured name."""
    if backend_name == "pymupdf":
        from table1_parser.extract.pymupdf_extractor import PyMuPDFExtractor

        return PyMuPDFExtractor()
    raise ValueError(f"Unsupported extraction backend: {backend_name}")


__all__ = ["BaseExtractor", "build_extractor"]
