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
    table1_continuation_groups = file.path(paper_dir, "table1_continuation_groups.json"),
    table_continuation_column_checks = file.path(paper_dir, "table_continuation_column_checks.json"),
    merged_table1 = file.path(paper_dir, "merged_table1_tables.json"),
    deterministic = file.path(paper_dir, "table_definitions.json"),
    parsed = file.path(paper_dir, "parsed_tables.json"),
    processing_status = file.path(paper_dir, "table_processing_status.json"),
    parse_quality_reports = file.path(paper_dir, "parse_quality_reports.json"),
    variable_plausibility = file.path(paper_dir, "table_variable_plausibility_llm.json"),
    variable_plausibility_debug_dir = file.path(paper_dir, "llm_variable_plausibility_debug"),
    paper_markdown = file.path(paper_dir, "paper_markdown.md"),
    paper_sections = file.path(paper_dir, "paper_sections.json"),
    paper_visual_inventory = file.path(paper_dir, "paper_visual_inventory.json"),
    paper_references = file.path(paper_dir, "paper_references.json"),
    paper_variable_inventory = file.path(paper_dir, "paper_variable_inventory.json"),
    paper_table_inventory = file.path(paper_dir, "paper_table_inventory.json"),
    table_profiles = file.path(paper_dir, "table_profiles.json"),
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
    table1_continuation_groups = read_optional_json(paths$table1_continuation_groups),
    table_continuation_column_checks = read_optional_json(paths$table_continuation_column_checks),
    merged_table1_tables = read_optional_json(paths$merged_table1),
    table_definitions = read_json_file(paths$deterministic),
    parsed_tables = read_optional_json(paths$parsed),
    table_processing_status = read_optional_json(paths$processing_status),
    parse_quality_reports = read_optional_json(paths$parse_quality_reports),
    table_profiles = read_optional_json(paths$table_profiles),
    table_variable_plausibility_llm = read_optional_json(paths$variable_plausibility),
    paper_markdown = read_text_file(paths$paper_markdown),
    paper_sections = read_json_file(paths$paper_sections),
    paper_visual_inventory = read_optional_json(paths$paper_visual_inventory) %||% list(),
    paper_references = read_optional_json(paths$paper_references) %||% list(),
    paper_variable_inventory = read_optional_json(paths$paper_variable_inventory),
    paper_table_inventory = read_optional_json(paths$paper_table_inventory),
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

paper_table_inventory_df <- function(outputs) {
  records <- outputs$paper_table_inventory$tables %||% list()
  rows <- lapply(records, function(record) {
    data.frame(
      table_number = as.integer(record$table_number %||% NA_integer_),
      table_id = as.character(record$table_id %||% ""),
      table_category = as.character(record$table_category %||% ""),
      category_confidence = as.numeric(record$category_confidence %||% NA_real_),
      continuation_of_table_number = as.integer(record$continuation_of_table_number %||% NA_integer_),
      table_family = as.character(record$table_family %||% NA_character_),
      processing_status = as.character(record$processing_status %||% NA_character_),
      failure_reason = as.character(record$failure_reason %||% NA_character_),
      title = as.character(record$title %||% record$caption %||% NA_character_),
      evidence = paste(as.character(unlist(record$category_evidence %||% list(), use.names = FALSE)), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0) {
    data.frame(
      table_number = integer(),
      table_id = character(),
      table_category = character(),
      category_confidence = numeric(),
      continuation_of_table_number = integer(),
      table_family = character(),
      processing_status = character(),
      failure_reason = character(),
      title = character(),
      evidence = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }
}

paper_table_inventory_list <- function(papers_dir = file.path("outputs", "papers")) {
  paper_dirs <- sort(list.dirs(papers_dir, full.names = TRUE, recursive = FALSE))
  inventories <- lapply(paper_dirs, function(paper_dir) {
    outputs <- load_paper_outputs(paper_dir)
    paper_table_inventory_df(outputs)
  })
  names(inventories) <- basename(paper_dirs)
  inventories
}

show_paper_table_inventory <- function(paper_dir) {
  outputs <- load_paper_outputs(paper_dir)
  inventory_df <- paper_table_inventory_df(outputs)

  cat(sprintf("Paper table inventory for %s\n\n", normalizePath(paper_dir, winslash = "/", mustWork = TRUE)))
  if (nrow(inventory_df) == 0) {
    cat("[No rows]\n")
    return(invisible(inventory_df))
  }
  print(inventory_df, row.names = FALSE, right = FALSE)
  continuation_df <- table_continuation_column_checks_df(outputs)
  cat("\nContinuation column checks\n")
  if (nrow(continuation_df) == 0) {
    cat("[No explicit demographic_description continuation column checks]\n")
  } else {
    display_columns <- c(
      "table_number",
      "base_table_id",
      "continuation_table_id",
      "base_n_cols",
      "continuation_n_cols",
      "header_signature_status",
      "coordinate_status",
      "overall_status",
      "confidence"
    )
    print(continuation_df[, display_columns, drop = FALSE], row.names = FALSE, right = FALSE)
  }
  invisible(inventory_df)
}

normalized_table_by_index <- function(outputs, table_index = 0L) {
  idx <- as.integer(table_index) + 1L
  table <- outputs$normalized_tables[[idx]]
  if (is.null(table)) {
    stop(sprintf("No normalized table found for table_index=%s.", table_index), call. = FALSE)
  }
  table
}

parsed_table_by_index <- function(outputs, table_index = 0L) {
  idx <- as.integer(table_index) + 1L
  table <- (outputs$parsed_tables %||% list())[[idx]]
  if (is.null(table)) {
    stop(sprintf("No parsed table found for table_index=%s.", table_index), call. = FALSE)
  }
  table
}

table_definition_by_index <- function(outputs, table_index = 0L) {
  idx <- as.integer(table_index) + 1L
  table <- outputs$table_definitions[[idx]]
  if (is.null(table)) {
    stop(sprintf("No deterministic table definition found for table_index=%s.", table_index), call. = FALSE)
  }
  table
}

table_number_for_table <- function(table) {
  metadata <- table$metadata %||% list()
  signals <- metadata$signals %||% list()
  value <- metadata$table_number %||% signals$caption_table_number %||% NULL
  if (is.null(value) || length(value) == 0 || is.na(value)) {
    text <- paste(
      as.character(table$title %||% ""),
      as.character(table$caption %||% ""),
      sep = " "
    )
    match <- regexpr("\\b[Tt]able\\s+([0-9]+)\\b", text, perl = TRUE)
    if (match < 0L) {
      return(NA_integer_)
    }
    matched <- regmatches(text, match)
    return(as.integer(sub(".*\\b[Tt]able\\s+([0-9]+)\\b.*", "\\1", matched, perl = TRUE)))
  }
  as.integer(value)
}

table_number_for_normalized_table <- function(table) {
  table_number_for_table(table)
}

table_number_for_outputs <- function(outputs, table_index) {
  idx <- as.integer(table_index) + 1L
  table_number_for_table(
    (outputs$normalized_tables %||% list())[[idx]] %||%
      (outputs$extracted_tables %||% list())[[idx]] %||%
      (outputs$table_definitions %||% list())[[idx]] %||%
      (outputs$parsed_tables %||% list())[[idx]] %||%
      list()
  )
}

table_index_by_number <- function(outputs, table_number) {
  requested <- as.integer(table_number)
  matches <- which(vapply(
    outputs$normalized_tables %||% list(),
    function(x) identical(table_number_for_normalized_table(x), requested),
    logical(1)
  ))
  if (length(matches) == 0) {
    stop(sprintf("No table found for table_number=%s.", requested), call. = FALSE)
  }
  if (length(matches) == 1) {
    return(as.integer(matches[[1]] - 1L))
  }

  non_failed <- matches[vapply(matches, function(idx) {
    status <- table_processing_status_by_index(outputs, table_index = idx - 1L)
    !identical(status$status %||% "", "failed")
  }, logical(1))]
  if (length(non_failed) > 0) {
    return(as.integer(non_failed[[1]] - 1L))
  }
  as.integer(matches[[1]] - 1L)
}

resolve_table_index <- function(outputs, table_number = 1L, table_index = NULL) {
  if (!is.null(table_index)) {
    return(as.integer(table_index))
  }
  if (!is.null(table_number)) {
    return(table_index_by_number(outputs, table_number))
  }
  stop("Provide table_number for public inspection, or table_index for low-level debugging.", call. = FALSE)
}

list_llm_variable_plausibility_debug_runs <- function(paper_dir) {
  debug_root <- paper_output_paths(paper_dir)$variable_plausibility_debug_dir
  if (!dir.exists(debug_root)) {
    return(character())
  }
  run_dirs <- sort(list.dirs(debug_root, full.names = TRUE, recursive = FALSE))
  run_dirs[file.exists(file.path(run_dirs, "llm_variable_plausibility_monitoring.json"))]
}

read_llm_variable_plausibility_monitoring <- function(paper_dir, run_id = NULL) {
  run_dirs <- list_llm_variable_plausibility_debug_runs(paper_dir)
  if (length(run_dirs) == 0) {
    stop("No llm_variable_plausibility_debug runs found for this paper.", call. = FALSE)
  }
  selected_dir <- if (is.null(run_id)) {
    run_dirs[[length(run_dirs)]]
  } else {
    candidates <- run_dirs[basename(run_dirs) == run_id]
    if (length(candidates) == 0) {
      stop(sprintf("No llm_variable_plausibility_debug run found for run_id=%s.", run_id), call. = FALSE)
    }
    candidates[[1]]
  }
  payload <- read_json_file(file.path(selected_dir, "llm_variable_plausibility_monitoring.json"))
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

table_processing_status_by_index <- function(outputs, table_index = 0L, table_id = NULL) {
  statuses <- outputs$table_processing_status %||% list()
  if (length(statuses) == 0) {
    return(NULL)
  }

  resolved_table_id <- as.character(table_id %||% "")
  if (!nzchar(resolved_table_id)) {
    idx <- as.integer(table_index) + 1L
    deterministic <- (outputs$table_definitions %||% list())[[idx]] %||% NULL
    normalized <- (outputs$normalized_tables %||% list())[[idx]] %||% NULL
    parsed <- (outputs$parsed_tables %||% list())[[idx]] %||% NULL
    resolved_table_id <- as.character(
      deterministic$table_id %||%
      normalized$table_id %||%
      parsed$table_id %||%
      ""
    )
  }

  if (nzchar(resolved_table_id)) {
    matching_statuses <- Filter(
      function(x) identical(as.character(x$table_id %||% ""), resolved_table_id),
      statuses
    )
    if (length(matching_statuses) > 0) {
      return(matching_statuses[[1]])
    }
  }

  idx <- as.integer(table_index) + 1L
  if (length(statuses) >= idx) {
    return(statuses[[idx]] %||% NULL)
  }
  NULL
}

table_profile_by_index <- function(outputs, table_index = 0L, table_id = NULL) {
  profiles <- outputs$table_profiles %||% list()
  if (length(profiles) == 0) {
    return(NULL)
  }

  resolved_table_id <- as.character(table_id %||% "")
  if (nzchar(resolved_table_id)) {
    matching_profiles <- Filter(
      function(x) identical(as.character(x$table_id %||% ""), resolved_table_id),
      profiles
    )
    if (length(matching_profiles) > 0) {
      return(matching_profiles[[1]])
    }
  }

  idx <- as.integer(table_index) + 1L
  if (length(profiles) >= idx) {
    return(profiles[[idx]] %||% NULL)
  }
  NULL
}

parse_quality_report_by_index <- function(outputs, table_index = 0L, table_id = NULL) {
  reports <- outputs$parse_quality_reports %||% list()
  if (length(reports) == 0) {
    return(NULL)
  }

  resolved_table_id <- as.character(table_id %||% "")
  if (!nzchar(resolved_table_id)) {
    idx <- as.integer(table_index) + 1L
    deterministic <- (outputs$table_definitions %||% list())[[idx]] %||% NULL
    normalized <- (outputs$normalized_tables %||% list())[[idx]] %||% NULL
    parsed <- (outputs$parsed_tables %||% list())[[idx]] %||% NULL
    resolved_table_id <- as.character(
      deterministic$table_id %||%
      normalized$table_id %||%
      parsed$table_id %||%
      ""
    )
  }

  if (nzchar(resolved_table_id)) {
    matching_reports <- Filter(
      function(x) identical(as.character(x$table_id %||% ""), resolved_table_id),
      reports
    )
    if (length(matching_reports) > 0) {
      return(matching_reports[[1]])
    }
  }

  idx <- as.integer(table_index) + 1L
  if (length(reports) >= idx) {
    return(reports[[idx]] %||% NULL)
  }
  NULL
}

quality_diagnostic_count <- function(report, group_name, severity) {
  if (is.null(report)) {
    return(NA_integer_)
  }
  items <- report[[group_name]] %||% list()
  as.integer(sum(vapply(
    items,
    function(item) identical(as.character(item$severity %||% ""), severity),
    logical(1)
  )))
}

diagnostic_items_df <- function(items) {
  rows <- lapply(items %||% list(), function(item) {
    data.frame(
      severity = as.character(item$severity %||% ""),
      code = as.character(item$code %||% ""),
      message = as.character(item$message %||% ""),
      row_idx = as.integer(item$row_idx %||% NA_integer_),
      col_idx = as.integer(item$col_idx %||% NA_integer_),
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0) {
    data.frame(
      severity = character(),
      code = character(),
      message = character(),
      row_idx = integer(),
      col_idx = integer(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }
}

summarize_table1_continuations <- function(paper_dir) {
  outputs <- load_paper_outputs(paper_dir)
  groups <- outputs$table1_continuation_groups %||% list()
  rows <- lapply(groups, function(group) {
    data.frame(
      group_id = as.character(group$group_id %||% ""),
      merge_decision = as.character(group$merge_decision %||% ""),
      decision_reason = as.character(group$decision_reason %||% ""),
      confidence = as.numeric(group$confidence %||% NA_real_),
      column_signature_match = as.logical(group$column_signature_match %||% FALSE),
      table_number = as.integer(group$table_number %||% NA_integer_),
      source_table_ids = paste(as.character(unlist(group$source_table_ids %||% list())), collapse = " | "),
      diagnostics = paste(as.character(unlist(group$diagnostics %||% list())), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  summary_df <- if (length(rows) == 0) {
    data.frame(
      group_id = character(),
      merge_decision = character(),
      decision_reason = character(),
      confidence = numeric(),
      column_signature_match = logical(),
      table_number = integer(),
      source_table_ids = character(),
      diagnostics = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }

  cat(sprintf("Table 1 continuation summary for %s\n\n", outputs$paper_dir))
  if (nrow(summary_df) == 0) {
    cat("[No Table 1 continuation groups]\n")
    return(invisible(summary_df))
  }
  print(summary_df, row.names = FALSE, right = FALSE)
  invisible(summary_df)
}

table_continuation_column_checks_df <- function(outputs) {
  checks <- outputs$table_continuation_column_checks %||% list()
  rows <- lapply(checks, function(check) {
    data.frame(
      check_id = as.character(check$check_id %||% ""),
      table_number = as.integer(check$table_number %||% NA_integer_),
      base_table_index = as.integer(check$base_table_index %||% NA_integer_),
      continuation_table_index = as.integer(check$continuation_table_index %||% NA_integer_),
      base_table_id = as.character(check$base_table_id %||% ""),
      continuation_table_id = as.character(check$continuation_table_id %||% ""),
      base_table_category = as.character(check$base_table_category %||% ""),
      continuation_table_category = as.character(check$continuation_table_category %||% ""),
      base_n_cols = as.integer(check$base_n_cols %||% NA_integer_),
      continuation_n_cols = as.integer(check$continuation_n_cols %||% NA_integer_),
      normalized_column_count_match = as.logical(check$normalized_column_count_match %||% NA),
      header_signature_status = as.character(check$header_signature_status %||% ""),
      coordinate_status = as.character(check$coordinate_status %||% ""),
      overall_status = as.character(check$overall_status %||% ""),
      confidence = as.numeric(check$confidence %||% NA_real_),
      diagnostics = paste(as.character(unlist(check$diagnostics %||% list())), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0) {
    data.frame(
      check_id = character(),
      table_number = integer(),
      base_table_index = integer(),
      continuation_table_index = integer(),
      base_table_id = character(),
      continuation_table_id = character(),
      base_table_category = character(),
      continuation_table_category = character(),
      base_n_cols = integer(),
      continuation_n_cols = integer(),
      normalized_column_count_match = logical(),
      header_signature_status = character(),
      coordinate_status = character(),
      overall_status = character(),
      confidence = numeric(),
      diagnostics = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }
}

summarize_table_continuation_column_checks <- function(paper_dir) {
  outputs <- load_paper_outputs(paper_dir)
  summary_df <- table_continuation_column_checks_df(outputs)

  cat(sprintf("Table continuation column checks for %s\n\n", outputs$paper_dir))
  if (nrow(summary_df) == 0) {
    cat("[No table continuation column checks]\n")
    return(invisible(summary_df))
  }
  print(summary_df, row.names = FALSE, right = FALSE)
  invisible(summary_df)
}

show_table_continuation_column_check <- function(paper_dir, check_index = 0L) {
  outputs <- load_paper_outputs(paper_dir)
  checks <- outputs$table_continuation_column_checks %||% list()
  idx <- as.integer(check_index) + 1L
  if (idx < 1L || length(checks) < idx) {
    stop(sprintf("No table continuation column check found for check_index=%s.", as.integer(check_index)), call. = FALSE)
  }
  check <- checks[[idx]]
  cat(sprintf("Table continuation column check %s\n", as.character(check$check_id %||% "")))
  cat(sprintf("table_number: %s\n", as.integer(check$table_number %||% NA_integer_)))
  cat(sprintf("base: %s\n", as.character(check$base_table_id %||% "")))
  cat(sprintf("continuation: %s\n", as.character(check$continuation_table_id %||% "")))
  cat(sprintf("categories: %s -> %s\n", as.character(check$base_table_category %||% ""), as.character(check$continuation_table_category %||% "")))
  cat(sprintf("columns: %s -> %s\n", as.integer(check$base_n_cols %||% NA_integer_), as.integer(check$continuation_n_cols %||% NA_integer_)))
  cat(sprintf("header_signature_status: %s\n", as.character(check$header_signature_status %||% "")))
  cat(sprintf("coordinate_status: %s\n", as.character(check$coordinate_status %||% "")))
  cat(sprintf("overall_status: %s\n", as.character(check$overall_status %||% "")))
  cat(sprintf("confidence: %.3f\n\n", as.numeric(check$confidence %||% NA_real_)))

  column_map <- check$column_map %||% list()
  column_rows <- lapply(column_map, function(entry) {
    data.frame(
      base_col_idx = as.integer(entry$base_col_idx %||% NA_integer_),
      continuation_col_idx = as.integer(entry$continuation_col_idx %||% NA_integer_),
      base_center = as.numeric(entry$base_center %||% NA_real_),
      continuation_center = as.numeric(entry$continuation_center %||% NA_real_),
      center_delta = as.numeric(entry$center_delta %||% NA_real_),
      base_width = as.numeric(entry$base_width %||% NA_real_),
      continuation_width = as.numeric(entry$continuation_width %||% NA_real_),
      width_delta = as.numeric(entry$width_delta %||% NA_real_),
      status = as.character(entry$status %||% ""),
      stringsAsFactors = FALSE
    )
  })
  cat("Column Map\n")
  if (length(column_rows) == 0) {
    cat("[No rows]\n\n")
  } else {
    print(do.call(rbind, column_rows), row.names = FALSE, right = FALSE)
    cat("\n")
  }

  diagnostics <- as.character(unlist(check$diagnostics %||% list()))
  cat("Diagnostics\n")
  if (length(diagnostics) == 0) {
    cat("[No rows]\n")
  } else {
    cat(paste0("- ", diagnostics, collapse = "\n"))
    cat("\n")
  }
  invisible(check)
}

show_merged_table1 <- function(paper_dir, group_index = 0L, max_rows = 30L) {
  outputs <- load_paper_outputs(paper_dir)
  merged_tables <- outputs$merged_table1_tables %||% list()
  idx <- as.integer(group_index) + 1L
  if (idx < 1L || length(merged_tables) < idx) {
    stop(sprintf("No merged Table 1 artifact found for group_index=%s.", as.integer(group_index)), call. = FALSE)
  }
  merged_table <- merged_tables[[idx]]
  rows <- merged_table$metadata$cleaned_rows %||% list()
  provenance <- merged_table$metadata$table1_continuation_merge$row_provenance %||% list()
  source_for_row <- vapply(
    seq_along(rows),
    function(row_position) {
      row_idx <- row_position - 1L
      matching <- Filter(
        function(x) identical(as.integer(x$merged_row_idx %||% -1L), as.integer(row_idx)),
        provenance
      )
      if (length(matching) == 0) {
        return("")
      }
      sprintf(
        "%s:%s",
        as.character(matching[[1]]$source_table_id %||% ""),
        as.character(matching[[1]]$source_row_idx %||% "")
      )
    },
    character(1)
  )
  max_cols <- max(vapply(rows, length, integer(1)), 0L)
  display_count <- min(length(rows), as.integer(max_rows))
  display_rows <- lapply(seq_len(display_count), function(row_position) {
    cells <- as.character(unlist(rows[[row_position]]))
    if (length(cells) < max_cols) {
      cells <- c(cells, rep("", max_cols - length(cells)))
    }
    data.frame(
      merged_row_idx = as.integer(row_position - 1L),
      source = source_for_row[[row_position]],
      as.list(stats::setNames(cells, paste0("col_", seq_len(max_cols) - 1L))),
      stringsAsFactors = FALSE,
      check.names = FALSE
    )
  })
  display_df <- if (length(display_rows) == 0) {
    data.frame()
  } else {
    do.call(rbind, display_rows)
  }

  cat(sprintf("Merged Table 1 for group_index=%s\n", as.integer(group_index)))
  cat(sprintf("table_id: %s\n", as.character(merged_table$table_id %||% "")))
  cat(sprintf("n_rows: %s, n_cols: %s\n\n", as.integer(merged_table$n_rows %||% 0L), as.integer(merged_table$n_cols %||% 0L)))
  if (nrow(display_df) == 0) {
    cat("[No rows]\n")
    return(invisible(display_df))
  }
  print(display_df, row.names = FALSE, right = FALSE)
  invisible(display_df)
}

summarize_table_processing <- function(paper_dir) {
  outputs <- load_paper_outputs(paper_dir)
  table_count <- max(
    length(outputs$extracted_tables %||% list()),
    length(outputs$normalized_tables %||% list()),
    length(outputs$table_definitions %||% list()),
    length(outputs$parsed_tables %||% list())
  )

  rows <- lapply(seq_len(table_count), function(index) {
    table_index <- index - 1L
    extracted <- outputs$extracted_tables[[index]] %||% NULL
    normalized <- outputs$normalized_tables[[index]] %||% NULL
    definition <- outputs$table_definitions[[index]] %||% NULL
    parsed <- outputs$parsed_tables[[index]] %||% NULL
    table_id <- as.character(
      definition$table_id %||%
      normalized$table_id %||%
      parsed$table_id %||%
      extracted$table_id %||%
      ""
    )
    status_record <- table_processing_status_by_index(outputs, table_index = table_index, table_id = table_id)
    table_profile <- table_profile_by_index(outputs, table_index = table_index, table_id = table_id)
    quality_report <- parse_quality_report_by_index(outputs, table_index = table_index, table_id = table_id)
    columns <- definition$column_definition$columns %||% definition$columns %||% list()
    attempts <- status_record$attempts %||% list()
    data.frame(
      table_number = table_number_for_outputs(outputs, table_index),
      table_id = table_id,
      title = as.character(
        definition$title %||%
        normalized$title %||%
        parsed$title %||%
        extracted$title %||%
        ""
      ),
      status = as.character(status_record$status %||% NA_character_),
      failure_stage = as.character(status_record$failure_stage %||% NA_character_),
      failure_reason = as.character(status_record$failure_reason %||% NA_character_),
      attempt_count = as.integer(length(attempts)),
      successful_attempt_count = as.integer(
        sum(vapply(attempts, function(attempt) isTRUE(attempt$succeeded %||% FALSE), logical(1)))
      ),
      variable_count = as.integer(length(definition$variables %||% list())),
      usable_column_count = as.integer(
        sum(vapply(
          columns,
          function(column) !identical(as.character(column$inferred_role %||% "unknown"), "unknown"),
          logical(1)
        ))
      ),
      value_count = as.integer(length(parsed$values %||% list())),
      table_family = as.character(table_profile$table_family %||% NA_character_),
      grid_refinement_source = as.character(extracted$metadata$grid_refinement_source %||% NA_character_),
      quality_table_warning_count = quality_diagnostic_count(quality_report, "table_diagnostics", "warning"),
      quality_table_error_count = quality_diagnostic_count(quality_report, "table_diagnostics", "error"),
      quality_row_warning_count = quality_diagnostic_count(quality_report, "row_diagnostics", "warning"),
      quality_row_error_count = quality_diagnostic_count(quality_report, "row_diagnostics", "error"),
      quality_column_warning_count = quality_diagnostic_count(quality_report, "column_diagnostics", "warning"),
      quality_column_error_count = quality_diagnostic_count(quality_report, "column_diagnostics", "error"),
      stringsAsFactors = FALSE
    )
  })

  summary_df <- if (length(rows) == 0) {
    data.frame(
      table_number = integer(),
      table_id = character(),
      title = character(),
      status = character(),
      failure_stage = character(),
      failure_reason = character(),
      attempt_count = integer(),
      successful_attempt_count = integer(),
      variable_count = integer(),
      usable_column_count = integer(),
      value_count = integer(),
      table_family = character(),
      grid_refinement_source = character(),
      quality_table_warning_count = integer(),
      quality_table_error_count = integer(),
      quality_row_warning_count = integer(),
      quality_row_error_count = integer(),
      quality_column_warning_count = integer(),
      quality_column_error_count = integer(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }

  cat(sprintf("Table processing summary for %s\n\n", outputs$paper_dir))
  if (nrow(summary_df) == 0) {
    cat("[No rows]\n")
    return(invisible(summary_df))
  }
  print(summary_df, row.names = FALSE, right = FALSE)
  invisible(summary_df)
}

show_table_processing <- function(paper_dir, table_number = 1L, table_index = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  resolved_table_number <- table_number_for_outputs(outputs, table_index)
  normalized <- normalized_table_by_index(outputs, table_index)
  definition <- table_definition_by_index(outputs, table_index)
  parsed <- parsed_table_by_index(outputs, table_index)
  status_record <- table_processing_status_by_index(
    outputs,
    table_index = table_index,
    table_id = as.character(definition$table_id %||% normalized$table_id %||% parsed$table_id %||% "")
  )

  if (is.na(resolved_table_number)) {
    cat("Table processing for unnumbered table\n")
  } else {
    cat(sprintf("Table processing for table_number=%s\n", as.integer(resolved_table_number)))
  }
  cat(sprintf("table_id: %s\n", definition$table_id %||% normalized$table_id %||% parsed$table_id %||% ""))
  if (!is.null(definition$title) && nzchar(definition$title)) {
    cat(sprintf("title: %s\n", definition$title))
  }
  if (!is.null(definition$caption) && nzchar(definition$caption) && !identical(definition$caption, definition$title)) {
    cat(sprintf("caption: %s\n", definition$caption))
  }

  if (is.null(status_record)) {
    cat("\n[No table_processing_status record found]\n")
    return(invisible(NULL))
  }

  columns <- definition$column_definition$columns %||% definition$columns %||% list()
  usable_column_count <- sum(vapply(
    columns,
    function(column) !identical(as.character(column$inferred_role %||% "unknown"), "unknown"),
    logical(1)
  ))
  cat(sprintf("status: %s\n", status_record$status %||% ""))
  if (!is.null(status_record$failure_stage) && nzchar(status_record$failure_stage)) {
    cat(sprintf("failure_stage: %s\n", status_record$failure_stage))
  }
  if (!is.null(status_record$failure_reason) && nzchar(status_record$failure_reason)) {
    cat(sprintf("failure_reason: %s\n", status_record$failure_reason))
  }
  notes <- as.character(unlist(status_record$notes %||% list(), use.names = FALSE))
  if (length(notes) > 0) {
    cat(sprintf("notes: %s\n", paste(notes, collapse = " | ")))
  }
  cat(sprintf("variable_count: %d\n", length(definition$variables %||% list())))
  cat(sprintf("usable_column_count: %d\n", usable_column_count))
  cat(sprintf("value_count: %d\n\n", length(parsed$values %||% list())))

  attempts <- status_record$attempts %||% list()
  cat("Attempts\n")
  if (length(attempts) == 0) {
    cat("[No rows]\n")
    return(invisible(status_record))
  }
  attempts_df <- do.call(
    rbind,
    lapply(attempts, function(attempt) {
      data.frame(
        stage = as.character(attempt$stage %||% ""),
        name = as.character(attempt$name %||% ""),
        considered = as.logical(attempt$considered %||% FALSE),
        ran = as.logical(attempt$ran %||% FALSE),
        succeeded = as.logical(attempt$succeeded %||% FALSE),
        note = as.character(attempt$note %||% ""),
        stringsAsFactors = FALSE
      )
    })
  )
  print(attempts_df, row.names = FALSE, right = FALSE)
  invisible(status_record)
}

show_parse_quality <- function(paper_dir, table_number = 1L, table_index = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  resolved_table_number <- table_number_for_outputs(outputs, table_index)
  normalized <- normalized_table_by_index(outputs, table_index)
  report <- parse_quality_report_by_index(
    outputs,
    table_index = table_index,
    table_id = as.character(normalized$table_id %||% "")
  )
  if (is.null(report)) {
    stop(sprintf("No parse_quality_reports.json record found for table_index=%s.", as.integer(table_index)), call. = FALSE)
  }

  summary <- report$summary %||% list()
  if (is.na(resolved_table_number)) {
    cat("Parse quality for unnumbered table\n")
  } else {
    cat(sprintf("Parse quality for table_number=%s\n", as.integer(resolved_table_number)))
  }
  cat(sprintf("table_id: %s\n", as.character(report$table_id %||% normalized$table_id %||% "")))
  cat(sprintf("total_body_rows: %s\n", as.integer(summary$total_body_rows %||% 0L)))
  cat(sprintf("unknown_row_count: %s\n", as.integer(summary$unknown_row_count %||% 0L)))
  cat(sprintf("unknown_row_fraction: %.3f\n", as.numeric(summary$unknown_row_fraction %||% NA_real_)))
  cat(sprintf("variable_block_count: %s\n", as.integer(summary$variable_block_count %||% 0L)))
  cat(sprintf("recognized_value_pattern_fraction: %.3f\n", as.numeric(summary$recognized_value_pattern_fraction %||% NA_real_)))
  cat(sprintf("row_warning_count: %s\n", as.integer(summary$row_warning_count %||% 0L)))
  cat(sprintf("column_warning_count: %s\n\n", as.integer(summary$column_warning_count %||% 0L)))

  sections <- list(
    "Table Diagnostics" = diagnostic_items_df(report$table_diagnostics),
    "Row Diagnostics" = diagnostic_items_df(report$row_diagnostics),
    "Column Diagnostics" = diagnostic_items_df(report$column_diagnostics)
  )
  for (section_name in names(sections)) {
    cat(sprintf("%s\n", section_name))
    section_df <- sections[[section_name]]
    if (nrow(section_df) == 0) {
      cat("[No rows]\n\n")
    } else {
      print(section_df, row.names = FALSE, right = FALSE)
      cat("\n")
    }
  }
  invisible(report)
}

show_table_structure <- function(paper_dir, table_number = 1L, table_index = NULL, max_rows = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  resolved_table_number <- table_number_for_outputs(outputs, table_index)
  normalized <- normalized_table_by_index(outputs, table_index)
  definition <- table_definition_by_index(outputs, table_index)
  status_record <- table_processing_status_by_index(
    outputs,
    table_index = table_index,
    table_id = as.character(definition$table_id %||% normalized$table_id %||% "")
  )

  cleaned_rows <- normalized$metadata$cleaned_rows %||% list()
  if (!is.null(max_rows)) {
    max_rows <- as.integer(max_rows)
    cleaned_rows <- cleaned_rows[seq_len(min(length(cleaned_rows), max_rows))]
  }

  if (is.na(resolved_table_number)) {
    cat("table_number: NA\n")
  } else {
    cat(sprintf("table_number: %s\n", as.integer(resolved_table_number)))
  }
  cat(sprintf("table_id: %s\n", definition$table_id %||% normalized$table_id %||% ""))
  if (!is.null(definition$title) && nzchar(definition$title)) {
    cat(sprintf("title: %s\n", definition$title))
  }
  if (!is.null(definition$caption) && nzchar(definition$caption) && !identical(definition$caption, definition$title)) {
    cat(sprintf("caption: %s\n", definition$caption))
  }
  cat("\n")
  if (!is.null(status_record)) {
    cat(sprintf("processing status: %s\n", status_record$status %||% ""))
    if (!is.null(status_record$failure_stage) && nzchar(status_record$failure_stage)) {
      cat(sprintf("failure_stage: %s\n", status_record$failure_stage))
    }
    if (!is.null(status_record$failure_reason) && nzchar(status_record$failure_reason)) {
      cat(sprintf("failure_reason: %s\n", status_record$failure_reason))
    }
    cat("\n")
  }

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
          cat(sprintf(
            "      level row %2d | %s\n",
            as.integer(level$row_idx %||% -1L),
            as.character(level$level_label %||% level$level_name %||% "")
          ))
        }
      }
    }
  }

  invisible(list(
    normalized_table = normalized,
    table_definition = definition
  ))
}

llm_variable_plausibility_review_by_index <- function(outputs, table_index = 0L) {
  reviews <- outputs$table_variable_plausibility_llm %||% list()
  if (length(reviews) == 0) {
    stop("No table_variable_plausibility_llm.json found for this paper.", call. = FALSE)
  }
  idx <- as.integer(table_index) + 1L
  review <- reviews[[idx]] %||% NULL
  if (!is.null(review)) {
    return(review)
  }
  definition <- table_definition_by_index(outputs, table_index)
  review_matches <- Filter(
    function(x) identical(as.character(x$table_id %||% ""), as.character(definition$table_id %||% "")),
    reviews
  )
  if (length(review_matches) == 0) {
    stop(sprintf("No variable-plausibility review found for table_index=%s.", table_index), call. = FALSE)
  }
  review_matches[[1]]
}

llm_variable_plausibility_df <- function(outputs, table_number = NULL, table_index = NULL) {
  reviews <- outputs$table_variable_plausibility_llm %||% list()
  if (!is.null(table_number) || !is.null(table_index)) {
    resolved_table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
    reviews <- list(llm_variable_plausibility_review_by_index(outputs, table_index = resolved_table_index))
  }

  rows <- list()
  for (review in reviews) {
    review_table_id <- as.character(review$table_id %||% "")
    matching_indices <- which(vapply(
      outputs$table_definitions %||% list(),
      function(x) identical(as.character(x$table_id %||% ""), review_table_id),
      logical(1)
    ))
    table_index_value <- if (length(matching_indices) == 0) NA_integer_ else as.integer(matching_indices[[1]] - 1L)
    table_number_value <- if (is.na(table_index_value)) NA_integer_ else table_number_for_outputs(outputs, table_index_value)
    for (variable in review$variables %||% list()) {
      levels <- variable$levels %||% list()
      rows[[length(rows) + 1L]] <- data.frame(
        table_number = table_number_value,
        table_id = review_table_id,
        row_start = as.integer(variable$row_start %||% NA_integer_),
        row_end = as.integer(variable$row_end %||% NA_integer_),
        variable_name = as.character(variable$variable_name %||% ""),
        variable_label = as.character(variable$variable_label %||% ""),
        variable_type = as.character(variable$variable_type %||% ""),
        levels = paste(
          vapply(levels, function(level) as.character(level$level_label %||% level$level_name %||% ""), character(1)),
          collapse = " | "
        ),
        level_count = as.integer(length(levels)),
        plausibility_score = as.numeric(variable$plausibility_score %||% NA_real_),
        plausibility_note = as.character(variable$plausibility_note %||% ""),
        stringsAsFactors = FALSE
      )
    }
  }

  if (length(rows) == 0) {
    return(data.frame(
      table_number = integer(),
      table_id = character(),
      row_start = integer(),
      row_end = integer(),
      variable_name = character(),
      variable_label = character(),
      variable_type = character(),
      levels = character(),
      level_count = integer(),
      plausibility_score = numeric(),
      plausibility_note = character(),
      stringsAsFactors = FALSE
    ))
  }
  do.call(rbind, rows)
}

show_variable_plausibility_review <- function(review, normalized_table, table_definition) {
  cleaned_rows <- normalized_table$metadata$cleaned_rows %||% list()

  cat(sprintf("Variable plausibility review for table_id=%s\n", review$table_id %||% table_definition$table_id %||% ""))
  if (!is.null(table_definition$title) && nzchar(table_definition$title)) {
    cat(sprintf("title: %s\n", table_definition$title))
  }
  if (!is.null(table_definition$caption) && nzchar(table_definition$caption) && !identical(table_definition$caption, table_definition$title)) {
    cat(sprintf("caption: %s\n", table_definition$caption))
  }
  if (!is.null(review$overall_plausibility)) {
    cat(sprintf("overall_plausibility: %.3f\n", as.numeric(review$overall_plausibility)))
  }
  notes <- as.character(unlist(review$notes %||% list(), use.names = FALSE))
  if (length(notes) > 0) {
    cat(sprintf("review notes: %s\n", paste(notes, collapse = " | ")))
  }
  cat("\n")

  cat("Rows\n")
  if (length(cleaned_rows) == 0) {
    cat("[No cleaned rows]\n\n")
  } else {
    for (i in seq_along(cleaned_rows)) {
      cat(sprintf("%2d | %s\n", i - 1L, paste(unlist(cleaned_rows[[i]], use.names = FALSE), collapse = " | ")))
    }
    cat("\n")
  }

  cat("Deterministic Variables\n")
  variables <- table_definition$variables %||% list()
  if (length(variables) == 0) {
    cat("[No variables]\n\n")
  } else {
    for (variable in variables) {
      label <- as.character(variable$variable_label %||% variable$variable_name %||% "")
      vtype <- as.character(variable$variable_type %||% "")
      row_start <- as.integer(variable$row_start %||% -1L)
      row_end <- as.integer(variable$row_end %||% -1L)
      cat(sprintf("%2d-%2d | %s | %s\n", row_start, row_end, vtype, label))
      levels <- variable$levels %||% list()
      if (length(levels)) {
        for (level in levels) {
          cat(sprintf(
            "      level row %2d | %s\n",
            as.integer(level$row_idx %||% -1L),
            as.character(level$level_label %||% level$level_name %||% "")
          ))
        }
      }
    }
    cat("\n")
  }

  cat("Variable Plausibility Review\n")
  review_variables <- review$variables %||% list()
  if (length(review_variables) == 0) {
    cat("[No rows]\n")
  } else {
    for (variable in review_variables) {
      label <- as.character(variable$variable_label %||% variable$variable_name %||% "")
      vtype <- as.character(variable$variable_type %||% "")
      row_start <- as.integer(variable$row_start %||% -1L)
      row_end <- as.integer(variable$row_end %||% -1L)
      score <- as.numeric(variable$plausibility_score %||% NA_real_)
      cat(sprintf("%2d-%2d | %s | %s | score=%.3f\n", row_start, row_end, vtype, label, score))
      levels <- variable$levels %||% list()
      if (length(levels) > 0) {
        cat("      levels:\n")
        for (level in levels) {
          cat(sprintf(
            "      row %2d | %s\n",
            as.integer(level$row_idx %||% -1L),
            as.character(level$level_label %||% level$level_name %||% "")
          ))
        }
      }
      note <- as.character(variable$plausibility_note %||% "")
      if (nzchar(note)) {
        cat(sprintf("      note: %s\n", note))
      }
      cat("\n")
    }
  }

  invisible(list(
    review = review,
    normalized_table = normalized_table,
    table_definition = table_definition
  ))
}

show_llm_variable_plausibility <- function(paper_dir, table_number = 1L, table_index = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  review <- llm_variable_plausibility_review_by_index(outputs, table_index = table_index)
  normalized <- normalized_table_by_index(outputs, table_index = table_index)
  definition <- table_definition_by_index(outputs, table_index = table_index)
  show_variable_plausibility_review(review, normalized, definition)
}

summarize_llm_variable_plausibility_monitoring <- function(paper_dir, run_id = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  loaded <- read_llm_variable_plausibility_monitoring(paper_dir, run_id = run_id)
  report <- loaded$monitoring
  items <- report$items %||% list()
  rows <- lapply(items, function(x) {
    matching_indices <- which(vapply(
      outputs$table_definitions %||% list(),
      function(y) identical(as.character(y$table_id %||% ""), as.character(x$table_id %||% "")),
      logical(1)
    ))
    table_index_value <- if (length(matching_indices) == 0) NA_integer_ else as.integer(matching_indices[[1]] - 1L)
    table_number_value <- if (is.na(table_index_value)) NA_integer_ else table_number_for_outputs(outputs, table_index_value)
    data.frame(
      table_number = table_number_value,
      table_id = as.character(x$table_id %||% ""),
      table_family = as.character(x$table_family %||% ""),
      eligible_for_review = as.logical(x$eligible_for_review %||% FALSE),
      status = as.character(x$status %||% ""),
      elapsed_seconds = as.numeric(x$elapsed_seconds %||% NA_real_),
      prompt_char_count = as.numeric(x$prompt_char_count %||% NA_real_),
      response_char_count = as.numeric(x$response_char_count %||% NA_real_),
      deterministic_variable_count = as.integer(x$deterministic_variable_count %||% 0L),
      attached_level_count = as.integer(x$attached_level_count %||% 0L),
      error_message = as.character(x$error_message %||% ""),
      stringsAsFactors = FALSE
    )
  })
  summary_df <- if (length(rows) == 0) {
    data.frame(
      table_number = integer(),
      table_id = character(),
      table_family = character(),
      eligible_for_review = logical(),
      status = character(),
      elapsed_seconds = numeric(),
      prompt_char_count = numeric(),
      response_char_count = numeric(),
      deterministic_variable_count = integer(),
      attached_level_count = integer(),
      error_message = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }

  cat(sprintf("Variable plausibility LLM monitoring summary: %s\n", loaded$run_dir))
  cat(sprintf("report_timestamp=%s provider=%s model=%s\n\n", report$report_timestamp %||% "", report$provider %||% "", report$model %||% ""))
  if (nrow(summary_df) == 0) {
    cat("[No rows]\n")
    return(invisible(summary_df))
  }
  print(summary_df, row.names = FALSE, right = FALSE)
  invisible(summary_df)
}

show_paper_visuals <- function(paper_dir, visual_kind = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  visuals <- outputs$paper_visual_inventory %||% list()
  if (!is.null(visual_kind)) {
    visuals <- Filter(function(x) identical(x$visual_kind %||% "", visual_kind), visuals)
  }

  cat(sprintf("Paper visuals: %s\n", outputs$paper_dir))
  if (length(visuals) == 0) {
    cat("[No visuals]\n")
    return(invisible(visuals))
  }

  for (visual in visuals) {
    cat(sprintf(
      "[%s] %s | %s | page=%s | source_table=%s | artifact=%s | reference_check=%s\n",
      visual$visual_id %||% "",
      visual$visual_kind %||% "",
      visual$label %||% "",
      format(visual$page_num %||% NA),
      visual$source_table_id %||% "",
      visual$artifact_path %||% "",
      visual$reference_check_status %||% ""
    ))
    if (length(visual$text_reference_ids %||% list()) > 0) {
      cat(sprintf("text references: %s\n", paste(unlist(visual$text_reference_ids, use.names = FALSE), collapse = ", ")))
    }
    if (!is.null(visual$caption) && nzchar(visual$caption)) {
      cat(visual$caption, "\n", sep = "")
    }
    cat("\n")
  }

  invisible(visuals)
}

show_paper_references <- function(paper_dir, reference_kind = NULL, reference_label = NULL, resolution_status = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  references <- outputs$paper_references %||% list()
  if (!is.null(reference_kind)) {
    references <- Filter(function(x) identical(x$reference_kind %||% "", reference_kind), references)
  }
  if (!is.null(reference_label)) {
    references <- Filter(function(x) identical(x$reference_label %||% "", reference_label), references)
  }
  if (!is.null(resolution_status)) {
    references <- Filter(function(x) identical(x$resolution_status %||% "", resolution_status), references)
  }

  cat(sprintf("Paper references: %s\n", outputs$paper_dir))
  if (length(references) == 0) {
    cat("[No references]\n")
    return(invisible(references))
  }

  for (reference in references) {
    cat(sprintf(
      "[%s] %s | %s | status=%s | visual=%s | paragraph=%s\n",
      reference$reference_id %||% "",
      reference$reference_label %||% "",
      reference$heading %||% "",
      reference$resolution_status %||% "",
      reference$resolved_visual_id %||% "",
      format(reference$paragraph_index %||% NA)
    ))
    cat(reference$anchor_text %||% "", "\n", sep = "")
    cat("\n")
  }

  invisible(references)
}

show_table_context <- function(paper_dir, table_number = 1L, table_index = NULL, match_type = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  resolved_table_number <- table_number_for_outputs(outputs, table_index)
  context <- table_context_by_index(outputs, table_index)
  passages <- context$passages %||% list()
  if (!is.null(match_type)) {
    passages <- Filter(function(x) identical(x$match_type %||% "", match_type), passages)
  }

  if (is.na(resolved_table_number)) {
    cat("Table context for unnumbered table\n")
  } else {
    cat(sprintf("Table context for table_number=%s\n", as.integer(resolved_table_number)))
  }
  if (!is.null(context$table_label)) {
    cat(sprintf("Label: %s\n", context$table_label))
  }
  if (!is.null(context$title) && nzchar(context$title)) {
    cat(sprintf("Title: %s\n", context$title))
  }
  if (!is.null(context$caption) && nzchar(context$caption)) {
    cat(sprintf("Caption: %s\n", context$caption))
  }
  if (length(context$reference_ids %||% list()) > 0) {
    cat(sprintf("Reference IDs: %s\n", paste(unlist(context$reference_ids, use.names = FALSE), collapse = ", ")))
  }
  if (length(context$resolved_visual_ids %||% list()) > 0) {
    cat(sprintf("Resolved visuals: %s\n", paste(unlist(context$resolved_visual_ids, use.names = FALSE), collapse = ", ")))
  }
  cat("\n")

  for (passage in passages) {
    cat(sprintf(
      "[%s] %s | %s | score=%s\n",
      passage$passage_id,
      passage$heading %||% "",
      passage$match_type %||% "",
      format(passage$score %||% NA)
    ))
    cat(passage$text %||% "", "\n\n", sep = "")
  }

  invisible(passages)
}
