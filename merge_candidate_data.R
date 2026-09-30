#!/usr/bin/env Rscript

required_packages <- c("dplyr", "readr", "readxl", "stringr")
missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)
]
if (length(missing_packages) > 0) {
  stop(
    "Install the missing R package(s) first: install.packages(c(",
    paste(sprintf('"%s"', missing_packages), collapse = ", "),
    "))"
  )
}

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(readxl)
  library(stringr)
})

# Usage from the project directory:
#   Rscript merge_candidate_data.R
#
# Optional arguments:
#   Rscript merge_candidate_data.R /path/to/data /path/to/output.csv

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_file <- if (length(script_arg) == 1) {
  sub("^--file=", "", script_arg)
} else {
  tryCatch(sys.frame(1)$ofile, error = function(e) NULL)
}
script_dir <- if (!is.null(script_file) && file.exists(script_file)) {
  dirname(normalizePath(script_file))
} else {
  getwd()
}

find_data_dir <- function() {
  candidates <- unique(c(
    file.path(script_dir, "_static", "conjoint", "data"),
    file.path(script_dir, "conjoint_project", "_static", "conjoint", "data"),
    file.path(getwd(), "_static", "conjoint", "data"),
    file.path(getwd(), "conjoint_project", "_static", "conjoint", "data")
  ))

  required_names <- c("ideology_db.xlsx", "base de datos.xlsx", "dataset.csv")
  complete <- vapply(
    candidates,
    function(path) all(file.exists(file.path(path, required_names))),
    logical(1)
  )

  if (!any(complete)) {
    stop(
      "Could not locate the data directory. Checked: ",
      paste(candidates, collapse = ", "),
      ". You can provide it explicitly, for example: ",
      "Rscript merge_candidate_data.R conjoint_project/_static/conjoint/data"
    )
  }

  normalizePath(candidates[which(complete)[1]], mustWork = TRUE)
}

args <- commandArgs(trailingOnly = TRUE)
data_dir <- if (length(args) >= 1) {
  normalizePath(args[[1]], mustWork = TRUE)
} else {
  find_data_dir()
}
output_file <- if (length(args) >= 2) {
  args[[2]]
} else {
  file.path(data_dir, "base_final_merged.csv")
}

ideology_file <- file.path(data_dir, "ideology_db.xlsx")
base_file <- file.path(data_dir, "base de datos.xlsx")
dataset_file <- file.path(data_dir, "dataset.csv")

required_files <- c(ideology_file, base_file, dataset_file)
missing_files <- required_files[!file.exists(required_files)]
if (length(missing_files) > 0) {
  stop("Missing input file(s): ", paste(missing_files, collapse = ", "))
}

normalize_id <- function(x) {
  id <- str_trim(as.character(x))
  id <- str_remove(id, "\\.0+$")
  id[id == ""] <- NA_character_
  id
}

require_columns <- function(data, columns, source_name) {
  missing <- setdiff(columns, names(data))
  if (length(missing) > 0) {
    stop(
      source_name,
      " is missing required column(s): ",
      paste(missing, collapse = ", ")
    )
  }
}

require_unique_ids <- function(data, source_name) {
  duplicates <- data |>
    filter(!is.na(ID)) |>
    count(ID, name = "n") |>
    filter(n > 1)
  
  if (nrow(duplicates) > 0) {
    stop(
      source_name,
      " contains duplicate ID values: ",
      paste(duplicates$ID, collapse = ", ")
    )
  }
}

# Read only the candidate-level description needed from ideology_db.xlsx.
ideology <- read_excel(
  ideology_file,
  sheet = "Clasificación Met3",
  col_types = "text",
  .name_repair = function(x) make.unique(x, sep = "_")
)
require_columns(ideology, c("ID", "TEXTO"), "ideology_db.xlsx")

ideology <- ideology |>
  transmute(
    ID = normalize_id(ID),
    Texto = str_trim(TEXTO),
    Texto = if_else(
      is.na(Texto) | Texto == "" | str_starts(Texto, "#"),
      NA_character_,
      Texto
    )
  ) |>
  filter(!is.na(ID))

# Base Final defines the candidates to retain in the result.
base_final <- read_excel(
  base_file,
  sheet = "Base Final",
  col_types = "text"
)
require_columns(base_final, "ID", "base de datos.xlsx [Base Final]")
base_final <- base_final |>
  mutate(ID = normalize_id(ID))

if (anyNA(base_final$ID)) {
  stop("base de datos.xlsx [Base Final] contains a blank ID.")
}

# Read all CSV columns as text so identifiers and comma-decimal source values
# are preserved exactly during the merge.
dataset <- read_csv(
  dataset_file,
  col_types = cols(.default = col_character()),
  show_col_types = FALSE
)
require_columns(dataset, "ID", "dataset.csv")
dataset <- dataset |>
  mutate(ID = normalize_id(ID)) |>
  filter(!is.na(ID))

require_unique_ids(ideology, "ideology_db.xlsx")
require_unique_ids(base_final, "base de datos.xlsx [Base Final]")
require_unique_ids(dataset, "dataset.csv")

# First append Texto to Base Final, then append every dataset.csv variable.
# left_join preserves all candidates and row order from Base Final.
base_with_text <- base_final |>
  left_join(ideology, by = "ID")

merged <- base_with_text |>
  left_join(
    dataset,
    by = "ID",
    suffix = c("_base_final", "_dataset")
  )

if (nrow(merged) != nrow(base_final)) {
  stop("The merge changed the number of Base Final rows.")
}

missing_text_ids <- base_with_text |>
  filter(is.na(Texto)) |>
  pull(ID)

missing_dataset_ids <- anti_join(
  base_final |> select(ID),
  dataset |> select(ID),
  by = "ID"
) |>
  pull(ID)

if (length(missing_text_ids) > 0) {
  warning(
    "No valid TEXTO was found for ID(s): ",
    paste(missing_text_ids, collapse = ", "),
    call. = FALSE
  )
}

if (length(missing_dataset_ids) > 0) {
  warning(
    "No dataset.csv row was found for ID(s): ",
    paste(missing_dataset_ids, collapse = ", "),
    call. = FALSE
  )
}

dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
write_csv(merged, output_file, na = "")

message(
  "Saved ", nrow(merged), " rows and ", ncol(merged),
  " columns to: ", normalizePath(output_file)
)
