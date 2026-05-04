"""Build deterministic TableDefinition artifacts."""

from __future__ import annotations

from table1_parser.heuristics.table_definition_columns import build_column_definition
from table1_parser.heuristics.table_definition_rows import build_defined_variables
from table1_parser.schemas import ColumnHeaderSchema, NormalizedTable, TableDefinition
from table1_parser.validation.table_definition import validate_table_definition


def build_table_definition(
    table: NormalizedTable,
    column_schema: ColumnHeaderSchema | None = None,
) -> TableDefinition:
    """Build one deterministic TableDefinition from a normalized table."""
    variables = build_defined_variables(table)
    column_definition = build_column_definition(table, column_schema)
    notes = ["rotated_table_layout"] if table.metadata.get("table_orientation") == "rotated" else []
    confidences = [variable.confidence for variable in variables if getattr(variable, "confidence", None) is not None]
    if getattr(column_definition, "confidence", None) is not None:
        confidences.append(column_definition.confidence)
    definition = TableDefinition(
        table_id=table.table_id,
        title=table.title,
        caption=table.caption,
        variables=variables,
        column_definition=column_definition,
        notes=notes,
        overall_confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
    )
    return validate_table_definition(definition, table)


def build_table_definitions(
    tables: list[NormalizedTable],
    column_schemas: list[ColumnHeaderSchema] | None = None,
) -> list[TableDefinition]:
    """Build deterministic TableDefinition artifacts for a list of tables."""
    return [
        build_table_definition(
            table,
            column_schemas[index] if column_schemas is not None and index < len(column_schemas) else None,
        )
        for index, table in enumerate(tables)
    ]


def table_definitions_to_payload(tables: list[TableDefinition]) -> list[dict[str, object]]:
    """Serialize TableDefinition models as JSON-friendly dictionaries."""
    return [table.model_dump(mode="json") for table in tables]
