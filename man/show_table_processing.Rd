\name{show_table_processing}
\alias{show_table_processing}
\title{Show processing status and rescue attempts for one table}
\description{
Prints one table's processing status, failure details, notes, and the recorded rescue-attempt rows
from \code{table_processing_status.json}.
}
\usage{
show_table_processing(paper_dir, table_number = "1", table_index = NULL)
}
\arguments{
  \item{paper_dir}{Path to one paper output directory.}
  \item{table_number}{Exact printed table identifier string, such as \code{"1"}, \code{"3.1"}, or \code{"S1"}.}
  \item{table_index}{Optional zero-based numeric table index for low-level debugging.}
}
\value{
Invisibly returns the matching processing-status record when present, otherwise \code{NULL}.
}
\examples{
\dontrun{
source("R/inspect_paper_outputs.R")
show_table_processing("outputs/papers/cobaltpaper", table_number = "1")
}
}
