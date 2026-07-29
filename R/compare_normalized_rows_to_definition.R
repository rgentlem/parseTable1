#!/usr/bin/env Rscript

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0) y else x
}

if (!exists("load_paper_outputs", mode = "function")) {
  candidate_paths <- c(
    file.path("R", "inspect_paper_outputs.R"),
    "inspect_paper_outputs.R"
  )
  helper_path <- candidate_paths[file.exists(candidate_paths)][1] %||% NA_character_
  if (is.na(helper_path) || !nzchar(helper_path)) {
    stop("Could not locate inspect_paper_outputs.R. Source that file first or run from the repo root / R directory.", call. = FALSE)
  }
  source(helper_path)
}

compare_normalized_rows_to_definition <- function(paper_dir, table_number = "1", table_index = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  resolved_index <- if (!is.null(table_index)) {
    as.integer(table_index) - 1L
  } else {
    resolve_table_index(outputs, table_number = table_number)
  }
  list_position <- as.integer(resolved_index) + 1L
  if (length(outputs$normalized_tables) < list_position) {
    stop(sprintf("No normalized table found for table_number=%s.", as.character(table_number)), call. = FALSE)
  }
  if (length(outputs$table_definitions) < list_position) {
    stop(sprintf("No table definition found for table_number=%s.", as.character(table_number)), call. = FALSE)
  }

  normalized_table <- outputs$normalized_tables[[list_position]]
  definition <- outputs$table_definitions[[list_position]]

  row_views <- normalized_table$row_views %||% list()
  row_view_map <- setNames(
    row_views,
    vapply(row_views, function(row) as.character(as.integer(row$row_idx %||% -1L)), character(1))
  )

  normalized_label_for_row <- function(row_idx) {
    row_view <- row_view_map[[as.character(as.integer(row_idx))]] %||% NULL
    if (!is.null(row_view)) {
      label <- row_view$first_cell_normalized %||% NULL
      if (!is.null(label) && nzchar(label)) {
        return(as.character(label))
      }
    }

    cleaned_rows <- normalized_table$metadata$cleaned_rows %||% list()
    row_position <- as.integer(row_idx) + 1L
    if (row_position >= 1L && row_position <= length(cleaned_rows) && length(cleaned_rows[[row_position]]) > 0) {
      return(as.character(cleaned_rows[[row_position]][[1]] %||% ""))
    }

    NA_character_
  }

  normalized_rows <- data.frame(
    row_idx = as.integer(normalized_table$body_rows %||% integer()),
    first_cell_normalized = vapply(
      as.integer(normalized_table$body_rows %||% integer()),
      normalized_label_for_row,
      character(1)
    ),
    stringsAsFactors = FALSE
  )

  definition_rows <- list()
  for (variable in table_definition_variables(definition)) {
    definition_rows[[length(definition_rows) + 1L]] <- data.frame(
      row_idx = as.integer(variable$row_start %||% -1L),
      row_kind = "variable",
      variable_label = as.character(variable$variable_label %||% NA_character_),
      variable_name = as.character(variable$variable_name %||% NA_character_),
      stringsAsFactors = FALSE
    )

    for (level in variable$levels %||% list()) {
      definition_rows[[length(definition_rows) + 1L]] <- data.frame(
        row_idx = as.integer(level$row_idx %||% -1L),
        row_kind = "level",
        variable_label = as.character(level$level_label %||% NA_character_),
        variable_name = as.character(level$level_name %||% NA_character_),
        stringsAsFactors = FALSE
      )
    }
  }

  definition_rows <- if (length(definition_rows) == 0) {
    data.frame(
      row_idx = integer(),
      row_kind = character(),
      variable_label = character(),
      variable_name = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, definition_rows)
  }

  merge(normalized_rows, definition_rows, by = "row_idx", all = TRUE, sort = TRUE)
}
