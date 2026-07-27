"""Collect positioned page text for page-furniture detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from table1_parser.schemas import (
    PageFurnitureCluster,
    PageFurnitureRegion,
    PageFurnitureRuleRegion,
    PageFurnitureTextObservation,
    PaperPageScope,
    PaperPageFurniture,
    PaperPositionedDocument,
)


_PAGE_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9.])\d+(?![A-Za-z0-9.])")
_CURRENT_TOTAL_PAGE_TEMPLATE_RE = re.compile(
    r"(?<![A-Za-z0-9.])<page_num>\s*(?:of|/)\s*(\d+)(?![A-Za-z0-9.])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _PageNumberSubstitutionCandidate:
    """One non-operative integer-slot proposal from a positioned source line."""

    observation_id: str
    page_num: int
    slot_index: int
    slot_value: int
    ordinary_matching_key: str
    template_key: str
    relative_bbox: tuple[float, float, float, float]
    orientation: str | None


@dataclass(frozen=True)
class _PageNumberSubstitutionCandidateGroup:
    """Numeric-slot candidates with positioned recurrence and one page offset."""

    template_key: str
    orientation: str | None
    common_relative_bbox: tuple[float, float, float, float]
    candidates: tuple[_PageNumberSubstitutionCandidate, ...]
    page_offset: int


def normalize_page_furniture_text(raw_text: str) -> str:
    """Normalize whitespace while preserving ordinary page-furniture text."""
    return " ".join(raw_text.split())


def collect_page_furniture_text_observations(
    pdf_path: str,
    *,
    paper_positioned_document: PaperPositionedDocument | None = None,
) -> tuple[
    list[PageFurnitureTextObservation],
    list[_PageNumberSubstitutionCandidateGroup],
    int,
]:
    """Collect observations, grouped non-operative numeric slots, and page count."""
    from table1_parser.context.paper_positioned_document import (
        build_paper_positioned_document,
    )

    positioned_document = paper_positioned_document or build_paper_positioned_document(
        pdf_path
    )

    observations: list[PageFurnitureTextObservation] = []
    page_number_candidates: list[_PageNumberSubstitutionCandidate] = []
    for page in positioned_document.pages:
        if page.page_width <= 0.0 or page.page_height <= 0.0:
            continue
        for line in page.lines:
            ordinary_matching_key = normalize_page_furniture_text(line.raw_text)
            relative_bbox = (
                line.bbox[0] / page.page_width,
                line.bbox[1] / page.page_height,
                line.bbox[2] / page.page_width,
                line.bbox[3] / page.page_height,
            )
            if not ordinary_matching_key:
                continue
            observations.append(
                PageFurnitureTextObservation(
                    observation_id=line.line_id,
                    page_num=page.page_num,
                    raw_text=line.raw_text,
                    normalized_text=ordinary_matching_key,
                    bbox=line.bbox,
                    relative_bbox=relative_bbox,
                    page_width=page.page_width,
                    page_height=page.page_height,
                    orientation=line.orientation,
                    block_index=line.block_index,
                    line_index=line.line_index,
                    source_artifact="paper_positioned_document.json",
                )
            )
            for slot_index, numeric_token in enumerate(
                _PAGE_NUMBER_TOKEN_RE.finditer(ordinary_matching_key)
            ):
                page_number_candidates.append(
                    _PageNumberSubstitutionCandidate(
                        observation_id=line.line_id,
                        page_num=page.page_num,
                        slot_index=slot_index,
                        slot_value=int(numeric_token.group(0)),
                        ordinary_matching_key=ordinary_matching_key,
                        template_key=(
                            ordinary_matching_key[: numeric_token.start()]
                            + "<page_num>"
                            + ordinary_matching_key[numeric_token.end() :]
                        ),
                        relative_bbox=relative_bbox,
                        orientation=line.orientation,
                    )
                )

    candidate_location_groups: dict[
        tuple[str, str | None],
        list[
            tuple[
                tuple[float, float, float, float],
                list[_PageNumberSubstitutionCandidate],
            ]
        ],
    ] = {}
    for candidate in page_number_candidates:
        position_groups = candidate_location_groups.setdefault(
            (candidate.template_key, candidate.orientation),
            [],
        )
        matching_groups: list[tuple[int, tuple[float, float, float, float]]] = []
        for group_index, (common_bbox, _) in enumerate(position_groups):
            intersection_bbox = (
                max(common_bbox[0], candidate.relative_bbox[0]),
                max(common_bbox[1], candidate.relative_bbox[1]),
                min(common_bbox[2], candidate.relative_bbox[2]),
                min(common_bbox[3], candidate.relative_bbox[3]),
            )
            if (
                intersection_bbox[0] < intersection_bbox[2]
                and intersection_bbox[1] < intersection_bbox[3]
            ):
                matching_groups.append((group_index, intersection_bbox))
        if len(matching_groups) == 1:
            group_index, intersection_bbox = matching_groups[0]
            _, candidate_group = position_groups[group_index]
            candidate_group.append(candidate)
            position_groups[group_index] = (intersection_bbox, candidate_group)
        elif not matching_groups:
            position_groups.append((candidate.relative_bbox, [candidate]))

    page_number_candidate_groups: list[_PageNumberSubstitutionCandidateGroup] = []
    for (template_key, orientation), position_groups in sorted(
        candidate_location_groups.items(),
        key=lambda item: (item[0][0], item[0][1] or ""),
    ):
        for common_bbox, candidate_group in sorted(
            position_groups,
            key=lambda item: item[0],
        ):
            candidate_page_nums = [candidate.page_num for candidate in candidate_group]
            page_nums = set(candidate_page_nums)
            page_offsets = {
                candidate.slot_value - candidate.page_num
                for candidate in candidate_group
            }
            all_page_nums = set(range(1, positioned_document.page_count + 1))
            expected_even_page_nums = set(
                range(2, positioned_document.page_count + 1, 2)
            )
            expected_odd_body_page_nums = set(
                range(3, positioned_document.page_count + 1, 2)
            )
            even_page_nums = {page_num for page_num in page_nums if page_num % 2 == 0}
            odd_body_page_nums = {
                page_num for page_num in page_nums if page_num > 1 and page_num % 2 == 1
            }
            has_complete_recurrence = (
                page_nums == all_page_nums
                or (
                    bool(expected_even_page_nums)
                    and even_page_nums == expected_even_page_nums
                )
                or (
                    bool(expected_odd_body_page_nums)
                    and odd_body_page_nums == expected_odd_body_page_nums
                )
            )
            if (
                len(page_nums) < 2
                or len(candidate_page_nums) != len(page_nums)
                or len(page_offsets) != 1
                or not has_complete_recurrence
            ):
                continue
            page_number_candidate_groups.append(
                _PageNumberSubstitutionCandidateGroup(
                    template_key=template_key,
                    orientation=orientation,
                    common_relative_bbox=common_bbox,
                    candidates=tuple(candidate_group),
                    page_offset=next(iter(page_offsets)),
                )
            )
    return observations, page_number_candidate_groups, positioned_document.page_count


def build_paper_page_furniture(
    pdf_path: str,
    *,
    paper_id: str | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
    min_pages: int = 3,
) -> PaperPageFurniture:
    """Build the paper-level page-furniture artifact."""
    if paper_positioned_document is None:
        from table1_parser.context.paper_positioned_document import (
            build_paper_positioned_document,
        )

        paper_positioned_document = build_paper_positioned_document(pdf_path)
    observations, page_number_candidate_groups, page_count = (
        collect_page_furniture_text_observations(
            pdf_path,
            paper_positioned_document=paper_positioned_document,
        )
    )
    reported_total: int | None = None
    printed_page_offset: int | None = None
    terminal_pdf_page_num: int | None = None
    source_observation_ids: list[str] = []
    for candidate_group in page_number_candidate_groups:
        counter_match = _CURRENT_TOTAL_PAGE_TEMPLATE_RE.search(
            candidate_group.template_key
        )
        if counter_match is None:
            continue
        candidate_total = int(counter_match.group(1))
        candidate_terminal = candidate_total - candidate_group.page_offset
        if not 1 <= candidate_terminal <= page_count or not any(
            candidate.slot_value == candidate_total
            for candidate in candidate_group.candidates
        ):
            continue
        reported_total = candidate_total
        printed_page_offset = candidate_group.page_offset
        terminal_pdf_page_num = candidate_terminal
        source_observation_ids = [
            candidate.observation_id for candidate in candidate_group.candidates
        ]
        break
    detected = terminal_pdf_page_num is not None
    included_terminal = (
        terminal_pdf_page_num if terminal_pdf_page_num is not None else page_count
    )
    page_scope = PaperPageScope(
        physical_page_count=page_count,
        detection_status="detected" if detected else "unknown",
        reported_paper_page_total=reported_total,
        terminal_pdf_page_num=terminal_pdf_page_num,
        included_page_nums=list(range(1, included_terminal + 1)),
        excluded_trailing_page_nums=(
            list(range(included_terminal + 1, page_count + 1)) if detected else []
        ),
        printed_page_offset=printed_page_offset,
        source_observation_ids=source_observation_ids,
        diagnostics=[
            "accepted_recurrent_current_total_page_furniture"
            if detected
            else "no_accepted_current_total_page_counter"
        ],
    )
    included_page_nums = set(page_scope.included_page_nums)
    clusters, ignored_regions = cluster_page_furniture_observations(
        [
            observation
            for observation in observations
            if observation.page_num in included_page_nums
        ],
        page_number_candidate_groups=page_number_candidate_groups,
        page_count=len(included_page_nums) or None,
    )

    min_rule_page_fraction = 0.8
    rule_groups: dict[
        tuple[str, tuple[float, float, float, float]],
        dict[
            int,
            tuple[
                tuple[float, float, float, float],
                tuple[float, float, float, float],
            ],
        ],
    ] = {}
    for page in paper_positioned_document.pages:
        if page.page_num not in included_page_nums:
            continue
        for segment in page.stroked_rule_segments:
            left = min(float(segment[0]), float(segment[2]))
            top = min(float(segment[1]), float(segment[3]))
            right = max(float(segment[0]), float(segment[2]))
            bottom = max(float(segment[1]), float(segment[3]))
            width = right - left
            height = bottom - top
            if width <= height:
                continue
            bbox = (left, top, right, bottom)
            relative_bbox = (
                left / page.page_width,
                top / page.page_height,
                right / page.page_width,
                bottom / page.page_height,
            )
            rule_groups.setdefault(("horizontal", bbox), {})[page.page_num] = (
                bbox,
                relative_bbox,
            )

    ignored_rule_regions: list[PageFurnitureRuleRegion] = []
    rule_cluster_count = 0
    for (rule_orientation, _), observations_by_page in sorted(rule_groups.items()):
        recurrence_page_nums = sorted(observations_by_page)
        page_fraction = (
            len(recurrence_page_nums) / len(included_page_nums)
            if included_page_nums
            else 0.0
        )
        if (
            len(recurrence_page_nums) < min_pages
            or page_fraction < min_rule_page_fraction
        ):
            continue
        rule_cluster_count += 1
        rule_cluster_id = f"page-furniture-rule-{rule_cluster_count}"
        confidence = round(min(0.99, 0.5 + page_fraction * 0.5), 3)
        recurrence_basis = [
            "stroked_horizontal_rule",
            "exact_absolute_bbox",
            f"orientation={rule_orientation}",
            f"min_pages={min_pages}",
            f"min_page_fraction={min_rule_page_fraction:.2f}",
        ]
        for page_num in recurrence_page_nums:
            bbox, relative_bbox = observations_by_page[page_num]
            ignored_rule_regions.append(
                PageFurnitureRuleRegion(
                    region_id=f"{rule_cluster_id}-page-{page_num}",
                    rule_cluster_id=rule_cluster_id,
                    page_num=page_num,
                    bbox=bbox,
                    relative_bbox=relative_bbox,
                    recurrence_page_nums=recurrence_page_nums,
                    page_fraction=round(page_fraction, 3),
                    confidence=confidence,
                    recurrence_basis=recurrence_basis,
                )
            )
    diagnostics = []
    if not observations:
        diagnostics.append("no_page_text_observations")
    elif not clusters:
        diagnostics.append("no_repeated_page_furniture")

    return PaperPageFurniture(
        paper_id=paper_id or Path(pdf_path).stem,
        source_pdf=pdf_path,
        page_scope=page_scope,
        observations=observations,
        clusters=clusters,
        ignored_regions=ignored_regions,
        ignored_rule_regions=ignored_rule_regions,
        metadata={
            "source_artifacts": ["paper_positioned_document.json"],
            "observation_count": len(observations),
            "cluster_count": len(clusters),
            "ignored_region_count": len(ignored_regions),
            "ignored_rule_region_count": len(ignored_rule_regions),
            "page_count": page_count,
            "thresholds": {
                "min_pages": min_pages,
                "min_rule_page_fraction": min_rule_page_fraction,
            },
            "diagnostics": diagnostics,
        },
    )


def cluster_page_furniture_observations(
    observations: list[PageFurnitureTextObservation],
    *,
    page_number_candidate_groups: list[_PageNumberSubstitutionCandidateGroup]
    | None = None,
    page_count: int | None = None,
) -> tuple[list[PageFurnitureCluster], list[PageFurnitureRegion]]:
    """Cluster repeated page text by content, overlapping position, and orientation."""
    if not observations:
        return [], []

    observed_page_count = max(observation.page_num for observation in observations)
    total_pages = max(page_count or observed_page_count, observed_page_count)
    if total_pages <= 0:
        return [], []
    all_page_nums = set(range(1, total_pages + 1))
    expected_even_page_nums = set(range(2, total_pages + 1, 2))
    expected_odd_body_page_nums = set(range(3, total_pages + 1, 2))

    location_groups: dict[
        tuple[str, str | None, str],
        list[
            tuple[
                tuple[float, float, float, float],
                list[PageFurnitureTextObservation],
            ]
        ],
    ] = {}
    matching_observations = [
        (observation.normalized_text, observation, "ordinary_text")
        for observation in observations
        if observation.normalized_text
    ]
    observations_by_id = {
        observation.observation_id: observation for observation in observations
    }
    for candidate_group in page_number_candidate_groups or []:
        for candidate in candidate_group.candidates:
            observation = observations_by_id.get(candidate.observation_id)
            if (
                observation is None
                or observation.normalized_text != candidate.ordinary_matching_key
            ):
                continue
            matching_observations.append(
                (
                    candidate_group.template_key,
                    observation,
                    "accepted_page_number_template",
                )
            )

    for matching_key, observation, matching_basis in matching_observations:
        position_groups = location_groups.setdefault(
            (matching_key, observation.orientation, matching_basis),
            [],
        )
        matching_groups: list[tuple[int, tuple[float, float, float, float]]] = []
        for group_index, (common_bbox, _) in enumerate(position_groups):
            intersection_bbox = (
                max(common_bbox[0], observation.relative_bbox[0]),
                max(common_bbox[1], observation.relative_bbox[1]),
                min(common_bbox[2], observation.relative_bbox[2]),
                min(common_bbox[3], observation.relative_bbox[3]),
            )
            if (
                intersection_bbox[0] < intersection_bbox[2]
                and intersection_bbox[1] < intersection_bbox[3]
            ):
                matching_groups.append((group_index, intersection_bbox))
        if len(matching_groups) == 1:
            group_index, intersection_bbox = matching_groups[0]
            _, text_group = position_groups[group_index]
            text_group.append(observation)
            position_groups[group_index] = (intersection_bbox, text_group)
        else:
            position_groups.append((observation.relative_bbox, [observation]))

    clusters: list[PageFurnitureCluster] = []
    regions: list[PageFurnitureRegion] = []

    for (normalized_text, orientation, matching_basis), position_groups in sorted(
        location_groups.items(),
        key=lambda item: (item[0][0], item[0][1] or "", item[0][2]),
    ):
        for _, text_group in sorted(position_groups, key=lambda item: item[0]):
            observed_page_nums = {observation.page_num for observation in text_group}
            accepted_scopes: list[
                tuple[str, set[int], list[PageFurnitureTextObservation]]
            ] = []
            if observed_page_nums == all_page_nums:
                accepted_scopes.append(("all_pages", all_page_nums, text_group))
            else:
                even_text_group = [
                    observation
                    for observation in text_group
                    if observation.page_num % 2 == 0
                ]
                if (
                    expected_even_page_nums
                    and {observation.page_num for observation in even_text_group}
                    == expected_even_page_nums
                ):
                    accepted_scopes.append(
                        ("even_pages", expected_even_page_nums, even_text_group)
                    )

                odd_body_text_group = [
                    observation
                    for observation in text_group
                    if observation.page_num > 1 and observation.page_num % 2 == 1
                ]
                if (
                    expected_odd_body_page_nums
                    and {observation.page_num for observation in odd_body_text_group}
                    == expected_odd_body_page_nums
                ):
                    accepted_scopes.append(
                        (
                            "odd_pages",
                            expected_odd_body_page_nums,
                            odd_body_text_group,
                        )
                    )

            for recurrence_scope, scope_page_nums, scoped_text_group in accepted_scopes:
                page_nums = sorted(scope_page_nums)
                page_fraction = len(page_nums) / total_pages
                cluster_id = f"page-furniture-cluster-{len(clusters) + 1}"
                representative_bbox = tuple(
                    sum(observation.bbox[index] for observation in scoped_text_group)
                    / len(scoped_text_group)
                    for index in range(4)
                )
                representative_relative_bbox = tuple(
                    sum(
                        observation.relative_bbox[index]
                        for observation in scoped_text_group
                    )
                    / len(scoped_text_group)
                    for index in range(4)
                )
                confidence = round(min(0.99, 0.5 + (page_fraction * 0.5)), 3)
                recurrence_basis = [
                    matching_basis,
                    "shared_relative_bbox_intersection",
                    f"complete_{recurrence_scope}_coverage",
                ]
                if orientation is not None:
                    recurrence_basis.append(f"orientation={orientation}")
                clusters.append(
                    PageFurnitureCluster(
                        cluster_id=cluster_id,
                        normalized_text_key=normalized_text,
                        representative_text=scoped_text_group[0].raw_text,
                        observation_ids=[
                            observation.observation_id
                            for observation in scoped_text_group
                        ],
                        page_nums=page_nums,
                        occurrence_count=len(scoped_text_group),
                        page_fraction=round(page_fraction, 3),
                        recurrence_scope=recurrence_scope,
                        scope_page_count=len(scope_page_nums),
                        scope_page_fraction=1.0,
                        representative_bbox=representative_bbox,
                        representative_relative_bbox=representative_relative_bbox,
                        recurrence_basis=recurrence_basis,
                        confidence=confidence,
                    )
                )

                for page_num in page_nums:
                    page_observations = [
                        observation
                        for observation in scoped_text_group
                        if observation.page_num == page_num
                    ]
                    regions.append(
                        PageFurnitureRegion(
                            region_id=f"{cluster_id}-page-{page_num}",
                            cluster_id=cluster_id,
                            page_num=page_num,
                            bbox=(
                                min(
                                    observation.bbox[0]
                                    for observation in page_observations
                                ),
                                min(
                                    observation.bbox[1]
                                    for observation in page_observations
                                ),
                                max(
                                    observation.bbox[2]
                                    for observation in page_observations
                                ),
                                max(
                                    observation.bbox[3]
                                    for observation in page_observations
                                ),
                            ),
                            relative_bbox=(
                                min(
                                    observation.relative_bbox[0]
                                    for observation in page_observations
                                ),
                                min(
                                    observation.relative_bbox[1]
                                    for observation in page_observations
                                ),
                                max(
                                    observation.relative_bbox[2]
                                    for observation in page_observations
                                ),
                                max(
                                    observation.relative_bbox[3]
                                    for observation in page_observations
                                ),
                            ),
                            source_observation_ids=[
                                observation.observation_id
                                for observation in page_observations
                            ],
                            confidence=confidence,
                        )
                    )

    return clusters, regions


def paper_page_furniture_to_payload(furniture: PaperPageFurniture) -> dict[str, object]:
    """Serialize paper page furniture as a JSON-friendly record."""
    return furniture.model_dump(mode="json")
