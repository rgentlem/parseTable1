"""Paper-level candidate variable inventory building."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from table1_parser.extract.table_detector import TABLE_IDENTIFIER_PATTERN
from table1_parser.normalize.text_normalizer import normalize_label_text
from table1_parser.schemas import (
    PaperSection,
    PaperVariableInventory,
    TableDefinition,
    VariableCandidate,
    VariableMention,
)
from table1_parser.text_cleaning import clean_text


TABLE_NUMBER_PATTERN = re.compile(
    rf"\bTable\s+(?P<table_number>{TABLE_IDENTIFIER_PATTERN.pattern})\b",
    re.IGNORECASE,
)
PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")
TRAILING_SUMMARY_PATTERN = re.compile(
    r"(?:,?\s*(?:n\s*\(%\)|no\.\s*\(%\)|mean\s*\(sd\)|mean\s*\(se\)|median\s*\(iqr\)|median\s*\(interquartile range\)|weighted mean\s*\(se\)))+$",
    re.IGNORECASE,
)
TRAILING_GROUP_PATTERN = re.compile(r"\s+groups?$", re.IGNORECASE)
TRAILING_QUANTILE_PATTERN = re.compile(r"\s+(?:quintiles?|quartiles?)$", re.IGNORECASE)
MODEL_LABEL_PATTERN = re.compile(r"^model[\s_-]*\d+$", re.IGNORECASE)
REFERENCE_FLAG_PATTERN = re.compile(r"\b(reference)\b", re.IGNORECASE)
TABLE_CONTINUED_PATTERN = re.compile(
    rf"^table\s+{TABLE_IDENTIFIER_PATTERN.pattern}.*continued",
    re.IGNORECASE,
)
QUANTILE_LEVEL_PATTERN = re.compile(r"^(?:q\d+|quartile[\s_-]*\d+|quintile[\s_-]*\d+)$", re.IGNORECASE)
RANGE_BIN_PATTERN = re.compile(
    r"^(?:[<>]=?\s*)?\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?\+?)?$|^\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\+?$",
    re.IGNORECASE,
)

_SECTION_PRIORITY = {
    "abstract_like": 1.0,
    "methods_like": 0.95,
    "conclusion_like": 0.9,
    "discussion_like": 0.85,
    "results_like": 0.65,
    "other": 0.35,
    "references_like": 0.0,
}
_PRIORITY_TEXT_ROLES = {"abstract_like", "methods_like", "conclusion_like", "discussion_like"}
_SOURCE_PRIORITY = {
    "text_based": 5,
    "table_variable_name": 4,
    "table_variable_label": 3,
    "table_caption": 2,
    "table_title": 2,
    "table_grouping_label": 1,
}
_PARENT_LEVEL_HINTS = {
    "sex": {"male", "female"},
    "gender": {"male", "female"},
    "smoking status": {"never", "former", "current"},
    "drinking status": {"never", "former", "current"},
    "marital status": {"married", "living", "living with partner", "single", "divorced", "separated", "widowed"},
    "race": {"mexican", "non hispanic", "other", "other multiracial", "white", "black"},
    "educational level": {"less", "college", "high", "less than high school", "high school", "college or above"},
}
_CANONICAL_ALIAS_MAP = {
    "Educational": "Educational level",
    "Marital": "Marital status",
    "Smoking": "Smoking status",
    "Drinking": "Drinking status",
}
_ADJUSTMENT_LIST_TOKENS = {
    "age",
    "bmi",
    "diabetes",
    "drinking",
    "educational",
    "education",
    "gender",
    "hypertension",
    "marital",
    "physical",
    "pir",
    "race",
    "sex",
    "smoking",
    "status",
}


@dataclass(frozen=True, slots=True)
class _TableClassificationContext:
    """Table-local context for deciding whether a label looks like a variable or a level."""

    parent_keys: set[str]
    level_keys: set[str]


@dataclass(frozen=True, slots=True)
class _SeedTerm:
    """Internal search term used to build text-based mentions."""

    raw_label: str
    normalized_label: str
    canonical_label: str
    canonical_key: str
    table_id: str
    table_index: int
    table_label: str | None
    canonical_label_source: str


def build_paper_variable_inventory(
    paper_id: str,
    sections: list[PaperSection],
    table_definitions: list[TableDefinition],
    *,
    entity_table_ids: set[str],
    resolved_table_numbers_by_id: dict[str, str] | None = None,
) -> PaperVariableInventory:
    """Build a conservative paper-level inventory from sections and table definitions."""
    mention_counter = 0
    mentions: list[VariableMention] = []
    seeds: list[_SeedTerm] = []
    seen_mentions: set[tuple[object, ...]] = set()
    table_contexts = _build_table_classification_contexts(table_definitions)
    entity_table_contexts = {
        key: context
        for key, context in table_contexts.items()
        if key[0] in entity_table_ids
    }
    paper_parent_keys = set().union(*(context.parent_keys for context in entity_table_contexts.values())) if entity_table_contexts else set()
    paper_level_keys = set().union(*(context.level_keys for context in entity_table_contexts.values())) if entity_table_contexts else set()

    for table_index, definition in enumerate(table_definitions):
        if definition.table_id not in entity_table_ids:
            continue
        table_key = (definition.table_id, table_index)
        table_context = table_contexts[table_key]
        resolved_table_number = (resolved_table_numbers_by_id or {}).get(
            definition.table_id
        )
        table_label = (
            f"Table {resolved_table_number}"
            if isinstance(resolved_table_number, str)
            and TABLE_IDENTIFIER_PATTERN.fullmatch(resolved_table_number) is not None
            else None
        )
        table_seeds: list[_SeedTerm] = []
        if table_label is None:
            for text in (definition.title, definition.caption):
                match = TABLE_NUMBER_PATTERN.search(text or "")
                if match is not None:
                    table_label = f"Table {match.group('table_number')}"
                    break

        for variable in definition.variables:
            variable_label = clean_text(variable.variable_label)
            variable_name = clean_text(variable.variable_name)
            canonical_from_name = _canonicalize_variable_label(variable_name)
            canonical_from_label = _canonicalize_variable_label(variable_label)
            canonical_label = canonical_from_name or canonical_from_label
            canonical_key = _candidate_key(canonical_label)
            canonical_label_source = "deterministic_variable_name" if canonical_from_name else "reduced_label"

            for raw_label, source_type in (
                (variable_label, "table_variable_label"),
                (variable_name, "table_variable_name"),
            ):
                if not raw_label:
                    continue
                mention_role = _classify_mention(
                    raw_label,
                    canonical_label,
                    table_context,
                    paper_parent_keys,
                    paper_level_keys,
                )
                mention_counter = _append_mention(
                    mentions=mentions,
                    seen_mentions=seen_mentions,
                    mention_counter=mention_counter,
                    raw_label=raw_label,
                    normalized_label=_normalized_label(raw_label),
                    source_type=source_type,
                    mention_role=mention_role,
                    canonical_label=canonical_label or None,
                    table_id=definition.table_id,
                    table_index=table_index,
                    table_label=table_label,
                    priority_weight=0.85 if source_type == "table_variable_name" else 0.8,
                    confidence=variable.confidence if variable.confidence is not None else (0.82 if source_type == "table_variable_name" else 0.8),
                )
                if canonical_key and mention_role in {"variable", "unknown"}:
                    table_seeds.append(
                        _SeedTerm(
                            raw_label=raw_label,
                            normalized_label=_normalized_label(raw_label),
                            canonical_label=canonical_label,
                            canonical_key=canonical_key,
                            table_id=definition.table_id,
                            table_index=table_index,
                            table_label=table_label,
                            canonical_label_source=canonical_label_source,
                        )
                    )
                    if clean_text(canonical_label).lower() != clean_text(raw_label).lower():
                        table_seeds.append(
                            _SeedTerm(
                                raw_label=canonical_label,
                                normalized_label=_normalized_label(canonical_label),
                                canonical_label=canonical_label,
                                canonical_key=canonical_key,
                                table_id=definition.table_id,
                                table_index=table_index,
                                table_label=table_label,
                                canonical_label_source=canonical_label_source,
                            )
                        )

        for grouping_term in (
            clean_text(definition.column_definition.grouping_name or ""),
            clean_text(definition.column_definition.grouping_label or ""),
        ):
            if not grouping_term:
                continue
            canonical_label = _canonicalize_variable_label(grouping_term)
            canonical_key = _candidate_key(canonical_label)
            mention_role = _classify_mention(
                grouping_term,
                canonical_label,
                table_context,
                paper_parent_keys,
                paper_level_keys,
            )
            mention_counter = _append_mention(
                mentions=mentions,
                seen_mentions=seen_mentions,
                mention_counter=mention_counter,
                raw_label=grouping_term,
                normalized_label=_normalized_label(grouping_term),
                source_type="table_grouping_label",
                mention_role=mention_role,
                canonical_label=canonical_label or None,
                table_id=definition.table_id,
                table_index=table_index,
                table_label=table_label,
                priority_weight=0.7,
                confidence=definition.column_definition.confidence if definition.column_definition.confidence is not None else 0.72,
            )
            if canonical_key and mention_role in {"variable", "unknown"}:
                table_seeds.append(
                    _SeedTerm(
                        raw_label=grouping_term,
                        normalized_label=_normalized_label(grouping_term),
                        canonical_label=canonical_label,
                        canonical_key=canonical_key,
                        table_id=definition.table_id,
                        table_index=table_index,
                        table_label=table_label,
                        canonical_label_source="reduced_grouping_label",
                    )
                )
                if clean_text(canonical_label).lower() != clean_text(grouping_term).lower():
                    table_seeds.append(
                        _SeedTerm(
                            raw_label=canonical_label,
                            normalized_label=_normalized_label(canonical_label),
                            canonical_label=canonical_label,
                            canonical_key=canonical_key,
                            table_id=definition.table_id,
                            table_index=table_index,
                            table_label=table_label,
                            canonical_label_source="reduced_grouping_label",
                        )
                    )

        unique_table_seeds: dict[tuple[str, str], _SeedTerm] = {}
        for seed in table_seeds:
            unique_table_seeds.setdefault((seed.canonical_key, seed.normalized_label.lower()), seed)

        for source_text, source_type in (
            (clean_text(definition.title or ""), "table_title"),
            (clean_text(definition.caption or ""), "table_caption"),
        ):
            if not source_text:
                continue
            normalized_source_text = _normalized_label(source_text).lower()
            for seed in unique_table_seeds.values():
                if not seed.normalized_label or not _term_in_normalized_text(seed.normalized_label.lower(), normalized_source_text):
                    continue
                mention_counter = _append_mention(
                    mentions=mentions,
                    seen_mentions=seen_mentions,
                    mention_counter=mention_counter,
                    raw_label=seed.raw_label,
                    normalized_label=seed.normalized_label,
                    source_type=source_type,
                    mention_role="variable",
                    canonical_label=seed.canonical_label,
                    evidence_text=source_text,
                    table_id=definition.table_id,
                    table_index=table_index,
                    table_label=table_label,
                    priority_weight=0.72 if source_type == "table_caption" else 0.68,
                    confidence=0.76 if source_type == "table_caption" else 0.72,
                )

        seeds.extend(unique_table_seeds.values())

    unique_seeds: dict[tuple[str, str], _SeedTerm] = {}
    for seed in seeds:
        if seed.canonical_key and seed.normalized_label:
            unique_seeds.setdefault((seed.canonical_key, seed.normalized_label.lower()), seed)

    for section in sections:
        if section.role_hint == "references_like":
            continue
        paragraphs = (
            [chunk for chunk in (clean_text(part) for part in PARAGRAPH_SPLIT_PATTERN.split(section.content)) if chunk]
            if section.content
            else []
        )
        for paragraph_index, paragraph in enumerate(paragraphs):
            normalized_paragraph = _normalized_label(paragraph).lower()
            for seed in unique_seeds.values():
                if not seed.normalized_label or not _term_in_normalized_text(seed.normalized_label.lower(), normalized_paragraph):
                    continue
                mention_counter = _append_mention(
                    mentions=mentions,
                    seen_mentions=seen_mentions,
                    mention_counter=mention_counter,
                    raw_label=seed.raw_label,
                    normalized_label=seed.normalized_label,
                    source_type="text_based",
                    mention_role="variable",
                    canonical_label=seed.canonical_label,
                    section_id=section.section_id,
                    heading=section.heading,
                    role_hint=section.role_hint,
                    paragraph_index=paragraph_index,
                    evidence_text=paragraph,
                    priority_weight=_SECTION_PRIORITY.get(section.role_hint, 0.0),
                    confidence=round(min(0.98, 0.45 + 0.5 * _SECTION_PRIORITY.get(section.role_hint, 0.0)), 4),
                )

    candidate_mentions: dict[str, list[VariableMention]] = defaultdict(list)
    excluded_mentions_by_key: dict[str, int] = defaultdict(int)
    for mention in mentions:
        canonical_key = _candidate_key(mention.canonical_label or "")
        if not canonical_key:
            continue
        if mention.mention_role in {"variable", "unknown"}:
            candidate_mentions[canonical_key].append(mention)
        else:
            excluded_mentions_by_key[canonical_key] += 1

    candidates: list[VariableCandidate] = []
    for candidate_index, candidate_key in enumerate(sorted(candidate_mentions.keys())):
        grouped_mentions = candidate_mentions[candidate_key]
        if not grouped_mentions:
            continue
        text_support_count = sum(mention.source_type == "text_based" for mention in grouped_mentions)
        priority_text_support_count = sum(
            mention.source_type == "text_based" and mention.role_hint in _PRIORITY_TEXT_ROLES for mention in grouped_mentions
        )
        table_support_count = sum(mention.source_type != "text_based" for mention in grouped_mentions)
        caption_support_count = sum(mention.source_type in {"table_caption", "table_title"} for mention in grouped_mentions)
        source_types = _unique_preserving_order(mention.source_type for mention in grouped_mentions)
        if not (
            priority_text_support_count > 0
            or "table_variable_name" in source_types
            or len(source_types) >= 2
            or (text_support_count > 0 and table_support_count > 0)
        ):
            continue

        canonical_labels = _unique_preserving_order(mention.canonical_label for mention in grouped_mentions if mention.canonical_label)
        canonical_label = canonical_labels[0] if canonical_labels else grouped_mentions[0].raw_label
        canonical_label_source = (
            "deterministic_variable_name"
            if "table_variable_name" in source_types
            else ("priority_text_support" if priority_text_support_count > 0 else "reduced_label")
        )
        promotion_basis = (
            "priority_text_plus_variable_name"
            if priority_text_support_count > 0 and "table_variable_name" in source_types
            else (
                "priority_text_support"
                if priority_text_support_count > 0
                else ("deterministic_variable_name" if "table_variable_name" in source_types else "multi_source_agreement")
            )
        )
        alternate_labels = _unique_preserving_order(
            mention.raw_label for mention in grouped_mentions if clean_text(mention.raw_label).lower() != clean_text(canonical_label).lower()
        )
        priority_score = round(
            min(1.0, max((mention.priority_weight for mention in grouped_mentions), default=0.0) + 0.04 * max(0, len(grouped_mentions) - 1)),
            4,
        )
        confidence = round(
            min(
                0.99,
                0.38
                + 0.1 * priority_text_support_count
                + 0.06 * text_support_count
                + 0.04 * table_support_count
                + 0.1 * max((mention.priority_weight for mention in grouped_mentions), default=0.0),
            ),
            4,
        )
        candidates.append(
            VariableCandidate(
                candidate_id=f"candidate_{candidate_index}",
                preferred_label=canonical_label,
                canonical_label=canonical_label,
                normalized_label=candidate_key,
                canonical_label_source=canonical_label_source,
                promotion_basis=promotion_basis,
                alternate_labels=alternate_labels,
                supporting_mention_ids=[mention.mention_id for mention in grouped_mentions],
                source_types=source_types,
                section_ids=_unique_preserving_order(mention.section_id for mention in grouped_mentions if mention.section_id),
                section_role_hints=_unique_preserving_order(mention.role_hint for mention in grouped_mentions if mention.role_hint),
                table_ids=_unique_preserving_order(mention.table_id for mention in grouped_mentions if mention.table_id),
                table_indices=_unique_preserving_order(mention.table_index for mention in grouped_mentions if mention.table_index is not None),
                text_support_count=text_support_count,
                table_support_count=table_support_count,
                caption_support_count=caption_support_count,
                filtered_mention_count=excluded_mentions_by_key.get(candidate_key, 0),
                priority_score=priority_score,
                confidence=confidence,
                interpretation_status="merged_conservatively" if len(grouped_mentions) > 1 else "uninterpreted",
                notes=[],
            )
        )

    return PaperVariableInventory(paper_id=paper_id, mentions=mentions, candidates=candidates)


def paper_variable_inventory_to_payload(inventory: PaperVariableInventory) -> dict[str, object]:
    """Serialize one inventory model as a JSON-friendly dictionary."""
    return inventory.model_dump(mode="json")


def _build_table_classification_contexts(
    table_definitions: list[TableDefinition],
) -> dict[tuple[str, int], _TableClassificationContext]:
    """Build parent-variable and level lookup sets for each table."""
    contexts: dict[tuple[str, int], _TableClassificationContext] = {}
    for table_index, definition in enumerate(table_definitions):
        parent_keys: set[str] = set()
        level_keys: set[str] = set()
        for variable in definition.variables:
            canonical_label = _canonicalize_variable_label(clean_text(variable.variable_name) or clean_text(variable.variable_label))
            canonical_key = _candidate_key(canonical_label)
            if canonical_key:
                parent_keys.add(canonical_key)
            for level in variable.levels:
                level_label = clean_text(level.level_label or level.level_name)
                normalized_level = _normalized_label(level_label).lower()
                if normalized_level:
                    level_keys.add(normalized_level)
        contexts[(definition.table_id, table_index)] = _TableClassificationContext(
            parent_keys=parent_keys,
            level_keys=level_keys,
        )
    return contexts


def _append_mention(
    *,
    mentions: list[VariableMention],
    seen_mentions: set[tuple[object, ...]],
    mention_counter: int,
    raw_label: str,
    normalized_label: str,
    source_type: str,
    mention_role: str,
    canonical_label: str | None = None,
    section_id: str | None = None,
    heading: str | None = None,
    role_hint: str | None = None,
    paragraph_index: int | None = None,
    evidence_text: str | None = None,
    table_id: str | None = None,
    table_index: int | None = None,
    table_label: str | None = None,
    priority_weight: float,
    confidence: float | None,
) -> int:
    """Append one mention if it has not already been recorded."""
    cleaned_label = clean_text(raw_label)
    normalized_clean = _normalized_label(normalized_label or cleaned_label)
    if not cleaned_label or not normalized_clean:
        return mention_counter
    key = (
        cleaned_label,
        normalized_clean.lower(),
        source_type,
        mention_role,
        clean_text(canonical_label or ""),
        section_id,
        paragraph_index,
        clean_text(evidence_text or ""),
        table_id,
        table_index,
    )
    if key in seen_mentions:
        return mention_counter
    seen_mentions.add(key)
    mentions.append(
        VariableMention(
            mention_id=f"mention_{mention_counter}",
            raw_label=cleaned_label,
            normalized_label=normalized_clean,
            source_type=source_type,
            mention_role=mention_role,
            canonical_label=clean_text(canonical_label or "") or None,
            section_id=section_id,
            heading=heading,
            role_hint=role_hint,
            paragraph_index=paragraph_index,
            evidence_text=clean_text(evidence_text or "") or None,
            table_id=table_id,
            table_index=table_index,
            table_label=table_label,
            priority_weight=round(priority_weight, 4),
            confidence=confidence,
            notes=[],
        )
    )
    return mention_counter + 1


def _canonicalize_variable_label(value: str) -> str:
    """Reduce one label to a cleaner variable-like canonical form."""
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    reduced = cleaned.replace("Ʃ", "").strip()
    reduced = TRAILING_SUMMARY_PATTERN.sub("", reduced).strip(" ,;:")

    while True:
        match = re.search(r"\(([^()]+)\)\s*$", reduced)
        if match is None or not _looks_like_units_parenthetical(match.group(1)):
            break
        reduced = reduced[: match.start()].rstrip(" ,;:")

    reduced = TRAILING_QUANTILE_PATTERN.sub("", reduced).rstrip(" ,;:")
    reduced = TRAILING_GROUP_PATTERN.sub("", reduced).rstrip(" ,;:")
    reduced = clean_text(reduced)
    return _CANONICAL_ALIAS_MAP.get(reduced, reduced)


def _classify_mention(
    raw_label: str,
    canonical_label: str,
    table_context: _TableClassificationContext,
    paper_parent_keys: set[str],
    paper_level_keys: set[str],
) -> str:
    """Classify one mention conservatively before candidate promotion."""
    cleaned = clean_text(raw_label)
    normalized = _normalized_label(cleaned).lower()
    if not cleaned:
        return "artifact"
    if TABLE_CONTINUED_PATTERN.search(cleaned):
        return "artifact"
    if MODEL_LABEL_PATTERN.fullmatch(cleaned.replace("__", "_")):
        return "artifact"
    if REFERENCE_FLAG_PATTERN.search(cleaned) and any(token in normalized for token in ("yes", "no", "reference")):
        return "artifact"
    if cleaned.count(",") >= 3 and len(cleaned) >= 30:
        return "artifact"
    if _looks_like_adjustment_variable_list(normalized):
        return "artifact"
    if normalized in table_context.level_keys or normalized in paper_level_keys:
        return "level"
    if QUANTILE_LEVEL_PATTERN.fullmatch(cleaned.replace(" ", "_")) or "quintile" in normalized or "quartile" in normalized:
        return "level"
    if _looks_like_range_or_bin(cleaned):
        return "range_bin"
    if _looks_like_common_level(normalized, table_context.parent_keys | paper_parent_keys):
        return "level"
    if _candidate_key(canonical_label):
        return "variable"
    if any(character.isalpha() for character in cleaned):
        return "unknown"
    return "artifact"


def _looks_like_units_parenthetical(value: str) -> bool:
    """Return whether a trailing parenthetical likely encodes units rather than a concept."""
    lowered = clean_text(value).lower()
    if not lowered:
        return False
    if any(token in lowered for token in ("status", "group", "level", "quintile", "quartile", "model", "reference")):
        return False
    if any(character.isdigit() for character in lowered):
        return True
    if "/" in lowered or "%" in lowered:
        return True
    return lowered in {
        "years",
        "year",
        "months",
        "month",
        "days",
        "day",
        "kg/m2",
        "kg m2",
        "hours",
        "hours week",
        "ng g",
        "mg dl",
        "mmhg",
    }


def _looks_like_range_or_bin(value: str) -> bool:
    """Return whether a label mostly describes a numeric bin rather than a variable."""
    compact = clean_text(value).replace(" ", "")
    if not compact or not any(character.isdigit() for character in compact):
        return False
    alpha_count = sum(character.isalpha() for character in compact)
    return alpha_count <= 1 and RANGE_BIN_PATTERN.fullmatch(compact) is not None


def _looks_like_common_level(normalized_label: str, parent_keys: set[str]) -> bool:
    """Return whether a label should be treated as a level because a matching parent variable exists."""
    for parent_key, level_tokens in _PARENT_LEVEL_HINTS.items():
        if parent_key in parent_keys and normalized_label in level_tokens:
            return True
    return False


def _looks_like_adjustment_variable_list(normalized_label: str) -> bool:
    """Return whether a label looks like a list of adjustment covariates rather than one variable."""
    tokens = [token for token in normalized_label.split() if token]
    if len(tokens) < 5:
        return False
    matched = sum(token in _ADJUSTMENT_LIST_TOKENS for token in tokens)
    return matched >= 4


def _candidate_key(value: str) -> str:
    """Return a conservative merge key for one canonical label."""
    normalized = _normalized_label(value).lower()
    return normalized if len(normalized.replace(" ", "")) >= 3 else ""


def _normalized_label(value: str) -> str:
    """Normalize one label for cross-artifact comparison."""
    return normalize_label_text(clean_text(value))


def _term_in_normalized_text(normalized_term: str, normalized_text: str) -> bool:
    """Return whether a normalized term appears in normalized text with loose word boundaries."""
    compact_term = normalized_term.replace(" ", "")
    if len(compact_term) < 3:
        return False
    pattern = r"\b" + r"\s+".join(re.escape(part) for part in normalized_term.split()) + r"\b"
    return re.search(pattern, normalized_text) is not None


def _unique_preserving_order(values) -> list:
    """Return unique non-empty values while preserving order."""
    seen = set()
    ordered = []
    for value in values:
        if value in (None, "", []):
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
