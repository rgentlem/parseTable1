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
    cell_text_annotations = file.path(paper_dir, "cell_text_annotations.json"),
    paper_footnotes = file.path(paper_dir, "paper_footnotes.json"),
    paper_page_furniture = file.path(paper_dir, "paper_page_furniture.json"),
    column_header_schemas = file.path(paper_dir, "column_header_schemas.json"),
    table1_continuation_groups = file.path(paper_dir, "table1_continuation_groups.json"),
    table_continuation_column_checks = file.path(paper_dir, "table_continuation_column_checks.json"),
    merged_table1 = file.path(paper_dir, "merged_table1_tables.json"),
    deterministic = file.path(paper_dir, "table_definitions.json"),
    continued_variable_integrations = file.path(paper_dir, "continued_variable_integrations.json"),
    parsed = file.path(paper_dir, "parsed_tables.json"),
    processing_status = file.path(paper_dir, "table_processing_status.json"),
    parse_quality_reports = file.path(paper_dir, "parse_quality_reports.json"),
    variable_plausibility = file.path(paper_dir, "table_variable_plausibility_llm.json"),
    variable_plausibility_debug_dir = file.path(paper_dir, "llm_variable_plausibility_debug"),
    paper_markdown = file.path(paper_dir, "paper_markdown.md"),
    paper_sections = file.path(paper_dir, "paper_sections.json"),
    paper_style_profile = file.path(paper_dir, "paper_style_profile.json"),
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

table_definition_variables <- function(definition) {
  definition$variables %||% list()
}

table_definition_columns <- function(definition) {
  column_definition <- definition$column_definition %||% list()
  column_definition$columns %||% definition$columns %||% list()
}

table_definition_header_spans <- function(definition) {
  column_definition <- definition$column_definition %||% list()
  column_definition$header_spans %||% list()
}

character_vector <- function(x) {
  values <- as.character(unlist(x %||% list(), use.names = FALSE))
  values[!is.na(values)]
}

named_count_text <- function(x) {
  if (is.null(x) || length(x) == 0L) {
    return("")
  }
  values <- unlist(x, use.names = TRUE)
  if (length(values) == 0L) {
    return("")
  }
  paste(sprintf("%s=%s", names(values), as.character(values)), collapse = " | ")
}

secondary_count_text <- function(x) {
  if (is.null(x) || length(x) == 0L) {
    return("")
  }
  parts <- vapply(names(x), function(name) {
    counts <- named_count_text(x[[name]])
    if (!nzchar(counts)) {
      return("")
    }
    sprintf("%s{%s}", name, counts)
  }, character(1))
  paste(parts[nzchar(parts)], collapse = " | ")
}

column_header_path_text <- function(column) {
  path <- character_vector(column$header_path)
  path <- path[nzchar(path)]
  if (length(path) > 0L) {
    return(paste(path, collapse = " > "))
  }
  group_labels <- character_vector(column$header_group_labels)
  group_labels <- group_labels[nzchar(group_labels)]
  leaf_label <- as.character(column$header_leaf_label %||% column$column_label %||% column$column_name %||% "")
  parts <- c(group_labels, leaf_label)
  parts <- parts[nzchar(parts)]
  paste(parts, collapse = " > ")
}

column_header_schema_by_index <- function(outputs, table_index = 0L) {
  schemas <- outputs$column_header_schemas %||% list()
  idx <- as.integer(table_index) + 1L
  if (idx < 1L || idx > length(schemas)) {
    return(NULL)
  }
  schemas[[idx]]
}

column_header_leaf_paths_df <- function(schema) {
  if (is.null(schema)) {
    return(data.frame(
      col_idx = integer(),
      leaf_label = character(),
      header_path = character(),
      is_row_label_column = logical(),
      stringsAsFactors = FALSE
    ))
  }
  groups <- schema$groups %||% list()
  rels <- schema$relationships %||% list()
  group_labels <- setNames(
    vapply(groups, function(g) as.character(g$label %||% ""), character(1)),
    vapply(groups, function(g) as.character(g$group_id %||% ""), character(1))
  )
  rows <- lapply(schema$leaves %||% list(), function(leaf) {
    parents <- rels[vapply(rels, function(r) identical(r$child_leaf_id, leaf$leaf_id), logical(1))]
    if (length(parents) > 1L) {
      parents <- parents[order(vapply(parents, function(r) as.integer(r$row_idx %||% 0L), integer(1)))]
    }
    path <- vapply(parents, function(r) group_labels[[as.character(r$parent_group_id %||% "")]] %||% "", character(1))
    leaf_label <- as.character(leaf$leaf_label %||% "")
    data.frame(
      col_idx = as.integer(leaf$col_idx %||% NA_integer_),
      leaf_label = leaf_label,
      header_path = paste(c(path[nzchar(path)], leaf_label), collapse = " > "),
      is_row_label_column = isTRUE(as.logical(leaf$is_row_label_column %||% FALSE)),
      stringsAsFactors = FALSE
    )
  })
  out <- if (length(rows)) do.call(rbind, rows) else {
    data.frame(col_idx = integer(), leaf_label = character(), header_path = character(), is_row_label_column = logical())
  }
  out[order(out$col_idx), , drop = FALSE]
}

table_structure_header_spans <- function(definition, column_header_schema = NULL) {
  spans <- table_definition_header_spans(definition)
  if (is.null(column_header_schema)) {
    return(spans)
  }
  existing_cols <- unique(as.integer(unlist(lapply(spans, function(span) {
    character_vector(span$leaf_col_indices)
  }), use.names = FALSE)))
  existing_cols <- existing_cols[!is.na(existing_cols)]
  span_leaf_levels <- as.integer(unlist(lapply(spans, function(span) {
    if (identical(as.character(span$source %||% ""), "leaf")) {
      return(as.integer(span$header_level %||% NA_integer_))
    }
    NA_integer_
  }), use.names = FALSE))
  leaf_level <- if (any(!is.na(span_leaf_levels))) {
    min(span_leaf_levels, na.rm = TRUE)
  } else {
    span_levels <- as.integer(unlist(lapply(spans, function(span) as.integer(span$header_level %||% NA_integer_)), use.names = FALSE))
    span_levels <- span_levels[!is.na(span_levels)]
    if (length(span_levels) > 0L) max(span_levels) + 1L else 0L
  }
  label_col_idx <- as.integer(column_header_schema$label_col_idx %||% NA_integer_)
  for (leaf in column_header_schema$leaves %||% list()) {
    col_idx <- as.integer(leaf$col_idx %||% NA_integer_)
    if (is.na(col_idx) || col_idx %in% existing_cols) {
      next
    }
    is_row_label <- isTRUE(as.logical(leaf$is_row_label_column %||% FALSE)) ||
      (!is.na(label_col_idx) && identical(col_idx, label_col_idx))
    if (!is_row_label) {
      next
    }
    spans <- c(list(list(
      header_level = leaf_level,
      row_idx = as.integer(leaf$leaf_header_row_idx %||% NA_integer_),
      label = as.character(leaf$leaf_label %||% ""),
      col_start = col_idx,
      col_end = col_idx,
      leaf_col_indices = list(col_idx),
      source = "leaf",
      source_id = as.character(leaf$leaf_id %||% ""),
      confidence = column_header_schema$confidence %||% NULL
    )), spans)
    existing_cols <- c(existing_cols, col_idx)
  }
  spans[order(
    vapply(spans, function(span) as.integer(span$header_level %||% 0L), integer(1)),
    vapply(spans, function(span) as.integer(span$row_idx %||% 0L), integer(1)),
    vapply(spans, function(span) as.integer(span$col_start %||% 0L), integer(1))
  )]
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
    cell_text_annotations = read_json_file(paths$cell_text_annotations),
    paper_footnotes = read_optional_json(paths$paper_footnotes) %||% list(),
    paper_page_furniture = read_optional_json(paths$paper_page_furniture) %||% list(),
    column_header_schemas = read_optional_json(paths$column_header_schemas) %||% list(),
    table1_continuation_groups = read_optional_json(paths$table1_continuation_groups),
    table_continuation_column_checks = read_optional_json(paths$table_continuation_column_checks),
    merged_table1_tables = read_optional_json(paths$merged_table1),
    table_definitions = read_json_file(paths$deterministic),
    continued_variable_integrations = read_optional_json(paths$continued_variable_integrations),
    parsed_tables = read_optional_json(paths$parsed),
    table_processing_status = read_optional_json(paths$processing_status),
    parse_quality_reports = read_optional_json(paths$parse_quality_reports),
    table_profiles = read_optional_json(paths$table_profiles),
    table_variable_plausibility_llm = read_optional_json(paths$variable_plausibility),
    paper_markdown = read_text_file(paths$paper_markdown),
    paper_sections = read_json_file(paths$paper_sections),
    paper_style_profile = read_optional_json(paths$paper_style_profile) %||% list(),
    paper_visual_inventory = read_optional_json(paths$paper_visual_inventory) %||% list(),
    paper_references = read_optional_json(paths$paper_references) %||% list(),
    paper_variable_inventory = read_optional_json(paths$paper_variable_inventory),
    paper_table_inventory = read_optional_json(paths$paper_table_inventory),
    table_contexts = read_table_contexts(paths$table_context_dir)
  )
}

paper_table_summary <- function(outputs) {
  rows <- lapply(seq_along(outputs$normalized_tables) - 1L, function(table_index) {
    idx <- as.integer(table_index) + 1L
    table <- outputs$normalized_tables[[idx]]
    status <- outputs$table_processing_status[[idx]]
    definition <- outputs$table_definitions[[idx]]
    schema <- outputs$column_header_schemas[[idx]]
    data.frame(
      table_index = as.integer(table_index),
      table_number = table_number_for_table(table),
      table_id = as.character(table$table_id %||% ""),
      page_num = as.integer(table$metadata$source_page_num %||% table$page_num %||% NA_integer_),
      n_rows = as.integer(table$n_rows %||% NA_integer_),
      n_cols = as.integer(table$n_cols %||% NA_integer_),
      column_label_count = length(schema$leaves %||% list()),
      variable_count = length(definition$variables %||% list()),
      failed = identical(status$status %||% "", "failed"),
      status = as.character(status$status %||% ""),
      failure_stage = as.character(status$failure_stage %||% ""),
      failure_reason = as.character(status$failure_reason %||% ""),
      title = as.character(table$title %||% table$caption %||% ""),
      stringsAsFactors = FALSE
    )
  })
  do.call(rbind, rows)
}

table_column_labels <- function(outputs, table_index = 0L, table_number = NULL) {
  selected_index <- if (!is.null(table_number)) resolve_table_index(outputs, table_number = table_number) else as.integer(table_index)
  labels <- column_header_leaf_paths_df(outputs$column_header_schemas[[selected_index + 1L]])
  labels[, c("col_idx", "leaf_label", "header_path", "is_row_label_column"), drop = FALSE]
}

table_row_labels <- function(outputs, table_index = 0L, table_number = NULL) {
  selected_index <- if (!is.null(table_number)) resolve_table_index(outputs, table_number = table_number) else as.integer(table_index)
  normalized <- outputs$normalized_tables[[selected_index + 1L]]
  schema <- column_header_schema_by_index(outputs, selected_index)
  label_col_idx <- as.integer(schema$label_col_idx %||% 0L)
  cleaned_rows <- normalized$metadata$cleaned_rows %||% list()
  row_indices <- as.integer(unlist(normalized$body_rows %||% list(), use.names = FALSE))
  data.frame(
    row_idx = row_indices,
    row_label = vapply(row_indices, function(row_idx) {
      as.character(cleaned_rows[[row_idx + 1L]][[label_col_idx + 1L]] %||% "")
    }, character(1)),
    stringsAsFactors = FALSE
  )
}

table_variable_definitions <- function(outputs, table_index = 0L, table_number = NULL) {
  selected_index <- if (!is.null(table_number)) resolve_table_index(outputs, table_number = table_number) else as.integer(table_index)
  definition <- outputs$table_definitions[[selected_index + 1L]]
  variables <- definition$variables %||% list()
  rows <- lapply(variables, function(variable) {
    levels <- vapply(variable$levels %||% list(), function(level) {
      row_idx <- as.integer(level$row_idx %||% NA_integer_)
      label <- as.character(level$level_label %||% level$level_name %||% "")
      if (is.na(row_idx)) label else sprintf("%s: %s", row_idx, label)
    }, character(1))
    data.frame(
      row_start = as.integer(variable$row_start %||% NA_integer_),
      row_end = as.integer(variable$row_end %||% NA_integer_),
      variable_name = as.character(variable$variable_name %||% ""),
      variable_label = as.character(variable$variable_label %||% ""),
      variable_type = as.character(variable$variable_type %||% ""),
      levels = paste(levels[nzchar(levels)], collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  do.call(rbind, rows)
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

paper_style_dimensions_df <- function(outputs) {
  profile <- outputs$paper_style_profile %||% list()
  dimension_names <- c(
    "footnote_marker_style",
    "bibliography_reference_style",
    "table_caption_placement",
    "figure_caption_evidence",
    "visual_reference_style"
  )
  rows <- lapply(dimension_names, function(name) {
    dimension <- profile[[name]] %||% list()
    data.frame(
      dimension = as.character(dimension$dimension %||% name),
      likely_style = as.character(dimension$likely_style %||% ""),
      confidence = as.numeric(dimension$confidence %||% NA_real_),
      count_by_style = named_count_text(dimension$count_by_style),
      count_by_source = named_count_text(dimension$count_by_source),
      secondary_counts = secondary_count_text(dimension$secondary_counts),
      evidence_count = length(dimension$evidence %||% list()),
      notes = paste(character_vector(dimension$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  do.call(rbind, rows)
}

paper_style_checks_df <- function(outputs) {
  checks <- outputs$paper_style_profile$checks %||% list()
  rows <- lapply(checks, function(check) {
    data.frame(
      check_id = as.character(check$check_id %||% ""),
      check_type = as.character(check$check_type %||% ""),
      status = as.character(check$status %||% ""),
      message = as.character(check$message %||% ""),
      evidence_count = length(check$evidence %||% list()),
      notes = paste(character_vector(check$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0L) {
    return(data.frame(
      check_id = character(),
      check_type = character(),
      status = character(),
      message = character(),
      evidence_count = integer(),
      notes = character(),
      stringsAsFactors = FALSE
    ))
  }
  do.call(rbind, rows)
}

paper_style_evidence_df <- function(outputs, dimension = NULL) {
  profile <- outputs$paper_style_profile %||% list()
  dimension_names <- c(
    "footnote_marker_style",
    "bibliography_reference_style",
    "table_caption_placement",
    "figure_caption_evidence",
    "visual_reference_style"
  )
  if (!is.null(dimension)) {
    dimension_names <- dimension_names[dimension_names %in% as.character(dimension)]
  }
  rows <- list()
  for (name in dimension_names) {
    dim_record <- profile[[name]] %||% list()
    for (evidence in dim_record$evidence %||% list()) {
      rows[[length(rows) + 1L]] <- data.frame(
        dimension = as.character(dim_record$dimension %||% name),
        evidence_id = as.character(evidence$evidence_id %||% ""),
        style = as.character(evidence$style %||% ""),
        source_artifact = as.character(evidence$source_artifact %||% ""),
        source_id = as.character(evidence$source_id %||% ""),
        page_num = as.integer(evidence$page_num %||% NA_integer_),
        table_id = as.character(evidence$table_id %||% ""),
        text = as.character(evidence$text %||% ""),
        notes = paste(character_vector(evidence$notes), collapse = " | "),
        stringsAsFactors = FALSE
      )
    }
  }
  if (length(rows) == 0L) {
    return(data.frame(
      dimension = character(),
      evidence_id = character(),
      style = character(),
      source_artifact = character(),
      source_id = character(),
      page_num = integer(),
      table_id = character(),
      text = character(),
      notes = character(),
      stringsAsFactors = FALSE
    ))
  }
  do.call(rbind, rows)
}

show_paper_style_profile <- function(paper_dir, include_evidence = FALSE) {
  outputs <- load_paper_outputs(paper_dir)
  dimensions <- paper_style_dimensions_df(outputs)
  checks <- paper_style_checks_df(outputs)

  cat(sprintf("Paper style profile for %s\n\n", normalizePath(paper_dir, winslash = "/", mustWork = TRUE)))
  if (nrow(dimensions) == 0L) {
    cat("[No style dimensions]\n")
  } else {
    print(dimensions, row.names = FALSE, right = FALSE)
  }
  cat("\nStyle consistency checks\n")
  if (nrow(checks) == 0L) {
    cat("[No checks]\n")
  } else {
    print(checks, row.names = FALSE, right = FALSE)
  }
  if (isTRUE(include_evidence)) {
    evidence <- paper_style_evidence_df(outputs)
    cat("\nStyle evidence examples\n")
    if (nrow(evidence) == 0L) {
      cat("[No evidence]\n")
    } else {
      print(evidence, row.names = FALSE, right = FALSE)
    }
    return(invisible(list(dimensions = dimensions, checks = checks, evidence = evidence)))
  }
  invisible(list(dimensions = dimensions, checks = checks))
}

paper_style_dimensions_list <- function(papers_dir = file.path("outputs", "papers")) {
  paper_dirs <- sort(list.dirs(papers_dir, full.names = TRUE, recursive = FALSE))
  dimensions <- lapply(paper_dirs, function(paper_dir) {
    outputs <- load_paper_outputs(paper_dir)
    paper_style_dimensions_df(outputs)
  })
  names(dimensions) <- basename(paper_dirs)
  dimensions
}

paper_style_checks_list <- function(papers_dir = file.path("outputs", "papers")) {
  paper_dirs <- sort(list.dirs(papers_dir, full.names = TRUE, recursive = FALSE))
  checks <- lapply(paper_dirs, function(paper_dir) {
    outputs <- load_paper_outputs(paper_dir)
    paper_style_checks_df(outputs)
  })
  names(checks) <- basename(paper_dirs)
  checks
}

paper_style_profiles_summary_df <- function(papers_dir = file.path("outputs", "papers")) {
  paper_dirs <- sort(list.dirs(papers_dir, full.names = TRUE, recursive = FALSE))
  rows <- lapply(paper_dirs, function(paper_dir) {
    outputs <- load_paper_outputs(paper_dir)
    dimensions <- paper_style_dimensions_df(outputs)
    checks <- paper_style_checks_df(outputs)
    dimension_row <- function(name) {
      match <- dimensions[dimensions$dimension == name, , drop = FALSE]
      if (nrow(match) == 0L) {
        return(list(likely_style = NA_character_, confidence = NA_real_, count_by_style = NA_character_))
      }
      list(
        likely_style = as.character(match$likely_style[[1]]),
        confidence = as.numeric(match$confidence[[1]]),
        count_by_style = as.character(match$count_by_style[[1]])
      )
    }
    check_row <- function(check_id) {
      match <- checks[checks$check_id == check_id, , drop = FALSE]
      if (nrow(match) == 0L) {
        return(list(status = NA_character_, message = NA_character_))
      }
      list(status = as.character(match$status[[1]]), message = as.character(match$message[[1]]))
    }
    bibliography <- dimension_row("bibliography_reference_style")
    footnote <- dimension_row("footnote_marker_style")
    table_caption <- dimension_row("table_caption_placement")
    figure_caption <- dimension_row("figure_caption_evidence")
    visual_reference <- dimension_row("visual_reference_style")
    bibliography_check <- check_row("bibliography_numbering_alignment")
    footnote_check <- check_row("footnote_link_coverage")
    table_caption_check <- check_row("table_caption_placement_coverage")
    figure_caption_check <- check_row("figure_caption_geometry_availability")
    visual_reference_check <- check_row("visual_reference_resolution_coverage")
    data.frame(
      paper = basename(paper_dir),
      bibliography_style = bibliography$likely_style,
      bibliography_confidence = bibliography$confidence,
      bibliography_counts = bibliography$count_by_style,
      bibliography_alignment_status = bibliography_check$status,
      bibliography_alignment_message = bibliography_check$message,
      footnote_style = footnote$likely_style,
      footnote_confidence = footnote$confidence,
      footnote_counts = footnote$count_by_style,
      footnote_link_status = footnote_check$status,
      table_caption_style = table_caption$likely_style,
      table_caption_status = table_caption_check$status,
      figure_caption_style = figure_caption$likely_style,
      figure_caption_status = figure_caption_check$status,
      visual_reference_style = visual_reference$likely_style,
      visual_reference_status = visual_reference_check$status,
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0L) {
    return(data.frame(
      paper = character(),
      bibliography_style = character(),
      bibliography_confidence = numeric(),
      bibliography_counts = character(),
      bibliography_alignment_status = character(),
      bibliography_alignment_message = character(),
      footnote_style = character(),
      footnote_confidence = numeric(),
      footnote_counts = character(),
      footnote_link_status = character(),
      table_caption_style = character(),
      table_caption_status = character(),
      figure_caption_style = character(),
      figure_caption_status = character(),
      visual_reference_style = character(),
      visual_reference_status = character(),
      stringsAsFactors = FALSE
    ))
  }
  do.call(rbind, rows)
}

show_paper_style_profiles <- function(papers_dir = file.path("outputs", "papers")) {
  summary_df <- paper_style_profiles_summary_df(papers_dir)
  cat(sprintf("Paper style profiles for %s\n\n", normalizePath(papers_dir, winslash = "/", mustWork = TRUE)))
  if (nrow(summary_df) == 0L) {
    cat("[No papers]\n")
    return(invisible(summary_df))
  }
  print(summary_df, row.names = FALSE, right = FALSE)
  invisible(summary_df)
}

paper_table_inventory_df <- function(outputs) {
  records <- outputs$paper_table_inventory$tables %||% list()
  rows <- lapply(records, function(record) {
    data.frame(
      table_number = as.character(record$table_number %||% NA_character_),
      table_id = as.character(record$table_id %||% ""),
      table_category = as.character(record$table_category %||% ""),
      category_confidence = as.numeric(record$category_confidence %||% NA_real_),
      continuation_of_table_number = as.character(record$continuation_of_table_number %||% NA_character_),
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
      table_number = character(),
      table_id = character(),
      table_category = character(),
      category_confidence = numeric(),
      continuation_of_table_number = character(),
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
      "column_header_status",
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

cell_text_annotation_table_by_index <- function(outputs, table_index = 0L) {
  annotation_tables <- outputs$cell_text_annotations %||% list()
  idx <- as.integer(table_index) + 1L
  if (idx < 1L || idx > length(annotation_tables)) {
    return(NULL)
  }
  annotation_tables[[idx]] %||% NULL
}

cell_text_annotations_df <- function(outputs, table_number = NULL, table_index = NULL) {
  empty_df <- data.frame(
    table_number = character(),
    table_index = integer(),
    table_id = character(),
    page_num = integer(),
    n_rows = integer(),
    n_cols = integer(),
    row_idx = integer(),
    col_idx = integer(),
    text = character(),
    annotation_type = character(),
    text_latex = character(),
    attached_to_text = character(),
    confidence = numeric(),
    bbox = character(),
    coordinate_frame = character(),
    diagnostics = character(),
    stringsAsFactors = FALSE
  )

  selected_table_index <- NULL
  annotation_tables <- outputs$cell_text_annotations %||% list()
  annotation_indices <- seq_along(annotation_tables) - 1L
  if (!is.null(table_number) || !is.null(table_index)) {
    selected_table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
    annotation_table <- cell_text_annotation_table_by_index(outputs, table_index = selected_table_index)
    if (is.null(annotation_table)) {
      annotation_tables <- list()
      annotation_indices <- integer()
    } else {
      annotation_tables <- list(annotation_table)
      annotation_indices <- as.integer(selected_table_index)
    }
  }

  table_count <- max(
    length(outputs$extracted_tables %||% list()),
    length(outputs$normalized_tables %||% list()),
    length(outputs$table_definitions %||% list()),
    length(outputs$parsed_tables %||% list())
  )

  rows <- list()
  for (annotation_table_position in seq_along(annotation_tables)) {
    annotation_table <- annotation_tables[[annotation_table_position]]
    if (is.null(annotation_table)) {
      next
    }
    table_id <- as.character(annotation_table$table_id %||% "")
    table_index_value <- as.integer(annotation_indices[[annotation_table_position]])

    table_number_value <- if (
      !is.na(table_index_value) &&
        table_index_value >= 0L &&
        table_index_value < table_count
    ) {
      table_number_for_outputs(outputs, table_index_value)
    } else {
      NA_character_
    }
    metadata <- annotation_table$metadata %||% list()
    diagnostics <- paste(character_vector(metadata$diagnostics), collapse = " | ")
    coordinate_frame <- as.character(metadata$coordinate_frame %||% "")
    for (annotation in annotation_table$annotations %||% list()) {
      bbox_values <- unlist(annotation$bbox %||% list(), use.names = FALSE)
      rows[[length(rows) + 1L]] <- data.frame(
        table_number = table_number_value,
        table_index = as.integer(table_index_value),
        table_id = table_id,
        page_num = as.integer(annotation_table$page_num %||% NA_integer_),
        n_rows = as.integer(annotation_table$n_rows %||% NA_integer_),
        n_cols = as.integer(annotation_table$n_cols %||% NA_integer_),
        row_idx = as.integer(annotation$row_idx %||% NA_integer_),
        col_idx = as.integer(annotation$col_idx %||% NA_integer_),
        text = as.character(annotation$text %||% ""),
        annotation_type = as.character(annotation$annotation_type %||% ""),
        text_latex = as.character(annotation$text_latex %||% ""),
        attached_to_text = as.character(annotation$attached_to_text %||% ""),
        confidence = as.numeric(annotation$confidence %||% NA_real_),
        bbox = paste(as.character(bbox_values), collapse = ","),
        coordinate_frame = coordinate_frame,
        diagnostics = diagnostics,
        stringsAsFactors = FALSE
      )
    }
  }

  if (length(rows) == 0L) {
    return(empty_df)
  }
  do.call(rbind, rows)
}

paper_footnote_filter_context <- function(outputs, table_number = NULL, table_index = NULL) {
  if (is.null(table_number) && is.null(table_index)) {
    return(NULL)
  }
  resolved_table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  list(
    table_index = as.integer(resolved_table_index),
    table_number = table_number_for_outputs(outputs, resolved_table_index),
    table_id = table_id_for_outputs(outputs, resolved_table_index),
    visual_id = table_visual_id_for_outputs(outputs, resolved_table_index)
  )
}

footnote_record_matches_context <- function(record, context) {
  table_id <- as.character(record$table_id %||% "")
  visual_id <- as.character(record$visual_id %||% "")
  identical(table_id, context$table_id) ||
    (nzchar(context$visual_id) && identical(visual_id, context$visual_id))
}

footnote_footers_df <- function(outputs, table_number = NULL, table_index = NULL) {
  empty_df <- data.frame(
    table_number = character(),
    table_index = integer(),
    table_id = character(),
    footer_id = character(),
    visual_id = character(),
    page_num = integer(),
    detection_basis = character(),
    start_row_idx = integer(),
    end_row_idx = integer(),
    row_indices = character(),
    row_texts = character(),
    raw_text = character(),
    source_artifact = character(),
    notes = character(),
    stringsAsFactors = FALSE
  )

  context <- paper_footnote_filter_context(outputs, table_number = table_number, table_index = table_index)
  footers <- outputs$paper_footnotes$footers %||% list()
  if (!is.null(context)) {
    footers <- Filter(function(footer) footnote_record_matches_context(footer, context), footers)
  }

  rows <- lapply(footers, function(footer) {
    table_id <- as.character(footer$table_id %||% "")
    row_table_index <- table_index_for_table_id(outputs, table_id)
    row_table_number <- if (is.na(row_table_index)) NA_character_ else table_number_for_outputs(outputs, row_table_index)
    footer_rows <- footer$rows %||% list()
    data.frame(
      table_number = row_table_number,
      table_index = as.integer(row_table_index),
      table_id = table_id,
      footer_id = as.character(footer$footer_id %||% ""),
      visual_id = as.character(footer$visual_id %||% ""),
      page_num = as.integer(footer$page_num %||% NA_integer_),
      detection_basis = as.character(footer$detection_basis %||% ""),
      start_row_idx = as.integer(footer$start_row_idx %||% NA_integer_),
      end_row_idx = as.integer(footer$end_row_idx %||% NA_integer_),
      row_indices = paste(vapply(footer_rows, function(row) as.character(row$row_idx %||% ""), character(1)), collapse = " | "),
      row_texts = paste(vapply(footer_rows, function(row) as.character(row$text %||% ""), character(1)), collapse = " | "),
      raw_text = as.character(footer$raw_text %||% ""),
      source_artifact = as.character(footer$source_artifact %||% ""),
      notes = paste(character_vector(footer$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })

  if (length(rows) == 0L) {
    return(empty_df)
  }
  do.call(rbind, rows)
}

footnote_anchors_df <- function(outputs, table_number = NULL, table_index = NULL) {
  empty_df <- data.frame(
    table_number = character(),
    table_index = integer(),
    table_id = character(),
    anchor_id = character(),
    glyph_raw = character(),
    glyph_key = character(),
    glyph_kind = character(),
    source_scope = character(),
    source_role = character(),
    source_id = character(),
    visual_id = character(),
    page_num = integer(),
    row_idx = integer(),
    col_idx = integer(),
    attached_to_text = character(),
    text_context = character(),
    confidence = numeric(),
    bbox = character(),
    coordinate_frame = character(),
    source_artifact = character(),
    notes = character(),
    stringsAsFactors = FALSE
  )

  context <- paper_footnote_filter_context(outputs, table_number = table_number, table_index = table_index)
  anchors <- outputs$paper_footnotes$anchors %||% list()
  if (!is.null(context)) {
    anchors <- Filter(function(anchor) footnote_record_matches_context(anchor, context), anchors)
  }

  rows <- lapply(anchors, function(anchor) {
    table_id <- as.character(anchor$table_id %||% "")
    row_table_index <- table_index_for_table_id(outputs, table_id)
    row_table_number <- if (is.na(row_table_index)) NA_character_ else table_number_for_outputs(outputs, row_table_index)
    bbox_values <- unlist(anchor$bbox %||% list(), use.names = FALSE)
    data.frame(
      table_number = row_table_number,
      table_index = as.integer(row_table_index),
      table_id = table_id,
      anchor_id = as.character(anchor$anchor_id %||% ""),
      glyph_raw = as.character(anchor$glyph_raw %||% ""),
      glyph_key = as.character(anchor$glyph_key %||% ""),
      glyph_kind = as.character(anchor$glyph_kind %||% ""),
      source_scope = as.character(anchor$source_scope %||% ""),
      source_role = as.character(anchor$source_role %||% ""),
      source_id = as.character(anchor$source_id %||% ""),
      visual_id = as.character(anchor$visual_id %||% ""),
      page_num = as.integer(anchor$page_num %||% NA_integer_),
      row_idx = as.integer(anchor$row_idx %||% NA_integer_),
      col_idx = as.integer(anchor$col_idx %||% NA_integer_),
      attached_to_text = as.character(anchor$attached_to_text %||% ""),
      text_context = as.character(anchor$text_context %||% ""),
      confidence = as.numeric(anchor$confidence %||% NA_real_),
      bbox = paste(as.character(bbox_values), collapse = ","),
      coordinate_frame = as.character(anchor$coordinate_frame %||% ""),
      source_artifact = as.character(anchor$source_artifact %||% ""),
      notes = paste(character_vector(anchor$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })

  if (length(rows) == 0L) {
    return(empty_df)
  }
  do.call(rbind, rows)
}

footnote_definitions_df <- function(outputs, table_number = NULL, table_index = NULL) {
  empty_df <- data.frame(
    table_number = character(),
    table_index = integer(),
    table_id = character(),
    definition_id = character(),
    glyph_raw = character(),
    glyph_key = character(),
    glyph_kind = character(),
    source_scope = character(),
    source_id = character(),
    visual_id = character(),
    page_num = integer(),
    raw_text = character(),
    clean_text = character(),
    definition_text = character(),
    confidence = numeric(),
    bbox = character(),
    line_index = integer(),
    source_artifact = character(),
    notes = character(),
    stringsAsFactors = FALSE
  )

  context <- paper_footnote_filter_context(outputs, table_number = table_number, table_index = table_index)
  definitions <- outputs$paper_footnotes$definitions %||% list()
  if (!is.null(context)) {
    anchor_ids <- vapply(
      Filter(
        function(anchor) footnote_record_matches_context(anchor, context),
        outputs$paper_footnotes$anchors %||% list()
      ),
      function(anchor) as.character(anchor$anchor_id %||% ""),
      character(1)
    )
    linked_definition_ids <- unique(unlist(lapply(outputs$paper_footnotes$links %||% list(), function(link) {
      if (!(as.character(link$anchor_id %||% "") %in% anchor_ids)) {
        return(character())
      }
      c(as.character(link$definition_id %||% ""), character_vector(link$candidate_definition_ids))
    }), use.names = FALSE))
    linked_definition_ids <- linked_definition_ids[nzchar(linked_definition_ids)]
    definitions <- Filter(function(definition) {
      footnote_record_matches_context(definition, context) ||
        as.character(definition$definition_id %||% "") %in% linked_definition_ids
    }, definitions)
  }

  rows <- lapply(definitions, function(definition) {
    table_id <- as.character(definition$table_id %||% "")
    row_table_index <- table_index_for_table_id(outputs, table_id)
    row_table_number <- if (is.na(row_table_index)) NA_character_ else table_number_for_outputs(outputs, row_table_index)
    bbox_values <- unlist(definition$bbox %||% list(), use.names = FALSE)
    data.frame(
      table_number = row_table_number,
      table_index = as.integer(row_table_index),
      table_id = table_id,
      definition_id = as.character(definition$definition_id %||% ""),
      glyph_raw = as.character(definition$glyph_raw %||% ""),
      glyph_key = as.character(definition$glyph_key %||% ""),
      glyph_kind = as.character(definition$glyph_kind %||% ""),
      source_scope = as.character(definition$source_scope %||% ""),
      source_id = as.character(definition$source_id %||% ""),
      visual_id = as.character(definition$visual_id %||% ""),
      page_num = as.integer(definition$page_num %||% NA_integer_),
      raw_text = as.character(definition$raw_text %||% ""),
      clean_text = as.character(definition$clean_text %||% ""),
      definition_text = as.character(definition$definition_text %||% ""),
      confidence = as.numeric(definition$confidence %||% NA_real_),
      bbox = paste(as.character(bbox_values), collapse = ","),
      line_index = as.integer(definition$line_index %||% NA_integer_),
      source_artifact = as.character(definition$source_artifact %||% ""),
      notes = paste(character_vector(definition$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })

  if (length(rows) == 0L) {
    return(empty_df)
  }
  do.call(rbind, rows)
}

footnote_links_df <- function(outputs, table_number = NULL, table_index = NULL) {
  empty_df <- data.frame(
    table_number = character(),
    table_index = integer(),
    table_id = character(),
    link_id = character(),
    anchor_id = character(),
    definition_id = character(),
    glyph_key = character(),
    link_status = character(),
    candidate_definition_ids = character(),
    link_basis = character(),
    scope_distance = character(),
    inference_type = character(),
    inference_source = character(),
    meaning_text = character(),
    marker_count = integer(),
    p_value_threshold = numeric(),
    threshold_notation = character(),
    inference_evidence = character(),
    confidence = numeric(),
    notes = character(),
    stringsAsFactors = FALSE
  )

  context <- paper_footnote_filter_context(outputs, table_number = table_number, table_index = table_index)
  anchors <- outputs$paper_footnotes$anchors %||% list()
  anchor_table_ids <- setNames(
    vapply(anchors, function(anchor) as.character(anchor$table_id %||% ""), character(1)),
    vapply(anchors, function(anchor) as.character(anchor$anchor_id %||% ""), character(1))
  )
  anchor_visual_ids <- setNames(
    vapply(anchors, function(anchor) as.character(anchor$visual_id %||% ""), character(1)),
    vapply(anchors, function(anchor) as.character(anchor$anchor_id %||% ""), character(1))
  )
  links <- outputs$paper_footnotes$links %||% list()
  if (!is.null(context)) {
    links <- Filter(function(link) {
      anchor_table_id <- anchor_table_ids[as.character(link$anchor_id %||% "")]
      anchor_visual_id <- anchor_visual_ids[as.character(link$anchor_id %||% "")]
      (!is.na(anchor_table_id) && identical(unname(anchor_table_id), context$table_id)) ||
        (
          nzchar(context$visual_id) &&
            !is.na(anchor_visual_id) &&
            identical(unname(anchor_visual_id), context$visual_id)
        )
    }, links)
  }

  rows <- lapply(links, function(link) {
    anchor_table_id <- anchor_table_ids[as.character(link$anchor_id %||% "")]
    table_id <- if (is.na(anchor_table_id)) "" else as.character(unname(anchor_table_id))
    row_table_index <- table_index_for_table_id(outputs, table_id)
    row_table_number <- if (is.na(row_table_index)) NA_character_ else table_number_for_outputs(outputs, row_table_index)
    inferred_meaning <- link$inferred_meaning %||% list()
    data.frame(
      table_number = row_table_number,
      table_index = as.integer(row_table_index),
      table_id = table_id,
      link_id = as.character(link$link_id %||% ""),
      anchor_id = as.character(link$anchor_id %||% ""),
      definition_id = as.character(link$definition_id %||% ""),
      glyph_key = as.character(link$glyph_key %||% ""),
      link_status = as.character(link$link_status %||% ""),
      candidate_definition_ids = paste(character_vector(link$candidate_definition_ids), collapse = " | "),
      link_basis = paste(character_vector(link$link_basis), collapse = " | "),
      scope_distance = as.character(link$scope_distance %||% ""),
      inference_type = as.character(inferred_meaning$inference_type %||% ""),
      inference_source = as.character(inferred_meaning$inference_source %||% ""),
      meaning_text = as.character(inferred_meaning$meaning_text %||% ""),
      marker_count = as.integer(inferred_meaning$marker_count %||% NA_integer_),
      p_value_threshold = as.numeric(inferred_meaning$p_value_threshold %||% NA_real_),
      threshold_notation = as.character(inferred_meaning$threshold_notation %||% ""),
      inference_evidence = paste(character_vector(inferred_meaning$evidence), collapse = " | "),
      confidence = as.numeric(link$confidence %||% NA_real_),
      notes = paste(character_vector(link$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })

  if (length(rows) == 0L) {
    return(empty_df)
  }
  do.call(rbind, rows)
}

show_paper_footnotes <- function(paper_dir, table_number = NULL, table_index = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  context <- paper_footnote_filter_context(outputs, table_number = table_number, table_index = table_index)
  anchors <- footnote_anchors_df(outputs, table_number = table_number, table_index = table_index)
  footers <- footnote_footers_df(outputs, table_number = table_number, table_index = table_index)
  definitions <- footnote_definitions_df(outputs, table_number = table_number, table_index = table_index)
  links <- footnote_links_df(outputs, table_number = table_number, table_index = table_index)
  metadata <- outputs$paper_footnotes$metadata %||% list()

  if (is.null(context)) {
    cat("Paper footnotes\n")
  } else if (is.na(context$table_number)) {
    cat("Paper footnotes for unnumbered table\n")
  } else {
    cat(sprintf("Paper footnotes for table_number=%s\n", as.character(context$table_number)))
  }
  cat(sprintf("paper_id: %s\n", as.character(outputs$paper_footnotes$paper_id %||% "")))
  if (!is.null(context)) {
    cat(sprintf("table_id: %s\n", context$table_id))
  }
  cat(sprintf("anchor_count: %s\n", nrow(anchors)))
  cat(sprintf("footer_count: %s\n", nrow(footers)))
  cat(sprintf("definition_count: %s\n", nrow(definitions)))
  cat(sprintf("link_count: %s\n", nrow(links)))
  cat(sprintf("resolved_link_count: %s\n", sum(links$link_status == "resolved", na.rm = TRUE)))
  cat(sprintf("ambiguous_link_count: %s\n", sum(links$link_status == "ambiguous", na.rm = TRUE)))
  cat(sprintf("inferred_link_count: %s\n", sum(links$link_status == "inferred", na.rm = TRUE)))
  cat(sprintf("unresolved_link_count: %s\n", sum(links$link_status == "unresolved", na.rm = TRUE)))

  sections <- list(
    Footers = footers[, c(
      "footer_id",
      "page_num",
      "detection_basis",
      "start_row_idx",
      "end_row_idx",
      "raw_text"
    ), drop = FALSE],
    Anchors = anchors[, c(
      "anchor_id",
      "glyph_raw",
      "glyph_key",
      "source_scope",
      "source_role",
      "row_idx",
      "col_idx",
      "attached_to_text",
      "confidence"
    ), drop = FALSE],
    Definitions = definitions[, c(
      "definition_id",
      "glyph_raw",
      "glyph_key",
      "source_scope",
      "definition_text",
      "confidence"
    ), drop = FALSE],
    Links = links[, c(
      "link_id",
      "anchor_id",
      "definition_id",
      "glyph_key",
      "link_status",
      "meaning_text",
      "scope_distance",
      "confidence"
    ), drop = FALSE]
  )
  for (section_name in names(sections)) {
    cat(sprintf("\n%s\n", section_name))
    section_df <- sections[[section_name]]
    if (nrow(section_df) == 0L) {
      cat("[No rows]\n")
    } else {
      print(section_df, row.names = FALSE, right = FALSE)
    }
  }
  invisible(list(footers = footers, anchors = anchors, definitions = definitions, links = links, metadata = metadata))
}

page_furniture_clusters_df <- function(outputs) {
  empty_df <- data.frame(
    cluster_id = character(),
    normalized_text_key = character(),
    representative_text = character(),
    page_nums = character(),
    occurrence_count = integer(),
    page_fraction = numeric(),
    recurrence_scope = character(),
    scope_page_count = integer(),
    scope_page_fraction = numeric(),
    representative_bbox = character(),
    representative_relative_bbox = character(),
    recurrence_basis = character(),
    confidence = numeric(),
    notes = character(),
    stringsAsFactors = FALSE
  )

  clusters <- outputs$paper_page_furniture$clusters %||% list()
  rows <- lapply(clusters, function(cluster) {
    data.frame(
      cluster_id = as.character(cluster$cluster_id %||% ""),
      normalized_text_key = as.character(cluster$normalized_text_key %||% ""),
      representative_text = as.character(cluster$representative_text %||% ""),
      page_nums = paste(character_vector(cluster$page_nums), collapse = ","),
      occurrence_count = as.integer(cluster$occurrence_count %||% NA_integer_),
      page_fraction = as.numeric(cluster$page_fraction %||% NA_real_),
      recurrence_scope = as.character(cluster$recurrence_scope %||% ""),
      scope_page_count = as.integer(cluster$scope_page_count %||% NA_integer_),
      scope_page_fraction = as.numeric(cluster$scope_page_fraction %||% NA_real_),
      representative_bbox = paste(character_vector(cluster$representative_bbox), collapse = ","),
      representative_relative_bbox = paste(character_vector(cluster$representative_relative_bbox), collapse = ","),
      recurrence_basis = paste(character_vector(cluster$recurrence_basis), collapse = " | "),
      confidence = as.numeric(cluster$confidence %||% NA_real_),
      notes = paste(character_vector(cluster$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })

  if (length(rows) == 0L) {
    return(empty_df)
  }
  do.call(rbind, rows)
}

page_furniture_regions_df <- function(outputs) {
  empty_df <- data.frame(
    region_id = character(),
    cluster_id = character(),
    page_num = integer(),
    bbox = character(),
    relative_bbox = character(),
    source_observation_ids = character(),
    confidence = numeric(),
    notes = character(),
    stringsAsFactors = FALSE
  )

  regions <- outputs$paper_page_furniture$ignored_regions %||% list()
  rows <- lapply(regions, function(region) {
    data.frame(
      region_id = as.character(region$region_id %||% ""),
      cluster_id = as.character(region$cluster_id %||% ""),
      page_num = as.integer(region$page_num %||% NA_integer_),
      bbox = paste(character_vector(region$bbox), collapse = ","),
      relative_bbox = paste(character_vector(region$relative_bbox), collapse = ","),
      source_observation_ids = paste(character_vector(region$source_observation_ids), collapse = " | "),
      confidence = as.numeric(region$confidence %||% NA_real_),
      notes = paste(character_vector(region$notes), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })

  if (length(rows) == 0L) {
    return(empty_df)
  }
  do.call(rbind, rows)
}

show_paper_page_furniture <- function(paper_dir) {
  outputs <- load_paper_outputs(paper_dir)
  clusters <- page_furniture_clusters_df(outputs)
  regions <- page_furniture_regions_df(outputs)
  furniture <- outputs$paper_page_furniture %||% list()
  metadata <- furniture$metadata %||% list()
  observations <- furniture$observations %||% list()

  cat("Paper page furniture\n")
  cat(sprintf("paper_id: %s\n", as.character(furniture$paper_id %||% "")))
  cat(sprintf("observation_count: %s\n", as.integer(metadata$observation_count %||% length(observations))))
  cat(sprintf("cluster_count: %s\n", nrow(clusters)))
  cat(sprintf("ignored_region_count: %s\n", nrow(regions)))
  diagnostics <- character_vector(metadata$diagnostics)
  if (length(diagnostics) > 0L) {
    cat(sprintf("diagnostics: %s\n", paste(diagnostics, collapse = " | ")))
  }

  sections <- list(
    Clusters = clusters[, c(
      "cluster_id",
      "recurrence_scope",
      "page_nums",
      "occurrence_count",
      "normalized_text_key",
      "confidence"
    ), drop = FALSE],
    "Ignored Regions" = regions[, c(
      "region_id",
      "cluster_id",
      "page_num",
      "relative_bbox",
      "confidence"
    ), drop = FALSE]
  )
  for (section_name in names(sections)) {
    cat(sprintf("\n%s\n", section_name))
    section_df <- sections[[section_name]]
    if (nrow(section_df) == 0L) {
      cat("[No rows]\n")
    } else {
      print(section_df, row.names = FALSE, right = FALSE)
    }
  }
  invisible(list(clusters = clusters, regions = regions, metadata = metadata))
}

show_column_header_tree <- function(paper_dir, table_index = 0L, table_number = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  if (!is.null(table_number)) {
    table_index <- resolve_table_index(outputs, table_number = table_number)
  }
  schema <- column_header_schema_by_index(outputs, table_index)
  if (is.null(schema)) {
    stop(sprintf("No column header schema found for table_index=%s.", table_index), call. = FALSE)
  }
  out <- column_header_leaf_paths_df(schema)
  print(out[, c("col_idx", "leaf_label", "header_path"), drop = FALSE], row.names = FALSE, right = FALSE)
  invisible(out)
}

show_column_header_trees <- function(paper_dir, table_number = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  schemas <- outputs$column_header_schemas %||% list()
  if (length(schemas) == 0L) {
    stop("No column_header_schemas.json found for this paper.", call. = FALSE)
  }
  table_indices <- seq_along(schemas) - 1L
  if (!is.null(table_number)) {
    wanted <- as.character(table_number)
    table_indices <- table_indices[vapply(table_indices, function(table_index) {
      table <- outputs$normalized_tables[[table_index + 1L]]
      identical(table_number_for_table(table), wanted)
    }, logical(1))]
  }
  rows <- lapply(table_indices, function(table_index) {
    cat(sprintf("\nTable index %s\n", as.integer(table_index)))
    out <- show_column_header_tree(paper_dir, table_index = table_index)
    if (nrow(out) == 0) {
      return(out)
    }
    cbind(table_index = as.integer(table_index), out, stringsAsFactors = FALSE)
  })
  out <- if (length(rows)) do.call(rbind, rows) else {
    data.frame(table_index = integer(), col_idx = integer(), leaf_label = character(), header_path = character())
  }
  invisible(out)
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
    match <- regexpr(
      "\\b[Tt]able\\s+((?=[A-Za-z0-9.]*[0-9])[A-Za-z0-9]+(?:\\.[A-Za-z0-9]+)*)\\b",
      text,
      perl = TRUE
    )
    if (match < 0L) {
      return(NA_character_)
    }
    matched <- regmatches(text, match)
    return(sub("^\\b[Tt]able\\s+", "", matched, perl = TRUE))
  }
  as.character(value)
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

table_id_for_outputs <- function(outputs, table_index) {
  idx <- as.integer(table_index) + 1L
  table <- (outputs$normalized_tables %||% list())[[idx]] %||%
    (outputs$extracted_tables %||% list())[[idx]] %||%
    (outputs$table_definitions %||% list())[[idx]] %||%
    (outputs$parsed_tables %||% list())[[idx]] %||%
    list()
  as.character(table$table_id %||% "")
}

table_visual_id_for_outputs <- function(outputs, table_index) {
  table_id <- table_id_for_outputs(outputs, table_index)
  if (!nzchar(table_id)) {
    return("")
  }

  for (group in outputs$table1_continuation_groups %||% list()) {
    source_table_ids <- character_vector(group$source_table_ids)
    if (table_id %in% source_table_ids) {
      table_number <- as.character(group$table_number %||% "")
      if (nzchar(table_number)) {
        return(sprintf("paper_visual:table:%s", table_number))
      }
    }
  }

  footnote_records <- c(
    outputs$paper_footnotes$anchors %||% list(),
    outputs$paper_footnotes$definitions %||% list(),
    outputs$paper_footnotes$footers %||% list()
  )
  for (record in footnote_records) {
    if (identical(as.character(record$table_id %||% ""), table_id)) {
      visual_id <- as.character(record$visual_id %||% "")
      if (nzchar(visual_id)) {
        return(visual_id)
      }
    }
  }

  table_number <- table_number_for_outputs(outputs, table_index)
  if (!is.na(table_number)) {
    return(sprintf("paper_visual:table:%s", as.character(table_number)))
  }
  ""
}

table_index_for_table_id <- function(outputs, table_id) {
  table_id <- as.character(table_id %||% "")
  if (!nzchar(table_id)) {
    return(NA_integer_)
  }
  table_count <- max(
    length(outputs$normalized_tables %||% list()),
    length(outputs$extracted_tables %||% list()),
    length(outputs$table_definitions %||% list()),
    length(outputs$parsed_tables %||% list())
  )
  for (table_index in seq_len(table_count) - 1L) {
    if (identical(table_id_for_outputs(outputs, table_index), table_id)) {
      return(as.integer(table_index))
    }
  }
  NA_integer_
}

table_index_by_number <- function(outputs, table_number) {
  requested <- as.character(table_number)
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

resolve_table_index <- function(outputs, table_number = "1", table_index = NULL) {
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
      column_headers_match = as.logical(group$column_headers_match %||% FALSE),
      table_number = as.character(group$table_number %||% NA_character_),
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
      column_headers_match = logical(),
      table_number = character(),
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

continued_variable_integrations_df <- function(outputs) {
  integrations <- outputs$continued_variable_integrations %||% list()
  rows <- lapply(integrations, function(integration) {
    metadata <- integration$metadata$continued_variable_integration %||% list()
    decisions <- metadata$boundary_decisions %||% list()
    data.frame(
      table_id = as.character(integration$table_id %||% ""),
      group_id = as.character(metadata$group_id %||% ""),
      source_table_ids = paste(as.character(unlist(metadata$source_table_ids %||% list())), collapse = " | "),
      variable_count = as.integer(length(integration$variables %||% list())),
      boundary_decision_count = as.integer(length(decisions)),
      attached_level_count = as.integer(sum(vapply(
        decisions,
        function(decision) as.integer(decision$attached_level_count %||% 0L),
        integer(1)
      ))),
      diagnostics = paste(as.character(unlist(metadata$diagnostics %||% list())), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0) {
    data.frame(
      table_id = character(),
      group_id = character(),
      source_table_ids = character(),
      variable_count = integer(),
      boundary_decision_count = integer(),
      attached_level_count = integer(),
      diagnostics = character(),
      stringsAsFactors = FALSE
    )
  } else {
    do.call(rbind, rows)
  }
}

summarize_continued_variable_integrations <- function(paper_dir) {
  outputs <- load_paper_outputs(paper_dir)
  summary_df <- continued_variable_integrations_df(outputs)
  cat(sprintf("Continued variable integrations for %s\n\n", outputs$paper_dir))
  if (nrow(summary_df) == 0) {
    cat("[No continued variable integrations]\n")
    return(invisible(summary_df))
  }
  print(summary_df, row.names = FALSE, right = FALSE)
  invisible(summary_df)
}

show_continued_variable_integration <- function(paper_dir, integration_index = 0L) {
  outputs <- load_paper_outputs(paper_dir)
  integrations <- outputs$continued_variable_integrations %||% list()
  idx <- as.integer(integration_index) + 1L
  if (idx < 1L || length(integrations) < idx) {
    stop(sprintf("No continued variable integration found for integration_index=%s.", as.integer(integration_index)), call. = FALSE)
  }
  integration <- integrations[[idx]]
  metadata <- integration$metadata$continued_variable_integration %||% list()
  cat(sprintf("Continued variable integration %s\n", as.character(metadata$group_id %||% "")))
  cat(sprintf("table_id: %s\n", as.character(integration$table_id %||% "")))
  cat(sprintf("sources: %s\n\n", paste(as.character(unlist(metadata$source_table_ids %||% list())), collapse = " | ")))

  cat("Boundary Decisions\n")
  decisions <- metadata$boundary_decisions %||% list()
  if (length(decisions) == 0) {
    cat("[No rows]\n\n")
  } else {
    decision_df <- do.call(rbind, lapply(decisions, function(decision) {
      data.frame(
        boundary_id = as.character(decision$boundary_id %||% ""),
        decision = as.character(decision$decision %||% ""),
        parent_variable_name = as.character(decision$parent_variable_name %||% ""),
        attached_level_count = as.integer(decision$attached_level_count %||% 0L),
        reasons = paste(as.character(unlist(decision$reasons %||% list())), collapse = " | "),
        stringsAsFactors = FALSE
      )
    }))
    print(decision_df, row.names = FALSE, right = FALSE)
    cat("\n")
  }

  cat("Variables\n")
  variables <- table_definition_variables(integration)
  if (length(variables) == 0) {
    cat("[No variables]\n")
  } else {
    for (variable in variables) {
      cat(sprintf(
        "%2d-%2d | %s | %s\n",
        as.integer(variable$row_start %||% -1L),
        as.integer(variable$row_end %||% -1L),
        as.character(variable$variable_type %||% ""),
        as.character(variable$variable_label %||% variable$variable_name %||% "")
      ))
      for (level in variable$levels %||% list()) {
        cat(sprintf(
          "      level row %2d | %s\n",
          as.integer(level$row_idx %||% -1L),
          as.character(level$level_label %||% level$level_name %||% "")
        ))
      }
    }
  }
  invisible(integration)
}

table_continuation_column_checks_df <- function(outputs) {
  checks <- outputs$table_continuation_column_checks %||% list()
  rows <- lapply(checks, function(check) {
    data.frame(
      check_id = as.character(check$check_id %||% ""),
      table_number = as.character(check$table_number %||% NA_character_),
      base_table_index = as.integer(check$base_table_index %||% NA_integer_),
      continuation_table_index = as.integer(check$continuation_table_index %||% NA_integer_),
      base_table_id = as.character(check$base_table_id %||% ""),
      continuation_table_id = as.character(check$continuation_table_id %||% ""),
      base_table_category = as.character(check$base_table_category %||% ""),
      continuation_table_category = as.character(check$continuation_table_category %||% ""),
      base_n_cols = as.integer(check$base_n_cols %||% NA_integer_),
      continuation_n_cols = as.integer(check$continuation_n_cols %||% NA_integer_),
      normalized_column_count_match = as.logical(check$normalized_column_count_match %||% NA),
      column_header_status = as.character(check$column_header_status %||% ""),
      overall_status = as.character(check$overall_status %||% ""),
      confidence = as.numeric(check$confidence %||% NA_real_),
      diagnostics = paste(as.character(unlist(check$diagnostics %||% list())), collapse = " | "),
      stringsAsFactors = FALSE
    )
  })
  if (length(rows) == 0) {
    data.frame(
      check_id = character(),
      table_number = character(),
      base_table_index = integer(),
      continuation_table_index = integer(),
      base_table_id = character(),
      continuation_table_id = character(),
      base_table_category = character(),
      continuation_table_category = character(),
      base_n_cols = integer(),
      continuation_n_cols = integer(),
      normalized_column_count_match = logical(),
      column_header_status = character(),
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
  cat(sprintf("table_number: %s\n", as.character(check$table_number %||% NA_character_)))
  cat(sprintf("base: %s\n", as.character(check$base_table_id %||% "")))
  cat(sprintf("continuation: %s\n", as.character(check$continuation_table_id %||% "")))
  cat(sprintf("categories: %s -> %s\n", as.character(check$base_table_category %||% ""), as.character(check$continuation_table_category %||% "")))
  cat(sprintf("columns: %s -> %s\n", as.integer(check$base_n_cols %||% NA_integer_), as.integer(check$continuation_n_cols %||% NA_integer_)))
  cat(sprintf("column_header_status: %s\n", as.character(check$column_header_status %||% "")))
  cat(sprintf("overall_status: %s\n", as.character(check$overall_status %||% "")))
  cat(sprintf("confidence: %.3f\n\n", as.numeric(check$confidence %||% NA_real_)))

  cat("Base Column Headers\n")
  cat(paste0("- ", as.character(unlist(check$base_column_headers %||% list())), collapse = "\n"))
  cat("\n\nContinuation Column Headers\n")
  cat(paste0("- ", as.character(unlist(check$continuation_column_headers %||% list())), collapse = "\n"))
  cat("\n\n")

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
    columns <- table_definition_columns(definition)
    variables <- table_definition_variables(definition)
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
      variable_count = as.integer(length(variables)),
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
      geometry_source = as.character(extracted$metadata$geometry_source %||% NA_character_),
      canonical_extraction_layer = as.character(extracted$metadata$canonical_extraction_layer %||% NA_character_),
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
      table_number = character(),
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
      geometry_source = character(),
      canonical_extraction_layer = character(),
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

show_table_processing <- function(paper_dir, table_number = "1", table_index = NULL) {
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
    cat(sprintf("Table processing for table_number=%s\n", as.character(resolved_table_number)))
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

  columns <- table_definition_columns(definition)
  variables <- table_definition_variables(definition)
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
  cat(sprintf("variable_count: %d\n", length(variables)))
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

show_parse_quality <- function(paper_dir, table_number = "1", table_index = NULL) {
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
    cat(sprintf("Parse quality for table_number=%s\n", as.character(resolved_table_number)))
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

show_cell_text_annotations <- function(paper_dir, table_number = "1", table_index = NULL) {
  outputs <- load_paper_outputs(paper_dir)
  table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  resolved_table_number <- table_number_for_outputs(outputs, table_index)
  annotation_table <- cell_text_annotation_table_by_index(outputs, table_index = table_index)
  if (is.null(annotation_table)) {
    stop(sprintf("No cell_text_annotations.json record found for table_index=%s.", as.integer(table_index)), call. = FALSE)
  }

  annotations <- cell_text_annotations_df(outputs, table_index = table_index)
  if (is.na(resolved_table_number)) {
    cat("Cell text annotations for unnumbered table\n")
  } else {
    cat(sprintf("Cell text annotations for table_number=%s\n", as.character(resolved_table_number)))
  }
  cat(sprintf("table_id: %s\n", as.character(annotation_table$table_id %||% "")))
  cat(sprintf("page_num: %s\n", as.integer(annotation_table$page_num %||% NA_integer_)))
  diagnostics <- character_vector(annotation_table$metadata$diagnostics)
  if (length(diagnostics) > 0L) {
    cat(sprintf("diagnostics: %s\n", paste(diagnostics, collapse = " | ")))
  }
  cat("\n")

  if (nrow(annotations) == 0L) {
    cat("[No cell text annotations]\n")
    return(invisible(annotations))
  }
  display_columns <- c(
    "row_idx",
    "col_idx",
    "text",
    "annotation_type",
    "text_latex",
    "attached_to_text",
    "confidence",
    "bbox"
  )
  print(annotations[, display_columns, drop = FALSE], row.names = FALSE, right = FALSE)
  invisible(annotations)
}

show_table_structure <- function(
  paper_dir,
  table_number = "1",
  table_index = NULL,
  max_rows = NULL,
  include_raw_header_rows = FALSE
) {
  outputs <- load_paper_outputs(paper_dir)
  table_index <- resolve_table_index(outputs, table_number = table_number, table_index = table_index)
  resolved_table_number <- table_number_for_outputs(outputs, table_index)
  normalized <- normalized_table_by_index(outputs, table_index)
  definition <- table_definition_by_index(outputs, table_index)
  column_header_schema <- column_header_schema_by_index(outputs, table_index)
  status_record <- table_processing_status_by_index(
    outputs,
    table_index = table_index,
    table_id = as.character(definition$table_id %||% normalized$table_id %||% "")
  )

  cleaned_rows <- normalized$metadata$cleaned_rows %||% list()
  variables <- table_definition_variables(definition)
  defined_row_indices <- integer()
  if (length(variables) > 0L) {
    for (variable in variables) {
      row_start <- as.integer(variable$row_start %||% NA_integer_)
      row_end <- as.integer(variable$row_end %||% NA_integer_)
      if (!is.na(row_start)) {
        if (!is.na(row_end) && row_end >= row_start) {
          defined_row_indices <- c(defined_row_indices, seq.int(row_start, row_end))
        } else {
          defined_row_indices <- c(defined_row_indices, row_start)
        }
      }
      for (level in variable$levels %||% list()) {
        level_row <- as.integer(level$row_idx %||% NA_integer_)
        if (!is.na(level_row)) {
          defined_row_indices <- c(defined_row_indices, level_row)
        }
      }
    }
  }
  defined_row_indices <- sort(unique(defined_row_indices))
  normalized_body_row_indices <- as.integer(character_vector(normalized$body_rows))
  normalized_body_row_indices <- normalized_body_row_indices[!is.na(normalized_body_row_indices)]
  if (length(defined_row_indices) > 0L) {
    display_row_indices <- defined_row_indices
    row_section_label <- "Rows (defined)"
  } else {
    display_row_indices <- normalized_body_row_indices
    row_section_label <- "Rows (body)"
  }
  if (length(display_row_indices) == 0L && length(cleaned_rows) > 0L) {
    display_row_indices <- seq_along(cleaned_rows) - 1L
  }
  display_row_indices <- display_row_indices[display_row_indices >= 0L & display_row_indices < length(cleaned_rows)]
  if (!is.null(max_rows)) {
    max_rows <- as.integer(max_rows)
    display_row_indices <- display_row_indices[seq_len(min(length(display_row_indices), max_rows))]
  }

  if (is.na(resolved_table_number)) {
    cat("table_number: NA\n")
  } else {
    cat(sprintf("table_number: %s\n", as.character(resolved_table_number)))
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

  cat("Column Header\n")
  header_spans <- table_structure_header_spans(definition, column_header_schema)
  if (length(header_spans) == 0L) {
    cat("[No structured column header spans]\n\n")
  } else {
    cat("level | row | cols | source | label\n")
    for (span in header_spans) {
      leaf_cols <- as.integer(character_vector(span$leaf_col_indices))
      leaf_cols <- leaf_cols[!is.na(leaf_cols)]
      if (length(leaf_cols) > 0L) {
        cols <- paste(leaf_cols, collapse = ",")
      } else {
        col_start <- as.integer(span$col_start %||% NA_integer_)
        col_end <- as.integer(span$col_end %||% NA_integer_)
        cols <- if (!is.na(col_start) && !is.na(col_end)) sprintf("%s-%s", col_start, col_end) else ""
      }
      cat(sprintf(
        "%5d | %3d | %s | %s | %s\n",
        as.integer(span$header_level %||% NA_integer_),
        as.integer(span$row_idx %||% NA_integer_),
        cols,
        as.character(span$source %||% ""),
        as.character(span$label %||% "")
      ))
    }
    cat("\n")
  }

  columns <- table_definition_columns(definition)
  leaf_paths <- column_header_leaf_paths_df(column_header_schema)
  cat("Column Header Paths\n")
  if (nrow(leaf_paths) > 0L) {
    for (i in seq_len(nrow(leaf_paths))) {
      role_suffix <- if (isTRUE(leaf_paths$is_row_label_column[[i]])) " [row_label]" else ""
      cat(sprintf("%2d | %s%s\n", leaf_paths$col_idx[[i]], leaf_paths$header_path[[i]], role_suffix))
    }
    cat("\n")
  } else if (length(columns) == 0L) {
    cat("[No column header paths]\n\n")
  } else {
    for (column in columns) {
      col_idx <- as.integer(column$col_idx %||% -1L)
      path_text <- column_header_path_text(column)
      label <- as.character(column$column_label %||% column$column_name %||% "")
      if (!nzchar(path_text)) {
        path_text <- label
      }
      cat(sprintf("%2d | %s\n", col_idx, path_text))
    }
    cat("\n")
  }

  cat(sprintf("%s\n", row_section_label))
  if (length(cleaned_rows) == 0L || length(display_row_indices) == 0L) {
    cat("[No displayed rows]\n\n")
  } else {
    for (row_idx in display_row_indices) {
      row_position <- as.integer(row_idx) + 1L
      if (row_position < 1L || row_position > length(cleaned_rows)) {
        next
      }
      cat(sprintf(
        "%2d | %s\n",
        as.integer(row_idx),
        paste(unlist(cleaned_rows[[row_position]], use.names = FALSE), collapse = " | ")
      ))
    }
    cat("\n")
  }

  if (isTRUE(include_raw_header_rows)) {
    raw_header_indices <- as.integer(character_vector(normalized$header_rows))
    raw_header_indices <- raw_header_indices[!is.na(raw_header_indices)]
    raw_header_indices <- raw_header_indices[raw_header_indices >= 0L & raw_header_indices < length(cleaned_rows)]
    cat("Raw Header Rows\n")
    if (length(cleaned_rows) == 0L || length(raw_header_indices) == 0L) {
      cat("[No raw header rows]\n\n")
    } else {
      for (row_idx in raw_header_indices) {
        row_position <- as.integer(row_idx) + 1L
        cat(sprintf(
          "%2d | %s\n",
          as.integer(row_idx),
          paste(unlist(cleaned_rows[[row_position]], use.names = FALSE), collapse = " | ")
        ))
      }
      cat("\n")
    }
  }

  cat("Columns\n")
  if (length(columns) == 0) {
    cat("[No column definitions]\n\n")
  } else {
    for (column in columns) {
      col_idx <- as.integer(column$col_idx %||% -1L)
      label <- as.character(column$column_label %||% column$column_name %||% "")
      role <- as.character(column$inferred_role %||% "")
      group_level <- as.character(column$group_level_label %||% "")
      stat <- as.character(column$statistic_subtype %||% "")
      path_text <- column_header_path_text(column)
      extras <- Filter(nzchar, c(
        if (nzchar(path_text) && !identical(path_text, label)) paste0("path=", path_text) else "",
        if (nzchar(group_level)) paste0("group_level=", group_level) else "",
        if (nzchar(stat)) paste0("stat=", stat) else ""
      ))
      suffix <- if (length(extras)) paste0(" [", paste(extras, collapse = ", "), "]") else ""
      cat(sprintf("%2d | %s | %s%s\n", col_idx, role, label, suffix))
    }
    cat("\n")
  }

  cat("Variables\n")
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
    table_definition = definition,
    column_header_schema = column_header_schema,
    header_spans = header_spans,
    columns = columns,
    variables = variables,
    displayed_rows = display_row_indices
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
    table_number_value <- if (is.na(table_index_value)) NA_character_ else table_number_for_outputs(outputs, table_index_value)
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
      table_number = character(),
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
  variables <- table_definition_variables(table_definition)
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

show_llm_variable_plausibility <- function(paper_dir, table_number = "1", table_index = NULL) {
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
    table_number_value <- if (is.na(table_index_value)) NA_character_ else table_number_for_outputs(outputs, table_index_value)
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
      table_number = character(),
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
    if (!is.null(visual$doi) && nzchar(visual$doi)) {
      cat(sprintf("doi: https://doi.org/%s\n", visual$doi))
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

show_table_context <- function(paper_dir, table_number = "1", table_index = NULL, match_type = NULL) {
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
    cat(sprintf("Table context for table_number=%s\n", as.character(resolved_table_number)))
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
