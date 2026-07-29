\name{show_table_context}
\alias{show_table_context}
\title{Show retrieved paper context for one table}
\description{
Prints the retrieved passages for one table context, including passage IDs, headings, match types, and text.
}
\usage{
show_table_context(paper_dir, table_number = "1", table_index = NULL, match_type = NULL)
}
\arguments{
  \item{paper_dir}{Path to one paper output directory.}
  \item{table_number}{Exact printed table identifier string, such as \code{"1"}, \code{"3.1"}, or \code{"S1"}.}
  \item{table_index}{Optional zero-based numeric table index matching parser output files such as \code{table_0_context.json}.}
  \item{match_type}{Optional match type filter such as \code{"table_reference"}.}
}
\value{
Invisibly returns the filtered passage list.
}
\examples{
\dontrun{
source("R/inspect_paper_outputs.R")
show_table_context("outputs/papers/cobaltpaper", table_number = "1")
show_table_context("outputs/papers/cobaltpaper", table_number = "3.1", match_type = "table_reference")
}
}
