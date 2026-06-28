"""Paper page-furniture observation tests."""

from __future__ import annotations

from table1_parser.paper_page_furniture import (
    build_paper_page_furniture,
    cluster_page_furniture_observations,
    collect_page_furniture_text_observations,
    normalize_page_furniture_text,
)
from table1_parser.schemas import PageFurnitureTextObservation


def test_normalize_page_furniture_text_masks_current_page_number() -> None:
    """Normalization should only change matching features, not raw artifact text."""
    assert normalize_page_furniture_text("  Page   3  ", page_num=3) == "Page <page_num>"
    assert normalize_page_furniture_text("3", page_num=3) == "<page_num>"
    assert normalize_page_furniture_text("Volume 2023", page_num=3) == "Volume 2023"
    assert normalize_page_furniture_text("p3 supplement", page_num=3) == "p3 supplement"
    assert normalize_page_furniture_text("3.0", page_num=3) == "3.0"


def test_collect_page_furniture_text_observations_from_pymupdf_lines(monkeypatch) -> None:
    """Collector should preserve positioned page text without clustering it."""

    class FakeRect:
        width = 600.0
        height = 800.0

    class FakePage:
        rect = FakeRect()

        def __init__(self, page_index: int) -> None:
            self.page_index = page_index

        def get_text(self, mode: str) -> dict[str, object]:
            assert mode == "dict"
            if self.page_index == 1:
                return {"blocks": []}
            return {
                "blocks": [
                    {
                        "lines": [
                            {
                                "dir": (1.0, 0.0),
                                "spans": [
                                    {"text": " Journal ", "bbox": (12.0, 20.0, 80.0, 30.0)},
                                    {"text": " Title ", "bbox": (84.0, 20.0, 140.0, 30.0)},
                                ],
                            },
                            {"spans": [{"text": "   ", "bbox": (10.0, 40.0, 20.0, 50.0)}]},
                            {"spans": [{"text": "Page 1", "bbox": (520.0, 760.0, 560.0, 770.0)}]},
                        ]
                    }
                ]
            }

    class FakeDocument:
        page_count = 2
        closed = False

        def load_page(self, page_index: int) -> FakePage:
            assert page_index in {0, 1}
            return FakePage(page_index)

        def close(self) -> None:
            self.closed = True

    fake_documents: list[FakeDocument] = []

    def fake_open_document(_: str) -> FakeDocument:
        fake_document = FakeDocument()
        fake_documents.append(fake_document)
        return fake_document

    monkeypatch.setattr("table1_parser.paper_page_furniture.open_pymupdf_document", fake_open_document)

    observations, page_count = collect_page_furniture_text_observations("paper.pdf")

    assert fake_documents[-1].closed is True
    assert page_count == 2
    assert len(observations) == 2
    assert observations[0].observation_id == "page-1-line-0"
    assert observations[0].raw_text == "Journal Title"
    assert observations[0].normalized_text == "Journal Title"
    assert observations[0].bbox == (12.0, 20.0, 140.0, 30.0)
    assert observations[0].relative_bbox == (0.02, 0.025, 0.23333333333333334, 0.0375)
    assert observations[0].orientation == "1.000,0.000"
    assert observations[1].observation_id == "page-1-line-2"
    assert observations[1].raw_text == "Page 1"
    assert observations[1].normalized_text == "Page <page_num>"
    assert build_paper_page_furniture("paper.pdf").metadata["page_count"] == 2


def test_cluster_page_furniture_observations_uses_content_position_and_parity() -> None:
    """Repeated page text should cluster only when the page-relative position is stable."""

    def observation(
        observation_id: str,
        page_num: int,
        text: str,
        relative_bbox: tuple[float, float, float, float],
    ) -> PageFurnitureTextObservation:
        return PageFurnitureTextObservation(
            observation_id=observation_id,
            page_num=page_num,
            raw_text=text,
            normalized_text=text,
            bbox=tuple(value * 1000.0 for value in relative_bbox),
            relative_bbox=relative_bbox,
            page_width=1000.0,
            page_height=1000.0,
            orientation="1.000,0.000",
        )

    observations = [
        observation("h1", 1, "Running Title", (0.10, 0.02, 0.40, 0.04)),
        observation("h2", 2, "Running Title", (0.11, 0.02, 0.41, 0.04)),
        observation("h3", 3, "Running Title", (0.10, 0.03, 0.40, 0.05)),
        observation("o1", 1, "Odd Header", (0.55, 0.02, 0.90, 0.04)),
        observation("o3", 3, "Odd Header", (0.55, 0.02, 0.90, 0.04)),
        observation("i1", 1, "Repeated Interior Cell", (0.30, 0.50, 0.45, 0.52)),
        observation("i2", 2, "Repeated Interior Cell", (0.30, 0.50, 0.45, 0.52)),
        observation("i3", 3, "Repeated Interior Cell", (0.30, 0.50, 0.45, 0.52)),
        observation("n1", 1, "Single Note", (0.15, 0.90, 0.45, 0.93)),
    ]

    clusters, regions = cluster_page_furniture_observations(
        observations,
        page_count=4,
        min_pages=3,
        min_page_fraction=0.7,
    )

    by_text = {cluster.normalized_text_key: cluster for cluster in clusters}
    assert set(by_text) == {"Odd Header", "Running Title"}
    assert by_text["Running Title"].recurrence_scope == "all_pages"
    assert by_text["Running Title"].page_nums == [1, 2, 3]
    assert by_text["Odd Header"].recurrence_scope == "odd_pages"
    assert by_text["Odd Header"].scope_page_count == 2
    assert by_text["Odd Header"].scope_page_fraction == 1.0
    assert len(regions) == 5
