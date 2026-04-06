#!/usr/bin/env Rscript

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0) y else x
}

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

read_text_file <- function(path) {
  if (!file.exists(path)) {
    return(NULL)
  }
  paste(readLines(path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
}

paper_output_paths <- function(paper_dir) {
  list(
    extracted = file.path(paper_dir, "extracted_tables.json"),
    normalized = file.path(paper_dir, "normalized_tables.json"),
    deterministic = file.path(paper_dir, "table_definitions.json"),
    llm = file.path(paper_dir, "table_definitions_llm.json"),
    llm_debug_dir = file.path(paper_dir, "llm_semantic_debug"),
    paper_markdown = file.path(paper_dir, "paper_markdown.md"),
    paper_sections = file.path(paper_dir, "paper_sections.json"),
    paper_variable_inventory = file.path(paper_dir, "paper_variable_inventory.json"),
    table_context_dir = file.path(paper_dir, "table_contexts")
  )
}

read_optional_json <- function(path) {
  if (!file.exists(path)) {
    return(NULL)
  }
  read_json_file(path)
}

read_table_contexts <- function(context_dir) {
  if (!dir.exists(context_dir)) {
    return(list())
  }
  paths <- sort(list.files(context_dir, pattern = "^table_[0-9]+_context\\.json$", full.names = TRUE))
  contexts <- lapply(paths, read_json_file)
  names(contexts) <- vapply(contexts, function(x) as.character(as.integer(x$table_index %||% -1L)), character(1))
  contexts
}

load_paper_outputs <- function(paper_dir) {
  paths <- paper_output_paths(paper_dir)
  list(
    paper_dir = normalizePath(paper_dir, winslash = "/", mustWork = TRUE),
    extracted_tables = read_json_file(paths$extracted),
    normalized_tables = read_json_file(paths$normalized),
    table_definitions = read_json_file(paths$deterministic),
    table_definitions_llm = read_optional_json(paths$llm),
    paper_markdown = read_text_file(paths$paper_markdown),
    paper_sections = read_json_file(paths$paper_sections),
    paper_variable_inventory = read_optional_json(paths$paper_variable_inventory),
    table_contexts = read_table_contexts(paths$table_context_dir)
  )
}

paper_variable_mentions_df <- function(outputs, role_hint = NULL, source_type = NULL, mention_role = NULL) {
  mentions <- outputs$paper_variable_inventory$mentions %||% list()
  rows <- lapply(mentions, function(x) {
    data.frame(
      mention_id = as.character(x$mention_id %||% ""),
      raw_label = as.character(x$raw_label %||% ""),
      normalized_label = as.character(x$normalized_label %||% ""),
      source_type = as.character(x$source_type %||% ""),
      mention_role = as.character(x$mention_role %||% ""),
      canonical_label = as.character(x$canonical_label %||% ""),
      section_id = as.character(x$section_id %||% ""),
      heading = as.character(x$heading %||% ""),
      role_hint = as.character(x$role_hint %||% ""),
      paragraph_index = as.integer(x$paragraph_index %||% NA_integer_),
      evidence_text = as.character(x$evidence_text %||% ""),
      table_id = as.character(x$table_id %||% ""),
      table_index = as.integer(x$table_index %||% NA_integer_),
      table_label = as.character(x$table_label %||% ""),
      priority_weight = as.numeric(x$priority_weight %||% NA_real_),
      confidence = as.numeric(x$confidence %||% NA_real_),
      stringsAsFactors = FALSE
    )
  })
  mentions_df <- if (length(rows) == 0) {
    data.frame(
      mention_id = character(),
      raw_label = character(),
      normalized_label = character(),
      source_type = character(),
      mention_role = character(),
      canonical_label = character(),
      section_id = character(),
      heading = character(),
      role_hint = character(),
      paragraph_index = integer(),
      evidence_text = character(),
      table_id = character(),
      table_index = integer(),
      table_label = character(),
      priority_weight = numeric(),
      confidence = numeric(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }
  if (!is.null(role_hint)) {
    mentions_df <- mentions_df[mentions_df$role_hint %in% as.character(role_hint), , drop = FALSE]
  }
  if (!is.null(source_type)) {
    mentions_df <- mentions_df[mentions_df$source_type %in% as.character(source_type), , drop = FALSE]
  }
  if (!is.null(mention_role)) {
    mentions_df <- mentions_df[mentions_df$mention_role %in% as.character(mention_role), , drop = FALSE]
  }
  mentions_df
}

paper_variable_candidates_df <- function(outputs, min_priority = NULL) {
  candidates <- outputs$paper_variable_inventory$candidates %||% list()
  rows <- lapply(candidates, function(x) {
    data.frame(
      candidate_id = as.character(x$candidate_id %||% ""),
      preferred_label = as.character(x$preferred_label %||% ""),
      canonical_label = as.character(x$canonical_label %||% ""),
      normalized_label = as.character(x$normalized_label %||% ""),
      canonical_label_source = as.character(x$canonical_label_source %||% ""),
      promotion_basis = as.character(x$promotion_basis %||% ""),
      alternate_labels = paste(unlist(x$alternate_labels %||% list(), use.names = FALSE), collapse = " | "),
      source_types = paste(unlist(x$source_types %||% list(), use.names = FALSE), collapse = " | "),
      section_ids = paste(unlist(x$section_ids %||% list(), use.names = FALSE), collapse = " | "),
      section_role_hints = paste(unlist(x$section_role_hints %||% list(), use.names = FALSE), collapse = " | "),
      table_ids = paste(unlist(x$table_ids %||% list(), use.names = FALSE), collapse = " | "),
      table_indices = paste(unlist(x$table_indices %||% list(), use.names = FALSE), collapse = " | "),
      text_support_count = as.integer(x$text_support_count %||% 0L),
      table_support_count = as.integer(x$table_support_count %||% 0L),
      caption_support_count = as.integer(x$caption_support_count %||% 0L),
      filtered_mention_count = as.integer(x$filtered_mention_count %||% 0L),
      priority_score = as.numeric(x$priority_score %||% NA_real_),
      confidence = as.numeric(x$confidence %||% NA_real_),
      interpretation_status = as.character(x$interpretation_status %||% ""),
      stringsAsFactors = FALSE
    )
  })
  candidates_df <- if (length(rows) == 0) {
    data.frame(
      candidate_id = character(),
      preferred_label = character(),
      canonical_label = character(),
      normalized_label = character(),
      canonical_label_source = character(),
      promotion_basis = character(),
      alternate_labels = character(),
      source_types = character(),
      section_ids = character(),
      section_role_hints = character(),
      table_ids = character(),
      table_indices = character(),
      text_support_count = integer(),
      table_support_count = integer(),
      caption_support_count = integer(),
      filtered_mention_count = integer(),
      priority_score = numeric(),
      confidence = numeric(),
      interpretation_status = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }
  if (!is.null(min_priority)) {
    candidates_df <- candidates_df[candidates_df$priority_score >= as.numeric(min_priority), , drop = FALSE]
  }
  candidates_df
}

show_paper_variable_mentions <- function(paper_dir, role_hint = NULL, source_type = NULL, mention_role = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  mentions_df <- paper_variable_mentions_df(
    outputs,
    role_hint = role_hint,
    source_type = source_type,
    mention_role = mention_role
  )

  cat(sprintf("Paper variable mentions for %s\n\n", normalizePath(paper_dir, winslash = "/", mustWork = TRUE)))
  if (nrow(mentions_df) == 0) {
    cat("[No rows]\n")
    return(invisible(mentions_df))
  }
  print(mentions_df, row.names = FALSE, right = FALSE)
  invisible(mentions_df)
}

show_paper_variable_candidates <- function(paper_dir, min_priority = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  candidates_df <- paper_variable_candidates_df(outputs, min_priority = min_priority)

  cat(sprintf("Paper variable candidates for %s\n\n", normalizePath(paper_dir, winslash = "/", mustWork = TRUE)))
  if (nrow(candidates_df) == 0) {
    cat("[No rows]\n")
    return(invisible(candidates_df))
  }
  print(candidates_df, row.names = FALSE, right = FALSE)
  invisible(candidates_df)
}

normalized_table_by_index <- function(outputs, table_index = 0L) {
  idx <- as.integer(table_index) + 1L
  table <- outputs$normalized_tables[[idx]]
  if (is.null(table)) {
    stop(sprintf("No normalized table found for table_index=%s.", table_index), call. = FALSE)
  }
  table
}

list_llm_semantic_debug_runs <- function(paper_dir) {
  debug_root <- paper_output_paths(paper_dir)$llm_debug_dir
  if (!dir.exists(debug_root)) {
    return(character())
  }
  run_dirs <- sort(list.dirs(debug_root, full.names = TRUE, recursive = FALSE))
  run_dirs[file.exists(file.path(run_dirs, "llm_semantic_monitoring.json"))]
}

read_llm_semantic_monitoring <- function(paper_dir, run_id = NULL) {
  run_dirs <- list_llm_semantic_debug_runs(paper_dir)
  if (length(run_dirs) == 0) {
    stop("No llm_semantic_debug runs found for this paper.", call. = FALSE)
  }
  selected_dir <- if (is.null(run_id)) {
    run_dirs[[length(run_dirs)]]
  } else {
    candidates <- run_dirs[basename(run_dirs) == run_id]
    if (length(candidates) == 0) {
      stop(sprintf("No llm_semantic_debug run found for run_id=%s.", run_id), call. = FALSE)
    }
    candidates[[1]]
  }
  payload <- read_json_file(file.path(selected_dir, "llm_semantic_monitoring.json"))
  list(run_dir = selected_dir, monitoring = payload)
}

table_context_by_index <- function(outputs, table_index = 0L) {
  key <- as.character(as.integer(table_index))
  context <- outputs$table_contexts[[key]]
  if (is.null(context)) {
    stop(sprintf("No table context found for table_index=%s.", key), call. = FALSE)
  }
  context
}

table_definitions_by_index <- function(outputs, table_index = 0L) {
  idx <- as.integer(table_index) + 1L
  deterministic <- outputs$table_definitions[[idx]]
  if (is.null(deterministic)) {
    stop(sprintf("No deterministic table definition found for table_index=%s.", table_index), call. = FALSE)
  }
  llm <- NULL
  if (!is.null(outputs$table_definitions_llm) && length(outputs$table_definitions_llm) >= idx) {
    llm <- outputs$table_definitions_llm[[idx]] %||% NULL
  }
  if (is.null(llm) && !is.null(outputs$table_definitions_llm)) {
    llm_matches <- Filter(
      function(x) identical(as.character(x$table_id %||% ""), as.character(deterministic$table_id %||% "")),
      outputs$table_definitions_llm
    )
    llm <- llm_matches[[1]] %||% NULL
  }
  list(deterministic = deterministic, llm = llm)
}

table_definition_variant_by_index <- function(outputs, table_index = 0L, variant = c("deterministic", "llm")) {
  variant <- match.arg(variant)
  definitions <- table_definitions_by_index(outputs, table_index)
  definition <- definitions[[variant]] %||% NULL
  if (is.null(definition)) {
    stop(
      sprintf("No %s table definition found for table_index=%s.", variant, as.integer(table_index)),
      call. = FALSE
    )
  }
  definition
}

normalize_variable_rows <- function(variables, source) {
  rows <- lapply(variables %||% list(), function(x) {
    data.frame(
      key = sprintf("%s:%s", as.integer(x$row_start %||% -1L), as.integer(x$row_end %||% -1L)),
      row_start = as.integer(x$row_start %||% -1L),
      row_end = as.integer(x$row_end %||% -1L),
      variable_label = as.character(x$variable_label %||% x$variable_name %||% ""),
      variable_type = as.character(x$variable_type %||% ""),
      disagrees_with_deterministic = as.logical(x$disagrees_with_deterministic %||% NA),
      source = source,
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0) {
    return(data.frame(key = character(), row_start = integer(), row_end = integer(), variable_label = character(), variable_type = character(), disagrees_with_deterministic = logical(), source = character(), stringsAsFactors = FALSE))
  }
  do.call(rbind, rows)
}

normalize_level_rows <- function(variables, source) {
  rows <- list()
  for (variable in variables %||% list()) {
    for (level in variable$levels %||% list()) {
      rows[[length(rows) + 1L]] <- data.frame(
        key = as.character(as.integer(level$row_idx %||% -1L)),
        row_idx = as.integer(level$row_idx %||% -1L),
        level_label = as.character(level$level_label %||% level$level_name %||% ""),
        parent_label = as.character(variable$variable_label %||% variable$variable_name %||% ""),
        disagrees_with_deterministic = as.logical(level$disagrees_with_deterministic %||% NA),
        source = source,
        stringsAsFactors = FALSE
      )
    }
  }
  if (length(rows) == 0) {
    return(data.frame(key = character(), row_idx = integer(), level_label = character(), parent_label = character(), disagrees_with_deterministic = logical(), source = character(), stringsAsFactors = FALSE))
  }
  do.call(rbind, rows)
}

normalize_column_rows <- function(columns, source) {
  rows <- lapply(columns %||% list(), function(x) {
    data.frame(
      key = as.character(as.integer(x$col_idx %||% -1L)),
      col_idx = as.integer(x$col_idx %||% -1L),
      column_label = as.character(x$column_label %||% x$column_name %||% ""),
      inferred_role = as.character(x$inferred_role %||% ""),
      grouping_variable_hint = as.character(x$grouping_variable_hint %||% ""),
      disagrees_with_deterministic = as.logical(x$disagrees_with_deterministic %||% NA),
      source = source,
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0) {
    return(data.frame(key = character(), col_idx = integer(), column_label = character(), inferred_role = character(), grouping_variable_hint = character(), disagrees_with_deterministic = logical(), source = character(), stringsAsFactors = FALSE))
  }
  do.call(rbind, rows)
}

compare_rows <- function(left, right, key_col, compare_cols, left_suffix = "deterministic", right_suffix = "llm") {
  merged <- merge(left, right, by = key_col, all = TRUE, suffixes = c(paste0("_", left_suffix), paste0("_", right_suffix)), sort = TRUE)
  status <- character(nrow(merged))
  for (i in seq_len(nrow(merged))) {
    if (is.na(merged[[paste0(compare_cols[[1]], "_", left_suffix)]][i])) {
      status[i] <- paste0(right_suffix, "_only")
    } else if (is.na(merged[[paste0(compare_cols[[1]], "_", right_suffix)]][i])) {
      status[i] <- paste0(left_suffix, "_only")
    } else {
      same <- all(vapply(compare_cols, function(col) {
        identical(
          merged[[paste0(col, "_", left_suffix)]][i] %||% "",
          merged[[paste0(col, "_", right_suffix)]][i] %||% ""
        )
      }, logical(1)))
      status[i] <- if (same) "same" else "different"
    }
  }
  merged$status <- status
  merged
}

print_comparison_block <- function(title, x) {
  cat(title, "\n", sep = "")
  if (nrow(x) == 0) {
    cat("[No rows]\n\n")
    return(invisible(x))
  }
  print(x, row.names = FALSE, right = FALSE)
  cat("\n")
  invisible(x)
}

show_table_structure <- function(
  paper_dir,
  table_index = 0L,
  variant = c("deterministic", "llm"),
  max_rows = NULL
) {
  variant <- match.arg(variant)
  outputs <- load_paper_outputs(paper_dir)
  normalized <- normalized_table_by_index(outputs, table_index)
  definition <- table_definition_variant_by_index(outputs, table_index, variant = variant)

  cleaned_rows <- normalized$metadata$cleaned_rows %||% list()
  if (!is.null(max_rows)) {
    max_rows <- as.integer(max_rows)
    cleaned_rows <- cleaned_rows[seq_len(min(length(cleaned_rows), max_rows))]
  }

  cat(sprintf("table_index: %s\n", as.integer(table_index)))
  cat(sprintf("table_id: %s\n", definition$table_id %||% normalized$table_id %||% ""))
  if (!is.null(definition$title) && nzchar(definition$title)) {
    cat(sprintf("title: %s\n", definition$title))
  }
  if (!is.null(definition$caption) && nzchar(definition$caption) && !identical(definition$caption, definition$title)) {
    cat(sprintf("caption: %s\n", definition$caption))
  }
  cat(sprintf("definition variant: %s\n\n", variant))

  cat("Rows\n")
  if (length(cleaned_rows) == 0) {
    cat("[No cleaned rows]\n\n")
  } else {
    for (i in seq_along(cleaned_rows)) {
      cat(sprintf("%2d | %s\n", i - 1L, paste(unlist(cleaned_rows[[i]], use.names = FALSE), collapse = " | ")))
    }
    cat("\n")
  }

  cat("Columns\n")
  columns <- definition$column_definition$columns %||% definition$columns %||% list()
  if (variant == "llm" && length(columns) == 0) {
    columns <- outputs$table_definitions[[as.integer(table_index) + 1L]]$column_definition$columns %||% list()
    if (length(columns) > 0) {
      cat("[Using deterministic columns; current LLM semantic output is row-only.]\n")
    }
  }
  if (length(columns) == 0) {
    cat("[No column definitions]\n\n")
  } else {
    for (column in columns) {
      col_idx <- as.integer(column$col_idx %||% -1L)
      label <- as.character(column$column_label %||% column$column_name %||% "")
      role <- as.character(column$inferred_role %||% "")
      group_level <- as.character(column$group_level_label %||% "")
      stat <- as.character(column$statistic_subtype %||% "")
      extras <- Filter(nzchar, c(
        if (nzchar(group_level)) paste0("group_level=", group_level) else "",
        if (nzchar(stat)) paste0("stat=", stat) else ""
      ))
      suffix <- if (length(extras)) paste0(" [", paste(extras, collapse = ", "), "]") else ""
      cat(sprintf("%2d | %s | %s%s\n", col_idx, role, label, suffix))
    }
    cat("\n")
  }

  cat("Variables\n")
  variables <- definition$variables %||% list()
  if (length(variables) == 0) {
    cat("[No variables]\n")
  } else {
    for (variable in variables) {
      label <- as.character(variable$variable_label %||% variable$variable_name %||% "")
      vtype <- as.character(variable$variable_type %||% "")
      row_start <- as.integer(variable$row_start %||% -1L)
      row_end <- as.integer(variable$row_end %||% -1L)
      summary_style <- as.character(variable$summary_style_hint %||% "")
      units <- as.character(variable$units_hint %||% "")
      extras <- Filter(nzchar, c(
        if (nzchar(summary_style)) paste0("summary=", summary_style) else "",
        if (nzchar(units)) paste0("units=", units) else ""
      ))
      suffix <- if (length(extras)) paste0(" [", paste(extras, collapse = ", "), "]") else ""
      cat(sprintf("%2d-%2d | %s | %s%s\n", row_start, row_end, vtype, label, suffix))
      levels <- variable$levels %||% list()
      if (length(levels)) {
        for (level in levels) {
          cat(sprintf("      level row %2d | %s\n",
                      as.integer(level$row_idx %||% -1L),
                      as.character(level$level_label %||% level$level_name %||% "")))
        }
      }
    }
  }

  invisible(list(
    normalized_table = normalized,
    table_definition = definition
  ))
}

compare_table_definitions <- function(paper_dir, table_index = 0L) {
  outputs <- load_paper_outputs(paper_dir)
  definitions <- table_definitions_by_index(outputs, table_index)
  if (is.null(definitions$llm)) {
    stop("No table_definitions_llm.json found for this paper.", call. = FALSE)
  }
  compare_table_definition_runs(
    paper_dir_a = paper_dir,
    paper_dir_b = paper_dir,
    table_index = table_index,
    variant_a = "deterministic",
    variant_b = "llm",
    label_a = "deterministic",
    label_b = "llm"
  )
}

compare_table_definition_runs <- function(
  paper_dir_a,
  paper_dir_b,
  table_index = 0L,
  variant_a = c("deterministic", "llm"),
  variant_b = c("deterministic", "llm"),
  label_a = NULL,
  label_b = NULL
) {
  variant_a <- match.arg(variant_a)
  variant_b <- match.arg(variant_b)

  outputs_a <- load_paper_outputs(paper_dir_a)
  outputs_b <- load_paper_outputs(paper_dir_b)
  definition_a <- table_definition_variant_by_index(outputs_a, table_index = table_index, variant = variant_a)
  definition_b <- table_definition_variant_by_index(outputs_b, table_index = table_index, variant = variant_b)

  label_a <- label_a %||% sprintf("run_a_%s", variant_a)
  label_b <- label_b %||% sprintf("run_b_%s", variant_b)

  variables <- compare_rows(
    normalize_variable_rows(definition_a$variables, label_a),
    normalize_variable_rows(definition_b$variables, label_b),
    "key",
    c("variable_label", "variable_type"),
    left_suffix = "left",
    right_suffix = "right"
  )
  levels <- compare_rows(
    normalize_level_rows(definition_a$variables, label_a),
    normalize_level_rows(definition_b$variables, label_b),
    "key",
    c("level_label", "parent_label"),
    left_suffix = "left",
    right_suffix = "right"
  )
  columns_a <- definition_a$column_definition$columns %||% definition_a$columns %||% list()
  columns_b <- definition_b$column_definition$columns %||% definition_b$columns %||% list()
  columns <- compare_rows(
    normalize_column_rows(columns_a, label_a),
    normalize_column_rows(columns_b, label_b),
    "key",
    c("column_label", "inferred_role", "grouping_variable_hint"),
    left_suffix = "left",
    right_suffix = "right"
  )

  cat(sprintf("Table comparison for table_index=%s\n", as.integer(table_index)))
  cat(sprintf("Left: %s (%s)\n", label_a, variant_a))
  cat(sprintf("Right: %s (%s)\n\n", label_b, variant_b))

  print_comparison_block("Variables", variables)
  print_comparison_block("Levels", levels)
  if (variant_a == "llm" || variant_b == "llm") {
    cat("Columns\n")
    cat("[LLM semantic variant is row-only; columns remain deterministic and are shown only for comparison context.]\n\n")
  }
  print_comparison_block("Columns", columns)

  invisible(
    list(
      variables = variables,
      levels = levels,
      columns = columns,
      metadata = list(
        paper_dir_a = normalizePath(paper_dir_a, winslash = "/", mustWork = TRUE),
        paper_dir_b = normalizePath(paper_dir_b, winslash = "/", mustWork = TRUE),
        table_index = as.integer(table_index),
        variant_a = variant_a,
        variant_b = variant_b,
        label_a = label_a,
        label_b = label_b
      )
    )
  )
}

summarize_llm_semantic_monitoring <- function(paper_dir, run_id = NULL) {
  loaded <- read_llm_semantic_monitoring(paper_dir, run_id = run_id)
  report <- loaded$monitoring
  items <- report$items %||% list()
  rows <- lapply(items, function(x) {
    data.frame(
      table_index = as.integer(x$table_index %||% -1L),
      table_id = as.character(x$table_id %||% ""),
      table_family = as.character(x$table_family %||% ""),
      should_run_llm_semantics = as.logical(x$should_run_llm_semantics %||% FALSE),
      status = as.character(x$status %||% ""),
      elapsed_seconds = as.numeric(x$elapsed_seconds %||% NA_real_),
      prompt_char_count = as.numeric(x$prompt_char_count %||% NA_real_),
      response_char_count = as.numeric(x$response_char_count %||% NA_real_),
      retrieved_passage_count = as.integer(x$retrieved_passage_count %||% 0L),
      deterministic_variable_count = as.integer(x$deterministic_variable_count %||% 0L),
      deterministic_column_count = as.integer(x$deterministic_column_count %||% 0L),
      error_message = as.character(x$error_message %||% ""),
      stringsAsFactors = FALSE
    )
  })
  summary_df <- if (length(rows) == 0) {
    data.frame(
      table_index = integer(),
      table_id = character(),
      table_family = character(),
      should_run_llm_semantics = logical(),
      status = character(),
      elapsed_seconds = numeric(),
      prompt_char_count = numeric(),
      response_char_count = numeric(),
      retrieved_passage_count = integer(),
      deterministic_variable_count = integer(),
      deterministic_column_count = integer(),
      error_message = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }

  cat(sprintf("Semantic LLM monitoring summary: %s\n", loaded$run_dir))
  cat(sprintf("report_timestamp=%s provider=%s model=%s\n\n", report$report_timestamp %||% "", report$provider %||% "", report$model %||% ""))
  if (nrow(summary_df) == 0) {
    cat("[No rows]\n")
    return(invisible(summary_df))
  }
  print(summary_df, row.names = FALSE, right = FALSE)
  invisible(summary_df)
}

show_table_context <- function(paper_dir, table_index = 0L, match_type = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  context <- table_context_by_index(outputs, table_index)
  passages <- context$passages %||% list()
  if (!is.null(match_type)) {
    passages <- Filter(function(x) identical(x$match_type %||% "", match_type), passages)
  }

  cat(sprintf("Table context for table_index=%s\n", as.integer(table_index)))
  if (!is.null(context$table_label)) {
    cat(sprintf("Label: %s\n", context$table_label))
  }
  if (!is.null(context$title) && nzchar(context$title)) {
    cat(sprintf("Title: %s\n", context$title))
  }
  if (!is.null(context$caption) && nzchar(context$caption)) {
    cat(sprintf("Caption: %s\n", context$caption))
  }
  cat("\n")

  for (passage in passages) {
    cat(sprintf("[%s] %s | %s | score=%s\n", passage$passage_id, passage$heading %||% "", passage$match_type %||% "", format(passage$score %||% NA)))
    cat(passage$text %||% "", "\n\n", sep = "")
  }

  invisible(passages)
}

resolve_evidence_passages <- function(table_context, passage_ids) {
  passages <- table_context$passages %||% list()
  passage_map <- setNames(passages, vapply(passages, function(x) x$passage_id %||% "", character(1)))
  lapply(passage_ids %||% character(), function(id) passage_map[[id]] %||% NULL)
}

show_llm_evidence <- function(paper_dir, table_index = 0L) {
  outputs <- load_paper_outputs(paper_dir)
  definitions <- table_definitions_by_index(outputs, table_index)
  if (is.null(definitions$llm)) {
    stop("No table_definitions_llm.json found for this paper.", call. = FALSE)
  }
  context <- table_context_by_index(outputs, table_index)
  llm <- definitions$llm

  cat(sprintf("LLM evidence for table_index=%s\n\n", as.integer(table_index)))

  for (variable in llm$variables %||% list()) {
    ids <- variable$evidence_passage_ids %||% list()
    if (length(ids) == 0) {
      next
    }
    cat(sprintf("Variable: %s [%s-%s]\n", variable$variable_label %||% variable$variable_name %||% "", variable$row_start %||% "", variable$row_end %||% ""))
    cat(sprintf("disagrees_with_deterministic: %s\n", as.character(variable$disagrees_with_deterministic %||% FALSE)))
    for (passage in resolve_evidence_passages(context, ids)) {
      if (is.null(passage)) {
        next
      }
      cat(sprintf("  [%s] %s\n", passage$passage_id, passage$heading %||% ""))
      cat(sprintf("  %s\n", passage$text %||% ""))
    }
    cat("\n")
  }

  invisible(llm)
}
