pt1_is_missing_scalar <- function(x) {
  length(x) == 1 && is.atomic(x) && is.na(x)
}

pt1_clean_scalar <- function(x, default = NULL) {
  if (is.null(x) || length(x) == 0 || pt1_is_missing_scalar(x)) {
    return(default)
  }
  x[[1]]
}

pt1_character_or_null <- function(x) {
  value <- pt1_clean_scalar(x, default = NULL)
  if (is.null(value)) {
    return(NULL)
  }
  as.character(value)
}

pt1_numeric_or_null <- function(x) {
  value <- pt1_clean_scalar(x, default = NULL)
  if (is.null(value)) {
    return(NULL)
  }
  as.numeric(value)
}

pt1_integer_or_null <- function(x) {
  value <- pt1_clean_scalar(x, default = NULL)
  if (is.null(value)) {
    return(NULL)
  }
  as.integer(value)
}

pt1_logical_or_false <- function(x) {
  value <- pt1_clean_scalar(x, default = FALSE)
  as.logical(value)
}

pt1_character_vector <- function(x) {
  if (is.null(x) || length(x) == 0) {
    return(character())
  }
  as.character(unlist(x, use.names = FALSE))
}

pt1_order_by_col_idx <- function(x) {
  if (length(x) == 0) {
    return(list())
  }
  x[order(vapply(x, function(item) as.integer(pt1_clean_scalar(item$col_idx, default = -1L)), integer(1)))]
}

pt1_table_definition_variables <- function(table_definition) {
  table_definition$variables %||% list()
}

pt1_table_definition_column_definition <- function(table_definition) {
  table_definition$column_definition %||% list()
}

pt1_table_definition_columns <- function(table_definition, parsed_table = NULL) {
  column_definition <- pt1_table_definition_column_definition(table_definition)
  columns <- column_definition$columns %||% table_definition$columns %||% list()
  if (length(columns) == 0 && !is.null(parsed_table)) {
    columns <- parsed_table$columns %||% list()
  }
  pt1_order_by_col_idx(columns)
}

pt1_pick_table_by_index <- function(x, table_index = 0L) {
  index <- as.integer(table_index) + 1L
  if (index < 1L || index > length(x)) {
    stop(sprintf("No table found for table_index=%s.", as.integer(table_index)), call. = FALSE)
  }
  x[[index]]
}

pt1_table_number_for_table <- function(table) {
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

pt1_table_index_by_number <- function(tables, table_number) {
  requested <- as.integer(table_number)
  matches <- which(vapply(
    tables %||% list(),
    function(x) identical(pt1_table_number_for_table(x), requested),
    logical(1)
  ))
  if (length(matches) == 0) {
    stop(sprintf("No table found for table_number=%s.", requested), call. = FALSE)
  }
  as.integer(matches[[1]] - 1L)
}

pt1_is_statistic_role <- function(role) {
  role %in% c("p_value", "smd", "statistic")
}

pt1_variable_lookup <- function(table_definition) {
  variables <- pt1_table_definition_variables(table_definition)
  names(variables) <- vapply(
    variables,
    function(variable) pt1_character_or_null(variable$variable_name) %||% "",
    character(1)
  )
  variables
}

`%||%` <- function(x, y) {
  pt1_null_coalesce(x, y)
}

new_observed_footnotes <- function(
  anchors = list(),
  definitions = list(),
  links = list(),
  metadata = list(),
  printToggle = TRUE,
  quote = FALSE,
  noSpaces = FALSE
) {
  object <- list(
    Anchors = anchors %||% list(),
    Definitions = definitions %||% list(),
    Links = links %||% list(),
    MetaData = metadata %||% list(),
    anchors = anchors %||% list(),
    definitions = definitions %||% list(),
    links = links %||% list(),
    metadata = metadata %||% list(),
    printToggle = as.logical(printToggle),
    quote = as.logical(quote),
    noSpaces = as.logical(noSpaces)
  )
  class(object) <- "ObservedFootnotes"
  validate_observed_footnotes(object)
}

validate_observed_footnotes <- function(x) {
  if (!inherits(x, "ObservedFootnotes")) {
    stop("Object must inherit from 'ObservedFootnotes'.", call. = FALSE)
  }
  if (!is.list(x$Anchors) || !is.list(x$Definitions) || !is.list(x$Links)) {
    stop("ObservedFootnotes must contain list fields Anchors, Definitions, and Links.", call. = FALSE)
  }
  if (!is.list(x$MetaData)) {
    stop("ObservedFootnotes$MetaData must be a list.", call. = FALSE)
  }
  x
}

print.ObservedFootnotes <- function(x, printToggle = x$printToggle, quote = x$quote, noSpaces = x$noSpaces, ...) {
  validate_observed_footnotes(x)
  if (!isTRUE(printToggle)) {
    return(invisible(x))
  }
  cat("<ObservedFootnotes>\n")
  table_id <- pt1_character_or_null(x$MetaData$table_id)
  table_number <- pt1_integer_or_null(x$MetaData$table_number)
  if (!is.null(table_id) && nzchar(table_id)) {
    cat(sprintf("table_id: %s\n", table_id))
  }
  if (!is.null(table_number) && !is.na(table_number)) {
    cat(sprintf("table_number: %s\n", table_number))
  }
  cat(sprintf("anchors: %d\n", length(x$Anchors %||% list())))
  cat(sprintf("definitions: %d\n", length(x$Definitions %||% list())))
  cat(sprintf("links: %d\n", length(x$Links %||% list())))
  link_statuses <- vapply(x$Links %||% list(), function(link) {
    pt1_character_or_null(link$link_status) %||% "unknown"
  }, character(1))
  if (length(link_statuses) > 0L) {
    status_counts <- table(link_statuses)
    cat(sprintf("link_status: %s\n", paste(sprintf("%s=%s", names(status_counts), as.integer(status_counts)), collapse = ", ")))
  }
  anchors <- x$Anchors %||% list()
  if (length(anchors) > 0L) {
    first_anchor <- anchors[[1]]
    first_anchor_glyph <- as.character(first_anchor$glyph_raw %||% "")
    if (isTRUE(noSpaces)) {
      first_anchor_glyph <- gsub("\\s+", "", first_anchor_glyph)
    }
    if (isTRUE(quote)) {
      first_anchor_glyph <- shQuote(first_anchor_glyph)
    }
    cat(sprintf(
      "first_anchor: %s %s %s\n",
      pt1_character_or_null(first_anchor$anchor_id) %||% "",
      first_anchor_glyph,
      pt1_character_or_null(first_anchor$source_id) %||% ""
    ))
  }
  invisible(x)
}

build_observed_footnotes <- function(
  paper_footnotes = NULL,
  table_id = NULL,
  table_number = NULL,
  printToggle = TRUE,
  quote = FALSE,
  noSpaces = FALSE
) {
  if (is.null(paper_footnotes) || length(paper_footnotes) == 0L) {
    return(new_observed_footnotes(
      metadata = list(table_id = table_id, table_number = table_number),
      printToggle = printToggle,
      quote = quote,
      noSpaces = noSpaces
    ))
  }

  resolved_table_id <- pt1_character_or_null(table_id) %||% ""
  anchors <- paper_footnotes$anchors %||% list()
  if (nzchar(resolved_table_id)) {
    anchors <- Filter(function(anchor) identical(pt1_character_or_null(anchor$table_id) %||% "", resolved_table_id), anchors)
  }
  anchor_ids <- vapply(anchors, function(anchor) pt1_character_or_null(anchor$anchor_id) %||% "", character(1))
  links <- Filter(function(link) {
    (pt1_character_or_null(link$anchor_id) %||% "") %in% anchor_ids
  }, paper_footnotes$links %||% list())
  linked_definition_ids <- unique(unlist(lapply(links, function(link) {
    c(pt1_character_or_null(link$definition_id) %||% "", pt1_character_vector(link$candidate_definition_ids))
  }), use.names = FALSE))
  linked_definition_ids <- linked_definition_ids[nzchar(linked_definition_ids)]
  definitions <- Filter(function(definition) {
    identical(pt1_character_or_null(definition$table_id) %||% "", resolved_table_id) ||
      (pt1_character_or_null(definition$definition_id) %||% "") %in% linked_definition_ids
  }, paper_footnotes$definitions %||% list())
  link_statuses <- vapply(links, function(link) pt1_character_or_null(link$link_status) %||% "", character(1))
  source_metadata <- paper_footnotes$metadata %||% list()
  metadata <- modifyList(
    source_metadata,
    list(
      paper_id = pt1_character_or_null(paper_footnotes$paper_id),
      source_pdf = pt1_character_or_null(paper_footnotes$source_pdf),
      table_id = table_id,
      table_number = table_number,
      anchor_count = length(anchors),
      definition_count = length(definitions),
      link_count = length(links),
      resolved_link_count = sum(link_statuses == "resolved", na.rm = TRUE),
      ambiguous_link_count = sum(link_statuses == "ambiguous", na.rm = TRUE),
      inferred_link_count = sum(link_statuses == "inferred", na.rm = TRUE),
      unresolved_link_count = sum(link_statuses == "unresolved", na.rm = TRUE)
    )
  )
  new_observed_footnotes(
    anchors = anchors,
    definitions = definitions,
    links = links,
    metadata = metadata,
    printToggle = printToggle,
    quote = quote,
    noSpaces = noSpaces
  )
}

new_observed_table_one <- function(
  table_id,
  title = NULL,
  caption = NULL,
  metadata = list(),
  columns = list(),
  continuous = list(variables = list(), values = list()),
  categorical = list(variables = list(), values = list()),
  footnotes = NULL,
  statistics = list(),
  provenance = list(),
  notes = character(),
  overall_confidence = NULL
) {
  footnotes <- footnotes %||% new_observed_footnotes(metadata = list(table_id = table_id))
  object <- list(
    table_id = as.character(table_id),
    title = pt1_character_or_null(title),
    caption = pt1_character_or_null(caption),
    ContTable = continuous,
    CatTable = categorical,
    Footnotes = footnotes,
    MetaData = metadata,
    metadata = metadata,
    columns = columns,
    continuous = continuous,
    categorical = categorical,
    footnotes = footnotes,
    statistics = statistics,
    provenance = provenance,
    notes = pt1_character_vector(notes),
    overall_confidence = pt1_numeric_or_null(overall_confidence)
  )
  class(object) <- "ObservedTableOne"
  validate_observed_table_one(object)
}

validate_observed_table_one <- function(x) {
  if (!inherits(x, "ObservedTableOne")) {
    stop("Object must inherit from 'ObservedTableOne'.", call. = FALSE)
  }
  if (is.null(x$table_id) || !nzchar(x$table_id)) {
    stop("ObservedTableOne$table_id must be a non-empty string.", call. = FALSE)
  }
  if (!is.list(x$metadata)) {
    stop("ObservedTableOne$metadata must be a list.", call. = FALSE)
  }
  if (!is.list(x$MetaData)) {
    stop("ObservedTableOne$MetaData must be a list.", call. = FALSE)
  }
  if (!is.list(x$columns)) {
    stop("ObservedTableOne$columns must be a list.", call. = FALSE)
  }
  if (!is.list(x$ContTable) || is.null(x$ContTable$variables) || is.null(x$ContTable$values)) {
    stop("ObservedTableOne$ContTable must contain 'variables' and 'values' lists.", call. = FALSE)
  }
  if (!is.list(x$CatTable) || is.null(x$CatTable$variables) || is.null(x$CatTable$values)) {
    stop("ObservedTableOne$CatTable must contain 'variables' and 'values' lists.", call. = FALSE)
  }
  if (!is.list(x$continuous) || is.null(x$continuous$variables) || is.null(x$continuous$values)) {
    stop("ObservedTableOne$continuous must contain 'variables' and 'values' lists.", call. = FALSE)
  }
  if (!is.list(x$categorical) || is.null(x$categorical$variables) || is.null(x$categorical$values)) {
    stop("ObservedTableOne$categorical must contain 'variables' and 'values' lists.", call. = FALSE)
  }
  if (!inherits(x$Footnotes, "ObservedFootnotes")) {
    stop("ObservedTableOne$Footnotes must inherit from 'ObservedFootnotes'.", call. = FALSE)
  }
  if (!is.list(x$statistics)) {
    stop("ObservedTableOne$statistics must be a list.", call. = FALSE)
  }
  x
}

print.ObservedTableOne <- function(x, ...) {
  validate_observed_table_one(x)
  cat("<ObservedTableOne>\n")
  cat(sprintf("table_id: %s\n", x$table_id))
  if (!is.null(x$title) && nzchar(x$title)) {
    cat(sprintf("title: %s\n", x$title))
  }
  if (!is.null(x$caption) && nzchar(x$caption) && !identical(x$caption, x$title)) {
    cat(sprintf("caption: %s\n", x$caption))
  }
  cat(sprintf("variables: %d\n", length(x$MetaData$vars %||% x$metadata$variables %||% list())))
  cat(sprintf("continuous variables: %d\n", length(x$ContTable$variables %||% list())))
  cat(sprintf("categorical variables: %d\n", length(x$CatTable$variables %||% list())))
  cat(sprintf("columns: %d\n", length(x$columns %||% list())))
  cat(sprintf("statistics: %d\n", length(x$statistics %||% list())))
  cat(sprintf("footnote links: %d\n", length(x$Footnotes$Links %||% list())))
  grouping_label <- pt1_character_or_null(x$MetaData$grouping_label %||% x$metadata$grouping_label)
  if (!is.null(grouping_label) && nzchar(grouping_label)) {
    cat(sprintf("grouping: %s\n", grouping_label))
  }
  processing_status <- pt1_character_or_null(x$provenance$processing_status)
  if (!is.null(processing_status) && nzchar(processing_status)) {
    cat(sprintf("processing status: %s\n", processing_status))
    failure_stage <- pt1_character_or_null(x$provenance$failure_stage)
    failure_reason <- pt1_character_or_null(x$provenance$failure_reason)
    if (!is.null(failure_stage) && nzchar(failure_stage)) {
      cat(sprintf("failure_stage: %s\n", failure_stage))
    }
    if (!is.null(failure_reason) && nzchar(failure_reason)) {
      cat(sprintf("failure_reason: %s\n", failure_reason))
    }
  }
  invisible(x)
}

build_observed_metadata <- function(table_definition, parsed_table) {
  variables <- lapply(pt1_table_definition_variables(table_definition), function(variable) {
    list(
      variable_name = pt1_character_or_null(variable$variable_name),
      variable_label = pt1_character_or_null(variable$variable_label),
      variable_type = pt1_character_or_null(variable$variable_type),
      row_start = pt1_integer_or_null(variable$row_start),
      row_end = pt1_integer_or_null(variable$row_end),
      summary_style_hint = pt1_character_or_null(variable$summary_style_hint),
      units_hint = pt1_character_or_null(variable$units_hint),
      printed_levels = lapply(variable$levels %||% list(), function(level) {
        list(
          level_name = pt1_character_or_null(level$level_name),
          level_label = pt1_character_or_null(level$level_label),
          row_idx = pt1_integer_or_null(level$row_idx),
          confidence = pt1_numeric_or_null(level$confidence)
        )
      }),
      confidence = pt1_numeric_or_null(variable$confidence)
    )
  })
  column_definition <- pt1_table_definition_column_definition(table_definition)
  columns <- pt1_table_definition_columns(table_definition)
  variable_order <- vapply(variables, function(variable) variable$variable_name %||% "", character(1))
  variable_type_by_order <- vapply(variables, function(variable) variable$variable_type %||% "unknown", character(1))
  logi_factors <- variable_type_by_order %in% c("binary", "categorical")
  var_labels <- lapply(variables, function(variable) variable$variable_label)
  names(var_labels) <- variable_order
  source_tableone <- table_definition$metadata$tableone %||% list()
  list(
    vars = pt1_character_vector(source_tableone$vars %||% variable_order),
    logiFactors = as.logical(unlist(source_tableone$logiFactors %||% logi_factors, use.names = FALSE)),
    varFactors = pt1_character_vector(source_tableone$varFactors %||% variable_order[logi_factors]),
    varNumerics = pt1_character_vector(source_tableone$varNumerics %||% variable_order[variable_type_by_order == "continuous"]),
    percentMissing = source_tableone$percentMissing %||% setNames(rep(NA_real_, length(variable_order)), variable_order),
    varLabels = source_tableone$varLabels %||% var_labels,
    variable_order = variable_order,
    variables = variables,
    grouping_label = pt1_character_or_null(column_definition$grouping_label),
    grouping_name = pt1_character_or_null(column_definition$grouping_name),
    column_header_spans = column_definition$header_spans %||% list(),
    overall_column_present = any(vapply(columns, function(column) identical(pt1_character_or_null(column$inferred_role), "overall"), logical(1))),
    statistic_columns = lapply(
      Filter(function(column) pt1_is_statistic_role(pt1_character_or_null(column$inferred_role) %||% "unknown"), columns),
      function(column) {
        list(
          col_idx = pt1_integer_or_null(column$col_idx),
          column_name = pt1_character_or_null(column$column_name),
          column_label = pt1_character_or_null(column$column_label),
          role = pt1_character_or_null(column$inferred_role),
          statistic_subtype = pt1_character_or_null(column$statistic_subtype),
          confidence = pt1_numeric_or_null(column$confidence)
        )
      }
    ),
    source_json = list(
      table_definition_table_id = pt1_character_or_null(table_definition$table_id),
      parsed_table_table_id = pt1_character_or_null(parsed_table$table_id)
    )
  )
}

build_observed_columns <- function(table_definition, parsed_table) {
  definition_columns <- pt1_table_definition_columns(table_definition, parsed_table)
  lapply(definition_columns, function(column) {
    list(
      col_idx = pt1_integer_or_null(column$col_idx),
      column_name = pt1_character_or_null(column$column_name),
      column_label = pt1_character_or_null(column$column_label),
      header_leaf_id = pt1_character_or_null(column$header_leaf_id),
      header_leaf_label = pt1_character_or_null(column$header_leaf_label),
      header_group_ids = pt1_character_vector(column$header_group_ids),
      header_group_labels = pt1_character_vector(column$header_group_labels),
      header_path = pt1_character_vector(column$header_path),
      role = pt1_character_or_null(column$inferred_role),
      grouping_variable_hint = pt1_character_or_null(column$grouping_variable_hint),
      group_level_label = pt1_character_or_null(column$group_level_label),
      group_level_name = pt1_character_or_null(column$group_level_name),
      group_order = pt1_integer_or_null(column$group_order),
      statistic_subtype = pt1_character_or_null(column$statistic_subtype),
      confidence = pt1_numeric_or_null(column$confidence)
    )
  })
}

build_observed_continuous <- function(table_definition, parsed_table, columns) {
  variable_lookup <- pt1_variable_lookup(table_definition)
  statistic_col_idx <- vapply(
    Filter(function(column) pt1_is_statistic_role(column$role %||% "unknown"), columns),
    function(column) pt1_integer_or_null(column$col_idx) %||% -1L,
    integer(1)
  )
  variables <- Filter(function(variable) {
    identical(pt1_character_or_null(variable$variable_type), "continuous")
  }, pt1_table_definition_variables(table_definition))
  variable_names <- vapply(variables, function(variable) pt1_character_or_null(variable$variable_name) %||% "", character(1))
  values <- lapply(
    Filter(function(value) {
      variable_name <- pt1_character_or_null(value$variable_name) %||% ""
      level_label <- pt1_character_or_null(value$level_label)
      col_idx <- pt1_integer_or_null(value$col_idx) %||% -1L
      variable_name %in% variable_names && is.null(level_label) && !(col_idx %in% statistic_col_idx)
    }, parsed_table$values %||% list()),
    function(value) {
      variable <- variable_lookup[[pt1_character_or_null(value$variable_name) %||% ""]] %||% list()
      list(
        variable_name = pt1_character_or_null(value$variable_name),
        variable_label = pt1_character_or_null(variable$variable_label),
        row_idx = pt1_integer_or_null(value$row_idx),
        column_name = pt1_character_or_null(value$column_name),
        col_idx = pt1_integer_or_null(value$col_idx),
        raw_value = pt1_character_or_null(value$raw_value),
        summary_style_hint = pt1_character_or_null(variable$summary_style_hint),
        parsed_numeric = pt1_numeric_or_null(value$parsed_numeric),
        parsed_secondary_numeric = pt1_numeric_or_null(value$parsed_secondary_numeric),
        confidence = pt1_numeric_or_null(value$confidence)
      )
    }
  )
  list(
    variables = lapply(variables, function(variable) {
      list(
        variable_name = pt1_character_or_null(variable$variable_name),
        variable_label = pt1_character_or_null(variable$variable_label),
        row_start = pt1_integer_or_null(variable$row_start),
        row_end = pt1_integer_or_null(variable$row_end),
        summary_style_hint = pt1_character_or_null(variable$summary_style_hint),
        units_hint = pt1_character_or_null(variable$units_hint),
        confidence = pt1_numeric_or_null(variable$confidence)
      )
    }),
    values = values
  )
}

build_observed_categorical <- function(table_definition, parsed_table, columns) {
  variable_lookup <- pt1_variable_lookup(table_definition)
  statistic_col_idx <- vapply(
    Filter(function(column) pt1_is_statistic_role(column$role %||% "unknown"), columns),
    function(column) pt1_integer_or_null(column$col_idx) %||% -1L,
    integer(1)
  )
  variables <- Filter(function(variable) {
    length(variable$levels %||% list()) > 0
  }, pt1_table_definition_variables(table_definition))
  variable_names <- vapply(variables, function(variable) pt1_character_or_null(variable$variable_name) %||% "", character(1))
  values <- lapply(
    Filter(function(value) {
      variable_name <- pt1_character_or_null(value$variable_name) %||% ""
      level_label <- pt1_character_or_null(value$level_label)
      col_idx <- pt1_integer_or_null(value$col_idx) %||% -1L
      variable_name %in% variable_names && !is.null(level_label) && !(col_idx %in% statistic_col_idx)
    }, parsed_table$values %||% list()),
    function(value) {
      variable <- variable_lookup[[pt1_character_or_null(value$variable_name) %||% ""]] %||% list()
      list(
        variable_name = pt1_character_or_null(value$variable_name),
        variable_label = pt1_character_or_null(variable$variable_label),
        level_label = pt1_character_or_null(value$level_label),
        row_idx = pt1_integer_or_null(value$row_idx),
        column_name = pt1_character_or_null(value$column_name),
        col_idx = pt1_integer_or_null(value$col_idx),
        raw_value = pt1_character_or_null(value$raw_value),
        parsed_count = pt1_numeric_or_null(value$parsed_numeric),
        parsed_percent = pt1_numeric_or_null(value$parsed_secondary_numeric),
        confidence = pt1_numeric_or_null(value$confidence)
      )
    }
  )
  list(
    variables = lapply(variables, function(variable) {
      list(
        variable_name = pt1_character_or_null(variable$variable_name),
        variable_label = pt1_character_or_null(variable$variable_label),
        variable_type = pt1_character_or_null(variable$variable_type),
        row_start = pt1_integer_or_null(variable$row_start),
        row_end = pt1_integer_or_null(variable$row_end),
        printed_levels = lapply(variable$levels %||% list(), function(level) {
          list(
            level_name = pt1_character_or_null(level$level_name),
            level_label = pt1_character_or_null(level$level_label),
            row_idx = pt1_integer_or_null(level$row_idx),
            confidence = pt1_numeric_or_null(level$confidence)
          )
        }),
        confidence = pt1_numeric_or_null(variable$confidence)
      )
    }),
    values = values
  )
}

build_observed_statistics <- function(parsed_table, columns) {
  statistic_columns <- Filter(function(column) pt1_is_statistic_role(column$role %||% "unknown"), columns)
  if (length(statistic_columns) == 0) {
    return(list())
  }
  statistic_lookup <- statistic_columns
  names(statistic_lookup) <- vapply(statistic_lookup, function(column) as.character(column$col_idx %||% -1L), character(1))
  lapply(
    Filter(function(value) {
      as.character(pt1_integer_or_null(value$col_idx) %||% -1L) %in% names(statistic_lookup)
    }, parsed_table$values %||% list()),
    function(value) {
      column <- statistic_lookup[[as.character(pt1_integer_or_null(value$col_idx) %||% -1L)]]
      list(
        variable_name = pt1_character_or_null(value$variable_name),
        level_label = pt1_character_or_null(value$level_label),
        row_idx = pt1_integer_or_null(value$row_idx),
        column_name = pt1_character_or_null(value$column_name),
        col_idx = pt1_integer_or_null(value$col_idx),
        raw_value = pt1_character_or_null(value$raw_value),
        statistic_type = pt1_character_or_null(column$role),
        statistic_subtype = pt1_character_or_null(column$statistic_subtype),
        parsed_numeric = pt1_numeric_or_null(value$parsed_numeric),
        confidence = pt1_numeric_or_null(value$confidence)
      )
    }
  )
}

build_observed_table_one <- function(
  table_definition,
  parsed_table,
  normalized_table = NULL,
  provenance = NULL,
  footnotes = NULL
) {
  table_definition_id <- pt1_character_or_null(table_definition$table_id)
  parsed_table_id <- pt1_character_or_null(parsed_table$table_id)
  if (!is.null(table_definition_id) && !is.null(parsed_table_id) && !identical(table_definition_id, parsed_table_id)) {
    stop("table_definition$table_id and parsed_table$table_id must match.", call. = FALSE)
  }
  columns <- build_observed_columns(table_definition, parsed_table)
  metadata <- build_observed_metadata(table_definition, parsed_table)
  continuous <- build_observed_continuous(table_definition, parsed_table, columns)
  categorical <- build_observed_categorical(table_definition, parsed_table, columns)
  statistics <- build_observed_statistics(parsed_table, columns)
  notes <- unique(c(
    pt1_character_vector(table_definition$notes),
    pt1_character_vector(parsed_table$notes)
  ))
  new_observed_table_one(
    table_id = table_definition_id %||% parsed_table_id,
    title = pt1_character_or_null(table_definition$title) %||% pt1_character_or_null(parsed_table$title),
    caption = pt1_character_or_null(table_definition$caption) %||% pt1_character_or_null(parsed_table$caption),
    metadata = metadata,
    columns = columns,
    continuous = continuous,
    categorical = categorical,
    footnotes = footnotes,
    statistics = statistics,
    provenance = provenance %||% list(
      table_definition_table_id = table_definition_id,
      parsed_table_table_id = parsed_table_id,
      normalized_table_table_id = pt1_character_or_null(normalized_table$table_id)
    ),
    notes = notes,
    overall_confidence = pt1_numeric_or_null(parsed_table$overall_confidence) %||% pt1_numeric_or_null(table_definition$overall_confidence)
  )
}

build_observed_table_one_from_paper_dir <- function(paper_dir, table_number = 1L, table_index = NULL) {
  paper_dir <- normalizePath(paper_dir, winslash = "/", mustWork = TRUE)
  table_definitions_path <- file.path(paper_dir, "table_definitions.json")
  parsed_tables_path <- file.path(paper_dir, "parsed_tables.json")
  normalized_tables_path <- file.path(paper_dir, "normalized_tables.json")
  processing_status_path <- file.path(paper_dir, "table_processing_status.json")
  paper_footnotes_path <- file.path(paper_dir, "paper_footnotes.json")

  table_definitions <- pt1_load_json_array(table_definitions_path)
  parsed_tables <- pt1_load_json_array(parsed_tables_path)
  normalized_tables <- pt1_read_optional_json(normalized_tables_path)
  processing_status_payload <- pt1_read_optional_json(processing_status_path)
  paper_footnotes <- pt1_read_optional_json(paper_footnotes_path)
  normalized_table_list <- if (is.null(normalized_tables)) list() else pt1_unwrap_table_array(normalized_tables)
  processing_status_list <- if (is.null(processing_status_payload)) list() else pt1_unwrap_table_array(processing_status_payload)
  resolved_table_index <- if (!is.null(table_index)) {
    as.integer(table_index)
  } else if (!is.null(table_number)) {
    if (length(normalized_table_list) > 0) {
      pt1_table_index_by_number(normalized_table_list, table_number)
    } else {
      pt1_table_index_by_number(table_definitions, table_number)
    }
  } else {
    stop("Provide table_number for public construction, or table_index for low-level debugging.", call. = FALSE)
  }

  table_definition <- pt1_pick_table_by_index(table_definitions, resolved_table_index)
  parsed_table <- pt1_pick_table_by_index(parsed_tables, resolved_table_index)
  normalized_table <- if (length(normalized_table_list) > as.integer(resolved_table_index)) {
    pt1_pick_table_by_index(normalized_table_list, resolved_table_index)
  } else {
    NULL
  }
  resolved_table_number <- if (!is.null(normalized_table)) {
    pt1_table_number_for_table(normalized_table)
  } else {
    pt1_table_number_for_table(table_definition)
  }
  processing_status <- NULL
  if (length(processing_status_list) > 0) {
    matching_statuses <- Filter(
      function(x) identical(
        pt1_character_or_null(x$table_id) %||% "",
        pt1_character_or_null(table_definition$table_id) %||% pt1_character_or_null(parsed_table$table_id) %||% ""
      ),
      processing_status_list
    )
    if (length(matching_statuses) > 0) {
      processing_status <- matching_statuses[[1]]
    } else if (length(processing_status_list) > as.integer(resolved_table_index)) {
      processing_status <- pt1_pick_table_by_index(processing_status_list, resolved_table_index)
    }
  }
  footnotes <- build_observed_footnotes(
    paper_footnotes = paper_footnotes,
    table_id = pt1_character_or_null(table_definition$table_id) %||% pt1_character_or_null(parsed_table$table_id),
    table_number = resolved_table_number
  )

  build_observed_table_one(
    table_definition = table_definition,
    parsed_table = parsed_table,
    normalized_table = normalized_table,
    footnotes = footnotes,
    provenance = list(
      paper_dir = paper_dir,
      table_number = resolved_table_number,
      table_definition_source = table_definitions_path,
      parsed_table_source = parsed_tables_path,
      normalized_table_source = if (file.exists(normalized_tables_path)) normalized_tables_path else NULL,
      processing_status_source = if (file.exists(processing_status_path)) processing_status_path else NULL,
      paper_footnotes_source = if (file.exists(paper_footnotes_path)) paper_footnotes_path else NULL,
      processing_status = pt1_character_or_null(processing_status$status),
      failure_stage = pt1_character_or_null(processing_status$failure_stage),
      failure_reason = pt1_character_or_null(processing_status$failure_reason),
      builder_version = "0.1.0"
    )
  )
}
