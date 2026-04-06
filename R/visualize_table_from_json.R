#!/usr/bin/env Rscript

read_json_file <- function(json_path) {
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("The 'jsonlite' package is required. Install it with install.packages('jsonlite').", call. = FALSE)
  }
  if (!file.exists(json_path)) {
    stop(sprintf("JSON file not found: %s", json_path), call. = FALSE)
  }
  json_text <- paste(readLines(json_path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  jsonlite::fromJSON(json_text, simplifyVector = FALSE)
}

normalize_indent_steps <- function(indent) {
  value <- as.integer(indent %||% 0L)
  if (is.na(value) || value <= 0) {
    return(0L)
  }
  max(1L, min(4L, as.integer(floor(value / 2L))))
}

pick_header <- function(payload) {
  header_rows <- payload$header_rows
  if (is.null(header_rows) || length(header_rows) == 0) {
    return(character())
  }
  if (is.list(header_rows[[1]])) {
    return(unlist(header_rows[[length(header_rows)]], use.names = FALSE))
  }
  cleaned_rows <- payload$metadata$cleaned_rows %||% list()
  header_idx <- as.integer(header_rows[[length(header_rows)]]) + 1L
  if (length(cleaned_rows) >= header_idx && header_idx >= 1L) {
    return(unlist(cleaned_rows[[header_idx]], use.names = FALSE))
  }
  character()
}

build_payload_display <- function(payload) {
  header <- pick_header(payload)
  body_rows <- payload$body_rows %||% payload$rows %||% list()
  compact_rows <- FALSE
  row_cells <- lapply(body_rows, function(row) {
    if (!is.null(row$label)) {
      compact_rows <<- TRUE
      vals <- if (isTRUE(row$vals %||% FALSE)) "Y" else ""
      num <- as.character(as.integer(row$num %||% 0L))
      if (identical(num, "0")) {
        num <- ""
      }
      indent <- as.character(as.integer(row$indent %||% 0L))
      if (identical(indent, "0")) {
        indent <- ""
      }
      cells <- c(
        paste0("[", as.integer(row$i %||% -1L), "] ", as.character(row$label %||% "")),
        vals,
        num,
        indent
      )
      return(cells)
    }
    cells <- unlist(row$cells %||% row, use.names = FALSE)
    label <- cells[1] %||% ""
    indent <- row$indent_level %||% 0
    heuristic_type <- row$heuristic_type %||% ""
    if (identical(heuristic_type, "level_row") && !is.null(label) && nzchar(label)) {
      label <- paste0(strrep("  ", max(1, indent %||% 1)), label)
    }
    cells[1] <- label
    cells
  })
  max_cols <- max(length(header), max(vapply(row_cells, length, integer(1)), 0L))
  if (max_cols == 0) {
    return(data.frame())
  }
  if (compact_rows) {
    header <- c("Row", "Vals", "Num", "Indent")
  } else if (length(header) == 0) {
    header <- c("Label", paste0("V", seq_len(max_cols - 1)))
  }
  header <- c(header, rep("", max_cols - length(header)))
  row_matrix <- do.call(
    rbind,
    lapply(row_cells, function(cells) c(cells, rep("", max_cols - length(cells))))
  )
  display <- as.data.frame(row_matrix, stringsAsFactors = FALSE, check.names = FALSE)
  names(display) <- header
  display
}

build_normalized_display <- function(payload) {
  cleaned_rows <- payload$metadata$cleaned_rows %||% list()
  body_rows <- payload$body_rows %||% list()
  row_views <- payload$row_views %||% list()
  if (length(cleaned_rows) == 0 || length(body_rows) == 0) {
    return(data.frame())
  }
  header <- pick_header(payload)
  indent_by_row <- setNames(
    vapply(row_views, function(row) as.integer(row$indent_level %||% 0L), integer(1)),
    vapply(row_views, function(row) as.character(as.integer(row$row_idx %||% -1L)), character(1))
  )
  row_cells <- lapply(body_rows, function(row_idx) {
    idx <- as.integer(row_idx)
    row_position <- idx + 1L
    if (is.na(idx) || row_position < 1L || row_position > length(cleaned_rows)) {
      return(character())
    }
    cells <- unlist(cleaned_rows[[row_position]], use.names = FALSE)
    key <- as.character(idx)
    indent <- indent_by_row[[key]] %||% 0L
    if (length(cells) > 0) {
      steps <- normalize_indent_steps(indent)
      if (steps > 0L) {
        cells[1] <- paste0(strrep("  ", steps), cells[1])
      }
    }
    cells
  })
  row_cells <- row_cells[vapply(row_cells, length, integer(1)) > 0L]
  max_cols <- max(length(header), max(vapply(row_cells, length, integer(1)), 0L))
  if (max_cols == 0) {
    return(data.frame())
  }
  if (length(header) == 0) {
    header <- c("Label", paste0("V", seq_len(max_cols - 1L)))
  }
  header <- c(header, rep("", max_cols - length(header)))
  row_matrix <- do.call(
    rbind,
    lapply(row_cells, function(cells) c(cells, rep("", max_cols - length(cells))))
  )
  display <- as.data.frame(row_matrix, stringsAsFactors = FALSE, check.names = FALSE)
  names(display) <- header
  display
}

build_parsed_display <- function(payload) {
  columns <- payload$columns %||% list()
  ordered_columns <- columns[order(vapply(columns, function(col) col$col_idx %||% 0L, integer(1)))]
  header <- c("Label", vapply(ordered_columns, function(col) col$column_label %||% col$column_name %||% "", character(1)))
  values <- payload$values %||% list()
  value_map <- list()
  for (value in values) {
    key <- paste(value$row_idx %||% -1L, value$col_idx %||% -1L, sep = "::")
    value_map[[key]] <- value$raw_value %||% ""
  }
  rows <- list()
  for (variable in payload$variables %||% list()) {
    parent_row_idx <- variable$row_start %||% variable$variable_row_idx %||% -1L
    row <- c(variable$variable_label %||% variable$variable_name %||% "")
    for (col in ordered_columns) {
      key <- paste(parent_row_idx, col$col_idx %||% -1L, sep = "::")
      row <- c(row, value_map[[key]] %||% "")
    }
    rows[[length(rows) + 1L]] <- row
    for (level in variable$levels %||% list()) {
      level_row <- c(paste0("  ", level$label %||% ""))
      for (col in ordered_columns) {
        key <- paste(level$row_idx %||% -1L, col$col_idx %||% -1L, sep = "::")
        level_row <- c(level_row, value_map[[key]] %||% "")
      }
      rows[[length(rows) + 1L]] <- level_row
    }
  }
  if (length(rows) == 0) {
    return(data.frame())
  }
  display <- as.data.frame(do.call(rbind, rows), stringsAsFactors = FALSE, check.names = FALSE)
  names(display) <- header
  display
}

unwrap_trace_payload <- function(payload) {
  if (!is.null(payload$payload) && is.list(payload$payload)) {
    return(payload$payload)
  }
  if (!is.null(payload$interpretation) && is.list(payload$interpretation)) {
    return(payload$interpretation)
  }
  if (!is.null(payload$response) && is.list(payload$response)) {
    return(payload$response)
  }
  payload
}

unwrap_table_array <- function(payload) {
  if (is.null(names(payload)) && length(payload) > 0 && is.list(payload[[1]])) {
    return(payload[[1]])
  }
  payload
}

looks_like_normalized_table <- function(payload) {
  !is.null(payload$row_views) &&
    !is.null(payload$metadata) &&
    !is.null(payload$metadata$cleaned_rows) &&
    !is.null(payload$body_rows)
}

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0) y else x
}

visualize_table_from_json <- function(json_path) {
  payload <- unwrap_table_array(unwrap_trace_payload(read_json_file(json_path)))
  title <- payload$title %||% NULL
  caption <- payload$caption %||% NULL
  table_text <- payload$table %||% NULL
  if (is.null(title) && is.null(caption) && !is.null(table_text) && nzchar(table_text)) {
    cat(table_text, "\n\n", sep = "")
  }
  if (!is.null(title) && nzchar(title)) {
    cat(title, "\n", sep = "")
  }
  if (!is.null(caption) && nzchar(caption) && !identical(caption, title)) {
    cat(caption, "\n", sep = "")
  }
  if (!is.null(title) || !is.null(caption)) {
    cat("\n")
  }

  display <- if (looks_like_normalized_table(payload)) {
    build_normalized_display(payload)
  } else if (!is.null(payload$body_rows) || !is.null(payload$rows)) {
    build_payload_display(payload)
  } else if (!is.null(payload$variables) && !is.null(payload$columns)) {
    build_parsed_display(payload)
  } else {
    stop("Unsupported JSON structure. Expected normalized rows, compact payload rows, or parsed variables/columns.", call. = FALSE)
  }

  if (nrow(display) == 0) {
    cat("[No table rows to display]\n")
    return(invisible(display))
  }
  print(display, row.names = FALSE, right = FALSE)
  invisible(display)
}

args <- commandArgs(trailingOnly = TRUE)
if (sys.nframe() == 0) {
  if (length(args) != 1) {
    stop("Usage: Rscript R/visualize_table_from_json.R path/to/file.json", call. = FALSE)
  }
  visualize_table_from_json(args[[1]])
}
