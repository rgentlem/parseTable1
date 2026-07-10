"""Extraction backends and helpers."""

from table1_parser.extract.base import BaseExtractor


def build_extractor(backend_name: str = "pymupdf4llm") -> BaseExtractor:
    """Create an extraction backend from its configured name."""
    if backend_name == "pymupdf4llm":
        from table1_parser.extract.pymupdf4llm_extractor import PyMuPDF4LLMExtractor

        return PyMuPDF4LLMExtractor()
    raise ValueError(f"Unsupported extraction backend: {backend_name}")


__all__ = ["BaseExtractor", "build_extractor"]
