# Faces or Facts? -- download, analysis, figures, tables, and paper compilation.
# This is the ONLY R file. Its named chunks are shared with the matching Rnw.
# Each external chunk starts with '## ---- label' and ends with '## ---- '.
# The Rnw loads all chunks once at the top, then calls them by matching label.
# Run from Terminal: Rscript visual_conjoint_design.R
# This refreshes the official data, runs the analyses, and rebuilds the paper.
#
# In R / RStudio:
#   source("/Users/hectorbahamonde/research/elections_colombia/conjoint_project/visual_conjoint_design.R")
# Running/source-ing the whole file does everything. To refresh the data only,
# run the download-functions and download-data sections, without later sections.
# dat and substantive analytical dataframes contain ONLY eligible completed
# responses from MAIN FIELDWORK. The 30 completed PRE-TEST / SOFT-LAUNCH cases
# are excluded from those analyses and retained separately in pretest for A1.
# Complete = final screen reached, all 15 main tasks submitted, >=13 valid votes,
# and no DETECTED prohibited reload/history event. Historical unmonitored records
# remain explicitly unknown, not falsely clean or retroactively excluded.
# Up to two main-task nonresponses are allowed; conditional missingness is valid.
# raw_dat retains the original export. recruitment_people retains status counts.
# conjoint_dat is the conjoint-format dataframe: one displayed candidate per row.
# Candidate IDs and attributes are checked against base_final_merged.csv.
#
# In Terminal, from this project folder:
#   Rscript visual_conjoint_design.R
#
# Uses your oTree ADMIN password, not Gabriel's dashboard password or your
# Render account password. On this Mac, a successfully verified password is
# saved in macOS Keychain and reused automatically on subsequent runs. It is
# never written into the script, project files, or downloaded data. macOS may
# request permission to access the saved item. No browser login is required.
# Required R packages: httr, xml2, askpass, keyring (installed on this Mac).
# No changes are made to the experiment, database, session, or completion rules.

## ---- script-session-setup
cat("\014")
rm(list=ls())

## ---- 

## ---- download-functions
.study_project_dir <- local({
  script <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  source_files <- vapply(sys.frames(), function(frame) {
    if (is.null(frame$ofile)) "" else as.character(frame$ofile)[1L]
  }, character(1))
  source_files <- source_files[nzchar(source_files)]
  path <- if (isTRUE(getOption("knitr.in.progress"))) {
    # A knit launched by another script still downloads into THIS paper folder.
    file.path(dirname(normalizePath(knitr::current_input(dir = TRUE), mustWork = TRUE)),
              "visual_conjoint_design.R")
  } else if (length(source_files)) {
    tail(source_files, 1L)
  } else if (length(script)) {
    sub("^--file=", "", script[1L])
  } else {
    "/Users/hectorbahamonde/research/elections_colombia/conjoint_project/visual_conjoint_design.R"
  }
  dirname(normalizePath(path, mustWork = TRUE))
})

.study_keychain_backend <- function() {
  if (!requireNamespace("keyring", quietly = TRUE)) {
    stop("Install keyring to remember the password securely in macOS Keychain.",
         call. = FALSE)
  }
  # Force the native backend, never an environment-variable or file fallback.
  keyring::backend_macos$new()
}

.study_prompt_password <- function() {
  if (!requireNamespace("askpass", quietly = TRUE)) {
    stop("Install askpass for the one-time secure password prompt.", call. = FALSE)
  }
  previous_options <- options(rlib_interactive = TRUE)
  tryCatch(
    askpass::askpass("oTree administrator password (saved securely on this Mac):"),
    finally = options(previous_options)
  )
}

.study_credentials <- function(server_url, username, password, use_keychain) {
  backend <- NULL
  service <- paste0("colombia-otree-export:", server_url)
  from_keychain <- FALSE
  if (use_keychain) {
    backend <- .study_keychain_backend()
    if (!nzchar(password)) {
      entries <- tryCatch(backend$list(service = service), error = function(error) {
        stop("macOS Keychain could not be accessed. Unlock it or allow R access, ",
             "then run the script again. No stored password was changed.", call. = FALSE)
      })
      if (username %in% entries$username) {
        password <- tryCatch(backend$get(service, username = username),
                             error = function(error) {
                               stop("R could not read the saved oTree password. Allow Keychain access ",
                                    "and run the script again. No stored password was changed.", call. = FALSE)
                             })
        from_keychain <- TRUE
      }
    }
  }
  if (is.null(password) || !nzchar(password)) password <- .study_prompt_password()
  if (is.null(password) || !nzchar(password)) {
    stop("Download cancelled. No data were changed.", call. = FALSE)
  }
  list(password = password, backend = backend, service = service,
       save = use_keychain && !from_keychain)
}

.study_remember_credentials <- function(credentials, username) {
  if (credentials$save) {
    tryCatch({
      credentials$backend$set_with_value(credentials$service, username = username,
                                         password = credentials$password)
      message("Verified oTree login saved securely in macOS Keychain.")
    }, error = function(error) {
      warning("The dataset was downloaded, but Keychain could not save the login. ",
              "Allow Keychain access before the next run. No password was saved ",
              "in project files.", call. = FALSE)
    })
  }
  invisible(NULL)
}

download_study_data <- function(
    server_url = Sys.getenv("OTREE_SERVER_URL", "https://colombia-conjoint.onrender.com"),
    room_name = "colombia_study",
    expected_session = Sys.getenv("OTREE_EXPORT_SESSION_CODE", "fhcmy7rf"),
    username = Sys.getenv("OTREE_ADMIN_USERNAME", "admin"),
    password = Sys.getenv("OTREE_ADMIN_PASSWORD", ""),
    output_dir = file.path(.study_project_dir, "data_exports"),
    remember_password = TRUE) {
  
  needed <- c("httr", "xml2")
  absent <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]
  if (length(absent)) {
    stop("Install the required R packages first: ", paste(absent, collapse = ", "),
         call. = FALSE)
  }
  
  server_url <- sub("/+$", "", server_url)
  address <- httr::parse_url(server_url)
  local_test <- identical(address$scheme, "http") &&
    address$hostname %in% c("127.0.0.1", "localhost", "::1")
  if (!(identical(address$scheme, "https") || local_test) ||
      !is.null(address$username) || !is.null(address$password) ||
      nzchar(address$path %||% "") || length(address$query) ||
      nzchar(address$fragment %||% "")) {
    stop("Use an HTTPS server origin, without credentials, paths, or query strings.",
         call. = FALSE)
  }
  if (!grepl("^[A-Za-z0-9_]+$", room_name) ||
      !grepl("^[A-Za-z0-9]+$", expected_session)) {
    stop("Set the expected official session code and room name before downloading.",
         call. = FALSE)
  }
  
  if (!is.logical(remember_password) || length(remember_password) != 1L ||
      is.na(remember_password)) {
    stop("remember_password must be TRUE or FALSE.", call. = FALSE)
  }
  credentials <- .study_credentials(server_url, username, password,
                                    use_keychain = remember_password && !local_test &&
                                      identical(Sys.info()[["sysname"]], "Darwin"))
  password <- credentials$password
  
  # A private, in-memory cookie handle. TLS remains verified, and redirects are
  # not followed, so credentials and authenticated requests stay on this origin.
  connection <- httr::handle(server_url)
  request_options <- httr::config(followlocation = FALSE)
  get <- function(path, query = NULL) {
    httr::GET(paste0(server_url, path), handle = connection, query = query,
              httr::add_headers(`Cache-Control` = "no-cache, no-store",
                                Pragma = "no-cache"),
              request_options, httr::timeout(180))
  }
  require_ok <- function(response, operation) {
    if (httr::status_code(response) != 200L) {
      stop(operation, " failed (HTTP ", httr::status_code(response),
           "). Check the administrator credentials and official session. ",
           "The previous latest.csv has not been replaced.", call. = FALSE)
    }
  }
  
  login_page <- get("/login")
  require_ok(login_page, "Opening oTree login")
  login_html <- xml2::read_html(httr::content(login_page, "text", encoding = "UTF-8"))
  csrf <- xml2::xml_attr(
    xml2::xml_find_first(login_html, "//input[@name='csrftoken']"), "value")
  if (is.na(csrf) || !nzchar(csrf)) {
    stop("The oTree login form was not recognized. Nothing was downloaded.", call. = FALSE)
  }
  login <- httr::POST(
    paste0(server_url, "/login"), handle = connection,
    body = list(username = username, password = password, csrftoken = csrf),
    encode = "form", request_options, httr::timeout(30))
  if (!httr::status_code(login) %in% c(302L, 303L)) {
    stop("oTree login failed. If the password changed, run download_study_data(",
         "password = .study_prompt_password()) once to update Keychain. Use the ",
         "ADMIN password from Render, not the monitor password. ",
         "No previous download was replaced.",
         call. = FALSE)
  }
  
  # Discover the room's current session, but refuse to silently switch from the
  # expected official session to a different or newly created testing session.
  room <- get(paste0("/room_with_session/", room_name))
  require_ok(room, "Reading the official room")
  room_html <- xml2::read_html(httr::content(room, "text", encoding = "UTF-8"))
  links <- xml2::xml_attr(xml2::xml_find_all(room_html, "//a[@href]"), "href")
  matches <- links[grepl("/SessionMonitor/[A-Za-z0-9]+/?$", links)]
  codes <- unique(sub(".*/SessionMonitor/([A-Za-z0-9]+)/?$", "\\1", matches))
  if (length(codes) != 1L || !identical(codes, expected_session)) {
    stop("The room does not point to the expected official session. Check it before ",
         "changing OTREE_EXPORT_SESSION_CODE. No previous download was replaced.",
         call. = FALSE)
  }
  
  response <- get("/ExportWide", query = list(session_code = codes, format = "csv_bom"))
  require_ok(response, "Downloading the responses")
  media_type <- httr::headers(response)[["content-type"]] %||% ""
  if (!grepl("^text/csv(?:;|$)", media_type, ignore.case = TRUE, perl = TRUE)) {
    stop("The server did not return a CSV export. No previous download was replaced.",
         call. = FALSE)
  }
  
  # Private local files only. Download to a temporary file and validate it before
  # publishing either the immutable snapshot or the replaceable latest copy.
  previous_umask <- Sys.umask("0077")
  on.exit(Sys.umask(previous_umask), add = TRUE)
  snapshots_dir <- file.path(output_dir, "snapshots")
  dir.create(snapshots_dir, recursive = TRUE, showWarnings = FALSE, mode = "0700")
  Sys.chmod(c(output_dir, snapshots_dir), mode = "0700")
  temporary <- tempfile(pattern = ".download-", tmpdir = output_dir, fileext = ".csv")
  on.exit(unlink(temporary), add = TRUE)
  writeBin(httr::content(response, "raw"), temporary)
  raw <- tryCatch(
    read.csv(temporary, fileEncoding = "UTF-8-BOM", check.names = FALSE,
             colClasses = "character", na.strings = "", stringsAsFactors = FALSE,
             comment.char = "", fill = FALSE),
    error = function(error) stop("The CSV could not be read. The previous latest.csv ",
                                 "has not been replaced.", call. = FALSE))
  required <- c("participant.code", "participant.visited", "session.code",
                "session.config.official_data_collection")
  truth <- c("1", "True", "TRUE", "true")
  if (!all(required %in% names(raw)) || !nrow(raw) ||
      anyNA(raw$participant.code) || anyDuplicated(raw$participant.code) ||
      anyNA(raw$session.code) || any(raw$session.code != expected_session) ||
      !all(raw$session.config.official_data_collection %in% truth)) {
    stop("The CSV is not a valid single official-session export. ",
         "The previous latest.csv has not been replaced.", call. = FALSE)
  }
  
  stamp <- format(Sys.time(), "%Y%m%dT%H%M%SZ", tz = "UTC")
  snapshot <- tempfile(pattern = paste0("conjoint_", codes, "_", stamp, "_"),
                       tmpdir = snapshots_dir, fileext = ".csv")
  if (!file.rename(temporary, snapshot)) {
    stop("Could not save the timestamped snapshot. The latest copy is unchanged.",
         call. = FALSE)
  }
  latest <- file.path(output_dir, "latest.csv")
  replacement <- tempfile(pattern = ".latest-", tmpdir = output_dir, fileext = ".csv")
  on.exit(unlink(replacement), add = TRUE)
  if (!file.copy(snapshot, replacement, overwrite = FALSE) ||
      !file.rename(replacement, latest)) {
    stop("The snapshot was saved, but latest.csv could not be refreshed. ",
         "The previous latest copy was not deleted.", call. = FALSE)
  }
  Sys.chmod(c(snapshot, latest), mode = "0600")
  # Save only after both authentication and the official CSV have been verified.
  .study_remember_credentials(credentials, username)
  
  started <- raw[raw$participant.visited %in% truth, , drop = FALSE]
  message("Downloaded official session ", codes, ": ", nrow(raw),
          " allocated slots; ", nrow(started), " participants have started.")
  message("Started includes partial and excluded attempts, not just completed surveys.")
  message("Latest: ", latest)
  message("Snapshot: ", snapshot)
  invisible(list(all_allocated = raw, started = started, session_code = codes,
                 latest_file = latest, snapshot_file = snapshot,
                 export_md5 = unname(tools::md5sum(snapshot)),
                 downloaded_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE)))
}

`%||%` <- function(value, fallback) if (is.null(value)) fallback else value

## ---- 

## ---- download-data
# One refresh per run. The saved Mac Keychain login is reused automatically.
# A direct Rnw build also refreshes the data. The build-paper chunk below passes
# this run's verified download to knitr, rather than downloading a second time.
# Set options(colombia.refresh_data = FALSE) explicitly for an offline build.
if (isTRUE(getOption("colombia.refresh_data", TRUE))) {
  download <- download_study_data()
  data_refresh_mode <- "fresh_download"
  dat <- download$started
} else if (isTRUE(getOption("knitr.in.progress")) &&
           !is.null(getOption("colombia.download_for_knit"))) {
  download <- getOption("colombia.download_for_knit")
  data_refresh_mode <- "same_build_download"
} else {
  download <- NULL
  data_refresh_mode <- "explicit_offline"
  warning("OFFLINE BUILD: using the last saved export, not current server data. ",
          "Set options(colombia.refresh_data = TRUE) for a fresh build.", call. = FALSE)
}

## ---- 

## ---- analysis-packages
# Load familiar packages. Install missing packages once, not on every analysis.
# install.packages(c("readr", "dplyr", "tidyr", "ggplot2", "broom", "fixest",
#                    "emmeans", "sandwich", "tableone", "knitr", "scales",
#                    "patchwork"))
library(readr)
library(dplyr)
library(tidyr)
library(ggplot2)
library(broom)
library(fixest)
library(emmeans)
library(tableone)
library(patchwork)
# Display chunks below print only during knitting, not when sourcing this file.
render_in_paper <- isTRUE(getOption("knitr.in.progress"))

project_dir <- "/Users/hectorbahamonde/research/elections_colombia/conjoint_project"
setwd(project_dir)
input_file <- file.path(project_dir, "data_exports", "latest.csv")
output_dir <- file.path(project_dir, "analysis_outputs")
dir.create(output_dir, showWarnings = FALSE)

# ONE visual system for every figure. Colour always identifies the decision
# environment (the three categorical slots of a palette validated for colour-
# vision deficiency across all pairs). Candidate gender is shown by SHAPE
# (filled = men, hollow = women), never by a second palette, so a colour means
# the same thing in every figure. Arms are also named on axes or in legends.
arm_colors <- c(Baseline = "#2A78D6", Time = "#EB6834", Cost = "#1BAF7A")
arm_shapes <- c(Baseline = 16, Time = 17, Cost = 15)
# Short arm names match the manuscript's \armB, \armT and \armC macros.
arm_labels <- c(Baseline = "Baseline", Time = "Time", Cost = "Cost")
arm_labels_wrapped <- arm_labels
gender_shapes <- c(Men = 16, Women = 1)
ink <- "#0B0B0B"
ink_muted <- "#52514E"
theme_paper <- function(base_size = 9.5) {
  theme_minimal(base_size = base_size) +
    theme(text = element_text(color = ink),
      axis.text = element_text(color = ink_muted),
      axis.title = element_text(color = ink_muted),
      panel.grid.major = element_line(color = "#ECEBE7", linewidth = 0.3),
      panel.grid.minor = element_blank(),
      strip.text = element_text(face = "bold", hjust = 0, color = ink),
      legend.position = "top", legend.justification = "left",
      legend.title = element_text(color = ink_muted),
      legend.margin = margin(0, 0, 0, 0),
      plot.tag = element_text(face = "bold"),
      plot.margin = margin(4, 6, 4, 4))
}
theme_set(theme_paper())

# Formatting helpers shared by LaTeX tables and live sentences in the Rnw.
# Negative numbers use a typographic minus. NA prints as a dash.
tex_num <- function(x, digits = 2) {
  if (!length(x)) return(character())
  unname(mapply(function(value, places) {
    if (is.na(value)) return("--")
    magnitude <- formatC(abs(value), format = "f", digits = places)
    if (round(value, places) < 0) paste0("$-$", magnitude) else magnitude
  }, x, rep_len(digits, length(x))))
}
tex_p <- function(p) {
  ifelse(is.na(p), "--",
         ifelse(p < 0.001, "$<$0.001", formatC(p, format = "f", digits = 3)))
}
tex_ci <- function(low, high, digits = 2) {
  paste0("[", tex_num(low, digits), ", ", tex_num(high, digits), "]")
}
# Write a booktabs tabular from a character data frame. Optional 'groups' adds
# italic panel headings, so related estimands are read together.
tex_tabular <- function(df, align, header = names(df), groups = NULL,
                        header_top = NULL, footer = NULL) {
  df <- as.data.frame(lapply(df, as.character), check.names = FALSE)
  rows <- apply(df, 1, paste, collapse = " & ")
  body <- character()
  current <- NULL
  for (i in seq_along(rows)) {
    if (!is.null(groups) && !identical(groups[i], current)) {
      if (!is.null(current)) body <- c(body, "\\addlinespace[2pt]")
      body <- c(body, sprintf("\\multicolumn{%d}{@{}l}{\\textit{%s}} \\\\",
                              ncol(df), groups[i]))
      current <- groups[i]
    }
    body <- c(body, paste0(rows[i], " \\\\"))
  }
  if (!is.null(footer)) {
    footer <- as.data.frame(lapply(footer, as.character), check.names = FALSE)
    body <- c(body, "\\midrule",
              paste0(apply(footer, 1, paste, collapse = " & "), " \\\\"))
  }
  cat(c(sprintf("\\begin{tabular}{%s}", align), "\\toprule", header_top,
        paste0(paste(header, collapse = " & "), " \\\\"), "\\midrule", body,
        "\\bottomrule", "\\end{tabular}"), sep = "\n")
}
# Live sentences: estimate, interval and the relevant p-value. live() keeps the
# manuscript compiling while an estimand cannot yet be computed.
live <- function(expr) tryCatch(expr, error = function(error) "[not yet estimable]")
pick_effect <- function(df, outcome_value, contrast_value) {
  row <- df[df$outcome == outcome_value & df$contrast == contrast_value, , drop = FALSE]
  stopifnot(nrow(row) == 1L)
  row
}
p_text <- function(p) {
  if (is.na(p)) "--" else if (p < 0.001) "$p<0.001$" else
    paste0("$p=", formatC(p, format = "f", digits = 3), "$")
}
effect_text <- function(row, scale = 1, digits = 2, unit = "", holm = TRUE) {
  p_part <- if (holm && "p_holm" %in% names(row)) {
    paste("Holm-adjusted", p_text(row$p_holm))
  } else {
    p_text(row$p.value)
  }
  paste0(tex_num(scale * row$estimate, digits), unit, " (95\\% CI ",
         tex_num(scale * row$conf.low, digits), " to ",
         tex_num(scale * row$conf.high, digits), "; ", p_part, ")")
}
ci_phrase <- function(row) {
  if (row$conf.low > 0 || row$conf.high < 0) "excludes zero" else "includes zero"
}

## ----

## ---- analysis-import
# Read the export saved by the download-data chunk above. Every build reruns the
# analyses on that file. Offline builds reuse the last successfully saved export.
# IDs remain text. Empty cells become NA, but the literal text "NA" is preserved.
stopifnot(file.exists(input_file))
export_checksum <- unname(tools::md5sum(input_file))
if (data_refresh_mode != "explicit_offline") {
  # The paper must analyze the exact bytes downloaded for this build. If another
  # process replaced latest.csv between stages, stop rather than mix versions.
  if (!identical(normalizePath(input_file), normalizePath(download$latest_file)) ||
      !identical(export_checksum, download$export_md5)) {
    stop("The export changed after download. Rebuild from the R file or Rnw; ",
         "the paper will not be compiled using a different dataset.")
  }
  export_time <- download$downloaded_at_utc
} else {
  export_time <- format(file.info(input_file)$mtime, tz = "UTC", usetz = TRUE)
}
message("DATA SOURCE: ", data_refresh_mode, "; export saved at ", export_time,
        "; MD5 ", export_checksum)
raw_dat <- read_csv(input_file, col_types = cols(.default = col_character()),
                na = "", trim_ws = FALSE, name_repair = "minimal",
                show_col_types = FALSE)
stopifnot(identical(export_checksum, unname(tools::md5sum(input_file))))
stopifnot(!anyDuplicated(raw_dat$participant.code),
          all(raw_dat$session.code == "fhcmy7rf"),
          all(raw_dat$session.config.official_data_collection %in% c("1", "True", "TRUE")))

## ---- 

## ---- analysis-report-parameters
# INTERNAL COHORT DEFINITION -- never print these logistics in the manuscript.
# PRE-TEST / SOFT LAUNCH: 19-20 October 2026, inclusive, in Chile/Santiago time.
# Earlier records are dropped from working analyses, NOT erased from raw files
# or Render. The 30 frozen complete pre-test cases are used ONLY for deadline
# calibration and Figure A1. New completed NINE-SECOND-version responses are
# retained for analysis, including the next 30-person collection wave.
cohort_timezone <- "America/Santiago"
pretest_start_date <- as.Date("2026-10-19")
pretest_end_date <- as.Date("2026-10-20")

# By default, use observed task VERSION, not an invented launch date, to identify
# the new collection. An optional confirmed UTC launch time can impose an EXTRA
# cutoff. Leave this unset until that exact timestamp is actually known.
main_fieldwork_start_utc <- as.POSIXct(
  getOption("colombia.main_start_utc", NA_character_), tz = "UTC")
if (!is.na(main_fieldwork_start_utc)) {
  stopifnot(as.Date(main_fieldwork_start_utc, tz = cohort_timezone) > pretest_end_date)
}
if (!exists("analysis_scope", inherits = FALSE)) analysis_scope <- "main"
stopifnot(analysis_scope %in% c("main", "pretest"))

pretest_file <- file.path(project_dir, "data_exports", "snapshots",
  "conjoint_fhcmy7rf_20261021T135317Z_1726c3149ade2.csv")
if (!file.exists(pretest_file)) stop("Restore the saved pre-test snapshot before analysis.")
stopifnot(unname(tools::md5sum(pretest_file)) == "530a620bb33162b42eb9b7c0ac480edf")
pretest_register <- read_csv(pretest_file,
  col_types = cols(.default = col_character()), na = "", trim_ws = FALSE,
  name_repair = "minimal", show_col_types = FALSE) |>
  filter(participant.visited %in% c("1", "True", "TRUE"),
         !participant._is_bot %in% c("1", "True", "TRUE"))
pretest_ids <- pretest_register$participant.code
pretest_start_dates <- range(substr(pretest_register$participant.time_started_utc, 1L, 10L))
stopifnot(!anyDuplicated(pretest_ids), !anyNA(pretest_register$participant.time_started_utc))

# Only respondent START time is exported. Convert UTC to the recruitment timezone
# before applying inclusive calendar dates. A late-finishing pre-test respondent
# stays pre-test because the original start date does not change.
raw_dat <- raw_dat |>
  mutate(start_time_utc = as.POSIXct(participant.time_started_utc,
                                    format = "%Y-%m-%d %H:%M:%OS", tz = "UTC"),
    start_date = as.Date(start_time_utc, tz = cohort_timezone),
    data_phase = case_when(
      !participant.visited %in% c("1", "True", "TRUE") ~ "unstarted",
      start_date < pretest_start_date ~ "excluded_before_pretest",
      start_date <= pretest_end_date ~ "pretest",
      !is.na(main_fieldwork_start_utc) & start_time_utc < main_fieldwork_start_utc ~
        "excluded_before_main_start",
      TRUE ~ "awaiting_task_version"),
    is_pretest = data_phase == "pretest")
stopifnot(!anyNA(raw_dat$start_time_utc[
  raw_dat$participant.visited %in% c("1", "True", "TRUE")]))

# Navigation monitoring was introduced after the pre-test. Old exports have no
# such columns, so retain UNKNOWN rather than inventing clean navigation or a
# violation. These are respondent-level audit fields, not questionnaire answers.
if (!"participant.navigation_monitoring_started" %in% names(raw_dat)) {
  raw_dat$participant.navigation_monitoring_started <- NA_character_
}
if (!"participant.navigation_violation" %in% names(raw_dat)) {
  raw_dat$participant.navigation_violation <- NA_character_
}
if (!"participant.navigation_reload_count" %in% names(raw_dat)) {
  raw_dat$participant.navigation_reload_count <- NA_character_
}
if (!"participant.navigation_history_count" %in% names(raw_dat)) {
  raw_dat$participant.navigation_history_count <- NA_character_
}
if (!"participant.navigation_events" %in% names(raw_dat)) {
  raw_dat$participant.navigation_events <- NA_character_
}
if (!"participant.navigation_partial_task" %in% names(raw_dat)) {
  raw_dat$participant.navigation_partial_task <- NA_character_
}
if (!"participant.study_terminated" %in% names(raw_dat)) {
  raw_dat$participant.study_terminated <- NA_character_
}
if (!"participant.study_termination_reason" %in% names(raw_dat)) {
  raw_dat$participant.study_termination_reason <- NA_character_
}
if (!"participant.study_terminated_at_utc" %in% names(raw_dat)) {
  raw_dat$participant.study_terminated_at_utc <- NA_character_
}
if (!"participant.study_termination_page_index" %in% names(raw_dat)) {
  raw_dat$participant.study_termination_page_index <- NA_character_
}
if (!"participant.study_termination_submitted_round" %in% names(raw_dat)) {
  raw_dat$participant.study_termination_submitted_round <- NA_character_
}

# Shared parameters for calculations, table headings, plots and Rnw notes.
# Derive the task design from the export and verify the recorded deadline.
# This section never imports oTree or opens the experiment database.
configured_deadline_line <- grep("^    COUNTDOWN_SECONDS = ",
  readLines(file.path(project_dir, "conjoint", "models.py")), value = TRUE)
stopifnot(length(configured_deadline_line) == 1L)
configured_deadline_seconds <- as.numeric(sub("^    COUNTDOWN_SECONDS = ", "",
                                              configured_deadline_line))
stopifnot(configured_deadline_seconds == 9)
practice_columns <- grep("^conjoint\\.[0-9]+\\.player\\.is_practice_round$",
                          names(raw_dat), value = TRUE)
practice_flags <- unlist(raw_dat[1L, practice_columns], use.names = FALSE)
n_total_tasks <- length(practice_columns)
n_practice_tasks <- sum(practice_flags %in% c("1", "True", "TRUE"))
n_main_tasks <- n_total_tasks - n_practice_tasks
profiles_per_task <- sum(grepl("^conjoint\\.1\\.player\\.(left|right)_candidate_id$",
                                names(raw_dat)))
profiles_per_respondent <- profiles_per_task * n_total_tasks
deadline_columns <- grep("^conjoint\\.[0-9]+\\.player\\.countdown_seconds$",
                          names(raw_dat), value = TRUE)
# Check every displayed practice/main task and the recorded arm in every round.
# Control and Math are untimed, but their stored deadline-version metadata still
# identifies the common study version. Nothing here caps their response times.
shown_tasks <- !is.na(as.matrix(raw_dat[sub("countdown_seconds$", "left_candidate_id",
                                          deadline_columns)])) |
  !is.na(as.matrix(raw_dat[sub("countdown_seconds$", "right_candidate_id",
                              deadline_columns)]))
recorded_task_deadlines <- as.matrix(raw_dat[deadline_columns])
arm_columns <- sub("countdown_seconds$", "treatment_arm", deadline_columns)
recorded_task_arms <- as.matrix(raw_dat[arm_columns])
raw_dat$recorded_deadline_matches_app <- rowSums(shown_tasks) > 0L &
  rowSums(shown_tasks & (is.na(recorded_task_deadlines) |
    recorded_task_deadlines != as.character(configured_deadline_seconds)), na.rm = TRUE) == 0L
# Unvisited future tasks do not yet have an arm recorded. Check only displayed
# tasks, so an unfinished or stopped nine-second case is not falsely called mixed.
raw_dat$recorded_arm_consistent <- !is.na(raw_dat$conjoint.1.player.treatment_arm) &
  rowSums(shown_tasks & (is.na(recorded_task_arms) |
    recorded_task_arms != raw_dat$conjoint.1.player.treatment_arm), na.rm = TRUE) == 0L
raw_dat <- raw_dat |>
  mutate(data_phase = case_when(
    data_phase != "awaiting_task_version" ~ data_phase,
    recorded_deadline_matches_app & recorded_arm_consistent ~ "main",
    rowSums(shown_tasks) > 0L ~ "excluded_other_or_mixed_version",
    TRUE ~ "awaiting_task_version"))
# Identify deadline versions within the SELECTED cohort only. Old pre-test
# deadlines must not prevent a later main-fieldwork deadline from being analyzed.
deadline_data <- raw_dat |>
  filter(participant.visited %in% c("1", "True", "TRUE"),
         if (analysis_scope == "pretest") data_phase == "pretest" else data_phase == "main")
recorded_deadlines <- as.numeric(unlist(deadline_data[deadline_columns], use.names = FALSE))
shown_profiles <- unlist(deadline_data[sub("countdown_seconds$", "left_candidate_id",
                                          deadline_columns)], use.names = FALSE)
deadline_seconds <- sort(unique(recorded_deadlines[
  !is.na(shown_profiles) & !is.na(recorded_deadlines) & recorded_deadlines > 0]))
if (length(deadline_seconds) == 0L && analysis_scope == "main") {
  # No main-study task shown yet: use the approved app setting, never the old
  # twenty-second pre-test. This supplies design metadata, not observations.
  deadline_seconds <- configured_deadline_seconds
}
if (length(deadline_seconds) != 1L) {
  stop("The selected cohort must have one observed deadline version. Report mixed versions separately.")
}
if (analysis_scope == "main" && deadline_seconds != configured_deadline_seconds) {
  stop("Main-fieldwork responses use a different deadline from the approved app. Report versions separately.")
}

# Read the same completion threshold used by the live monitor. It is a plain
# constant in this source file, so no Python execution or database read is needed.
completion_rule_line <- grep("^MIN_VALID_MAIN_CHOICES = ",
  readLines(file.path(project_dir, "completion_rules.py")), value = TRUE)
stopifnot(length(completion_rule_line) == 1L)
minimum_valid_main_choices <- as.integer(sub("^MIN_VALID_MAIN_CHOICES = ", "",
                                            completion_rule_line))
allowed_missing_choices <- n_main_tasks - minimum_valid_main_choices
stopifnot(n_main_tasks > 0L, profiles_per_task == 2L,
          minimum_valid_main_choices > 0L, allowed_missing_choices >= 0L)

# Compare first-selection timing over the SAME observed window in every arm.
# The main-study window is nine seconds. Only the isolated historical pre-test
# uses its original twenty-second window. Full Control/Math durations stay intact.
selection_window_seconds <- deadline_seconds
confidence_level <- 0.95
duration_quantiles <- c(0.75, 0.90, 0.95)
ci_percent <- format(100 * confidence_level, trim = TRUE, scientific = FALSE)
ci_column <- paste0(ci_percent, "% CI")
no_selection_label <- paste0("No selection by ", selection_window_seconds, " s (%)")

## ---- 

## ---- analysis-participants
# Make ONE row per respondent. Do not mistake the 600 allocated slots for 600
# respondents. Screening exclusions can reach the final page without doing tasks.
# Identify eligible starters first. Final completion requires task counts below.
dat <- raw_dat |> filter(participant.visited %in% c("1", "True", "TRUE"))
participants <- raw_dat |>
  transmute(
    respondent_id = participant.code,
    started_utc = participant.time_started_utc,
    is_pretest = is_pretest,
    data_phase = data_phase,
    recorded_deadline_matches_app = recorded_deadline_matches_app,
    recorded_arm_consistent = recorded_arm_consistent,
    visited = participant.visited %in% c("1", "True", "TRUE"),
    bot = participant._is_bot %in% c("1", "True", "TRUE"),
    navigation_monitoring_started = case_when(
      participant.navigation_monitoring_started %in% c("1", "True", "TRUE") ~ TRUE,
      participant.navigation_monitoring_started %in% c("0", "False", "FALSE") ~ FALSE,
      TRUE ~ NA),
    navigation_violation = case_when(
      participant.navigation_violation %in% c("1", "True", "TRUE") ~ TRUE,
      participant.navigation_violation %in% c("0", "False", "FALSE") ~ FALSE,
      TRUE ~ NA),
    navigation_reload_count = as.integer(participant.navigation_reload_count),
    navigation_history_count = as.integer(participant.navigation_history_count),
    navigation_events = participant.navigation_events,
    navigation_partial_task = participant.navigation_partial_task,
    study_terminated = case_when(
      participant.study_terminated %in% c("1", "True", "TRUE") ~ TRUE,
      participant.study_terminated %in% c("0", "False", "FALSE") ~ FALSE,
      TRUE ~ NA),
    study_termination_reason = participant.study_termination_reason,
    study_terminated_at_utc = participant.study_terminated_at_utc,
    study_termination_page_index = as.integer(participant.study_termination_page_index),
    study_termination_submitted_round = as.integer(participant.study_termination_submitted_round),
    page_index = as.integer(participant._index_in_pages),
    max_page_index = as.integer(participant._max_page_index),
    consent = conjoint.1.player.consent_accepted %in% c("1", "True", "TRUE"),
    country = conjoint.1.player.country_of_residence,
    nationality = conjoint.1.player.nationality,
    lived_colombia = conjoint.1.player.lived_in_colombia,
    exclusion_reason = conjoint.1.player.screening_exclusion_reason,
    screened_out = conjoint.1.player.screening_excluded %in% c("1", "True", "TRUE") |
      !is.na(exclusion_reason),
    age = as.numeric(conjoint.1.player.age_years),
    gender = factor(conjoint.1.player.gender_identity,
                    levels = c("mujer", "hombre", "otra", "prefiero_no_responder"),
                    labels = c("Woman", "Man", "Another identity", "No response")),
    education = factor(conjoint.1.player.education_level,
      levels = c("basica_o_menos", "media_completa", "tecnica_profesional_completa", "postgrado"),
      labels = c("Basic or less", "Secondary", "Technical or university", "Postgraduate")),
    occupation = factor(conjoint.1.player.occupation_status,
      levels = c("tiempo_completo", "tiempo_parcial", "cuenta_propia", "estudia",
                 "labores_domesticas_cuidado", "jubilado_pensionado",
                 "desempleado_busca", "desempleado_no_busca", "otra"),
      labels = c("Full-time paid work", "Part-time paid work", "Self-employed", "Student",
                 "Unpaid domestic or care work", "Retired", "Unemployed, seeking work",
                 "Unemployed, not seeking work", "Other")),
    voted = factor(conjoint.1.player.voted_last_municipal,
                   levels = c("yes", "no", "dont_know"),
                   labels = c("Yes", "No", "Do not recall")),
    political_interest = as.numeric(conjoint.1.player.political_interest),
    discussion = factor(conjoint.1.player.politics_frequency,
      levels = c("never", "less_than_once_per_week", "once_or_twice_per_week",
                 "several_times_per_week", "every_day"),
      labels = c("Never", "Less than weekly", "Once or twice weekly",
                 "Several times weekly", "Daily")),
    ideology_response = conjoint.1.player.left_right_self_placement,
    ideology = as.numeric(if_else(ideology_response %in% as.character(1:10),
                                  ideology_response, NA_character_)),
    arm = factor(conjoint.1.player.treatment_arm,
      levels = c("control_ver_mas", "timer_mostrar_mas", "captcha_ver_mas"),
      labels = c("Baseline", "Time", "Cost")),
    first_pair_loaded = !is.na(conjoint.1.player.left_candidate_id) &
      !is.na(conjoint.1.player.right_candidate_id)
  ) |>
  mutate(
    navigation_record_status = case_when(
      navigation_violation %in% TRUE ~ "detected_violation",
      navigation_monitoring_started %in% TRUE & navigation_violation %in% FALSE ~
        "monitored_no_detected_violation",
      TRUE ~ "unknown"),
    eligible = visited & !bot & consent & !screened_out &
      !is.na(country) & country != "CO" & !is.na(nationality) & nationality != "CO" &
      !is.na(lived_colombia) & lived_colombia == "no" &
      !is.na(age) & age %in% 18:65 & !is.na(gender) &
      !is.na(education) & !is.na(occupation),
    sequence_started = eligible & first_pair_loaded,
    eligible_final_screen_completion = sequence_started & page_index >= max_page_index
  )
stopifnot(all(participants$max_page_index == 200),
          all(!is.na(participants$arm[participants$sequence_started])),
          all(participants$age[participants$sequence_started] %in% 18:65))

## ---- 

## ---- analysis-tasks
# Convert the wide export into ONE row per person and round. All original player
# fields survive this reshape, including candidate attributes and raw responses.
rounds <- dat |>
  select(respondent_id = participant.code, matches("^conjoint\\.[0-9]+\\.player\\.")) |>
  pivot_longer(-respondent_id, names_to = c("round", ".value"),
               names_pattern = "conjoint\\.([0-9]+)\\.player\\.(.+)") |>
  mutate(round = as.integer(round)) |>
  select(-treatment_arm) |>
  left_join(participants |> select(respondent_id, arm, page_index, sequence_started,
      is_pretest, data_phase, navigation_monitoring_started, navigation_violation,
      navigation_reload_count, navigation_history_count, navigation_events,
      navigation_partial_task, navigation_record_status, study_terminated, study_termination_reason,
      study_terminated_at_utc, study_termination_page_index,
      study_termination_submitted_round),
            by = "respondent_id") |>
  mutate(
    # This 10-page-per-round index comes from the current oTree page sequence.
    # Profiles are assigned when a page opens, so IDs alone do not prove submission.
    task_page_index = 10L * (round - 1L) + 7L,
    # Fail-fast termination leaves the page index unchanged. Only an exported
    # saved-POST marker may count that stopped Task as submitted. Reload/history
    # stops without a Task POST do not invent a response or a timeout.
    submitted = sequence_started & (page_index > task_page_index |
      (study_terminated %in% TRUE & study_termination_submitted_round == round &
       study_termination_page_index == task_page_index & page_index == task_page_index)),
    task = round - n_practice_tasks
  )

all_submitted_tasks <- rounds |>
  filter(sequence_started, submitted) |>
  mutate(across(c(time_spent_seconds, time_to_first_choice_seconds, stimulus_load_seconds,
                  choice_changes, learn_more_clicks, info_cost_attempts,
                  rushed_scale, info_cost_scale), as.numeric),
    recorded_choice = case_when(
      decision_side == "left" & decision_candidate_id == left_candidate_id ~ TRUE,
      decision_side == "right" & decision_candidate_id == right_candidate_id ~ TRUE,
      TRUE ~ FALSE),
    deadline_expired = countdown_expired %in% c("1", "True", "TRUE"),
    # Q is terminal NONSELECTION, not simply an expired timer.
    terminal_timeout = as.integer(arm == "Time" & deadline_expired &
      is.na(decision_candidate_id) & is.na(decision_side)),
    left_opened = as.integer(left_ideology_opened %in% c("1", "True", "TRUE")),
    right_opened = as.integer(right_ideology_opened %in% c("1", "True", "TRUE")),
    n_descriptions = left_opened + right_opened,                 # K
    any_information = as.integer(n_descriptions >= 1),          # A
    both_information = as.integer(n_descriptions == 2),         # X
    # Zero is the SOFTWARE SENTINEL for no selection, not a zero-second decision.
    first_selection_seconds = if_else(terminal_timeout == 1L, NA_real_,
                                      time_to_first_choice_seconds),
    capped_latency = if_else(terminal_timeout == 1L, selection_window_seconds,
                              pmin(first_selection_seconds, selection_window_seconds)),
    slow_selection = if_else(terminal_timeout == 1L, 1L,
                              as.integer(first_selection_seconds > selection_window_seconds)),
    real_election_support = case_when(realistic_vote == "yes" ~ 1,
                                      realistic_vote == "no" ~ 0,
                                      TRUE ~ NA_real_)
  )

# Stop on inconsistent data rather than silently inventing votes or timing values.
stopifnot(all(all_submitted_tasks$recorded_choice |
                all_submitted_tasks$terminal_timeout == 1L),
          !anyNA(all_submitted_tasks$left_candidate_id),
          !anyNA(all_submitted_tasks$right_candidate_id),
          !anyNA(all_submitted_tasks$left_ideology_opened),
          !anyNA(all_submitted_tasks$right_ideology_opened),
          !anyNA(all_submitted_tasks$capped_latency),
          all(all_submitted_tasks$capped_latency >= 0),
          all(all_submitted_tasks$capped_latency <= selection_window_seconds),
          all(is.na(all_submitted_tasks$first_selection_seconds) |
                all_submitted_tasks$first_selection_seconds <=
                all_submitted_tasks$time_spent_seconds + 0.05))

practice_tasks <- all_submitted_tasks |> filter(round <= n_practice_tasks)
tasks <- all_submitted_tasks |> filter(round > n_practice_tasks) |>
  group_by(respondent_id) |>
  mutate(respondent_weight = 1 / n()) |>
  ungroup()

# Count unfinished respondents too. Zero submitted analytical tasks is not fifteen
# timeouts, and currently unfinished respondents are not necessarily withdrawals.
task_counts <- tasks |>
  group_by(respondent_id) |>
  summarise(n_tasks = n(), n_choices = sum(recorded_choice),
            n_timeouts = sum(terminal_timeout), .groups = "drop")
# This is the ONE completion threshold used by all analyses and paper outputs.
# Mirror the live monitor's completion_rules.py. Do not use complete.cases():
# intentionally skipped follow-ups and up to two unanswered choices are allowed.
# A detected monitored reload/history event overrides completion, including for
# a response stopped before the final screen. Unknown historical records are
# not retroactively flagged; the frozen pre-test is therefore unchanged.
participants <- participants |>
  left_join(task_counts, by = "respondent_id") |>
  mutate(across(c(n_tasks, n_choices, n_timeouts), ~replace_na(.x, 0L)),
         n_missing_choices = n_tasks - n_choices,
         minimum_valid_main_choices = minimum_valid_main_choices,
         study_complete = eligible_final_screen_completion & n_tasks == n_main_tasks &
           n_choices >= minimum_valid_main_choices & !navigation_violation %in% TRUE &
           !study_terminated %in% TRUE,
         in_selected_cohort = if (analysis_scope == "pretest") data_phase == "pretest" else data_phase == "main",
         in_analysis = study_complete & in_selected_cohort,
         completion_status = case_when(
           navigation_violation %in% TRUE ~ "navigation_incomplete",
           study_terminated %in% TRUE & study_termination_reason == "insufficient_choices" ~
             "terminated_insufficient_choices",
           study_terminated %in% TRUE ~ "terminated_incomplete",
           !eligible ~ "ineligible",
           study_complete ~ "complete",
           eligible_final_screen_completion ~ "finished_insufficient_choices",
           TRUE ~ "in_progress"))
cohort_audit <- participants |> filter(visited, !bot)
incomplete_people <- cohort_audit |> filter(!study_complete)
incomplete_tasks <- tasks |> semi_join(incomplete_people, by = "respondent_id")
recruitment_people <- cohort_audit |> filter(in_selected_cohort)
analysis_people <- participants |> filter(in_analysis)
has_main_data <- nrow(analysis_people) > 0L
# Treatment contrasts require observations in all three arms. This is a data-
# availability check, not a significance or precision threshold.
has_model_data <- has_main_data & n_distinct(analysis_people$arm) == 3L
if (analysis_scope == "main") {
  stopifnot(!any(analysis_people$is_pretest))
  message("MAIN FIELDWORK: ", nrow(analysis_people), " eligible completes. PRE-TEST: ",
          sum(cohort_audit$is_pretest & cohort_audit$study_complete),
          " completed cases excluded; raw responses are preserved.")
  if (is.na(main_fieldwork_start_utc)) message(
    "New collection is identified by consistent recorded nine-second task metadata ",
    "after the original pre-test window; no launch date has been assumed.")
}

# Central complete-only filter. All downstream tables, models, plots and exported
# analysis frames inherit this sample. Raw responses are never deleted or edited.
dat <- raw_dat |>
  semi_join(analysis_people, by = c("participant.code" = "respondent_id")) |>
  left_join(analysis_people |> select(respondent_id, study_complete,
    eligible_final_screen_completion, n_tasks, n_choices, n_missing_choices,
    minimum_valid_main_choices, completion_status),
    by = c("participant.code" = "respondent_id"))
tasks <- tasks |> semi_join(analysis_people, by = "respondent_id")
all_submitted_tasks <- all_submitted_tasks |>
  semi_join(analysis_people, by = "respondent_id")
practice_tasks <- all_submitted_tasks |> filter(round <= n_practice_tasks)
stopifnot(nrow(tasks) == n_main_tasks * nrow(analysis_people),
          all(analysis_people$n_choices >= minimum_valid_main_choices),
          all(analysis_people$n_missing_choices <= allowed_missing_choices),
          !any(analysis_people$navigation_violation %in% TRUE),
          !any(analysis_people$study_terminated %in% TRUE),
          !anyDuplicated(tasks[c("respondent_id", "task")]))

## ---- 

## ---- analysis-candidates
# Make TWO rows per submitted analytical task, one per displayed profile. Preserve
# every exported candidate attribute. SEXO is the complete, documented candidate-sex
# classification. GENERO and the machine-predicted sex field are not substitutes.
candidate_tasks <- tasks |>
  select(respondent_id, round, task, arm, respondent_weight,
         decision_candidate_id, decision_side, recorded_choice,
         terminal_timeout, deadline_expired, time_spent_seconds,
         first_selection_seconds, capped_latency, n_descriptions,
         matches("^(left|right)_")) |>
  select(-left_right_self_placement) |>
  pivot_longer(matches("^(left|right)_"), names_to = c("side", ".value"),
               names_pattern = "(left|right)_(.+)") |>
  mutate(
    side = factor(side, levels = c("left", "right")),
    woman = case_when(sexo == "Femenino" ~ 1L, sexo == "Masculino" ~ 0L,
                      TRUE ~ NA_integer_),
    information_opened = as.integer(ideology_opened %in% c("1", "True", "TRUE")), # M^s
    # Y is a REGISTERED SELECTION EVENT. A missing vote stays missing in the
    # original field, but both event indicators equal zero for a submitted timeout.
    selected = as.integer(!is.na(decision_candidate_id) &
                            decision_candidate_id == candidate_id),
    candidate_gender = factor(woman, levels = c(0, 1), labels = c("Men", "Women")),
    candidate_ideology = factor(ideologia, levels = c("Izquierda", "Centro", "Derecha"),
                                labels = c("Left", "Center", "Right"))
  )
stopifnot(!anyNA(candidate_tasks$woman), !anyNA(candidate_tasks$selected),
          nrow(candidate_tasks) == 2L * nrow(tasks))
choice_check <- candidate_tasks |>
  group_by(respondent_id, round) |>
  summarise(selection_events = sum(selected), timeout = first(terminal_timeout),
            .groups = "drop")
stopifnot(all(choice_check$selection_events == 1L - choice_check$timeout))

## ---- 

## ---- analysis-candidate-attributes
# This is the SAME candidate file used by the experiment. IDs stay as text.
# The export already contains all candidate metadata, so do not append rows or
# merge by row position. Validate IDs, then join readable attributes by ID only.
candidate_file <- file.path(project_dir, "_static", "conjoint", "data",
                            "base_final_merged.csv")
candidate_catalogue <- read_csv(candidate_file,
  col_types = cols(.default = col_character()), na = "", trim_ws = TRUE,
  name_repair = "minimal", show_col_types = FALSE)
stopifnot(!anyNA(candidate_catalogue$ID), !anyDuplicated(candidate_catalogue$ID))
candidate_file_checksum <- unname(tools::md5sum(candidate_file))

# Check IDs from EVERY recorded presentation, not just the retained completes.
# anti_join returns IDs used in the experiment but absent from the source CSV.
used_candidate_ids <- raw_dat |>
  select(matches("^conjoint\\.[0-9]+\\.player\\.(left|right)_candidate_id$")) |>
  pivot_longer(everything(), values_to = "candidate_id", values_drop_na = TRUE) |>
  distinct(candidate_id)
unmatched_candidate_ids <- used_candidate_ids |>
  anti_join(candidate_catalogue, by = c("candidate_id" = "ID"))
if (nrow(unmatched_candidate_ids) > 0L) {
  stop("Candidate IDs used in the experiment are missing from base_final_merged.csv.")
}

# The app excludes a profile if its information text is missing. The remaining
# CSV rows are its eligible profile pool. All displayed profiles must belong to it.
eligible_candidate_catalogue <- candidate_catalogue |>
  filter(!is.na(Texto), nzchar(trimws(Texto)))
stopifnot(nrow(anti_join(used_candidate_ids, eligible_candidate_catalogue,
                        by = c("candidate_id" = "ID"))) == 0L)
candidate_id_coverage <- tibble(
  source_profiles = nrow(candidate_catalogue),
  eligible_profiles = nrow(eligible_candidate_catalogue),
  used_profiles = nrow(used_candidate_ids),
  unmatched_profiles = nrow(unmatched_candidate_ids))

# Protect what respondents actually saw. If someone later edits the source CSV,
# stop rather than silently overwrite the historical exported classifications.
candidate_metadata_check <- candidate_tasks |>
  distinct(candidate_id, sexo, ideologia, dominancia, edad_categoria, texto) |>
  left_join(candidate_catalogue |>
    select(ID, Sexo, Ideologia, Dominancia, Edad, Texto),
    by = c("candidate_id" = "ID"), relationship = "many-to-one")
stopifnot(all(candidate_metadata_check$sexo == candidate_metadata_check$Sexo),
          all(candidate_metadata_check$ideologia == candidate_metadata_check$Ideologia),
          all(candidate_metadata_check$dominancia == candidate_metadata_check$Dominancia),
          all(candidate_metadata_check$edad_categoria == candidate_metadata_check$Edad),
          all(candidate_metadata_check$texto == candidate_metadata_check$Texto))

# Readable analytical columns. 'Ideologia' is the candidate's displayed ideology.
# Do NOT replace it with the auxiliary party-based 'ideologia_cat' classification.
# Dominance is an appearance classification, not a measure of attractiveness.
# The age category describes the profile classification, not recorded age in years.
# Decimal commas in the facial/age metadata must be parsed explicitly.
candidate_attributes <- candidate_catalogue |>
  transmute(candidate_id = ID,
    candidate_gender = factor(Sexo, levels = c("Masculino", "Femenino"),
                              labels = c("Men", "Women")),
    candidate_ideology = factor(Ideologia, levels = c("Centro", "Izquierda", "Derecha"),
                                labels = c("Center", "Left", "Right")),
    candidate_dominance = factor(Dominancia, levels = c("Baja", "Alta"),
                                 labels = c("Low", "High")),
    candidate_age_group = factor(Edad, levels = c("Joven", "Mayor"),
                                 labels = c("Younger", "Older")),
    candidate_age_years = parse_double(EDAD, locale = locale(decimal_mark = ",")),
    candidate_estimated_age_years = parse_double(`age (estimada)`,
                                                locale = locale(decimal_mark = ",")),
    candidate_fhwr = parse_double(fhwr, locale = locale(decimal_mark = ",")),
    candidate_fhwr_corrected = parse_double(fhwr_correg,
                                           locale = locale(decimal_mark = ",")),
    candidate_party = PARTIDO)
candidate_tasks <- candidate_tasks |>
  select(-candidate_gender, -candidate_ideology) |>
  left_join(candidate_attributes, by = "candidate_id", relationship = "many-to-one") |>
  mutate(
    # Standard conjoint outcome. No response means NA for BOTH alternatives.
    chosen = if_else(recorded_choice, selected, NA_integer_)
    # 'selected' remains the registered-selection event used by the proposal:
    # it is zero for both candidates in a retained no-choice timeout.
  ) |>
  left_join(analysis_people |>
    transmute(respondent_id, study_complete, n_choices, n_missing_choices,
      respondent_age = age, respondent_gender = gender,
      respondent_ideology = ideology, respondent_political_interest = political_interest),
    by = "respondent_id", relationship = "many-to-one")

# This is the dataframe to use for conjoint-style analyses. Each task has TWO
# rows, one per displayed candidate, including all 41 original metadata columns.
# Wide 'dat' is retained for compatibility; conjoint_dat is its candidate-level view.
conjoint_dat <- candidate_tasks |>
  mutate(choice_set_id = paste(respondent_id, task, sep = "_")) |>
  relocate(respondent_id, task, choice_set_id, arm, side, candidate_id, chosen, selected,
           information_opened, candidate_gender, candidate_ideology,
           candidate_dominance, candidate_age_group, study_complete)
stopifnot(nrow(conjoint_dat) == 2L * nrow(tasks),
          n_distinct(conjoint_dat$choice_set_id) == nrow(tasks),
          !anyDuplicated(conjoint_dat[c("choice_set_id", "side")]),
          all(conjoint_dat$study_complete),
          all(conjoint_dat$candidate_id == conjoint_dat$id),
          !anyNA(conjoint_dat$candidate_gender),
          !anyNA(conjoint_dat$candidate_ideology),
          !anyNA(conjoint_dat$candidate_dominance),
          !anyNA(conjoint_dat$candidate_age_group),
          sum(is.na(conjoint_dat$chosen)) == 2L * sum(tasks$terminal_timeout))

# The eligible pool was assembled as a crossed design of real candidates:
# gender x displayed ideology x dominance x age group. Report its cell sizes and
# the facial width-to-height ratio (fWHR) behind the dominance classification.
pool_design <- eligible_candidate_catalogue |> count(Sexo, Ideologia, Dominancia, Edad)
pool_fwhr <- eligible_candidate_catalogue |>
  transmute(Dominancia, fwhr = parse_double(fhwr_correg, locale = locale(decimal_mark = ","))) |>
  group_by(Dominancia) |>
  summarise(median_fwhr = median(fwhr, na.rm = TRUE), .groups = "drop")
pool_counts <- list(cells = nrow(pool_design), min_per_cell = min(pool_design$n),
  max_per_cell = max(pool_design$n),
  fwhr_high = pool_fwhr$median_fwhr[pool_fwhr$Dominancia == "Alta"],
  fwhr_low = pool_fwhr$median_fwhr[pool_fwhr$Dominancia == "Baja"])

## ----

## ---- analysis-descriptives
if (has_main_data) {
  # Describe PEOPLE once each, not the two candidate rows or fifteen repeated tasks.
  # tableone produces familiar means/SDs and categorical counts/percentages.
  sample_for_table <- analysis_people |>
    select(arm, Age = age, Gender = gender, Education = education,
           `Voted in last election` = voted,
           `Political interest (1-7)` = political_interest,
           `Left-right position (1-10)` = ideology)
  sample_table <- CreateTableOne(data = sample_for_table, strata = "arm",
    vars = names(sample_for_table)[-1L], addOverall = TRUE, test = FALSE, includeNA = TRUE)
  sample_table_print <- print(sample_table, showAllLevels = TRUE, printToggle = FALSE,
    noSpaces = TRUE, missing = TRUE, contDigits = 1)
  rownames(sample_table_print) <- gsub(" (mean (SD))", "",
    rownames(sample_table_print), fixed = TRUE)
  colnames(sample_table_print)[1L] <- "Category"
  sample_table_print <- data.frame(Characteristic = rownames(sample_table_print),
    sample_table_print, check.names = FALSE, row.names = NULL)

  # Residence is summarised in the table note rather than in a long table.
  residence_counts <- analysis_people |>
    count(country, sort = TRUE) |>
    mutate(percent = 100 * n / sum(n))
  residence_note <- residence_counts |>
    slice_head(n = 3L) |>
    mutate(note = paste0(country, " ", sprintf("%.0f", percent), "\\%")) |>
    pull(note) |>
    paste(collapse = ", ")

  # Recruitment accounting covers EVERY started attempt, as in Gabriel's panel.
  # Other-protocol completes are shown separately, never pooled into the models.
  # These mutually exclusive labels retain stopped cases and distinguish pending
  # screening from a genuine screen-out. No raw record or response is deleted.
  flow_categories <- c("Screened out", "Initial screening or baseline not completed",
    "Eligible participants not yet finished", "Finished below the response threshold",
    "Excluded after detected reload or browser-history navigation",
    "Stopped after exceeding the permitted missing choices",
    "Other terminated incomplete cases", "Other-protocol completes excluded from analysis",
    "Eligible completes included in analysis")
  flow_counts <- cohort_audit |>
    mutate(Stage = case_when(
      completion_status == "navigation_incomplete" ~ flow_categories[5L],
      completion_status == "terminated_insufficient_choices" ~ flow_categories[6L],
      completion_status == "terminated_incomplete" ~ flow_categories[7L],
      screened_out ~ flow_categories[1L],
      study_complete & in_analysis ~ flow_categories[9L],
      study_complete ~ flow_categories[8L],
      eligible_final_screen_completion ~ flow_categories[4L],
      eligible ~ flow_categories[3L],
      TRUE ~ flow_categories[2L]),
      Stage = factor(Stage, levels = flow_categories)) |>
    count(Stage, name = "N", .drop = FALSE) |>
    mutate(Stage = as.character(Stage))
  flow_table <- bind_rows(
    tibble(Stage = "Survey entrants across study versions", N = nrow(cohort_audit)),
    flow_counts)
  stopifnot(sum(flow_table$N[-1L]) == flow_table$N[1L])
  arm_flow <- analysis_people |> group_by(arm) |>
    summarise(Respondents = n(), Tasks = sum(n_tasks),
      `Valid choices` = sum(n_choices), `Missing choices` = sum(n_missing_choices),
      .groups = "drop")

  # ONE implementation table: how each environment was experienced. Deadline
  # quantities are reported only where they exist (Time); hurry is asked in
  # Baseline and Time; effort and arithmetic only in Cost. Follow-up means
  # describe respondents who were asked AND answered, so they stay descriptive.
  manipulation_checks <- tasks |> group_by(arm) |>
    summarise(
      respondents = n_distinct(respondent_id), tasks = n(),
      both_pct = 100 * mean(both_information),
      expired_pct = 100 * mean(deadline_expired),
      timeout_pct = 100 * mean(terminal_timeout),
      first_median = median(first_selection_seconds, na.rm = TRUE),
      duration_median = median(time_spent_seconds),
      duration_p90 = unname(quantile(time_spent_seconds, 0.90)),
      hurry_mean = mean(rushed_scale, na.rm = TRUE),
      hurry_n = sum(!is.na(rushed_scale)),
      effort_mean = mean(info_cost_scale, na.rm = TRUE),
      effort_n = sum(!is.na(info_cost_scale)),
      attempts_mean = mean(info_cost_attempts),
      passed_pct = 100 * mean(info_cost_task_completed %in% c("1", "True", "TRUE")),
      .groups = "drop") |>
    mutate(across(where(is.numeric), ~if_else(is.nan(.x), NA_real_, .x)),
      across(c(expired_pct, timeout_pct), ~if_else(arm == "Time", .x, NA_real_)),
      across(c(hurry_mean, hurry_n), ~if_else(arm == "Cost", NA_real_, .x)),
      across(c(effort_mean, effort_n, attempts_mean, passed_pct),
             ~if_else(arm == "Cost", .x, NA_real_)))
  implementation_labels <- tribble(~measure, ~Measure, ~digits,
    "respondents", "Eligible completed respondents", 0,
    "tasks", "Analytical tasks", 0,
    "both_pct", "Both descriptions opened (\\%)", 1,
    "expired_pct", "Deadline reached (\\%)", 1,
    "timeout_pct", "Ended without a selection, $Q$ (\\%)", 1,
    "first_median", "Median time to first selection (s)", 2,
    "duration_median", "Median task duration (s)", 2,
    "duration_p90", "90th percentile of task duration (s)", 2,
    "hurry_mean", "Reported hurry, 1--7 (mean)", 2,
    "hurry_n", "\\quad Hurry answers (n)", 0,
    "effort_mean", "Reported effort, 1--7 (mean)", 2,
    "effort_n", "\\quad Effort answers (n)", 0,
    "attempts_mean", "Arithmetic attempts per task (mean)", 2,
    "passed_pct", "Tasks with a solved arithmetic problem (\\%)", 1)
  implementation_print <- manipulation_checks |>
    pivot_longer(-arm, names_to = "measure", values_to = "value") |>
    inner_join(implementation_labels, by = "measure") |>
    mutate(Value = unname(mapply(function(v, d) if (is.na(v)) "--" else
             formatC(v, format = "f", digits = d), value, digits)),
           measure = factor(measure, levels = implementation_labels$measure)) |>
    select(measure, Measure, arm, Value) |>
    pivot_wider(names_from = arm, values_from = Value) |>
    arrange(measure) |>
    select(-measure)
}

## ----

## ---- analysis-estimates
if (has_model_data) {
  # TWO ESTIMATORS OF THE SAME completion-conditioned contrasts (paper, Sec. 5).
  # (a) MAIN, PREREGISTERED: differences in condition means for the process
  #     family (eq. 1), and the condition-by-candidate-gender LPM with side and
  #     task indicators for the gender family (eq. 2). Objects without a suffix.
  # (b) COMPLEMENTARY: regression-adjusted models, eqs. (3)-(5). They target
  #     the same contrasts and remove outcome variation explained by regressors
  #     fixed before the environment is revealed. Objects end in _adj. NEVER add
  #     clicks, revealed text, hurry, arithmetic success or timing to them:
  #     those are outcomes of the assigned environment.
  # The paper reads both: Table 2 classifies each test by whether both, one or
  # neither estimator rejects zero at Holm-adjusted p < evidence_alpha.
  # Binary outcomes are linear probability models, so coefficients are
  # differences in probabilities. Uncertainty is clustered by respondent (the
  # level of assignment), plus candidate for candidate appearances; fixest uses
  # t critical values on (smallest cluster count - 1) degrees of freedom.
  family_process <- "Primary process family"
  family_gender <- "Primary gender-interaction family"
  family_baseline <- "Baseline descriptive family (gender not randomized)"
  estimator_levels <- c("Preregistered", "Regression-adjusted")
  evidence_alpha <- 0.05
  process_outcomes <- tibble(
    variable = c("any_information", "n_descriptions", "capped_latency", "slow_selection"),
    outcome = c("Any information", "Descriptions revealed",
                "Capped first-selection time (s)",
                paste0("No selection within ", selection_window_seconds, " seconds")),
    panel = c("Any description opened (%)", "Descriptions opened (0-2)",
              paste0("Time to first selection (s, capped at ", selection_window_seconds, ")"),
              paste0("No selection within ", selection_window_seconds, " s (%)")),
    scale = c(100, 1, 1, 100))
  # Time and Cost coefficients, Holm-adjusted across the eight process tests.
  tidy_process <- function(models) {
    bind_rows(lapply(names(models), function(o)
      tidy(models[[o]], conf.int = TRUE, conf.level = confidence_level) |>
        mutate(outcome = o))) |>
      filter(term %in% c("armTime", "armCost")) |>
      mutate(contrast = recode(term, armTime = "Time - Baseline",
                               armCost = "Cost - Baseline"),
             p_holm = p.adjust(p.value, method = "holm")) |>
      select(outcome, contrast, estimate, std.error, conf.low, conf.high, p.value, p_holm)
  }

  # ---- (a) Main process estimator, eq. (1): difference in condition means.
  process_models_dim <- lapply(setNames(process_outcomes$variable, process_outcomes$outcome),
    function(y) feols(as.formula(paste(y, "~ arm")), data = tasks, vcov = ~respondent_id))
  process_effects <- tidy_process(process_models_dim)

  # ---- (b) Complementary process estimator, eq. (3): Lin (2013) adjustment.
  # Pretreatment covariates from the baseline questionnaire, centred at the
  # analytical-sample mean and interacted with condition. That equals separate
  # regressions per condition compared at the COMMON covariate mean, so the arm
  # coefficients estimate the same contrasts as the difference in means, and
  # asymptotically never less precisely. Keep the list short: each covariate
  # costs three parameters and the interim arms are small. Task indicators are
  # omitted on purpose: every respondent completes all fifteen tasks, so they
  # are orthogonal to respondent-level regressors and would change nothing.
  covariate_key <- tibble(
    variable = c("age10", "resp_woman", "tertiary", "interest"),
    label = c("Age (decades)", "Woman respondent", "Tertiary education",
              "Political interest (1--7)"))
  respondent_covariates <- analysis_people |>
    transmute(respondent_id, arm, age10 = age / 10,
      resp_woman = as.integer(gender == "Woman"),
      tertiary = as.integer(education %in% c("Technical or university", "Postgraduate")),
      interest = political_interest)
  stopifnot(!anyNA(respondent_covariates),
            !anyDuplicated(respondent_covariates$respondent_id))
  centered_terms <- paste0(covariate_key$variable, "_c")
  model_tasks <- tasks |>
    left_join(respondent_covariates |> select(-arm) |>
      mutate(across(all_of(covariate_key$variable), ~ .x - mean(.x), .names = "{.col}_c")),
      by = "respondent_id", relationship = "many-to-one")
  stopifnot(nrow(model_tasks) == nrow(tasks), !anyNA(model_tasks[centered_terms]))
  process_models <- lapply(setNames(process_outcomes$variable, process_outcomes$outcome),
    function(y) feols(as.formula(paste(y, "~ arm * (",
                                       paste(centered_terms, collapse = " + "), ")")),
                      data = model_tasks, vcov = ~respondent_id))
  stopifnot(all(vapply(process_models, nobs, integer(1)) == nrow(tasks)))
  process_effects_adj <- tidy_process(process_models)

  # A direct pressure check uses observed hurry answers in Time and Baseline.
  # This is conditional on answering the post-choice question, not an unconditional ITT.
  model_hurry <- feols(rushed_scale ~ arm,
    data = tasks |> filter(arm != "Cost") |> mutate(arm = droplevels(arm)),
    vcov = ~respondent_id)
  hurry_check <- tidy(model_hurry, conf.int = TRUE, conf.level = confidence_level) |>
    filter(term == "armTime")

  # Observed condition means behind Figure 2A, on the same clustered footing.
  condition_means <- bind_rows(lapply(seq_len(nrow(process_outcomes)), function(k) {
    fit <- feols(as.formula(paste(process_outcomes$variable[k], "~ 0 + arm")),
                 data = tasks, vcov = ~respondent_id)
    tidy(fit, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(arm = factor(sub("^arm", "", term), levels = levels(tasks$arm)),
             outcome = process_outcomes$outcome[k])
  })) |>
    left_join(process_outcomes, by = "outcome")
  stopifnot(nrow(condition_means) == 3L * nrow(process_outcomes))

  # ---- (a) Main gender estimator, eq. (2). Side and task indicators follow the
  # proposal; two-way clustering allows repeated respondents AND candidates.
  # Candidate gender is bundled with other traits, so these are NOT gender AMCEs.
  model_information <- feols(information_opened ~ arm * woman + side + factor(task),
    data = candidate_tasks, vcov = ~respondent_id + candidate_id)
  model_choice <- feols(selected ~ arm * woman + side + factor(task),
    data = candidate_tasks, vcov = ~respondent_id + candidate_id)
  gender_effects <- bind_rows(
    tidy(model_information, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(outcome = "Information acquisition"),
    tidy(model_choice, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(outcome = "Registered selection")
  ) |> filter(term %in% c("armTime:woman", "armCost:woman")) |>
    mutate(contrast = recode(term, `armTime:woman` = "Time - Baseline",
                            `armCost:woman` = "Cost - Baseline"),
           p_holm = p.adjust(p.value, method = "holm")) |>
    select(outcome, contrast, estimate, std.error, conf.low, conf.high, p.value, p_holm)
  # emmeans forms Gamma within each condition from the same clustered covariance,
  # with degrees of freedom from the smaller cluster count.
  gender_df <- min(n_distinct(candidate_tasks$respondent_id),
                   n_distinct(candidate_tasks$candidate_id)) - 1L
  information_means <- emmeans(model_information, ~woman | arm,
    data = candidate_tasks, at = list(woman = c(0, 1)), df = gender_df)
  choice_means <- emmeans(model_choice, ~woman | arm,
    data = candidate_tasks, at = list(woman = c(0, 1)), df = gender_df)
  gamma_summary <- function(means) as.data.frame(summary(contrast(means,
    method = list(`Women - men` = c(-1, 1))), infer = c(TRUE, TRUE),
    level = confidence_level))
  gender_contrasts <- bind_rows(
    gamma_summary(information_means) |> mutate(Outcome = "Information acquisition"),
    gamma_summary(choice_means) |> mutate(Outcome = "Registered selection")) |>
    transmute(Outcome, Condition = factor(arm, levels = levels(tasks$arm)),
              Gamma = estimate, std.error = SE, conf.low = lower.CL,
              conf.high = upper.CL, p = p.value) |>
    group_by(Condition) |>
    mutate(holm_p = if_else(Condition == "Baseline", p.adjust(p, method = "holm"),
                            NA_real_)) |>
    ungroup()
  # Observed candidate-level means mu_g(z) behind Figure 3A.
  gender_means <- bind_rows(
    as.data.frame(summary(information_means, infer = c(TRUE, FALSE),
                          level = confidence_level)) |>
      mutate(Outcome = "Information acquisition"),
    as.data.frame(summary(choice_means, infer = c(TRUE, FALSE),
                          level = confidence_level)) |>
      mutate(Outcome = "Registered selection")) |>
    mutate(candidate_gender = factor(woman, levels = c(0, 1), labels = c("Men", "Women")),
           arm = factor(arm, levels = levels(tasks$arm)))

  # ---- (b) Complementary gender estimators, eqs. (4) and (5).
  # Respondent fixed effects absorb each person's propensity to open or select,
  # the assigned environment and EVERY respondent covariate. Candidate fixed
  # effects absorb everything fixed about a real profile: face, party, biography
  # AND gender. Psi is then identified by how the within-respondent women-minus-
  # men gap moves across randomized environments for the same real candidates.
  # Gamma needs candidate gender, so equation (5) drops candidate effects.
  # Congruence compares the PRETREATMENT self-placement (left 1-4, centre 5-6,
  # right 7-10) with the displayed ideology; it is zero without a numeric
  # placement and may differ by condition. woman x centred respondent gender
  # absorbs same-gender affinity. All of these are independent of assignment.
  candidate_model_data <- conjoint_dat |>
    left_join(respondent_covariates |> select(respondent_id, resp_woman),
              by = "respondent_id", relationship = "many-to-one") |>
    mutate(resp_woman_c = resp_woman - mean(respondent_covariates$resp_woman),
      respondent_side = cut(respondent_ideology, breaks = c(0, 4, 6, 10),
                            labels = c("Left", "Center", "Right")),
      congruent = as.integer(!is.na(respondent_side) &
        as.character(respondent_side) == as.character(candidate_ideology)))
  stopifnot(nrow(candidate_model_data) == nrow(conjoint_dat),
            !anyNA(candidate_model_data[c("resp_woman_c", "congruent", "woman")]))
  gender_outcomes <- c(`Information acquisition` = "information_opened",
                       `Registered selection` = "selected")
  candidate_controls <- "i(arm, congruent) + woman:resp_woman_c + side"
  psi_models <- lapply(gender_outcomes, function(y) feols(as.formula(paste(y,
      "~ i(arm, woman, ref = 'Baseline') +", candidate_controls,
      "| respondent_id + candidate_id + task")),
    data = candidate_model_data, vcov = ~respondent_id + candidate_id))
  gamma_models <- lapply(gender_outcomes, function(y) feols(as.formula(paste(y,
      "~ i(arm, woman) +", candidate_controls, "| respondent_id + task")),
    data = candidate_model_data, vcov = ~respondent_id + candidate_id))
  stopifnot(all(vapply(c(psi_models, gamma_models), nobs, integer(1)) ==
                  nrow(candidate_model_data)))
  tidy_models <- function(models, outcome_name = "outcome") {
    bind_rows(lapply(names(models), function(o)
      tidy(models[[o]], conf.int = TRUE, conf.level = confidence_level) |>
        mutate(!!outcome_name := o)))
  }
  gender_effects_adj <- tidy_models(psi_models) |>
    filter(term %in% c("arm::Time:woman", "arm::Cost:woman")) |>
    mutate(contrast = recode(term, `arm::Time:woman` = "Time - Baseline",
                             `arm::Cost:woman` = "Cost - Baseline"),
           p_holm = p.adjust(p.value, method = "holm")) |>
    select(outcome, contrast, estimate, std.error, conf.low, conf.high, p.value, p_holm)
  gender_contrasts_adj <- tidy_models(gamma_models, "Outcome") |>
    filter(grepl("^arm::.+:woman$", term)) |>
    transmute(Outcome,
      Condition = factor(sub("^arm::(.+):woman$", "\\1", term), levels = levels(tasks$arm)),
      Gamma = estimate, std.error, conf.low, conf.high, p = p.value) |>
    group_by(Condition) |>
    mutate(holm_p = if_else(Condition == "Baseline", p.adjust(p, method = "holm"),
                            NA_real_)) |>
    ungroup()
  # The pool crosses gender with ideology, so congruence is nearly orthogonal
  # to candidate gender; the paper reports this correlation next to eq. (5).
  congruence_gender_cor <- cor(candidate_model_data$woman, candidate_model_data$congruent)
  stopifnot(nrow(process_effects_adj) == 8L, nrow(gender_effects_adj) == 4L,
            nrow(gender_contrasts_adj) == 6L, nrow(process_effects) == 8L,
            nrow(gender_effects) == 4L,
            !anyDuplicated(process_effects_adj[c("outcome", "contrast")]),
            !anyDuplicated(gender_effects_adj[c("outcome", "contrast")]))

  # TABLE 2: every preregistered primary test, keyed to its estimand and
  # hypothesis: the main preregistered differences, the complementary
  # regression-adjusted estimate, and which of the two reject zero. Probabilities
  # are in percentage points, counts in descriptions and latency in seconds.
  # Holm corrections stay within family and estimator. SE ratio = adjusted over
  # main standard error (<1 = precision gain from adjustment).
  d_label <- paste0("D^{", selection_window_seconds, "}")
  s_label <- paste0("S^{", selection_window_seconds, "}")
  no_selection_outcome <- process_outcomes$outcome[4L]
  test_key <- tribble(~outcome, ~contrast, ~Estimand, ~Hypothesis, ~Expected, ~Unit, ~scale, ~digits,
    "Any information", "Time - Baseline", "$\\tau^{A}_{TB}$", "H1", "$<0$", "pp", 100, 1,
    "Any information", "Cost - Baseline", "$\\tau^{A}_{CB}$", "H1", "$<0$", "pp", 100, 1,
    "Descriptions revealed", "Time - Baseline", "$\\tau^{K}_{TB}$", "H1", "$<0$", "count", 1, 2,
    "Descriptions revealed", "Cost - Baseline", "$\\tau^{K}_{CB}$", "H1", "$<0$", "count", 1, 2,
    "Capped first-selection time (s)", "Time - Baseline",
      paste0("$\\tau^{", d_label, "}_{TB}$"), "H2", "$<0$", "s", 1, 2,
    "Capped first-selection time (s)", "Cost - Baseline",
      paste0("$\\tau^{", d_label, "}_{CB}$"), "H2", "$\\neq 0$", "s", 1, 2,
    no_selection_outcome, "Time - Baseline",
      paste0("$\\tau^{", s_label, "}_{TB}$"), "H2", "$\\neq 0$", "pp", 100, 1,
    no_selection_outcome, "Cost - Baseline",
      paste0("$\\tau^{", s_label, "}_{CB}$"), "H2", "$\\neq 0$", "pp", 100, 1,
    "Information acquisition", "Time - Baseline", "$\\Psi_M(T)$", "H3", "$<0$", "pp", 100, 1,
    "Information acquisition", "Cost - Baseline", "$\\Psi_M(C)$", "H3", "$<0$", "pp", 100, 1,
    "Registered selection", "Time - Baseline", "$\\Psi_Y(T)$", "H4", "$\\neq 0$", "pp", 100, 1,
    "Registered selection", "Cost - Baseline", "$\\Psi_Y(C)$", "H4", "$\\neq 0$", "pp", 100, 1,
    "Information acquisition", "Baseline", "$\\Gamma_M(B)$", "H3", "$>0$", "pp", 100, 1,
    "Registered selection", "Baseline", "$\\Gamma_Y(B)$", "--", "$\\neq 0$", "pp", 100, 1) |>
    mutate(order = row_number())
  stack_tests <- function(process, gender, contrasts) {
    bind_rows(
      process |> mutate(Family = family_process),
      gender |> mutate(Family = family_gender),
      contrasts |> filter(Condition == "Baseline") |>
        transmute(outcome = Outcome, contrast = "Baseline", estimate = Gamma, std.error,
                  conf.low, conf.high, p.value = p, p_holm = holm_p,
                  Family = family_baseline))
  }
  adjusted_tests <- stack_tests(process_effects_adj, gender_effects_adj,
                                gender_contrasts_adj) |>
    select(outcome, contrast, adj_estimate = estimate, adj_se = std.error,
           adj_low = conf.low, adj_high = conf.high, adj_p = p.value, adj_p_holm = p_holm)
  # Joint reading of the two estimators (paper, Sec. 5.3): which of them reject
  # zero at the Holm-adjusted level, and whether their signs agree.
  classify_evidence <- function(main_estimate, main_p, adj_estimate, adj_p,
                                alpha = evidence_alpha) {
    main_rejects <- main_p < alpha
    adj_rejects <- adj_p < alpha
    case_when(main_rejects & adj_rejects & sign(main_estimate) == sign(adj_estimate) ~ "both",
              main_rejects & adj_rejects ~ "conflicting",
              main_rejects ~ "main only",
              adj_rejects ~ "adjusted only",
              TRUE ~ "neither")
  }
  primary_tests <- stack_tests(process_effects, gender_effects, gender_contrasts) |>
    inner_join(test_key, by = c("outcome", "contrast")) |>
    left_join(adjusted_tests, by = c("outcome", "contrast")) |>
    mutate(se_ratio = adj_se / std.error,
           evidence = classify_evidence(estimate, p_holm, adj_estimate, adj_p_holm)) |>
    arrange(order)
  stopifnot(nrow(primary_tests) == nrow(test_key), !anyNA(primary_tests$adj_se),
            !anyNA(primary_tests$evidence))
  primary_tests_print <- primary_tests |>
    transmute(Estimand,
      Hypothesis = if_else(Hypothesis == "--", Expected, paste0(Hypothesis, ", ", Expected)),
      Unit,
      Estimate = tex_num(scale * estimate, digits),
      CI = tex_ci(scale * conf.low, scale * conf.high, digits),
      p = tex_p(p.value), `Holm p` = tex_p(p_holm),
      `Adjusted estimate` = tex_num(scale * adj_estimate, digits),
      `Adjusted Holm p` = tex_p(adj_p_holm),
      `SE ratio` = formatC(se_ratio, format = "f", digits = 2),
      `Rejected by` = evidence)
}

## ----

## ---- analysis-model-tables
if (has_model_data) {
  # APPENDIX TABLES B1-B2: the fitted equations behind Table 2. Each cell is a
  # coefficient with its clustered standard error below. Binary outcomes are
  # rescaled to percentage points so the tables read like Table 2.
  # 'spec' is a list of rows; each row names the coefficient in every column,
  # or NA where that column's model does not contain it.
  coefficient_rows <- function(models, spec, scales) {
    tables <- lapply(models, coeftable)
    cell <- function(m, term, what) {
      if (is.na(term) || !term %in% rownames(tables[[m]])) return("")
      value <- scales[m] * tables[[m]][term, what]
      if (what == 1L) tex_num(value, 2) else
        paste0("(", formatC(value, format = "f", digits = 2), ")")
    }
    bind_rows(lapply(spec, function(row) {
      tibble(Term = c(row$label, ""),
             !!!setNames(lapply(seq_along(models), function(m)
               c(cell(m, row$terms[m], 1L), cell(m, row$terms[m], 2L))),
               paste0("m", seq_along(models))),
             group = row$group)
    }))
  }
  model_footer <- function(models, rows) {
    stats <- tibble(Term = c("Observations", "$R^2$"),
      !!!setNames(lapply(seq_along(models), function(m)
        c(format(nobs(models[[m]]), big.mark = ","),
          formatC(r2(models[[m]], "r2"), format = "f", digits = 2))),
        paste0("m", seq_along(models))))
    bind_rows(rows, stats)
  }
  same_term <- function(term, n) rep(term, n)

  process_table_spec <- c(
    list(list(label = "\\armT", terms = same_term("armTime", 4),
              group = "Condition (difference from \\textup{\\armB})"),
         list(label = "\\armC", terms = same_term("armCost", 4),
              group = "Condition (difference from \\textup{\\armB})")),
    lapply(seq_len(nrow(covariate_key)), function(k)
      list(label = covariate_key$label[k], terms = same_term(centered_terms[k], 4),
           group = "Centered covariates (slopes in \\textup{\\armB})")))
  process_model_table <- coefficient_rows(process_models, process_table_spec,
                                          scales = process_outcomes$scale)
  process_model_footer <- model_footer(process_models, tibble(
    Term = c("Covariates $\\times$ condition", "Respondents (clusters)"),
    m1 = c("Yes", as.character(n_distinct(model_tasks$respondent_id))),
    m2 = c("Yes", as.character(n_distinct(model_tasks$respondent_id))),
    m3 = c("Yes", as.character(n_distinct(model_tasks$respondent_id))),
    m4 = c("Yes", as.character(n_distinct(model_tasks$respondent_id)))))

  candidate_models <- list(model_information, model_choice,
                           psi_models[[1]], psi_models[[2]],
                           gamma_models[[1]], gamma_models[[2]])
  # Terms per column: preregistered LPM (2), then eqs. (4) and (5), each M and Y.
  row_terms <- function(lpm, psi, gamma) rep(c(lpm, psi, gamma), each = 2L)
  group_condition <- "Condition (difference from \\textup{\\armB})"
  group_psi <- "Change in the women-minus-men gap, $\\Psi(z)$"
  group_gamma <- "Women-minus-men gap, $\\Gamma(z)$"
  group_controls <- "Other regressors"
  candidate_table_spec <- list(
    list(label = "\\armT", terms = row_terms("armTime", NA, NA), group = group_condition),
    list(label = "\\armC", terms = row_terms("armCost", NA, NA), group = group_condition),
    list(label = "Woman candidate $\\times$ \\armT",
         terms = row_terms("armTime:woman", "arm::Time:woman", NA), group = group_psi),
    list(label = "Woman candidate $\\times$ \\armC",
         terms = row_terms("armCost:woman", "arm::Cost:woman", NA), group = group_psi),
    list(label = "Woman candidate (\\armB)",
         terms = row_terms("woman", NA, "arm::Baseline:woman"), group = group_gamma),
    list(label = "Woman candidate in \\armT",
         terms = row_terms(NA, NA, "arm::Time:woman"), group = group_gamma),
    list(label = "Woman candidate in \\armC",
         terms = row_terms(NA, NA, "arm::Cost:woman"), group = group_gamma),
    list(label = "Congruent in \\armB",
         terms = row_terms(NA, "arm::Baseline:congruent", "arm::Baseline:congruent"),
         group = group_controls),
    list(label = "Congruent in \\armT",
         terms = row_terms(NA, "arm::Time:congruent", "arm::Time:congruent"),
         group = group_controls),
    list(label = "Congruent in \\armC",
         terms = row_terms(NA, "arm::Cost:congruent", "arm::Cost:congruent"),
         group = group_controls),
    list(label = "Woman candidate $\\times$ woman respondent",
         terms = row_terms(NA, "woman:resp_woman_c", "woman:resp_woman_c"),
         group = group_controls),
    list(label = "Right-hand position", terms = row_terms("sideright", "sideright", "sideright"),
         group = group_controls))
  candidate_model_table <- coefficient_rows(candidate_models, candidate_table_spec,
                                            scales = rep(100, length(candidate_models)))
  candidate_footer_column <- function(respondent_fe, candidate_fe) c(respondent_fe,
    candidate_fe, "Yes", as.character(n_distinct(candidate_model_data$respondent_id)), as.character(n_distinct(candidate_model_data$candidate_id)))
  candidate_model_footer <- model_footer(candidate_models, tibble(
    Term = c("Respondent fixed effects", "Candidate fixed effects",
             "Task-position fixed effects", "Respondents (clusters)",
             "Candidates (clusters)"),
    m1 = candidate_footer_column("No", "No"), m2 = candidate_footer_column("No", "No"),
    m3 = candidate_footer_column("Yes", "Yes"), m4 = candidate_footer_column("Yes", "Yes"),
    m5 = candidate_footer_column("Yes", "No"), m6 = candidate_footer_column("Yes", "No")))
}

## ----

## ---- analysis-variable-summary
if (has_model_data) {
  # TABLE 1: every variable used in the models or the results, at the level at
  # which it is measured, with overall moments and means by condition. Binary
  # variables are shares. Follow-up items are summarised where they were asked
  # and answered, so their N is smaller and some conditions show a dash.
  describe_variable <- function(data, variable, label, panel, digits = 2) {
    x <- as.numeric(data[[variable]])
    keep <- !is.na(x)
    by_arm <- vapply(levels(tasks$arm), function(a) {
      v <- x[keep & data$arm == a]
      if (length(v)) mean(v) else NA_real_
    }, numeric(1))
    tibble(Panel = panel, Variable = label, N = sum(keep), Mean = mean(x[keep]),
           SD = sd(x[keep]), Min = min(x[keep]), Max = max(x[keep]),
           Baseline = by_arm[["Baseline"]], Time = by_arm[["Time"]],
           Cost = by_arm[["Cost"]], digits = digits)
  }
  summary_people <- analysis_people |>
    select(respondent_id, arm, age, ideology) |>
    left_join(respondent_covariates |> select(-arm), by = "respondent_id") |>
    mutate(no_placement = as.integer(is.na(ideology)))
  summary_candidates <- candidate_model_data |>
    mutate(ideology_left = as.integer(candidate_ideology == "Left"),
           ideology_right = as.integer(candidate_ideology == "Right"),
           high_dominance = as.integer(candidate_dominance == "High"),
           older = as.integer(candidate_age_group == "Older"))
  panel_people <- paste0("A. Respondents (pretreatment questionnaire)")
  panel_tasks <- "B. Analytical tasks"
  panel_candidates <- "C. Candidate appearances"
  window <- selection_window_seconds
  variable_summary <- bind_rows(
    describe_variable(summary_people, "age", "Age (years)", panel_people, 1),
    describe_variable(summary_people, "resp_woman", "Woman", panel_people),
    describe_variable(summary_people, "tertiary", "Tertiary education", panel_people),
    describe_variable(summary_people, "interest", "Political interest (1--7)", panel_people),
    describe_variable(summary_people, "ideology", "Left--right self-placement (1--10)",
                      panel_people),
    describe_variable(summary_people, "no_placement", "No numeric self-placement",
                      panel_people),
    describe_variable(tasks, "any_information", "Any description opened, $A$", panel_tasks),
    describe_variable(tasks, "n_descriptions", "Descriptions opened, $K$", panel_tasks),
    describe_variable(tasks, "both_information", "Both descriptions opened, $X$",
                      panel_tasks),
    describe_variable(tasks, "capped_latency",
      paste0("Time to first selection, capped, $D^{", window, "}$ (s)"), panel_tasks),
    describe_variable(tasks, "slow_selection",
      paste0("No selection within ", window, " s, $S^{", window, "}$"), panel_tasks),
    describe_variable(tasks, "terminal_timeout", "Ended without a selection, $Q$",
                      panel_tasks),
    describe_variable(tasks, "time_spent_seconds", "Task duration (s)", panel_tasks),
    describe_variable(tasks, "real_election_support",
                      "Would vote for the choice in a real election", panel_tasks),
    describe_variable(tasks, "rushed_scale", "Reported hurry (1--7)", panel_tasks),
    describe_variable(tasks, "info_cost_scale", "Reported effort (1--7)", panel_tasks),
    describe_variable(summary_candidates, "information_opened",
                      "Description opened, $M$", panel_candidates),
    describe_variable(summary_candidates, "selected", "Registered selection, $Y$",
                      panel_candidates),
    describe_variable(summary_candidates, "woman", "Woman candidate, $W$", panel_candidates),
    describe_variable(summary_candidates, "ideology_left", "Displayed ideology: left",
                      panel_candidates),
    describe_variable(summary_candidates, "ideology_right", "Displayed ideology: right",
                      panel_candidates),
    describe_variable(summary_candidates, "high_dominance", "High facial dominance",
                      panel_candidates),
    describe_variable(summary_candidates, "older", "Older age group", panel_candidates),
    describe_variable(summary_candidates, "congruent", "Ideologically congruent, $G$",
                      panel_candidates))
  # Whole numbers print without decimals (counts, scale endpoints, 0/1).
  summary_value <- function(x, digits) unname(mapply(function(v, d) {
    if (is.na(v)) "--" else if (abs(v - round(v)) < 1e-9) tex_num(v, 0) else tex_num(v, d)
  }, x, digits))
  variable_summary_print <- variable_summary |>
    transmute(Variable, N = format(N, big.mark = ","),
      Mean = tex_num(Mean, digits), SD = tex_num(SD, digits),
      Min = summary_value(Min, digits), Max = summary_value(Max, digits),
      Baseline = tex_num(Baseline, digits), Time = tex_num(Time, digits),
      Cost = tex_num(Cost, digits))
}

## ----

## ---- analysis-candidate-summaries
# Describe what was SHOWN as well as what was CHOSEN. A trait can appear often
# among chosen candidates simply because it was displayed more often.
# These summaries retain all 15 submitted main tasks of qualifying completes.
candidate_traits_long <- conjoint_dat |>
  select(respondent_id, candidate_id, arm, selected, chosen, information_opened,
         candidate_gender, candidate_ideology, candidate_dominance, candidate_age_group) |>
  mutate(across(c(candidate_gender, candidate_ideology, candidate_dominance,
                  candidate_age_group), as.character)) |>
  pivot_longer(c(candidate_gender, candidate_ideology, candidate_dominance,
                 candidate_age_group), names_to = "attribute", values_to = "Level") |>
  mutate(Attribute = recode(attribute, candidate_gender = "Gender",
    candidate_ideology = "Ideology", candidate_dominance = "Dominance",
    candidate_age_group = "Age category"))
candidate_trait_summary <- candidate_traits_long |>
  group_by(Attribute, Level, arm) |>
  summarise(Shown = n(), Chosen = sum(selected),
    No_vote = sum(is.na(chosen)),
    chosen_per_shown_pct = 100 * mean(selected),
    information_opened_pct = 100 * mean(information_opened), .groups = "drop") |>
  group_by(Attribute, arm) |>
  mutate(among_chosen_pct = 100 * Chosen / sum(Chosen)) |>
  ungroup()

# Also provide ONE row per candidate with every column in the source CSV.
# This is a useful descriptive lookup, not 71 independent randomized traits.
candidate_profiles <- conjoint_dat |> group_by(candidate_id) |>
  summarise(presentations = n(), respondents = n_distinct(respondent_id),
    registered_choices = sum(selected), unanswered_presentations = sum(is.na(chosen)),
    selection_pct = 100 * mean(selected),
    information_opened_pct = 100 * mean(information_opened), .groups = "drop") |>
  left_join(candidate_catalogue, by = c("candidate_id" = "ID"),
            relationship = "many-to-one")

# Profile-specific selection probabilities theta_c(z) and Delta_c(z). Side and
# rival are randomized, so the share of a profile's appearances in which it is
# selected estimates theta_c(z) directly. Each point is noisy while each
# profile has few appearances per arm; the correlation summarises stability.
profile_selection <- conjoint_dat |>
  group_by(candidate_id, arm) |>
  summarise(appearances = n(), theta = mean(selected), .groups = "drop")
profile_comparison <- profile_selection |>
  filter(arm != "Baseline") |>
  inner_join(profile_selection |> filter(arm == "Baseline") |>
               select(candidate_id, theta_baseline = theta,
                      appearances_baseline = appearances),
             by = "candidate_id") |>
  mutate(delta = theta - theta_baseline) |>
  left_join(candidate_attributes |> select(candidate_id, candidate_gender),
            by = "candidate_id", relationship = "many-to-one")
profile_correlations <- profile_comparison |>
  group_by(arm) |>
  summarise(n_profiles = n(),
    r = if (n() > 2L && sd(theta) > 0 && sd(theta_baseline) > 0)
      cor(theta, theta_baseline) else NA_real_,
    mean_abs_delta = mean(abs(delta)),
    median_appearances = median(appearances), .groups = "drop")

## ----

## ---- analysis-candidate-trait-model
if (has_model_data) {
  # An exploratory conjoint-style linear probability model considers all FOUR
  # main profile classifications jointly, allowing associations to differ by arm.
  # References are Men, Center, Low dominance and Younger. Side/task adjust for
  # presentation position and task order. Do not control for opening information:
  # it happens after treatment and is itself an outcome of interest.
  # Whole candidate profiles were randomized, NOT their component attributes.
  # Therefore these coefficients are ADJUSTED ASSOCIATIONS, not causal AMCEs.
  # With a small sample, fixest may use its standard covariance-matrix correction.
  # The outcome is a registered selection: retained no-choice tasks give two zeros.
  # The original decision ID and the standard conjoint 'chosen' variable stay NA.
  model_candidate_traits <- feols(
    selected ~ arm * (candidate_gender + candidate_ideology +
                        candidate_dominance + candidate_age_group) + side + factor(task),
    data = conjoint_dat, vcov = ~respondent_id + candidate_id)
  stopifnot(nobs(model_candidate_traits) == nrow(conjoint_dat))

  # emmeans forms each within-condition trait contrast from this ONE model and
  # its two-way clustered covariance. No manual coefficient arithmetic is needed.
  # The df matches the smaller cluster count, as in the existing candidate models.
  candidate_trait_df <- min(n_distinct(conjoint_dat$respondent_id),
                             n_distinct(conjoint_dat$candidate_id)) - 1L
  trait_contrast <- function(term) {
    means <- emmeans(model_candidate_traits, as.formula(paste("~", term, "| arm")),
                     data = conjoint_dat, df = candidate_trait_df)
    as.data.frame(summary(
      contrast(means, method = "trt.vs.ctrl", ref = 1, adjust = "none"),
      infer = c(TRUE, TRUE), adjust = "none", level = confidence_level))
  }
  candidate_trait_effects <- bind_rows(
    trait_contrast("candidate_gender") |> mutate(Attribute = "Gender"),
    trait_contrast("candidate_ideology") |> mutate(Attribute = "Ideology"),
    trait_contrast("candidate_dominance") |> mutate(Attribute = "Dominance"),
    trait_contrast("candidate_age_group") |> mutate(Attribute = "Age category")) |>
    transmute(Attribute, Contrast = as.character(contrast), Condition = arm,
      estimate, std.error = SE, conf.low = lower.CL, conf.high = upper.CL, p.value)
  expected_trait_contrasts <- nlevels(conjoint_dat$arm) *
    (nlevels(conjoint_dat$candidate_gender) - 1L +
     nlevels(conjoint_dat$candidate_ideology) - 1L +
     nlevels(conjoint_dat$candidate_dominance) - 1L +
     nlevels(conjoint_dat$candidate_age_group) - 1L)
  stopifnot(nrow(candidate_trait_effects) == expected_trait_contrasts,
            !anyNA(candidate_trait_effects$estimate))

  # Ideological congruence (exploratory "facts" benchmark). The 1-10 self-
  # placement is grouped as left (1-4), center (5-6) and right (7-10) and
  # compared with the profile's displayed ideology. A respondent can learn that
  # ideology only by opening the description, so a congruence premium that
  # shrinks under a constraint is consistent with less programmatic voting.
  # Respondents without a numeric placement are excluded from this model only.
  congruence_dat <- conjoint_dat |>
    filter(!is.na(respondent_ideology)) |>
    mutate(respondent_side = cut(respondent_ideology, breaks = c(0, 4, 6, 10),
                                 labels = c("Left", "Center", "Right")),
           congruent = as.integer(as.character(respondent_side) ==
                                    as.character(candidate_ideology)))
  model_congruence <- feols(selected ~ arm * congruent + side + factor(task),
    data = congruence_dat, vcov = ~respondent_id + candidate_id)
  congruence_df <- min(n_distinct(congruence_dat$respondent_id),
                       n_distinct(congruence_dat$candidate_id)) - 1L
  congruence_means <- emmeans(model_congruence, ~congruent | arm,
    at = list(congruent = c(0, 1)), data = congruence_dat, df = congruence_df)
  congruence_effects <- as.data.frame(summary(contrast(congruence_means,
    method = list(`Congruent - Incongruent` = c(-1, 1))),
    infer = c(TRUE, TRUE), level = confidence_level)) |>
    transmute(Attribute = "Ideological congruence",
      Contrast = "Congruent - Incongruent", Condition = arm,
      estimate, std.error = SE, conf.low = lower.CL, conf.high = upper.CL, p.value)
  congruence_n_respondents <- n_distinct(congruence_dat$respondent_id)
  congruence_n_rows <- nrow(congruence_dat)
}

## ----

## ---- analysis-decision-factors
if (has_model_data) {
  # Post-choice follow-ups record STATED reasons. Real-election support is asked
  # only after a registered selection, and reasons only after a "yes". Ideology
  # and policy-priority reasons are offered only if a description was opened, so
  # their denominator is those tasks. All shares are descriptive and conditional
  # on these post-treatment events; they are not causal effects of the arm.
  factor_key <- tibble(
    key = c("apariencia_primera_impresion", "edad", "genero",
            "ideologia_revelada", "focos_programaticos_revelados", "otra_razon"),
    Reason = c("Appearance or first impression", "Apparent age", "Perceived gender",
               "Ideology shown", "Policy priorities shown", "Another reason"),
    Source = c("Cues visible in the photograph", "Cues visible in the photograph",
               "Cues visible in the photograph", "Revealed description",
               "Revealed description", "Other"))
  support_tasks <- tasks |> filter(recorded_choice, !is.na(real_election_support))
  reason_tasks <- tasks |> filter(realistic_vote %in% "yes")
  reason_sets <- strsplit(coalesce(reason_tasks$decision_factors, ""), ",", fixed = TRUE)
  reason_long <- bind_rows(lapply(seq_len(nrow(factor_key)), function(k) {
    offered <- if (factor_key$Source[k] == "Revealed description") {
      reason_tasks$any_information == 1L
    } else {
      rep(TRUE, nrow(reason_tasks))
    }
    tibble(respondent_id = reason_tasks$respondent_id[offered],
           arm = reason_tasks$arm[offered], key = factor_key$key[k],
           cited = as.integer(vapply(reason_sets[offered],
             function(x) factor_key$key[k] %in% trimws(x), logical(1))))
  })) |>
    left_join(factor_key, by = "key")

  # Respondent-clustered shares by arm, using the same estimator as Figure 2A.
  clustered_share <- function(data, outcome) {
    data <- data |> mutate(arm = droplevels(arm))
    fit <- feols(as.formula(paste(outcome, "~ 0 + arm")), data = data,
                 vcov = ~respondent_id)
    tidy(fit, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(arm = factor(sub("^arm", "", term), levels = levels(tasks$arm)),
             n_tasks = as.integer(table(data$arm)[sub("^arm", "", term)]))
  }
  reason_estimates <- bind_rows(
    clustered_share(support_tasks, "real_election_support") |>
      mutate(Reason = "Would vote for the chosen candidate",
             Source = "Real-election support"),
    bind_rows(lapply(split(reason_long, reason_long$key), function(d) {
      clustered_share(d, "cited") |> mutate(Reason = d$Reason[1L], Source = d$Source[1L])
    }))) |>
    mutate(conf.low = pmax(conf.low, 0), conf.high = pmin(conf.high, 1))
  reason_counts <- list(support_tasks = nrow(support_tasks),
    reason_tasks = nrow(reason_tasks),
    reason_revealed_tasks = sum(reason_tasks$any_information == 1L))
}

## ----

## ---- analysis-respondent-scrutiny
if (has_model_data) {
  # Show BOTH respondent groups, not a women-minus-men contrast. The outcome is
  # whether a displayed candidate's information was opened at least once. It is
  # not a count of clicks and cannot establish that the description was read.
  # All rows already come from eligible completed responses. Other respondent
  # gender categories remain in the other analyses, but are not relabelled here.
  scrutiny_dat <- conjoint_dat |>
    filter(respondent_gender %in% c("Man", "Woman")) |>
    mutate(respondent_gender = factor(respondent_gender,
      levels = c("Man", "Woman"), labels = c("Men", "Women")))
  scrutiny_observed <- scrutiny_dat |>
    group_by(arm, candidate_gender, respondent_gender) |>
    summarise(respondents = n_distinct(respondent_id),
      appearances = n(), openings = sum(information_opened),
      observed_probability = mean(information_opened), .groups = "drop")

  # A saturated binomial model gives one opening probability for every
  # condition x candidate-gender x respondent-gender cell. These fitted points
  # equal the observed cell rates. No gender contrasts or causal gender effects
  # are estimated here, and the existing primary models stay unchanged.
  model_scrutiny <- glm(
    information_opened ~ arm * candidate_gender * respondent_gender,
    data = scrutiny_dat, family = binomial())
  stopifnot(model_scrutiny$converged,
            nobs(model_scrutiny) == nrow(scrutiny_dat))

  # Repeated decisions and repeated candidates are not independent observations.
  # sandwich supplies the two-way clustered covariance. emmeans then calculates
  # intervals on the log-odds scale and transforms them to probabilities, keeping
  # the bounds between zero and one without clipping an ordinary linear interval.
  scrutiny_vcov <- sandwich::vcovCL(model_scrutiny,
    cluster = ~respondent_id + candidate_id, type = "HC1", fix = TRUE)
  scrutiny_df <- min(n_distinct(scrutiny_dat$respondent_id),
                      n_distinct(scrutiny_dat$candidate_id)) - 1L
  scrutiny_means <- emmeans(model_scrutiny,
    ~candidate_gender | respondent_gender * arm,
    vcov. = scrutiny_vcov, df = scrutiny_df)
  respondent_scrutiny <- as.data.frame(summary(scrutiny_means,
    type = "response", infer = c(TRUE, FALSE), level = confidence_level)) |>
    transmute(arm, candidate_gender, respondent_gender,
      probability = prob, conf.low = lower.CL, conf.high = upper.CL,
      confidence = confidence_level) |>
    left_join(scrutiny_observed,
      by = c("arm", "candidate_gender", "respondent_gender"),
      relationship = "one-to-one")
  stopifnot(!anyNA(respondent_scrutiny),
            all(abs(respondent_scrutiny$probability -
                      respondent_scrutiny$observed_probability) < 1e-7),
            all(respondent_scrutiny$conf.low >= 0),
            all(respondent_scrutiny$conf.high <= 1))

  # Counts and the sentence used in the paper update with the downloaded sample.
  scrutiny_arm_counts <- scrutiny_dat |>
    distinct(respondent_id, arm, respondent_gender) |>
    count(arm, respondent_gender, name = "respondents") |>
    complete(arm, respondent_gender, fill = list(respondents = 0L)) |>
    pivot_wider(names_from = respondent_gender, values_from = respondents)
  scrutiny_sample_note <- scrutiny_arm_counts |>
    mutate(note = paste0(arm, " men ", Men, " and women ", Women)) |>
    pull(note) |>
    paste(collapse = ". ")

  # Separate respondent panels put their information-seeking behavior at the
  # center. Colour marks the arm and shape the candidate's gender, as elsewhere.
  plot_respondent_scrutiny <- ggplot(respondent_scrutiny,
    aes(arm, 100 * probability, color = arm,
        shape = candidate_gender, group = candidate_gender)) +
    geom_errorbar(aes(ymin = 100 * conf.low, ymax = 100 * conf.high),
      position = position_dodge(width = 0.5), width = 0, linewidth = 0.7) +
    geom_point(position = position_dodge(width = 0.5), size = 2.6, stroke = 0.9) +
    facet_wrap(~respondent_gender, nrow = 1,
      labeller = labeller(respondent_gender =
        c(Men = "Male respondents", Women = "Female respondents"))) +
    scale_color_manual(values = arm_colors, guide = "none") +
    scale_shape_manual(values = gender_shapes, name = "Candidate gender") +
    scale_x_discrete(labels = arm_labels_wrapped) +
    scale_y_continuous(breaks = seq(0, 100, by = 25), limits = c(0, 100),
      labels = scales::label_percent(scale = 1)) +
    labs(x = NULL, y = "Candidate description opened (95% CI)")
}

## ---- 

## ---- analysis-plots
if (has_model_data) {
  # FIGURE 2 -- the primary process family (H1, H2). Panel A shows the observed
  # condition means; panel B each contrast tau_zB from the main preregistered
  # difference in means (filled circle, eq. 1) next to the complementary
  # regression-adjusted estimate (hollow diamond, eq. 3). Columns share an
  # outcome, so A and B read together.
  # Proportions are in percent (percentage points for contrasts). Linear
  # intervals for proportions are truncated at the 0-100 bounds for display.
  estimator_shapes <- c(Preregistered = 16, `Regression-adjusted` = 23)
  panel_levels <- process_outcomes$panel
  proportion_panels <- process_outcomes$panel[process_outcomes$scale == 100]
  means_plot_data <- condition_means |>
    mutate(across(c(estimate, conf.low, conf.high), ~ .x * scale),
      conf.low = if_else(panel %in% proportion_panels, pmax(conf.low, 0), conf.low),
      conf.high = if_else(panel %in% proportion_panels, pmin(conf.high, 100), conf.high),
      panel = factor(panel, levels = panel_levels))
  plot_process_means <- ggplot(means_plot_data,
    aes(arm, estimate, color = arm, shape = arm)) +
    geom_errorbar(aes(ymin = conf.low, ymax = conf.high), width = 0, linewidth = 0.7) +
    geom_point(size = 2.6) +
    facet_wrap(~panel, nrow = 1, scales = "free_y", labeller = label_wrap_gen(20)) +
    scale_color_manual(values = arm_colors, guide = "none") +
    scale_shape_manual(values = arm_shapes, guide = "none") +
    scale_x_discrete(labels = arm_labels_wrapped) +
    labs(x = NULL, y = "Observed mean (95% CI)", tag = "A")

  contrast_plot_data <- bind_rows(
    process_effects_adj |> mutate(Estimator = "Regression-adjusted"),
    process_effects |> mutate(Estimator = "Preregistered")) |>
    select(outcome, contrast, estimate, conf.low, conf.high, Estimator) |>
    left_join(process_outcomes |> select(outcome, panel, scale), by = "outcome") |>
    mutate(across(c(estimate, conf.low, conf.high), ~ .x * scale),
      arm = factor(sub(" - Baseline$", "", contrast), levels = c("Time", "Cost")),
      panel = factor(panel, levels = panel_levels),
      Estimator = factor(Estimator, levels = estimator_levels))
  stopifnot(nrow(contrast_plot_data) == 16L)
  plot_process_contrasts <- ggplot(contrast_plot_data,
    aes(arm, estimate, color = arm, shape = Estimator, group = Estimator)) +
    geom_hline(yintercept = 0, color = ink_muted, linewidth = 0.4) +
    geom_errorbar(aes(ymin = conf.low, ymax = conf.high),
      position = position_dodge(width = 0.55), width = 0, linewidth = 0.7) +
    geom_point(position = position_dodge(width = 0.55), size = 2.6,
               fill = "white", stroke = 0.9) +
    facet_wrap(~panel, nrow = 1, scales = "free_y", labeller = label_wrap_gen(20)) +
    scale_color_manual(values = arm_colors, guide = "none") +
    scale_shape_manual(values = estimator_shapes, name = NULL,
      labels = c(Preregistered = "Difference in means (main)",
                 `Regression-adjusted` = "Regression-adjusted")) +
    scale_x_discrete(labels = arm_labels) +
    labs(x = NULL, y = "Difference from Baseline", tag = "B")
  plot_process <- plot_process_means / plot_process_contrasts

  # FIGURE 3 -- gendered scrutiny and selection (H3, H4). Panel A: observed
  # candidate-level means mu_g(z) (shape = candidate gender). Panel B: the
  # tested estimands Gamma(B), Psi(T) and Psi(C): main preregistered LPM (filled
  # circle, eq. 2) next to the regression-adjusted models (hollow diamond,
  # eqs. 4-5). Colour = arm:
  # Gamma(B) is a Baseline quantity, Psi(z) the change under arm z.
  gender_outcome_labels <- c(`Information acquisition` = "Description opened (%)",
                             `Registered selection` = "Candidate selected (%)")
  plot_gender_means <- ggplot(gender_means,
    aes(arm, 100 * emmean, color = arm, shape = candidate_gender,
        group = candidate_gender)) +
    geom_errorbar(aes(ymin = 100 * lower.CL, ymax = 100 * upper.CL),
      position = position_dodge(width = 0.5), width = 0, linewidth = 0.7) +
    geom_point(position = position_dodge(width = 0.5), size = 2.6, stroke = 0.9) +
    facet_wrap(~Outcome, ncol = 1, scales = "free_y",
               labeller = labeller(Outcome = gender_outcome_labels)) +
    scale_color_manual(values = arm_colors, guide = "none") +
    scale_shape_manual(values = gender_shapes, name = "Candidate gender") +
    scale_x_discrete(labels = arm_labels_wrapped) +
    labs(x = NULL, y = "Observed mean among displayed profiles (95% CI)", tag = "A")
  gender_estimand_levels <- c("Gamma(B)", "Psi(T)", "Psi(C)")
  baseline_gap_rows <- function(df, estimator) df |>
    filter(Condition == "Baseline") |>
    transmute(Outcome, arm = "Baseline", estimand = "Gamma(B)", estimate = Gamma,
              conf.low, conf.high, Estimator = estimator)
  psi_rows <- function(df, estimator) df |>
    transmute(Outcome = outcome, arm = sub(" - Baseline$", "", contrast),
              estimand = paste0("Psi(", substr(arm, 1, 1), ")"), estimate,
              conf.low, conf.high, Estimator = estimator)
  gender_estimand_data <- bind_rows(
    baseline_gap_rows(gender_contrasts_adj, "Regression-adjusted"),
    baseline_gap_rows(gender_contrasts, "Preregistered"),
    psi_rows(gender_effects_adj, "Regression-adjusted"),
    psi_rows(gender_effects, "Preregistered")) |>
    mutate(estimand = factor(estimand, levels = gender_estimand_levels),
           arm = factor(arm, levels = levels(tasks$arm)),
           Estimator = factor(Estimator, levels = estimator_levels))
  stopifnot(nrow(gender_estimand_data) == 12L, !anyNA(gender_estimand_data$estimand))
  gender_estimand_labels <- c(`Information acquisition` = "Women minus men: description opened",
                              `Registered selection` = "Women minus men: selection")
  plot_gender_estimands <- ggplot(gender_estimand_data,
    aes(estimand, 100 * estimate, color = arm, shape = Estimator, group = Estimator)) +
    geom_hline(yintercept = 0, color = ink_muted, linewidth = 0.4) +
    geom_errorbar(aes(ymin = 100 * conf.low, ymax = 100 * conf.high),
      position = position_dodge(width = 0.55), width = 0, linewidth = 0.7) +
    geom_point(position = position_dodge(width = 0.55), size = 2.6,
               fill = "white", stroke = 0.9) +
    facet_wrap(~Outcome, ncol = 1, scales = "free_y",
               labeller = labeller(Outcome = gender_estimand_labels)) +
    scale_color_manual(values = arm_colors, guide = "none") +
    scale_shape_manual(values = estimator_shapes, name = NULL,
      labels = c(Preregistered = "Preregistered differences (main)",
                 `Regression-adjusted` = "Regression-adjusted")) +
    scale_x_discrete(labels = function(x) parse(text = x)) +
    labs(x = NULL, y = "Percentage points (95% CI)", tag = "B")
  plot_gender <- (plot_gender_means | plot_gender_estimands) +
    plot_layout(widths = c(1.15, 1), guides = "collect") &
    theme(legend.position = "top", legend.box = "vertical",
          legend.box.just = "left")

  # FIGURE 4 -- faces or facts? Within-condition associations between selection
  # and the profile's classifications, plus respondent-candidate congruence.
  trait_plot_data <- bind_rows(candidate_trait_effects, congruence_effects) |>
    mutate(Contrast = gsub(" - ", " vs. ", Contrast, fixed = TRUE),
      Contrast = factor(Contrast, levels = rev(c("Women vs. Men", "Left vs. Center",
        "Right vs. Center", "High vs. Low", "Older vs. Younger",
        "Congruent vs. Incongruent"))),
      Attribute = factor(Attribute,
        levels = c("Gender", "Ideology", "Dominance", "Age category",
                   "Ideological congruence"),
        labels = c("Candidate gender", "Displayed ideology",
                   "Facial dominance (fWHR)", "Age group",
                   "Ideological congruence")),
      Condition = factor(Condition, levels = levels(tasks$arm)))
  plot_candidate_traits <- ggplot(trait_plot_data,
    aes(100 * estimate, Contrast, color = Condition, shape = Condition)) +
    geom_vline(xintercept = 0, color = ink_muted, linewidth = 0.4) +
    geom_errorbar(aes(xmin = 100 * conf.low, xmax = 100 * conf.high),
      orientation = "y", width = 0, linewidth = 0.7,
      position = position_dodge(width = 0.6, orientation = "y", reverse = TRUE)) +
    geom_point(size = 2.4,
      position = position_dodge(width = 0.6, orientation = "y", reverse = TRUE)) +
    facet_grid(Attribute ~ ., scales = "free_y", space = "free_y",
               labeller = label_wrap_gen(14)) +
    scale_color_manual(values = arm_colors, labels = arm_labels, name = NULL) +
    scale_shape_manual(values = arm_shapes, labels = arm_labels, name = NULL) +
    labs(x = "Difference in probability of selection, percentage points (95% CI)",
         y = NULL) +
    theme(strip.text.y = element_text(angle = 0, hjust = 0),
          panel.spacing.y = grid::unit(7, "pt"))

  # FIGURE 5 -- stated reasons. Shares by arm with respondent-clustered intervals.
  reason_levels <- c("Would vote for the chosen candidate", factor_key$Reason)
  reason_plot_data <- reason_estimates |>
    mutate(Reason = factor(Reason, levels = rev(reason_levels)),
      Source = factor(Source, levels = c("Real-election support",
        "Cues visible in the photograph", "Revealed description", "Other")),
      arm = factor(arm, levels = levels(tasks$arm)))
  plot_reasons <- ggplot(reason_plot_data,
    aes(100 * estimate, Reason, color = arm, shape = arm)) +
    geom_errorbar(aes(xmin = 100 * conf.low, xmax = 100 * conf.high),
      orientation = "y", width = 0, linewidth = 0.7,
      position = position_dodge(width = 0.6, orientation = "y", reverse = TRUE)) +
    geom_point(size = 2.4,
      position = position_dodge(width = 0.6, orientation = "y", reverse = TRUE)) +
    facet_grid(Source ~ ., scales = "free_y", space = "free_y",
               labeller = label_wrap_gen(16)) +
    scale_color_manual(values = arm_colors, labels = arm_labels, name = NULL) +
    scale_shape_manual(values = arm_shapes, labels = arm_labels, name = NULL) +
    scale_x_continuous(limits = c(0, 100), breaks = seq(0, 100, 20),
                       labels = scales::label_percent(scale = 1)) +
    labs(x = "Share of eligible tasks (95% CI)", y = NULL) +
    theme(strip.text.y = element_text(angle = 0, hjust = 0),
          panel.spacing.y = grid::unit(7, "pt"))

  # FIGURE 6 -- profile-specific selection probabilities theta_c(z) against
  # theta_c(B). The dashed line marks Delta_c(z) = 0. Point area: appearances.
  profile_panels <- c(Time = "Time vs. Baseline", Cost = "Cost vs. Baseline")
  profile_plot_data <- profile_comparison |>
    mutate(panel = factor(profile_panels[as.character(arm)], levels = profile_panels))
  profile_label_data <- profile_correlations |>
    mutate(panel = factor(profile_panels[as.character(arm)], levels = profile_panels),
      label = paste0("Correlation r = ",
                     ifelse(is.na(r), "--", sprintf("%.2f", round(r, 2) + 0)),
                     "\nMean absolute change = ",
                     sprintf("%.1f", 100 * mean_abs_delta), " pp",
                     "\n", n_profiles, " profiles"))
  plot_profiles <- ggplot(profile_plot_data,
    aes(100 * theta_baseline, 100 * theta, color = arm, shape = candidate_gender)) +
    geom_abline(slope = 1, intercept = 0, color = ink_muted, linetype = "dashed",
                linewidth = 0.4) +
    geom_point(aes(size = appearances), stroke = 0.8, alpha = 0.85) +
    geom_text(data = profile_label_data, aes(x = 3, y = 97, label = label),
              hjust = 0, vjust = 1, size = 2.6, color = ink_muted,
              lineheight = 0.95, inherit.aes = FALSE) +
    facet_wrap(~panel, nrow = 1) +
    coord_equal(xlim = c(0, 100), ylim = c(0, 100)) +
    scale_color_manual(values = arm_colors, guide = "none") +
    scale_shape_manual(values = gender_shapes, name = "Candidate gender") +
    scale_size_area(max_size = 3.6, name = "Appearances in arm") +
    scale_x_continuous(labels = scales::label_percent(scale = 1)) +
    scale_y_continuous(labels = scales::label_percent(scale = 1)) +
    labs(x = "Selection probability under Baseline",
         y = "Selection probability under Time or Cost")
}

## ----



## ---- analysis-duration-completes
if (has_main_data) {
  # Current-data timing plot, also reused by the daily monitoring script.
  # The paper's pre-test Figure A1 is kept separate in analysis-pretest-calibration.
  # Keep separate dataframes so the other analyses retain their existing samples.
  completed_people <- analysis_people |> filter(study_complete)
  completed_tasks <- tasks |>
    semi_join(completed_people, by = "respondent_id")

  # Each complete must contribute exactly one observation to each main task, 1-15.
  # Retain automatic timed submissions, including those without a recorded vote.
  # This is full choice-page duration, NOT capped first-selection latency. It
  # includes reading, arithmetic and idle time, but not loading or follow-up pages.
  stopifnot(nrow(completed_people) > 0L,
            nrow(completed_tasks) == n_main_tasks * nrow(completed_people),
            !anyDuplicated(completed_tasks[c("respondent_id", "task")]),
            all(completed_tasks$task %in% seq_len(n_main_tasks)),
            all(is.finite(completed_tasks$time_spent_seconds)),
            all(completed_tasks$time_spent_seconds >= 0))

  # Within each condition and task, average across people. There is only ONE row
  # per person in each cell, so an ordinary t interval uses the correct unit.
  # These are pointwise intervals, not a simultaneous band or causal tests.
  # Do not discard slow cases or restrict untimed durations to twenty seconds.
  task_duration_completes <- completed_tasks |>
    group_by(arm, task) |>
    summarise(n_respondents = n(),
              mean_seconds = mean(time_spent_seconds),
              sd_seconds = sd(time_spent_seconds), .groups = "drop") |>
    mutate(se_seconds = sd_seconds / sqrt(n_respondents),
           critical_t = qt((1 + confidence_level) / 2,
                           df = pmax(n_respondents - 1L, 1L)),
           conf.low = mean_seconds - critical_t * se_seconds,
           conf.high = mean_seconds + critical_t * se_seconds)
  duration_counts <- completed_people |> count(arm, name = "n_respondents", .drop = FALSE)
  duration_arm_labels <- setNames(
    paste0(c("No time limit", paste0(deadline_seconds, "-second limit"), "Arithmetic task"),
           " (n = ", duration_counts$n_respondents, ")"),
    as.character(duration_counts$arm))

  # One compact panel permits direct comparisons on the SAME seconds scale.
  # Slight horizontal offsets separate overlapping intervals at the same task.
  # Shape and line type distinguish conditions even in a black-and-white print.
  plot_task_duration_completes <- ggplot(task_duration_completes,
    aes(task, mean_seconds, group = arm, color = arm, shape = arm, linetype = arm)) +
    geom_hline(yintercept = deadline_seconds, linetype = "dotted", color = "grey55") +
    geom_errorbar(aes(ymin = conf.low, ymax = conf.high),
      position = position_dodge(width = 0.5), width = 0.12,
      linewidth = 0.4, alpha = 0.55, linetype = "solid") +
    geom_line(position = position_dodge(width = 0.5), linewidth = 0.65) +
    geom_point(position = position_dodge(width = 0.5), size = 2.2) +
    scale_color_manual(values = arm_colors, labels = duration_arm_labels) +
    scale_shape_manual(values = c(Baseline = 16, Time = 17, Cost = 15),
                       labels = duration_arm_labels) +
    scale_linetype_manual(values = c(Baseline = "solid", Time = "dashed",
                                    Cost = "dotdash"), labels = duration_arm_labels) +
    scale_x_continuous(breaks = seq_len(n_main_tasks), minor_breaks = NULL) +
    scale_y_continuous(breaks = scales::breaks_pretty(n = 7), minor_breaks = NULL) +
    labs(x = "Choice task", y = "Mean task duration (seconds)",
         color = NULL, shape = NULL, linetype = NULL) +
    theme(legend.position = "top", legend.text = element_text(size = 9),
          legend.key.width = grid::unit(0.38, "in"),
          panel.grid.minor = element_blank(),
          plot.margin = margin(8, 8, 5.5, 5.5))
}

## ---- 

## ---- analysis-pretest-calibration
# Historical pre-test evidence must not grow when later responses are downloaded.
# Use the saved export underlying the original Figure A1, not latest.csv.
# A missing or altered snapshot stops the build rather than changing the cohort.
pretest_file <- file.path(project_dir, "data_exports", "snapshots",
  "conjoint_fhcmy7rf_20261021T135317Z_1726c3149ade2.csv")
if (!file.exists(pretest_file)) {
  stop("The saved pre-test snapshot is missing. Restore it before building the paper.")
}
stopifnot(unname(tools::md5sum(pretest_file)) == "530a620bb33162b42eb9b7c0ac480edf")
# The filename records download time; file modification time can change on copying.
pretest_download_stamp <- sub("^conjoint_[^_]+_([0-9]{8}T[0-9]{6}Z)_.*$",
                             "\\1", basename(pretest_file))
pretest_download_time <- format(as.POSIXct(pretest_download_stamp,
  format = "%Y%m%dT%H%M%SZ", tz = "UTC"), tz = "UTC", usetz = TRUE)

# The Rnw has already loaded these named chunks. Load them here too when the
# whole R file is sourced. Reading chunks does not download or run their code.
if (!render_in_paper) knitr::read_chunk(file.path(project_dir, "visual_conjoint_design.R"))

# local() keeps the historical data separate from the current analysis objects.
# Reuse the SAME eligibility, completion and timing code rather than duplicating it.
pretest <- local({
  # Only this isolated calibration calculation is allowed to include pre-test data.
  analysis_scope <- "pretest"
  raw_dat <- read_csv(pretest_file,
    col_types = cols(.default = col_character()), na = "", trim_ws = FALSE,
    name_repair = "minimal", show_col_types = FALSE)
  eval(parse(text = knitr::knit_code$get("analysis-report-parameters")))
  eval(parse(text = knitr::knit_code$get("analysis-participants")))
  eval(parse(text = knitr::knit_code$get("analysis-tasks")))

  # This pre-test used 15 main tasks and allowed at most two missing choices.
  # A later change to the completion rule must not silently redefine the pre-test.
  stopifnot(n_main_tasks == 15L, minimum_valid_main_choices == 13L,
            deadline_seconds == 20)
  eval(parse(text = knitr::knit_code$get("analysis-duration-completes")))

  # Count PEOPLE separately from repeated TASK observations. Durations are pooled
  # task-level descriptives, not 195 or 150 independent participants.
  by_arm <- completed_tasks |>
    group_by(arm) |>
    summarise(n_respondents = n_distinct(respondent_id), n_tasks = n(),
      mean_seconds = mean(time_spent_seconds),
      sd_seconds = sd(time_spent_seconds),
      median_seconds = median(time_spent_seconds),
      q25_seconds = unname(quantile(time_spent_seconds, 0.25)),
      q75_seconds = unname(quantile(time_spent_seconds, 0.75)),
      first_selection_median = median(first_selection_seconds, na.rm = TRUE),
      n_over_deadline = sum(time_spent_seconds > deadline_seconds),
      percent_over_deadline = 100 * mean(time_spent_seconds > deadline_seconds),
      .groups = "drop")
  baseline <- by_arm |> filter(arm == "Baseline")
  time <- by_arm |> filter(arm == "Time")
  cost <- by_arm |> filter(arm == "Cost")
  stopifnot(nrow(baseline) == 1L, nrow(time) == 1L, nrow(cost) == 1L)

  # The 20% calibration benchmark comes from Kocher et al.; nine seconds is the
  # selected design rule, not an estimate that should change with later recruitment.
  calibration_fraction <- 0.80
  selected_deadline_seconds <- 9
  list(n_respondents = nrow(completed_people), n_tasks = nrow(completed_tasks),
    n_main_tasks = n_main_tasks, n_practice_tasks = n_practice_tasks,
    minimum_valid_main_choices = minimum_valid_main_choices,
    allowed_missing_choices = allowed_missing_choices,
    deadline_seconds = deadline_seconds,
    export_time = pretest_download_time,
    summary = by_arm, baseline = baseline, time = time, cost = cost,
    reference_seconds = calibration_fraction * baseline$median_seconds,
    selected_deadline_seconds = selected_deadline_seconds,
    reduction_percent = 100 * (1 - selected_deadline_seconds / baseline$median_seconds),
    task_times = task_duration_completes, plot = plot_task_duration_completes)
})

## ---- 

## ---- analysis-duration-comparison
# Figure A1 keeps the original pre-test separate from the current nine-second
# cohort. Both panels use the same seconds scale and the same completion rule.
# The frozen pre-test values and the calibration calculations above do not change.
if (has_main_data) {
  timing_comparison <- bind_rows(
    pretest$task_times |> mutate(panel = "pretest"),
    task_duration_completes |> mutate(panel = "current")) |>
    mutate(panel = factor(panel, levels = c("pretest", "current")))

  # Ns count PEOPLE, not repeated tasks. Each complete supplies all 15 tasks.
  timing_panel_counts <- bind_rows(
    pretest$summary |> select(arm, n_respondents) |> mutate(panel = "pretest"),
    duration_counts |> mutate(panel = "current")) |>
    mutate(condition = recode(as.character(arm), Baseline = "No limit",
                              Time = "Timed", Cost = "Arithmetic")) |>
    group_by(panel) |>
    summarise(sample_note = paste0(condition, " n = ", n_respondents,
                                   collapse = "; "), .groups = "drop") |>
    mutate(title = if_else(panel == "pretest",
      paste0("A. Original pre-test: ", pretest$deadline_seconds, "-second deadline"),
      paste0("B. Current cohort: ", deadline_seconds, "-second deadline")),
      label = paste(title, sample_note, sep = "\n"))
  timing_panel_labels <- setNames(timing_panel_counts$label, timing_panel_counts$panel)
  timing_deadlines <- tibble(
    panel = factor(c("pretest", "current"), levels = c("pretest", "current")),
    seconds = c(pretest$deadline_seconds, deadline_seconds))

  plot_task_duration_comparison <- ggplot(timing_comparison,
    aes(task, mean_seconds, group = arm, color = arm, shape = arm, linetype = arm)) +
    geom_hline(data = timing_deadlines, aes(yintercept = seconds),
               inherit.aes = FALSE, linetype = "dotted", color = "grey55") +
    geom_errorbar(aes(ymin = conf.low, ymax = conf.high),
      position = position_dodge(width = 0.5), width = 0.12,
      linewidth = 0.4, alpha = 0.55, linetype = "solid") +
    geom_line(position = position_dodge(width = 0.5), linewidth = 0.65) +
    geom_point(position = position_dodge(width = 0.5), size = 2.0) +
    facet_wrap(~panel, ncol = 1, scales = "fixed",
               labeller = labeller(panel = timing_panel_labels)) +
    scale_color_manual(values = arm_colors,
      labels = c(Baseline = "No time limit", Time = "Deadline condition", Cost = "Arithmetic task")) +
    scale_shape_manual(values = c(Baseline = 16, Time = 17, Cost = 15),
      labels = c(Baseline = "No time limit", Time = "Deadline condition", Cost = "Arithmetic task")) +
    scale_linetype_manual(values = c(Baseline = "solid", Time = "dashed", Cost = "dotdash"),
      labels = c(Baseline = "No time limit", Time = "Deadline condition", Cost = "Arithmetic task")) +
    scale_x_continuous(breaks = seq_len(n_main_tasks), minor_breaks = NULL) +
    scale_y_continuous(breaks = scales::breaks_pretty(n = 6), minor_breaks = NULL) +
    labs(x = "Choice task", y = "Mean task duration (seconds)",
         color = NULL, shape = NULL, linetype = NULL) +
    theme(legend.position = "top", legend.text = element_text(size = 9),
          legend.key.width = grid::unit(0.38, "in"),
          strip.text = element_text(size = 9, face = "bold", hjust = 0),
          panel.grid.minor = element_blank(),
          plot.margin = margin(6, 8, 5.5, 5.5))
}
## ---- 

## ---- analysis-paper-counts
# Numbers in table/figure notes are calculated here, after sample filtering.
# The Rnw inserts these values with Sexpr, so no sample-size prose is hand-edited.
target_respondents <- 462L
arm_counts <- table(factor(analysis_people$arm, levels = c("Baseline", "Time", "Cost")))
paper_counts <- list(
  completed_respondents = nrow(analysis_people),
  target_respondents = target_respondents,
  percent_of_target = 100 * nrow(analysis_people) / target_respondents,
  baseline_respondents = unname(arm_counts["Baseline"]),
  time_respondents = unname(arm_counts["Time"]),
  cost_respondents = unname(arm_counts["Cost"]),
  women_respondents = sum(analysis_people$gender == "Woman", na.rm = TRUE),
  analytical_tasks = nrow(tasks),
  candidate_appearances = nrow(conjoint_dat),
  candidate_profiles = n_distinct(conjoint_dat$candidate_id),
  eligible_profiles = nrow(eligible_candidate_catalogue),
  process_family_n = if (has_model_data) nrow(process_effects) else 0L,
  gender_family_n = if (has_model_data) nrow(gender_effects) else 0L,
  baseline_family_n = if (has_model_data) sum(gender_contrasts$Condition == "Baseline") else 0L,
  hurry_model_n = if (has_model_data) nobs(model_hurry) else 0L,
  hurry_respondents = n_distinct(tasks$respondent_id[
    tasks$arm != "Cost" & !is.na(tasks$rushed_scale)]),
  scrutiny_respondents = if (has_model_data) n_distinct(scrutiny_dat$respondent_id) else 0L,
  scrutiny_appearances = if (has_model_data) nrow(scrutiny_dat) else 0L,
  scrutiny_excluded_respondents = n_distinct(conjoint_dat$respondent_id) -
    if (has_model_data) n_distinct(scrutiny_dat$respondent_id) else 0L,
  source_entrants = nrow(cohort_audit),
  cumulative_completes = sum(cohort_audit$study_complete),
  other_protocol_completes = sum(cohort_audit$study_complete & !cohort_audit$in_analysis),
  screened_out = sum(cohort_audit$screened_out),
  navigation_excluded = sum(cohort_audit$completion_status == "navigation_incomplete")
)
# Date of the analysed export, for the title page of the live draft.
data_date <- trimws(format(as.POSIXct(export_time, tz = "UTC"), "%e %B %Y"))

## ----

## ---- analysis-text
# Accessors for the live sentences in the Rnw's results section. Each returns a
# one-row frame with estimate, conf.low, conf.high and a p-value, ready for
# effect_text() and ci_phrase(). Wrap every call in live() in the Rnw, so the
# manuscript still compiles before an estimand can be computed.
process_row <- function(outcome_label, condition) {
  pick_effect(process_effects, outcome_label, paste(condition, "- Baseline"))
}
psi_row <- function(outcome_label, condition) {
  pick_effect(gender_effects, outcome_label, paste(condition, "- Baseline"))
}
gamma_row <- function(outcome_label, condition) {
  row <- gender_contrasts |>
    filter(Outcome == outcome_label, Condition == condition) |>
    transmute(estimate = Gamma, conf.low, conf.high, p.value = p, p_holm = holm_p)
  stopifnot(nrow(row) == 1L)
  if (condition != "Baseline") row$p_holm <- NULL
  row
}
mean_value <- function(outcome_label, condition, digits = 1) {
  row <- condition_means |> filter(outcome == outcome_label, arm == condition)
  stopifnot(nrow(row) == 1L)
  tex_num(row$scale * row$estimate, digits)
}
trait_row <- function(attribute, condition, contrast_label = NULL) {
  rows <- bind_rows(candidate_trait_effects, congruence_effects) |>
    filter(Attribute == attribute, Condition == condition)
  if (!is.null(contrast_label)) rows <- rows |> filter(Contrast == contrast_label)
  stopifnot(nrow(rows) == 1L)
  rows
}
reason_share <- function(reason, condition) {
  row <- reason_estimates |> filter(Reason == reason, arm == condition)
  stopifnot(nrow(row) == 1L)
  formatC(100 * row$estimate, format = "f", digits = 0)
}
# Direction words follow the reported test: Holm-adjusted for primary
# estimands, unadjusted otherwise, at the conventional 0.05 level.
change_verb <- function(row, up = "increased", down = "reduced",
                        none = "did not detectably change") {
  p <- if ("p_holm" %in% names(row) && !is.na(row$p_holm)) row$p_holm else row$p.value
  if (p >= 0.05) none else if (row$estimate > 0) up else down
}
profile_r <- function(condition) {
  r <- profile_correlations$r[profile_correlations$arm == condition]
  if (!length(r) || is.na(r)) "--" else tex_num(r, 2)
}
# Realized precision of the regression-adjusted estimator relative to the main
# (preregistered) one, within a family of Table 2: median SE ratio, its range,
# and how many adjusted standard errors are smaller. Below one = precision gain.
se_ratio_text <- function(family) {
  r <- primary_tests$se_ratio[primary_tests$Family == family]
  stopifnot(length(r) > 0L, !anyNA(r))
  paste0(formatC(median(r), format = "f", digits = 2), " (range ",
         formatC(min(r), format = "f", digits = 2), "--",
         formatC(max(r), format = "f", digits = 2), "; smaller in ",
         sum(r < 1), " of ", length(r), ")")
}
# The complementary regression-adjusted estimate of a Table 2 estimand, as a
# short phrase: estimate, unit and Holm-adjusted p (its interval is plotted).
adjusted_text <- function(outcome_label, contrast_label, unit = "") {
  row <- primary_tests |> filter(outcome == outcome_label, contrast == contrast_label)
  stopifnot(nrow(row) == 1L)
  paste0(tex_num(row$scale * row$adj_estimate, row$digits), unit, " (Holm-adjusted ",
         p_text(row$adj_p_holm), ")")
}
# Joint reading of both estimators for one outcome's Time and Cost contrasts,
# from the 'evidence' classes of Table 2. Returns a clause such as "for X,
# neither estimator rejects zero under either constraint".
evidence_clause <- function(class, both_arms = FALSE) {
  if (both_arms) switch(class,
    both = "both estimators reject zero under both constraints",
    neither = "neither estimator rejects zero under either constraint",
    `main only` = "only the preregistered differences reject zero, under both constraints",
    `adjusted only` = "only the regression-adjusted estimates reject zero, under both constraints",
    conflicting = "the two estimators reject zero with opposite signs under both constraints")
  else switch(class,
    both = "both estimators reject zero",
    neither = "neither estimator rejects zero",
    `main only` = "only the preregistered difference rejects zero",
    `adjusted only` = "only the regression-adjusted estimate rejects zero",
    conflicting = "the two estimators reject zero with opposite signs")
}
# Symbols live here, not in the Rnw: knitr's inline \Sexpr{} ends at the first
# closing brace, so LaTeX braces cannot be passed from the manuscript.
agreement_symbols <- c(
  `Any information` = "$\\tau^{A}_{zB}$",
  `Descriptions revealed` = "$\\tau^{K}_{zB}$",
  `Capped first-selection time (s)` = paste0("$\\tau^{D^{", selection_window_seconds, "}}_{zB}$"),
  `Information acquisition` = "$\\Psi_M(z)$",
  `Registered selection` = "$\\Psi_Y(z)$")
agreement_symbols[[paste0("No selection within ", selection_window_seconds, " seconds")]] <-
  paste0("$\\tau^{S^{", selection_window_seconds, "}}_{zB}$")
agreement_text <- function(outcome_label, symbol = agreement_symbols[[outcome_label]]) {
  classes <- vapply(c("Time", "Cost"), function(z) {
    row <- primary_tests |> filter(outcome == outcome_label, contrast == paste(z, "- Baseline"))
    stopifnot(nrow(row) == 1L)
    row$evidence
  }, character(1))
  if (classes[["Time"]] == classes[["Cost"]]) {
    paste0("for ", symbol, ", ", evidence_clause(classes[["Time"]], both_arms = TRUE))
  } else {
    paste0("for ", symbol, ", ", evidence_clause(classes[["Time"]]), " under \\armT\\ and ",
           evidence_clause(classes[["Cost"]]), " under \\armC")
  }
}
# One sentence summarising Table 2's last column across all primary tests.
evidence_summary <- function() {
  n <- nrow(primary_tests)
  listed <- function(class) {
    rows <- primary_tests[primary_tests$evidence == class, ]
    if (!nrow(rows)) return("none")
    paste0(nrow(rows), " (", paste(rows$Estimand, collapse = ", "), ")")
  }
  counted <- function(class) sum(primary_tests$evidence == class)
  paste0("Of the ", n, " primary tests, ", listed("both"),
    " reject zero under both estimators, ", listed("main only"),
    " only under the preregistered differences, ", listed("adjusted only"),
    " only under the regression-adjusted models, and ", counted("neither"),
    " under neither",
    if (counted("conflicting")) paste0("; ", counted("conflicting"),
      " reject zero with opposite signs") else "")
}

## ----

## ---- analysis-save
# Save MAIN FIELDWORK frames even when empty, so old pre-test rows are not reused.
# Raw downloads and the historical pre-test snapshot are never deleted or changed.
# Respondent-level files stay in the private, git-ignored data_exports folder;
# analysis_outputs holds aggregate estimates only.
private_umask <- Sys.umask("0077")
write_csv(analysis_people, file.path(project_dir, "data_exports", "analysis_participants.csv"))
write_csv(cohort_audit, file.path(project_dir, "data_exports", "completion_status.csv"))
write_csv(incomplete_people, file.path(project_dir, "data_exports", "incomplete_participants.csv"))
write_csv(incomplete_tasks, file.path(project_dir, "data_exports", "incomplete_tasks.csv"))
write_csv(tasks, file.path(project_dir, "data_exports", "analysis_tasks.csv"))
write_csv(conjoint_dat, file.path(project_dir, "data_exports", "analysis_candidates.csv"))
write_csv(candidate_profiles, file.path(project_dir, "data_exports", "analysis_candidate_profiles.csv"))
write_csv(candidate_id_coverage, file.path(output_dir, "candidate_id_coverage.csv"))

if (has_main_data) {
  write_csv(manipulation_checks, file.path(output_dir, "manipulation_checks.csv"))
  write_csv(task_duration_completes, file.path(output_dir, "task_duration_completes.csv"))
  write_csv(candidate_trait_summary, file.path(output_dir, "candidate_trait_summary.csv"))
}
if (has_model_data) {
  write_csv(flow_table, file.path(output_dir, "recruitment_flow.csv"))
  # Main (preregistered) and regression-adjusted estimates of every primary test.
  write_csv(primary_tests |>
    select(Family, outcome, contrast, estimate, std.error, conf.low, conf.high,
           p.value, p_holm, adjusted_estimate = adj_estimate,
           adjusted_std.error = adj_se, adjusted_conf.low = adj_low,
           adjusted_conf.high = adj_high, adjusted_p.value = adj_p,
           adjusted_p_holm = adj_p_holm, se_ratio, evidence),
    file.path(output_dir, "primary_tests.csv"))
  write_csv(variable_summary |> select(-digits), file.path(output_dir, "variable_summary.csv"))
  write_csv(condition_means |> select(outcome, arm, estimate, std.error, conf.low, conf.high),
    file.path(output_dir, "condition_means.csv"))
  write_csv(bind_rows(process_effects_adj |> mutate(estimator = "Regression-adjusted"),
                      process_effects |> mutate(estimator = "Preregistered")),
    file.path(output_dir, "primary_process_effects.csv"))
  write_csv(bind_rows(gender_effects_adj |> mutate(estimator = "Regression-adjusted"),
                      gender_effects |> mutate(estimator = "Preregistered")),
    file.path(output_dir, "primary_gender_effects.csv"))
  write_csv(bind_rows(gender_contrasts_adj |> mutate(estimator = "Regression-adjusted"),
                      gender_contrasts |> mutate(estimator = "Preregistered")),
    file.path(output_dir, "gender_contrasts_by_condition.csv"))
  write_csv(bind_rows(candidate_trait_effects, congruence_effects),
    file.path(output_dir, "candidate_trait_associations.csv"))
  write_csv(reason_estimates |>
    select(Source, Reason, arm, estimate, std.error, conf.low, conf.high, n_tasks),
    file.path(output_dir, "decision_reasons.csv"))
  # Per-candidate rates name real politicians, so they stay in private exports.
  write_csv(profile_selection, file.path(project_dir, "data_exports",
                                         "analysis_profile_selection.csv"))
  write_csv(respondent_scrutiny, file.path(output_dir, "respondent_gender_scrutiny.csv"))
}
writeLines(c(
  "Substantive analysis cohort: MAIN FIELDWORK ONLY; PRE-TEST EXCLUDED.",
  paste("Data refresh mode:", data_refresh_mode),
  paste("Pre-test completed responses in frozen calibration:", pretest$n_respondents),
  paste("Started responses across study versions:", paper_counts$source_entrants),
  paste("Cumulative eligible completes (dashboard definition):", paper_counts$cumulative_completes),
  paste("Other-protocol completes excluded from current analyses:", paper_counts$other_protocol_completes),
  paste("Main-fieldwork eligible completes:", nrow(analysis_people)),
  paste("Treatment models available:", has_model_data),
  paste(if (data_refresh_mode == "explicit_offline") "Offline export file timestamp:" else
          "Verified live download timestamp:", export_time),
  paste("Export MD5:", export_checksum),
  paste("Candidate catalogue MD5:", candidate_file_checksum),
  capture.output(sessionInfo())), file.path(output_dir, "analysis_provenance.txt"))
Sys.umask(private_umask)
message("MAIN FIELDWORK: ", nrow(analysis_people), " eligible completes; ",
  nrow(tasks), " analytical tasks. PRE-TEST: ", pretest$n_respondents,
  " completes retained ONLY for calibration and Figure A1.")
message("RECRUITMENT RECONCILIATION: ", paper_counts$source_entrants,
  " started responses; ", paper_counts$cumulative_completes,
  " cumulative eligible completes = ", paper_counts$completed_respondents,
  " current-protocol analytical completes + ", paper_counts$other_protocol_completes,
  " other-protocol completes excluded from current analyses.")
if (!has_model_data) message(
  "Substantive model outputs are omitted until main-fieldwork data cover all three arms.")

## ----

# The Rnw contains only matching labelled callers for these displays. Keeping
# the code here means table formatting and figures share the SAME R analysis.
# The guard prevents printing tables or opening graphics devices when the whole
# R file is sourced. During knitting the matching chunk prints its own output.

# ---------------------------- Main text ----------------------------------------

## ---- table-variable-summary
if (render_in_paper) {
  tex_tabular(variable_summary_print, align = "@{}lrrrrrrrr@{}",
    header = c("Variable", "N", "Mean", "SD", "Min", "Max", arm_labels),
    header_top = paste0(" & \\multicolumn{5}{c}{All conditions} & ",
      "\\multicolumn{3}{c}{Mean by condition} \\\\ \\cmidrule(lr){2-6}\\cmidrule(l){7-9}"),
    groups = variable_summary$Panel)
}
## ----

## ---- table-primary-tests
if (render_in_paper) {
  tex_tabular(primary_tests_print, align = "@{}lllrrrrrrrl@{}",
    header = c("Estimand", "Hypothesis", "Unit", "Estimate", "95\\% CI",
               "$p$", "Holm $p$", "Estimate", "Holm $p$", "SE ratio", "Rejected by"),
    header_top = paste0(" & & & \\multicolumn{4}{c}{Preregistered differences (main)} & ",
      "\\multicolumn{3}{c}{Regression-adjusted} & \\\\ ",
      "\\cmidrule(lr){4-7}\\cmidrule(lr){8-10}"),
    groups = primary_tests$Family)
}
## ----

## ---- figure-process
if (render_in_paper) print(plot_process)
## ----

## ---- figure-gender
if (render_in_paper) print(plot_gender)
## ----

## ---- figure-candidate-traits
if (render_in_paper) print(plot_candidate_traits)
## ----

## ---- figure-reasons
if (render_in_paper) print(plot_reasons)
## ----

## ---- figure-profiles
if (render_in_paper) print(plot_profiles)
## ----

# ---------------------------- Appendix -----------------------------------------

## ---- table-recruitment
if (render_in_paper) {
  tex_tabular(flow_table |> mutate(N = as.character(N)), align = "@{}lr@{}",
    header = c("Stage", "N"))
  cat("\n\\par\\medskip\n")
  tex_tabular(arm_flow |> mutate(arm = arm_labels[as.character(arm)]),
    align = "@{}lrrrr@{}",
    header = c("Condition", "Respondents", "Tasks", "Valid choices", "Missing choices"))
}
## ----

## ---- table-sample
if (render_in_paper) {
  knitr::kable(sample_table_print, format = "latex", booktabs = TRUE, row.names = FALSE,
    align = c("P{1.35in}", "P{1.15in}", "r", "r", "r", "r", "r"))
}
## ----

## ---- table-implementation
if (render_in_paper) {
  tex_tabular(implementation_print, align = "@{}lrrr@{}",
    header = c("Measure", arm_labels[names(implementation_print)[-1L]]))
}
## ----


## ---- figure-task-duration-comparison
if (render_in_paper) {
  if (has_main_data) print(plot_task_duration_comparison) else print(pretest$plot)
}
## ----

## ---- table-process-models
if (render_in_paper) {
  tex_tabular(process_model_table |> select(-group), align = "@{}lrrrr@{}",
    header = c("", paste0("$", c("A", "K", paste0("D^{", selection_window_seconds, "}"),
      paste0("S^{", selection_window_seconds, "}")), "$ (", c("pp", "count", "s", "pp"), ")")),
    groups = process_model_table$group,
    footer = process_model_footer)
}
## ----

## ---- table-candidate-models
if (render_in_paper) {
  tex_tabular(candidate_model_table |> select(-group), align = "@{}lrrrrrr@{}",
    header = c("", rep(c("$M$", "$Y$"), 3)),
    header_top = paste0(" & \\multicolumn{2}{c}{Eq.~\\eqref{eq:lpm}, main} & ",
      "\\multicolumn{2}{c}{Eq.~\\eqref{eq:psi}} & ",
      "\\multicolumn{2}{c}{Eq.~\\eqref{eq:gamma}} \\\\ ",
      "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(l){6-7}"),
    groups = candidate_model_table$group, footer = candidate_model_footer)
}
## ----

## ---- figure-respondent-scrutiny
if (render_in_paper) print(plot_respondent_scrutiny)
## ----

## ---- build-paper
# Knit the matching Rnw manuscript with the named chunks in THIS R file.
# Knitting reuses the exact export downloaded above; it does not contact Render
# again. Only this build receives that object, and every option is restored.
previous_refresh_option <- options(
  colombia.refresh_data = FALSE,
  colombia.download_for_knit = if (data_refresh_mode != "explicit_offline") download else NULL)
tryCatch(
  knitr::knit(file.path(project_dir, "visual_conjoint_design.Rnw"),
              output = file.path(project_dir, "visual_conjoint_design.tex"),
              envir = new.env(), quiet = TRUE),
  finally = options(previous_refresh_option)
)
# Remove only whitespace added by the document generator.
generated_tex <- file.path(project_dir, "visual_conjoint_design.tex")
writeLines(sub("[ \t]+$", "", readLines(generated_tex)), generated_tex)
latexmk <- Sys.which("latexmk")
if (!nzchar(latexmk)) latexmk <- "/Library/TeX/texbin/latexmk"
stopifnot(file.exists(latexmk))
compile_status <- system2(latexmk, c("-norc", "-pdf", "-interaction=nonstopmode",
                                    "-halt-on-error", "visual_conjoint_design.tex"),
                          stdout = file.path(output_dir, "latex_build.log"),
                          stderr = file.path(output_dir, "latex_build.log"))
stopifnot(compile_status == 0L)
message("Updated paper: ", file.path(project_dir, "visual_conjoint_design.pdf"))
## ---- 
