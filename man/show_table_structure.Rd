\name{show_table_structure}
\alias{show_table_structure}
\title{Show rows, columns, and semantic table definition for one table}
\description{
Prints the normalized rows, semantic columns, and variable definitions for one
table in a saved paper output directory. When available, the header also shows
the processing status and terminal failure information from
\code{table_processing_status.json}.
}
\usage{
show_table_structure(
  paper_dir,
  table_number = "1",
  table_index = NULL,
  max_rows = NULL,
  include_raw_header_rows = FALSE
)
}
\arguments{
  \item{paper_dir}{Path to one paper output directory.}
  \item{table_number}{Exact printed table identifier string, such as \code{"1"}, \code{"3.1"}, or \code{"S1"}.}
  \item{table_index}{Optional zero-based numeric table index for low-level debugging.}
  \item{max_rows}{Optional maximum number of normalized rows to print.}
  \item{include_raw_header_rows}{Whether to include normalized header rows in the row display.}
}
\value{
Invisibly returns a list with \code{normalized_table} and \code{table_definition}.
}
\examples{
\dontrun{
source("R/inspect_paper_outputs.R")
show_table_structure("outputs/papers/cobaltpaper", table_number = "1")
show_table_structure("outputs/papers/cobaltpaper", table_number = "3.1", max_rows = 20L)
}
}
