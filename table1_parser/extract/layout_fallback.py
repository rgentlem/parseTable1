"""Backend-agnostic helpers for geometry-driven table fallback extraction."""

from __future__ import annotations

import re
from typing import NamedTuple

from table1_parser.page_furniture_mask import (
    filter_positioned_items_for_page_furniture,
    page_furniture_cluster_ids_for_bbox,
)
from table1_parser.schemas import PaperPageFurniture
from table1_parser.extract.table_detector import (
    DetectedTableCandidate,
    _is_rectangular,
    _normalize_rows,
    _table_caption_metadata,
    score_candidate,
)


ALPHA_TOKEN_PATTERN = re.compile(r"[A-Za-z]")
NUMERIC_TOKEN_PATTERN = re.compile(r"\d")
TABLE_CAPTION_PATTERN = re.compile(r"^\s*table\s*\d+\b(?:\s*[:.])?", re.IGNORECASE)
TABLE_NUMBER_PATTERN = re.compile(r"\btable\s*(\d+)\b", re.IGNORECASE)
SENTENCE_TERMINAL_PATTERN = re.compile(r"[.!?][\"')\]]*$")
LINE_MERGE_TOLERANCE = 4.0
COLUMN_CLUSTER_TOLERANCE = 18.0
COLLAPSED_LABEL_PATTERN = re.compile(r"[a-z][A-Z]|[A-Za-z-]{8,}")
P_VALUE_ANCHOR_PATTERN = re.compile(r"^(?:[<>]=?)?(?:0?\.\d+|\.\d+|1\.0+)(?:[*†‡§¶#{}|]+|[a-z])*$", re.IGNORECASE)
TABLE_VALUE_TEXT_PATTERN = re.compile(r"^(?:[<>]=?\s*)?[\d.,/%()\-+±\s]+$")
CONTINUATION_PAGE_NOTE_PATTERN = re.compile(
    r"\b(?:cont\.?|continued|continues?)\b.*\b(?:previous|next)\s+page\b|"
    r"\b(?:previous|next)\s+page\b.*\b(?:cont\.?|continued|continues?)\b",
    re.IGNORECASE,
)


class TrimmedTableRows(NamedTuple):
    """Candidate rows plus metadata after trailing continuation-note removal."""

    raw_rows: list[list[str]]
    cell_bboxes: list[list[tuple[float, float, float, float] | None]]
    row_bounds: list[tuple[float, float]]
    metadata: dict[str, object] | None


def detect_horizontal_rules(
    rule_segments: list[tuple[float, float, float, float]] | None,
    bbox: tuple[float, float, float, float] | None,
) -> list[float]:
    """Detect wide horizontal rules spanning most of the candidate table width."""
    if bbox is None or not rule_segments:
        return []

    left, top, right, bottom = bbox
    table_width = max(1.0, float(right) - float(left))
    rule_segments_by_y: list[tuple[float, float, float]] = []
    for x0, y0, x1, y1 in rule_segments:
        if abs(y1 - y0) > 1.5:
            continue
        y_mid = (float(y0) + float(y1)) / 2.0
        if y_mid < top - 12.0 or y_mid > bottom + 12.0:
            continue
        overlap_left = max(float(left), min(x0, x1))
        overlap_right = min(float(right), max(x0, x1))
        if overlap_right <= overlap_left:
            continue
        rule_segments_by_y.append((y_mid, overlap_left, overlap_right))

    if not rule_segments_by_y:
        return []

    buckets: list[dict[str, object]] = []
    for y_mid, overlap_left, overlap_right in sorted(rule_segments_by_y):
        if not buckets or abs(y_mid - float(buckets[-1]["y"])) > 3.0:
            buckets.append({"y": y_mid, "spans": [(overlap_left, overlap_right)]})
            continue
        bucket_spans = buckets[-1]["spans"]
        if not isinstance(bucket_spans, list):
            continue
        bucket_spans.append((overlap_left, overlap_right))
        buckets[-1]["y"] = (float(buckets[-1]["y"]) + y_mid) / 2.0

    deduped: list[float] = []
    for bucket in buckets:
        spans = sorted(bucket["spans"]) if isinstance(bucket["spans"], list) else []
        merged_spans: list[list[float]] = []
        for span_left, span_right in spans:
            if not merged_spans or span_left > merged_spans[-1][1] + 3.0:
                merged_spans.append([span_left, span_right])
                continue
            merged_spans[-1][1] = max(merged_spans[-1][1], span_right)
        coverage = sum(span_right - span_left for span_left, span_right in merged_spans)
        if coverage / table_width < 0.8:
            continue
        deduped.append(float(bucket["y"]))
    return deduped


def normalize_positioned_geometry_for_rotation(
    *,
    words: list[dict[str, object]],
    chars: list[dict[str, object]] | None,
    rule_segments: list[tuple[float, float, float, float]] | None,
    bbox: tuple[float, float, float, float],
    rotation_direction: str,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[tuple[float, float, float, float]],
    tuple[float, float, float, float],
]:
    """Normalize clipped positioned geometry into an upright table-local coordinate frame."""
    left, top, right, bottom = bbox
    if rotation_direction not in {"vertical_text_up", "vertical_text_down"}:
        return (words, chars or [], rule_segments or [], bbox)

    def _transform_point(x: float, y: float) -> tuple[float, float]:
        if rotation_direction == "vertical_text_up":
            return (bottom - y, x - left)
        return (y - top, right - x)

    transformed_words: list[dict[str, object]] = []
    for word in words:
        x0 = float(word["x0"])
        x1 = float(word["x1"])
        word_top = float(word["top"])
        word_bottom = float(word["bottom"])
        transformed_corners = [
            _transform_point(x0, word_top),
            _transform_point(x1, word_top),
            _transform_point(x0, word_bottom),
            _transform_point(x1, word_bottom),
        ]
        transformed_words.append(
            {
                "text": word["text"],
                "x0": min(point[0] for point in transformed_corners),
                "x1": max(point[0] for point in transformed_corners),
                "top": min(point[1] for point in transformed_corners),
                "bottom": max(point[1] for point in transformed_corners),
            }
        )

    transformed_chars: list[dict[str, object]] = []
    for char in chars or []:
        x0 = float(char["x0"])
        x1 = float(char["x1"])
        char_top = float(char["top"])
        char_bottom = float(char["bottom"])
        transformed_corners = [
            _transform_point(x0, char_top),
            _transform_point(x1, char_top),
            _transform_point(x0, char_bottom),
            _transform_point(x1, char_bottom),
        ]
        transformed_left = min(point[0] for point in transformed_corners)
        transformed_right = max(point[0] for point in transformed_corners)
        transformed_top = min(point[1] for point in transformed_corners)
        transformed_bottom = max(point[1] for point in transformed_corners)
        transformed_char = {
            key: value
            for key, value in char.items()
            if key not in {"x0", "x1", "top", "bottom", "char_height"}
        }
        transformed_char.update(
            {
                "x0": transformed_left,
                "x1": transformed_right,
                "top": transformed_top,
                "bottom": transformed_bottom,
                "char_height": transformed_bottom - transformed_top,
            }
        )
        transformed_chars.append(transformed_char)

    transformed_rule_segments: list[tuple[float, float, float, float]] = []
    for x0, y0, x1, y1 in rule_segments or []:
        start_x, start_y = _transform_point(float(x0), float(y0))
        end_x, end_y = _transform_point(float(x1), float(y1))
        transformed_rule_segments.append((start_x, start_y, end_x, end_y))

    transformed_bbox = (0.0, 0.0, float(bottom) - float(top), float(right) - float(left))
    return (transformed_words, transformed_chars, transformed_rule_segments, transformed_bbox)


def _is_numeric_like(text: str) -> bool:
    """Return whether a token looks numeric enough to be a table value."""
    return bool(NUMERIC_TOKEN_PATTERN.search(text))


def _nonempty_cell_count(row: list[str]) -> int:
    """Count populated cells in one fallback row."""
    return sum(bool(cell.strip()) for cell in row)


def _table_value_cell_count(row: list[str]) -> int:
    """Count strict numeric/value cells outside the row-label column."""
    return sum(
        bool(TABLE_VALUE_TEXT_PATTERN.fullmatch(cell.strip()))
        and bool(NUMERIC_TOKEN_PATTERN.search(cell))
        for cell in row[1:]
        if cell.strip()
    )


def trim_trailing_non_table_rows(
    raw_rows: list[list[str]],
    *,
    cell_bboxes: list[list[tuple[float, float, float, float] | None]] | None = None,
    row_bounds: list[tuple[float, float]] | None = None,
) -> TrimmedTableRows:
    """Remove explicit trailing continuation-page notes from a table candidate."""
    rows = _normalize_rows(raw_rows)
    bboxes = cell_bboxes or []
    bounds = row_bounds or []
    suffix_start = len(rows)
    removed_continuation_note = False
    continuation_note_texts: list[str] = []
    continuation_table_number: int | None = None
    while suffix_start > 0:
        suffix_row = rows[suffix_start - 1]
        populated = [cell.strip() for cell in suffix_row if cell.strip()]
        if not populated:
            if removed_continuation_note:
                suffix_start -= 1
            break
        suffix_text = " ".join(populated)
        if (
            len(populated) <= 3
            and _table_value_cell_count(suffix_row) == 0
            and CONTINUATION_PAGE_NOTE_PATTERN.search(suffix_text)
        ):
            removed_continuation_note = True
            continuation_note_texts.insert(0, suffix_text)
            table_number_match = TABLE_NUMBER_PATTERN.search(suffix_text)
            if table_number_match is not None:
                continuation_table_number = int(table_number_match.group(1))
            suffix_start -= 1
            continue
        break
    if removed_continuation_note:
        data_row_indices = [
            row_idx
            for row_idx, row in enumerate(rows[:suffix_start])
            if _table_value_cell_count(row) >= (2 if len(row) >= 4 else 1)
        ]
        return TrimmedTableRows(
            rows[:suffix_start],
            bboxes[:suffix_start] if bboxes else bboxes,
            bounds[:suffix_start] if bounds else bounds,
            {
                "start_row_idx": suffix_start,
                "removed_row_count": len(rows) - suffix_start,
                "last_value_row_idx": data_row_indices[-1] if data_row_indices else None,
                "reasons": ["trailing_continuation_note"],
                "gap_after_last_value_row": None,
                "continuation_note_texts": continuation_note_texts,
                "continuation_table_number": continuation_table_number,
            },
        )
    return TrimmedTableRows(rows, bboxes, bounds, None)


def _has_header_like_top_row(rows: list[list[str]]) -> bool:
    """Return whether the first fallback row looks like a table header."""
    if not rows:
        return False
    top_row = [cell.strip() for cell in rows[0]]
    if _nonempty_cell_count(top_row) < 3:
        return False
    first_cell = top_row[0]
    if not first_cell or NUMERIC_TOKEN_PATTERN.search(first_cell):
        return False
    header_text = " ".join(cell.lower() for cell in top_row if cell)
    return bool(
        re.search(
            r"\b(?:variable|variables|characteristic|characteristics|overall|total|case|cases|control|controls|model|or|ci|p|q\d+)\b",
            header_text,
        )
    )


def _has_strong_uncaptioned_table_geometry(rows: list[list[str]]) -> bool:
    """Return whether an uncaptioned fallback grid is table-like enough to preserve."""
    n_cols = max((len(row) for row in rows), default=0)
    if n_cols < 3 or len(rows) < 4:
        return False
    if not _has_header_like_top_row(rows):
        return False
    multi_column_rows = sum(_nonempty_cell_count(row) >= 3 for row in rows)
    if multi_column_rows < max(3, len(rows) // 2):
        return False
    data_like_rows = sum(
        sum(bool(NUMERIC_TOKEN_PATTERN.search(cell)) for cell in row[1:] if cell.strip()) >= 2
        for row in rows[1:]
    )
    return data_like_rows >= 2


def build_word_lines(words: list[dict[str, object]]) -> list[dict[str, object]]:
    """Cluster positioned words into reading-order text lines."""
    if not words:
        return []
    lines: list[dict[str, object]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        bottom = float(word["bottom"])
        if not lines or abs(top - float(lines[-1]["top"])) > LINE_MERGE_TOLERANCE:
            lines.append({"top": top, "bottom": bottom, "words": [word]})
            continue
        lines[-1]["words"].append(word)
        lines[-1]["bottom"] = max(float(lines[-1]["bottom"]), bottom)
    for line in lines:
        line["words"] = sorted(line["words"], key=lambda item: float(item["x0"]))
        line["text"] = " ".join(str(word["text"]).strip() for word in line["words"]).strip()
    return lines


def build_row_grid_from_lines(
    lines: list[dict[str, object]],
    page_chars: list[dict[str, object]] | None = None,
    column_start_boundaries: list[float] | None = None,
) -> tuple[list[list[str]], list[list[tuple[float, float, float, float] | None]]]:
    """Convert text lines into a row-major grid and cell bounding boxes."""
    explicit_boundaries = sorted(
        {
            round(float(boundary), 4)
            for boundary in (column_start_boundaries or [])
        }
    )
    has_left_label_anchor = bool(explicit_boundaries)
    if explicit_boundaries:
        boundaries = explicit_boundaries
        row_width = len(boundaries) + 1
    else:
        broad_numeric_positions = sorted(
            float(word["x0"])
            for line in lines
            for word in line["words"]
            if _is_numeric_like(str(word["text"]))
        )
        numeric_position_items: list[tuple[float, int]] = []
        for line_index, line in enumerate(lines):
            for word in line["words"]:
                text = str(word["text"]).strip()
                compact_text = re.sub(r"[\s,\u00a0\u2009\u202f]+", "", text)
                if not NUMERIC_TOKEN_PATTERN.search(compact_text):
                    continue
                if ALPHA_TOKEN_PATTERN.search(compact_text) and P_VALUE_ANCHOR_PATTERN.fullmatch(compact_text) is None:
                    continue
                numeric_position_items.append((float(word["x0"]), line_index))
        numeric_position_items = sorted(numeric_position_items)
        if not numeric_position_items:
            numeric_anchors = []
        else:
            clusters: list[list[tuple[float, int]]] = [[numeric_position_items[0]]]
            for position_item in numeric_position_items[1:]:
                if abs(position_item[0] - clusters[-1][-1][0]) <= COLUMN_CLUSTER_TOLERANCE:
                    clusters[-1].append(position_item)
                else:
                    clusters.append([position_item])
            line_count = len(lines)
            if line_count <= 4:
                minimum_anchor_lines = 1
            elif line_count <= 12:
                minimum_anchor_lines = 2
            else:
                minimum_anchor_lines = max(3, min(5, line_count // 8))
            value_anchors = [
                sum(position for position, _line_index in cluster) / len(cluster)
                for cluster in clusters
                if len({_line_index for _position, _line_index in cluster}) >= minimum_anchor_lines
            ]
            if line_count > 20:
                for prefix_limit in (4, 8, 12, 16, 20):
                    prefix_items = [(position, line_index) for position, line_index in numeric_position_items if line_index < prefix_limit]
                    prefix_clusters: list[list[tuple[float, int]]] = [[prefix_items[0]]] if prefix_items else []
                    for position_item in prefix_items[1:]:
                        if abs(position_item[0] - prefix_clusters[-1][-1][0]) <= COLUMN_CLUSTER_TOLERANCE:
                            prefix_clusters[-1].append(position_item)
                        else:
                            prefix_clusters.append([position_item])
                    prefix_anchors = [
                        sum(position for position, _line_index in cluster) / len(cluster)
                        for cluster in prefix_clusters
                        if len({_line_index for _position, _line_index in cluster}) >= 3
                    ]
                    if len(prefix_anchors) >= 4 and len(prefix_anchors) > len(value_anchors):
                        value_anchors = prefix_anchors
            if len(value_anchors) < 3 and broad_numeric_positions:
                broad_clusters: list[list[float]] = [[broad_numeric_positions[0]]]
                for position in broad_numeric_positions[1:]:
                    if abs(position - broad_clusters[-1][-1]) <= COLUMN_CLUSTER_TOLERANCE:
                        broad_clusters[-1].append(position)
                    else:
                        broad_clusters.append([position])
                numeric_anchors = [sum(cluster) / len(cluster) for cluster in broad_clusters]
            elif value_anchors:
                leftmost_word_x0 = min(
                    float(word["x0"])
                    for line in lines
                    for word in line["words"]
                )
                if value_anchors[0] - leftmost_word_x0 > COLUMN_CLUSTER_TOLERANCE:
                    numeric_anchors = [leftmost_word_x0, *value_anchors]
                    has_left_label_anchor = True
                else:
                    numeric_anchors = value_anchors
            else:
                numeric_anchors = []
        if not numeric_anchors:
            return ([], [])
        boundaries = [
            (numeric_anchors[index] + numeric_anchors[index + 1]) / 2.0
            for index in range(len(numeric_anchors) - 1)
        ]
        row_width = len(numeric_anchors) if has_left_label_anchor else len(numeric_anchors) + 1
    if not boundaries and row_width <= 1:
        return ([], [])
    rows: list[list[str]] = []
    bbox_rows: list[list[tuple[float, float, float, float] | None]] = []
    for line in lines:
        row_cells = [""] * row_width
        row_bboxes: list[tuple[float, float, float, float] | None] = [None] * row_width
        for word in line["words"]:
            text = str(word["text"]).strip()
            word_width = float(word["x1"]) - float(word["x0"])
            word_height = float(word["bottom"]) - float(word["top"])
            if text.isdigit() and len(text) >= 4 and word_width <= max(6.0, word_height * 0.5):
                continue
            column_index = 0
            while column_index < len(boundaries) and float(word["x0"]) >= boundaries[column_index] - 1.0:
                column_index += 1
            column_index = min(column_index, row_width - 1)
            if (
                column_index <= 1
                and " " not in text
                and ALPHA_TOKEN_PATTERN.search(text)
                and not NUMERIC_TOKEN_PATTERN.search(text)
                and COLLAPSED_LABEL_PATTERN.search(text)
            ):
                if page_chars:
                    x0 = float(word["x0"])
                    x1 = float(word["x1"])
                    top = float(word["top"])
                    bottom = float(word["bottom"])
                    chars_in_word = [
                        char
                        for char in page_chars
                        if top - 0.5 <= (float(char["top"]) + float(char["bottom"])) / 2.0 <= bottom + 0.5
                        and float(char["x0"]) >= x0 - 0.5
                        and float(char["x1"]) <= x1 + 0.5
                    ]
                    if chars_in_word:
                        ordered_chars = sorted(chars_in_word, key=lambda char: float(char["x0"]))
                        pieces: list[str] = []
                        previous_char: dict[str, object] | None = None
                        for char in ordered_chars:
                            char_text = str(char.get("text", ""))
                            if not char_text:
                                continue
                            if previous_char is not None:
                                gap = float(char["x0"]) - float(previous_char["x1"])
                                previous_width = float(previous_char["x1"]) - float(previous_char["x0"])
                                current_width = float(char["x1"]) - float(char["x0"])
                                gap_threshold = max(1.5, min(previous_width, current_width) * 0.6)
                                previous_text = str(previous_char.get("text", ""))
                                if previous_text.isalpha() and char_text.isalpha() and (previous_text.islower() or char_text.isupper()):
                                    gap_threshold = min(gap_threshold, max(1.2, min(previous_width, current_width) * 0.45))
                                if gap > gap_threshold:
                                    pieces.append(" ")
                            pieces.append(char_text)
                            previous_char = char
                        restored = "".join(pieces).strip()
                        if restored:
                            text = restored
            row_cells[column_index] = f"{row_cells[column_index]} {text}".strip()
            word_bbox = (
                float(word["x0"]),
                float(word["top"]),
                float(word["x1"]),
                float(word["bottom"]),
            )
            existing_bbox = row_bboxes[column_index]
            if existing_bbox is None:
                row_bboxes[column_index] = word_bbox
            else:
                row_bboxes[column_index] = (
                    min(existing_bbox[0], word_bbox[0]),
                    min(existing_bbox[1], word_bbox[1]),
                    max(existing_bbox[2], word_bbox[2]),
                    max(existing_bbox[3], word_bbox[3]),
                )
        populated_indices = [index for index, cell in enumerate(row_cells) if cell.strip()]
        if len(populated_indices) >= 2 and row_width >= 4:
            rightmost_index = populated_indices[-1]
            interior_indices = [index for index in populated_indices if 0 < index < rightmost_index]
            if (
                rightmost_index == row_width - 1
                and _is_numeric_like(row_cells[rightmost_index])
                and interior_indices
                and not any(_is_numeric_like(row_cells[index]) for index in interior_indices)
            ):
                row_cells[0] = " ".join(
                    cell
                    for cell in [row_cells[0], *(row_cells[index] for index in interior_indices)]
                    if cell.strip()
                ).strip()
                for index in interior_indices:
                    if row_bboxes[index] is not None:
                        existing_bbox = row_bboxes[0]
                        moved_bbox = row_bboxes[index]
                        if existing_bbox is None:
                            row_bboxes[0] = moved_bbox
                        elif moved_bbox is not None:
                            row_bboxes[0] = (
                                min(existing_bbox[0], moved_bbox[0]),
                                min(existing_bbox[1], moved_bbox[1]),
                                max(existing_bbox[2], moved_bbox[2]),
                                max(existing_bbox[3], moved_bbox[3]),
                            )
                    row_cells[index] = ""
                    row_bboxes[index] = None
        rows.append(row_cells)
        bbox_rows.append(row_bboxes)
    normalized_rows = _normalize_rows(rows)
    max_cols = max((len(row) for row in normalized_rows), default=0)
    normalized_bboxes = [row + [None] * (max_cols - len(row)) for row in bbox_rows]
    return (normalized_rows, normalized_bboxes)


def _build_rows_from_line_segment(
    lines: list[dict[str, object]],
    page_chars: list[dict[str, object]] | None = None,
) -> list[list[str]]:
    """Convert a line segment into a row-major grid using x-position anchors."""
    rows, _ = build_row_grid_from_lines(lines, page_chars=page_chars)
    return rows


def build_text_layout_candidates(
    *,
    page_num: int,
    page_text: str,
    words: list[dict[str, object]],
    chars: list[dict[str, object]] | None = None,
    rule_segments: list[tuple[float, float, float, float]] | None = None,
    layout_source: str = "text_positions",
    paper_page_furniture: PaperPageFurniture | None = None,
) -> list[DetectedTableCandidate]:
    """Build scored candidates from page word and char geometry."""
    working_words, word_mask_metadata = filter_positioned_items_for_page_furniture(
        words,
        paper_page_furniture,
        page_num=page_num,
    )
    page_chars, char_mask_metadata = filter_positioned_items_for_page_furniture(
        chars or [],
        paper_page_furniture,
        page_num=page_num,
    )
    lines = build_word_lines(working_words)

    caption_indices = [index for index, line in enumerate(lines) if TABLE_CAPTION_PATTERN.search(str(line["text"]))]
    candidates: list[DetectedTableCandidate] = []
    segments: list[dict[str, object]] = []
    for segment_index, start_index in enumerate(caption_indices):
        end_index = caption_indices[segment_index + 1] if segment_index + 1 < len(caption_indices) else len(lines)
        segment_lines = lines[start_index:end_index]
        if len(segment_lines) < 3:
            continue
        first_caption_text = str(segment_lines[0]["text"]).strip()
        first_caption_metadata = _table_caption_metadata(first_caption_text)
        caption_parts = [
            str(first_caption_metadata["caption"])
            if first_caption_metadata is not None
            else first_caption_text
        ]
        content_start = 1
        while content_start < len(segment_lines) and not SENTENCE_TERMINAL_PATTERN.search(" ".join(caption_parts)):
            next_line_text = str(segment_lines[content_start]["text"]).strip()
            next_line_word_count = len(segment_lines[content_start]["words"])
            if (
                len(next_line_text) >= 4
                and (
                    next_line_word_count <= 2
                    or (
                        next_line_word_count <= 12
                        and next_line_text[:1].islower()
                        and SENTENCE_TERMINAL_PATTERN.search(next_line_text)
                    )
                )
                and not _is_numeric_like(next_line_text)
            ):
                caption_parts.append(next_line_text)
                content_start += 1
                continue
            break
        content_lines = segment_lines[content_start:]
        rows, cell_bboxes = build_row_grid_from_lines(content_lines, page_chars=page_chars)
        if not rows:
            continue
        initial_row_bounds = [(float(line["top"]), float(line["bottom"])) for line in content_lines]
        trimmed = trim_trailing_non_table_rows(
            rows,
            cell_bboxes=cell_bboxes,
            row_bounds=initial_row_bounds,
        )
        rows = trimmed.raw_rows
        cell_bboxes = trimmed.cell_bboxes
        content_lines = content_lines[: len(rows)]
        if not rows or not content_lines:
            continue
        caption = "\n".join(caption_parts)
        caption_signal = first_caption_metadata is not None
        strong_geometry = _has_strong_uncaptioned_table_geometry(rows)
        if not caption_signal and not strong_geometry:
            continue
        left = min(float(word["x0"]) for line in content_lines for word in line["words"])
        right = max(float(word["x1"]) for line in content_lines for word in line["words"])
        bbox = (
            left,
            float(segment_lines[0]["top"]),
            right,
            max(float(line["bottom"]) for line in content_lines),
        )
        table_bbox_cluster_ids = page_furniture_cluster_ids_for_bbox(
            paper_page_furniture,
            page_num=page_num,
            bbox=bbox,
            min_overlap_fraction=0.0,
        )
        segments.append(
            {
                "caption": caption if caption_signal else None,
                "caption_signal": caption_signal,
                "strong_uncaptioned_table_geometry": strong_geometry,
                "content_lines": content_lines,
                "rows": rows,
                "cell_bboxes": cell_bboxes,
                "row_bounds": trimmed.row_bounds,
                "bbox": bbox,
                "trailing_non_table_rows": trimmed.metadata,
                "page_furniture_overlap": {
                    "source_artifact": "paper_page_furniture.json",
                    "has_overlap": bool(table_bbox_cluster_ids),
                    "table_bbox_cluster_ids": table_bbox_cluster_ids,
                },
                "page_furniture_mask": {
                    key: value
                    for key, value in {
                        "word_items": word_mask_metadata,
                        "char_items": char_mask_metadata,
                    }.items()
                    if value is not None
                },
            }
        )
    for table_index, segment in enumerate(segments):
        raw_rows = segment.get("rows", [])
        if not isinstance(raw_rows, list):
            continue
        table_rows = _normalize_rows(raw_rows)
        bbox = segment["bbox"]
        candidates.append(
            score_candidate(
                DetectedTableCandidate(
                    page_num=page_num,
                    table_index=table_index,
                    bbox=bbox,
                    raw_rows=table_rows,
                    caption=segment["caption"],
                    page_text=page_text,
                    metadata={
                        "is_rectangular": _is_rectangular(table_rows),
                        "layout_source": layout_source,
                        "table_cells": segment.get("cell_bboxes", []),
                        "row_bounds": segment["row_bounds"],
                        "horizontal_rules": detect_horizontal_rules(rule_segments, bbox),
                        "caption_signal": segment["caption_signal"],
                        "strong_uncaptioned_table_geometry": segment["strong_uncaptioned_table_geometry"],
                        "trailing_non_table_rows": segment["trailing_non_table_rows"],
                        "page_furniture_overlap": segment["page_furniture_overlap"],
                        "page_furniture_mask": segment["page_furniture_mask"],
                    },
                )
            )
        )
    return candidates
