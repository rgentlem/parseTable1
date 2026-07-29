\name{build_observed_table_one}
\alias{build_observed_table_one}
\alias{build_observed_table_one_from_paper_dir}
\alias{new_observed_table_one}
\alias{validate_observed_table_one}
\title{Construct observed Table 1 semantic objects}
\description{
Builds an \code{ObservedTableOne} object from parser JSON-derived structures.
The object is grounded in the printed table and preserves observed row, column,
continuous, categorical, and statistic semantics.
}
\usage{
build_observed_table_one(table_definition, parsed_table, normalized_table = NULL, provenance = NULL)

build_observed_table_one_from_paper_dir(
  paper_dir,
  table_number = "1",
  table_index = NULL
)

new_observed_table_one(
  table_id,
  title = NULL,
  caption = NULL,
  metadata = list(),
  columns = list(),
  continuous = list(variables = list(), values = list()),
  categorical = list(variables = list(), values = list()),
  statistics = list(),
  provenance = list(),
  notes = character(),
  overall_confidence = NULL
)

validate_observed_table_one(x)
}
\arguments{
  \item{table_definition}{One parsed entry from \code{table_definitions.json}.}
  \item{parsed_table}{One parsed entry from \code{parsed_tables.json}.}
  \item{normalized_table}{Optional matching entry from \code{normalized_tables.json}.}
  \item{provenance}{Optional list describing the source of the constructed object.}
  \item{paper_dir}{Path to one paper output directory under \code{outputs/papers/}.}
  \item{table_number}{Exact printed table identifier string, such as \code{"1"}, \code{"3.1"}, or \code{"S1"}.}
  \item{table_index}{Optional zero-based numeric table index for low-level debugging.}
  \item{table_id}{Stable table identifier.}
  \item{title}{Optional table title.}
  \item{caption}{Optional table caption.}
  \item{metadata}{Observed metadata derived from the printed table.}
  \item{columns}{Observed printed non-label columns.}
  \item{continuous}{Continuous-variable block.}
  \item{categorical}{Categorical-variable block.}
  \item{statistics}{Statistic-column block.}
  \item{notes}{Character vector of notes.}
  \item{overall_confidence}{Optional overall confidence value.}
  \item{x}{An \code{ObservedTableOne} object.}
}
\value{
For the builders and constructor, an object of class \code{ObservedTableOne}.
For \code{validate_observed_table_one()}, the validated object invisibly.
}
\examples{
\dontrun{
source("R/pt1_json_io.R")
source("R/observed_table_one.R")

x <- build_observed_table_one_from_paper_dir(
  "outputs/papers/cobaltpaper",
  table_number = "1"
)
print(x)
}
}
