"""Selection logic for scored table candidates."""

from __future__ import annotations

from table1_parser.extract.table_detector import DetectedTableCandidate


def _candidate_key(candidate: DetectedTableCandidate) -> tuple[int, int]:
    """Return a stable candidate key for deduplication."""
    return (candidate.page_num, candidate.table_index)


def select_top_candidates(
    candidates: list[DetectedTableCandidate],
    max_candidates: int,
    confidence_threshold: float,
) -> list[DetectedTableCandidate]:
    """Return extracted candidates in stable paper order after plausibility checks."""
    del max_candidates, confidence_threshold
    selected: dict[tuple[int, int], DetectedTableCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda candidate: (candidate.page_num, candidate.table_index, -candidate.score),
    ):
        key = _candidate_key(candidate)
        existing = selected.get(key)
        if existing is None or candidate.score > existing.score:
            selected[key] = candidate

    ordered_candidates = sorted(
        selected.values(),
        key=lambda candidate: (candidate.page_num, candidate.table_index),
    )
    candidate_table_numbers: list[int | None] = []
    for candidate in ordered_candidates:
        signals = candidate.metadata.get("signals")
        number_value = candidate.metadata.get("table_number")
        if number_value is None and isinstance(signals, dict):
            number_value = signals.get("caption_table_number")
        table_number: int | None = None
        if isinstance(number_value, int) and not isinstance(number_value, bool):
            table_number = number_value if number_value > 0 else None
        elif isinstance(number_value, float) and number_value.is_integer():
            parsed_number = int(number_value)
            table_number = parsed_number if parsed_number > 0 else None
        elif isinstance(number_value, str) and number_value.isdigit():
            parsed_number = int(number_value)
            table_number = parsed_number if parsed_number > 0 else None
        candidate_table_numbers.append(table_number)

    numbered_positions = [
        (index, table_number)
        for index, table_number in enumerate(candidate_table_numbers)
        if table_number is not None
    ]
    if not numbered_positions:
        return ordered_candidates

    first_table_one_indices = [
        index
        for index, table_number in numbered_positions
        if table_number == 1
    ]
    first_table_one_index = min(first_table_one_indices) if first_table_one_indices else None

    filtered_candidates: list[DetectedTableCandidate] = []
    for index, candidate in enumerate(ordered_candidates):
        if candidate_table_numbers[index] is not None or candidate.caption:
            filtered_candidates.append(candidate)
            continue

        previous_numbered: tuple[int, int] | None = None
        next_numbered: tuple[int, int] | None = None
        for numbered_index, table_number in numbered_positions:
            if numbered_index < index:
                previous_numbered = (numbered_index, table_number)
            elif numbered_index > index:
                next_numbered = (numbered_index, table_number)
                break

        signals = candidate.metadata.get("signals")
        signal_values = signals if isinstance(signals, dict) else {}
        try:
            first_column_text_ratio = float(signal_values.get("first_column_text_ratio", 0.0))
        except (TypeError, ValueError):
            first_column_text_ratio = 0.0
        try:
            later_column_numeric_ratio = float(signal_values.get("later_column_numeric_ratio", 0.0))
        except (TypeError, ValueError):
            later_column_numeric_ratio = 0.0
        value_anchors = candidate.metadata.get("value_matrix_column_anchors")
        has_value_matrix_anchors = isinstance(value_anchors, list) and len(value_anchors) >= 3
        column_count = max((len(row) for row in candidate.raw_rows), default=0)
        has_strong_unnumbered_geometry = has_value_matrix_anchors or (
            len(candidate.raw_rows) >= 4
            and column_count >= 3
            and first_column_text_ratio >= 0.6
            and later_column_numeric_ratio >= 0.5
        )
        possible_continuation_geometry = False
        if previous_numbered is not None:
            previous_candidate = ordered_candidates[previous_numbered[0]]
            possible_continuation_geometry = (
                0 <= candidate.page_num - previous_candidate.page_num <= 1
                and len(candidate.raw_rows) >= 3
                and column_count >= 2
                and first_column_text_ratio >= 0.6
                and later_column_numeric_ratio >= 0.5
            )
        if has_strong_unnumbered_geometry or possible_continuation_geometry:
            filtered_candidates.append(candidate)
            continue

        suppress_candidate = first_table_one_index is not None and index < first_table_one_index
        if not suppress_candidate:
            suppress_candidate = (
                previous_numbered is not None
                and next_numbered is not None
                and next_numbered[1] == previous_numbered[1] + 1
            )
        if not suppress_candidate:
            filtered_candidates.append(candidate)

    return filtered_candidates
