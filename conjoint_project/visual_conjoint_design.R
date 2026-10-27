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
# interviews from MAIN FIELDWORK. The 30 completed PRE-TEST / SOFT-LAUNCH cases
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
                 downloaded_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE)))
}

`%||%` <- function(value, fallback) if (is.null(value)) fallback else value

## ---- 

## ---- download-data
# One refresh per run. The saved Mac Keychain login is reused automatically.
# A direct Rnw build also refreshes the data. The build-paper chunk below turns
# off only the SECOND download when this whole R script has already refreshed it.
# Set options(colombia.refresh_data = FALSE) explicitly for an offline build.
if (isTRUE(getOption("colombia.refresh_data", TRUE))) {
  download <- download_study_data()
  dat <- download$started
}

## ---- 

## ---- analysis-packages
# Load familiar packages. Install missing packages once, not on every analysis.
# install.packages(c("readr", "dplyr", "tidyr", "ggplot2", "broom", "fixest",
#                    "emmeans", "sandwich", "tableone", "knitr"))
library(readr)
library(dplyr)
library(tidyr)
library(ggplot2)
library(broom)
library(fixest)
library(emmeans)
library(tableone)
# Display chunks below print only during knitting, not when sourcing this file.
render_in_paper <- isTRUE(getOption("knitr.in.progress"))

project_dir <- "/Users/hectorbahamonde/research/elections_colombia/conjoint_project"
setwd(project_dir)
input_file <- file.path(project_dir, "data_exports", "latest.csv")
output_dir <- file.path(project_dir, "analysis_outputs")
dir.create(output_dir, showWarnings = FALSE)
arm_colors <- c(Baseline = "#3A526B", Time = "#B35236", Cost = "#347F78")
theme_set(theme_bw(base_size = 11))

## ---- 

## ---- analysis-import
# Read the export saved by the download-data chunk above. Every build reruns the
# analyses on that file. Offline builds reuse the last successfully saved export.
# IDs remain text. Empty cells become NA, but the literal text "NA" is preserved.
stopifnot(file.exists(input_file))
export_time <- format(file.info(input_file)$mtime, tz = "UTC", usetz = TRUE)
export_checksum <- unname(tools::md5sum(input_file))
raw_dat <- read_csv(input_file, col_types = cols(.default = col_character()),
                na = "", trim_ws = FALSE, name_repair = "minimal",
                show_col_types = FALSE)
stopifnot(!anyDuplicated(raw_dat$participant.code),
          all(raw_dat$session.code == "fhcmy7rf"),
          all(raw_dat$session.config.official_data_collection %in% c("1", "True", "TRUE")))

## ---- 

## ---- analysis-report-parameters
# INTERNAL COHORT DEFINITION -- never print these logistics in the manuscript.
# PRE-TEST / SOFT LAUNCH: 19-20 October 2026, inclusive, in Chile/Santiago time.
# Earlier records are dropped from working analyses, NOT erased from raw files
# or Render. The 30 frozen complete pre-test cases are used ONLY for deadline
# calibration and Figure A1. New completed NINE-SECOND-version interviews are
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
raw_dat$recorded_arm_consistent <- !is.na(raw_dat$conjoint.1.player.treatment_arm) &
  rowSums(is.na(recorded_task_arms) |
    recorded_task_arms != raw_dat$conjoint.1.player.treatment_arm, na.rm = TRUE) == 0L
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
# an interview stopped before the final screen. Unknown historical records are
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


## ---- 

## ---- analysis-descriptives
if (has_main_data) {
  # Describe PEOPLE once each, not the two candidate rows or fifteen repeated tasks.
  # tableone produces familiar means/SDs and categorical counts/percentages.
  sample_for_table <- analysis_people |>
    select(arm, Age = age, Gender = gender, Education = education,
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

  supplement_for_table <- analysis_people |>
    select(arm, Occupation = occupation, `Voted last election` = voted,
           `Political discussion` = discussion, `Residence (ISO)` = country,
           `Nationality (ISO)` = nationality)
  supplement_table <- CreateTableOne(data = supplement_for_table, strata = "arm",
    vars = names(supplement_for_table)[-1L], addOverall = TRUE, test = FALSE, includeNA = TRUE)
  supplement_table_print <- print(supplement_table, showAllLevels = TRUE,
    printToggle = FALSE, noSpaces = TRUE, missing = TRUE)
  colnames(supplement_table_print)[1L] <- "Category"
  supplement_table_print <- data.frame(Characteristic = rownames(supplement_table_print),
    supplement_table_print, check.names = FALSE, row.names = NULL)

  # Main-fieldwork coverage excludes the pre-test. Unfinished people are not
  # automatically called dropouts; all raw pre-test responses remain preserved.
  excluded_by_termination <- recruitment_people$completion_status %in%
    c("navigation_incomplete", "terminated_insufficient_choices", "terminated_incomplete")
  flow_table <- tibble(
    Stage = c("Survey entrants", "Screened out", "Other interviews not entering the experiment",
              "Eligible interviews not yet finished", "Finished below the response threshold",
              "Excluded after detected reload or browser-history navigation",
              "Stopped after exceeding the permitted missing choices",
              "Other terminated incomplete interviews",
              "Eligible completed interviews included in analysis"),
    N = c(nrow(recruitment_people),
          sum(recruitment_people$screened_out &
                !excluded_by_termination),
          sum(!recruitment_people$screened_out & !recruitment_people$sequence_started &
                !excluded_by_termination),
          sum(recruitment_people$sequence_started &
                !excluded_by_termination &
                !recruitment_people$eligible_final_screen_completion),
          sum(recruitment_people$eligible_final_screen_completion &
                !excluded_by_termination &
                !recruitment_people$study_complete),
          sum(recruitment_people$completion_status == "navigation_incomplete"),
          sum(recruitment_people$completion_status == "terminated_insufficient_choices"),
          sum(recruitment_people$completion_status == "terminated_incomplete"),
          nrow(analysis_people)))
  stopifnot(sum(flow_table$N[-1L]) == flow_table$N[1L])
  arm_flow <- analysis_people |> group_by(arm) |>
    summarise(Respondents = n(), Tasks = sum(n_tasks),
      `Valid choices` = sum(n_choices), `Missing choices` = sum(n_missing_choices),
      .groups = "drop")

  # Means for the proposal's process outcomes. For binary variables, the mean is a
  # proportion. A no-choice timeout contributes to these outcomes but not a fake vote.
  task_means <- tasks |> group_by(arm) |>
    summarise(Respondents = n_distinct(respondent_id), Tasks = n(),
      `Any information (%)` = 100 * mean(any_information),
      `Descriptions (mean)` = mean(n_descriptions),
      `Both descriptions (%)` = 100 * mean(both_information),
      `Capped first-selection time (s)` = mean(capped_latency),
      no_selection_pct = 100 * mean(slow_selection),
      `Terminal nonselection (%)` = 100 * mean(terminal_timeout),
      `Expired deadlines` = sum(deadline_expired),
      `Task duration (median s)` = median(time_spent_seconds),
      .groups = "drop")
  names(task_means)[names(task_means) == "no_selection_pct"] <- no_selection_label
  task_mean_print <- task_means |>
    pivot_longer(-arm, names_to = "Measure", values_to = "Value") |>
    mutate(Value = if_else(Measure %in% c("Respondents", "Tasks", "Expired deadlines"),
                           sprintf("%.0f", Value), sprintf("%.2f", Value))) |>
    pivot_wider(names_from = arm, values_from = Value)

  # Direct manipulation checks: reported hurry and cost, actual response times,
  # arithmetic attempts and successful access. Undefined follow-up answers stay NA.
  # These follow-up means describe respondents who were asked AND answered the item.
  manipulation_checks <- tasks |> group_by(arm) |>
    summarise(
      `First selection (median s)` = median(first_selection_seconds, na.rm = TRUE),
      `Full task duration (mean s)` = mean(time_spent_seconds),
      `Full task duration (median s)` = median(time_spent_seconds),
      duration_percentile_1 = unname(quantile(time_spent_seconds, duration_quantiles[1L])),
      duration_percentile_2 = unname(quantile(time_spent_seconds, duration_quantiles[2L])),
      duration_percentile_3 = unname(quantile(time_spent_seconds, duration_quantiles[3L])),
      `Hurry responses (n)` = sum(!is.na(rushed_scale)),
      `Reported hurry (1-7)` = mean(rushed_scale, na.rm = TRUE),
      `Cost responses (n)` = sum(!is.na(info_cost_scale)),
      `Reported effort (1-7)` = mean(info_cost_scale, na.rm = TRUE),
      `Arithmetic attempts (mean)` = if_else(first(arm) == "Cost",
                                                       mean(info_cost_attempts), NA_real_),
      `Arithmetic passed (%)` = if_else(first(arm) == "Cost",
        100 * mean(info_cost_task_completed %in% c("1", "True", "TRUE")), NA_real_),
      .groups = "drop") |>
    mutate(across(where(is.numeric), ~if_else(is.nan(.x), NA_real_, .x)))
  names(manipulation_checks)[grepl("^duration_percentile_", names(manipulation_checks))] <-
    paste0("Full task duration (", 100 * duration_quantiles, "th percentile s)")
  manipulation_print <- manipulation_checks |>
    pivot_longer(-arm, names_to = "Measure", values_to = "Value") |>
    mutate(Value = case_when(is.na(Value) ~ "--",
                            grepl("responses", Measure) ~ sprintf("%.0f", Value),
                            TRUE ~ sprintf("%.2f", Value))) |>
    pivot_wider(names_from = arm, values_from = Value)
}

## ---- 

## ---- analysis-estimates
if (has_model_data) {
  # Four familiar regressions give completion-conditioned Time/Cost contrasts
  # against Baseline, not full-sample intention-to-treat effects by themselves.
  # feols fits ordinary linear models here. Its vcov argument clusters uncertainty
  # by respondent, because fifteen tasks from one person are not independent.
  model_any <- feols(any_information ~ arm, data = tasks, vcov = ~respondent_id)
  model_number <- feols(n_descriptions ~ arm, data = tasks, vcov = ~respondent_id)
  model_latency <- feols(capped_latency ~ arm, data = tasks, vcov = ~respondent_id)
  model_slow <- feols(slow_selection ~ arm, data = tasks, vcov = ~respondent_id)
  # A direct pressure check uses observed hurry answers in Time and Baseline.
  # This is conditional on answering the post-choice question, not an unconditional ITT.
  model_hurry <- feols(rushed_scale ~ arm,
    data = tasks |> filter(arm != "Cost") |> mutate(arm = droplevels(arm)),
    vcov = ~respondent_id)
  hurry_check <- tidy(model_hurry, conf.int = TRUE, conf.level = confidence_level) |>
    filter(term == "armTime")
  hurry_check_print <- hurry_check |>
    transmute(Contrast = "Hurry: Time - Baseline", Estimate = estimate,
      CI = sprintf("[%.3f, %.3f]", conf.low, conf.high),
      p = format.pval(p.value, digits = 2, eps = 0.001))
  names(hurry_check_print)[names(hurry_check_print) == "CI"] <- ci_column
  process_effects <- bind_rows(
    tidy(model_any, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(outcome = "Any information"),
    tidy(model_number, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(outcome = "Descriptions revealed"),
    tidy(model_latency, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(outcome = "Capped first-selection time (s)"),
    tidy(model_slow, conf.int = TRUE, conf.level = confidence_level) |>
      mutate(outcome = paste0("No selection within ", selection_window_seconds, " seconds"))
  ) |> filter(term %in% c("armTime", "armCost")) |>
    mutate(contrast = recode(term, armTime = "Time - Baseline",
                            armCost = "Cost - Baseline"),
           # Adjust across all reported process tests in this family.
           p_holm = p.adjust(p.value, method = "holm")) |>
    select(outcome, contrast, estimate, std.error, conf.low, conf.high, p.value, p_holm)

  # Candidate models estimate Psi_M and Psi_Y. Side and task indicators follow
  # the proposal. Two-way clustering allows repeated respondents AND candidates.
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

  # emmeans handles the simple linear combinations for Gamma within each condition.
  # It reuses the same clustered covariance. Degrees of freedom use the smaller
  # cluster count, as in the candidate models.
  gender_df <- min(n_distinct(candidate_tasks$respondent_id),
                    n_distinct(candidate_tasks$candidate_id)) - 1L
  information_means <- emmeans(model_information, ~woman | arm,
    data = candidate_tasks, at = list(woman = c(0, 1)), df = gender_df)
  choice_means <- emmeans(model_choice, ~woman | arm,
    data = candidate_tasks, at = list(woman = c(0, 1)), df = gender_df)
  gamma_information <- as.data.frame(summary(contrast(information_means,
    method = list(`Women - men` = c(-1, 1))), infer = c(TRUE, TRUE),
    level = confidence_level))
  gamma_choice <- as.data.frame(summary(contrast(choice_means,
    method = list(`Women - men` = c(-1, 1))), infer = c(TRUE, TRUE),
    level = confidence_level))
  gender_contrasts <- bind_rows(
    gamma_information |> mutate(Outcome = "Information acquisition"),
    gamma_choice |> mutate(Outcome = "Registered selection")) |>
    transmute(Outcome, Condition = arm, Gamma = estimate, conf.low = lower.CL,
              conf.high = upper.CL, p = p.value) |>
    group_by(Condition) |>
    mutate(holm_p = if_else(Condition == "Baseline",
                            p.adjust(p, method = "holm"), NA_real_)) |>
    ungroup()
  stopifnot(nrow(process_effects) > 0L, nrow(gender_effects) > 0L,
            !anyDuplicated(process_effects[c("outcome", "contrast")]),
            !anyDuplicated(gender_effects[c("outcome", "contrast")]))

  # Format table columns here so the Rnw only displays the results.
  process_print <- process_effects |>
    transmute(Outcome = outcome, Contrast = contrast, Estimate = estimate,
      CI = sprintf("[%.3f, %.3f]", conf.low, conf.high),
      p = format.pval(p.value, digits = 2, eps = 0.001),
      `Holm p` = format.pval(p_holm, digits = 2, eps = 0.001))
  names(process_print)[names(process_print) == "CI"] <- ci_column
  gender_print <- gender_effects |>
    transmute(Outcome = outcome, Contrast = contrast, Estimate = estimate,
      CI = sprintf("[%.3f, %.3f]", conf.low, conf.high),
      p = format.pval(p.value, digits = 2, eps = 0.001),
      `Holm p` = format.pval(p_holm, digits = 2, eps = 0.001))
  names(gender_print)[names(gender_print) == "CI"] <- ci_column
  gamma_print <- gender_contrasts |>
    transmute(Outcome, Condition, Gamma,
      CI = sprintf("[%.3f, %.3f]", conf.low, conf.high),
      p = format.pval(p, digits = 2, eps = 0.001),
      `Holm p` = if_else(is.na(holm_p), "--",
        format.pval(holm_p, digits = 2, eps = 0.001)))
  names(gamma_print)[names(gamma_print) == "CI"] <- ci_column
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
candidate_trait_summary_print <- candidate_trait_summary |>
  transmute(Attribute, Level, Condition = arm, Shown, Chosen,
    `Chosen / shown (%)` = sprintf("%.1f", chosen_per_shown_pct),
    `Among chosen (%)` = sprintf("%.1f", among_chosen_pct))

# Also provide ONE row per candidate with every column in the source CSV.
# This is a useful descriptive lookup, not 71 independent randomized traits.
candidate_profiles <- conjoint_dat |> group_by(candidate_id) |>
  summarise(presentations = n(), respondents = n_distinct(respondent_id),
    registered_choices = sum(selected), unanswered_presentations = sum(is.na(chosen)),
    selection_pct = 100 * mean(selected),
    information_opened_pct = 100 * mean(information_opened), .groups = "drop") |>
  left_join(candidate_catalogue, by = c("candidate_id" = "ID"),
            relationship = "many-to-one")

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
  trait_gender_means <- emmeans(model_candidate_traits, ~candidate_gender | arm,
                                data = conjoint_dat, df = candidate_trait_df)
  trait_ideology_means <- emmeans(model_candidate_traits, ~candidate_ideology | arm,
                                  data = conjoint_dat, df = candidate_trait_df)
  trait_dominance_means <- emmeans(model_candidate_traits, ~candidate_dominance | arm,
                                   data = conjoint_dat, df = candidate_trait_df)
  trait_age_means <- emmeans(model_candidate_traits, ~candidate_age_group | arm,
                              data = conjoint_dat, df = candidate_trait_df)
  trait_gender_contrasts <- as.data.frame(summary(
    contrast(trait_gender_means, method = "trt.vs.ctrl", ref = 1, adjust = "none"),
    infer = c(TRUE, TRUE), adjust = "none", level = confidence_level))
  trait_ideology_contrasts <- as.data.frame(summary(
    contrast(trait_ideology_means, method = "trt.vs.ctrl", ref = 1, adjust = "none"),
    infer = c(TRUE, TRUE), adjust = "none", level = confidence_level))
  trait_dominance_contrasts <- as.data.frame(summary(
    contrast(trait_dominance_means, method = "trt.vs.ctrl", ref = 1, adjust = "none"),
    infer = c(TRUE, TRUE), adjust = "none", level = confidence_level))
  trait_age_contrasts <- as.data.frame(summary(
    contrast(trait_age_means, method = "trt.vs.ctrl", ref = 1, adjust = "none"),
    infer = c(TRUE, TRUE), adjust = "none", level = confidence_level))
  candidate_trait_effects <- bind_rows(
    trait_gender_contrasts |> mutate(Attribute = "Gender"),
    trait_ideology_contrasts |> mutate(Attribute = "Ideology"),
    trait_dominance_contrasts |> mutate(Attribute = "Dominance"),
    trait_age_contrasts |> mutate(Attribute = "Age category")) |>
    transmute(Attribute, Contrast = contrast, Condition = arm,
      estimate, std.error = SE, conf.low = lower.CL, conf.high = upper.CL, p.value)
  expected_trait_contrasts <- nlevels(conjoint_dat$arm) *
    (nlevels(conjoint_dat$candidate_gender) - 1L +
     nlevels(conjoint_dat$candidate_ideology) - 1L +
     nlevels(conjoint_dat$candidate_dominance) - 1L +
     nlevels(conjoint_dat$candidate_age_group) - 1L)
  stopifnot(nrow(candidate_trait_effects) == expected_trait_contrasts,
            !anyNA(candidate_trait_effects$estimate))
  candidate_trait_effects_print <- candidate_trait_effects |>
    transmute(Attribute, Contrast, Condition,
      Estimate = sprintf("%.1f", 100 * estimate),
      CI = sprintf("[%.1f, %.1f]", 100 * conf.low, 100 * conf.high),
      p = format.pval(p.value, digits = 2, eps = 0.001))
  names(candidate_trait_effects_print)[names(candidate_trait_effects_print) == "CI"] <- ci_column
}

## ---- 

## ---- analysis-respondent-scrutiny
if (has_model_data) {
  # Show BOTH respondent groups, not a women-minus-men contrast. The outcome is
  # whether a displayed candidate's information was opened at least once. It is
  # not a count of clicks and cannot establish that the description was read.
  # All rows already come from eligible completed interviews. Other respondent
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
  # center. Within each panel, color AND shape distinguish candidate gender.
  # All conditions use the same scale and aligned offsets for dots and intervals.
  plot_respondent_scrutiny <- ggplot(respondent_scrutiny,
    aes(arm, 100 * probability, color = candidate_gender,
        shape = candidate_gender, group = candidate_gender)) +
    geom_errorbar(aes(ymin = 100 * conf.low, ymax = 100 * conf.high),
      position = position_dodge(width = 0.45), width = 0.12, linewidth = 0.65) +
    geom_point(position = position_dodge(width = 0.45), size = 2.8) +
    facet_wrap(~respondent_gender, nrow = 1,
      labeller = labeller(respondent_gender =
        c(Men = "Male respondents", Women = "Female respondents"))) +
    scale_color_manual(values = c(Men = "#29648A", Women = "#C66935")) +
    scale_shape_manual(values = c(Men = 16, Women = 17)) +
    scale_x_discrete(labels = c(Baseline = "Baseline", Time = "Time limit",
                                Cost = "Arithmetic cost")) +
    scale_y_continuous(breaks = seq(0, 100, by = 20), limits = c(0, 100),
      labels = scales::label_percent(scale = 1),
      expand = expansion(mult = c(0.02, 0.04))) +
    labs(x = "Decision environment", y = "Information opened (%)",
         color = "Candidate gender", shape = "Candidate gender") +
    theme(legend.position = "top", panel.grid.minor = element_blank(),
          panel.grid.major.x = element_blank(),
          strip.background = element_rect(fill = "#EDF1F4"),
          strip.text = element_text(face = "bold"),
          axis.text.x = element_text(size = 9),
          plot.margin = margin(8, 8, 5.5, 5.5))
}

## ---- 

## ---- analysis-plots
if (has_model_data) {
  # Plot 1. Compare the condition means directly. Panels use different natural units.
  means_for_plot <- task_means |>
    select(arm, `Any information (%)`, `Descriptions (mean)`,
           `Capped first-selection time (s)`, all_of(no_selection_label)) |>
    pivot_longer(-arm, names_to = "measure", values_to = "mean")
  plot_treatment_means <- ggplot(means_for_plot, aes(arm, mean, fill = arm)) +
    geom_col(width = 0.6) + facet_wrap(~measure, scales = "free_y", ncol = 2) +
    scale_fill_manual(values = arm_colors) +
    labs(x = NULL, y = NULL) + theme(legend.position = "none",
                                    strip.text = element_text(size = 9))

  # Plot 2. Assignment contrasts with respondent-clustered confidence intervals.
  plot_process <- ggplot(process_effects, aes(estimate, contrast, color = contrast,
                                             xmin = conf.low, xmax = conf.high)) +
    geom_vline(xintercept = 0, linetype = 2, color = "grey55") +
    geom_errorbar(orientation = "y", width = 0.12) +
    geom_point(size = 2.5) + facet_wrap(~outcome, scales = "free_x", ncol = 2) +
    scale_color_manual(values = c(`Time - Baseline` = "#B35236",
                                  `Cost - Baseline` = "#347F78")) +
    labs(x = paste0("Difference from baseline (", ci_column, ")"), y = NULL) +
    theme(legend.position = "none", strip.text = element_text(size = 9))

  # Plot 3. Gender-indexed interactions with two-way clustered intervals.
  plot_gender <- ggplot(gender_effects, aes(estimate, contrast, color = contrast,
                                           xmin = conf.low, xmax = conf.high)) +
    geom_vline(xintercept = 0, linetype = 2, color = "grey55") +
    geom_errorbar(orientation = "y", width = 0.12) +
    geom_point(size = 2.5) + facet_wrap(~outcome, ncol = 1) +
    scale_color_manual(values = c(`Time - Baseline` = "#B35236",
                                  `Cost - Baseline` = "#347F78")) +
    labs(x = paste0("Change in women-minus-men contrast (", ci_column, ")"), y = NULL) +
    theme(legend.position = "none", plot.margin = margin(5.5, 12, 5.5, 5.5))

  # Plot 4. Familiar conjoint-style contrasts, but interpreted as associations.
  # Every point compares a trait level with its stated reference within one arm.
  plot_candidate_traits <- ggplot(candidate_trait_effects,
    aes(100 * estimate, Contrast, color = Condition, shape = Condition,
        xmin = 100 * conf.low, xmax = 100 * conf.high)) +
    geom_vline(xintercept = 0, linetype = 2, color = "grey55") +
    geom_errorbar(orientation = "y", position = position_dodge(width = 0.55),
                  width = 0.12, linewidth = 0.5) +
    geom_point(position = position_dodge(width = 0.55), size = 2.2) +
    facet_grid(Attribute ~ ., scales = "free_y", space = "free_y") +
    scale_color_manual(values = arm_colors) +
    scale_shape_manual(values = c(Baseline = 16, Time = 17, Cost = 15)) +
    labs(x = "Adjusted difference in registered selection (percentage points)",
         y = NULL, color = NULL, shape = NULL) +
    theme(legend.position = "top", strip.text.y = element_text(angle = 0))
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

## ---- analysis-paper-counts
# Numbers in table/figure notes are calculated here, after sample filtering.
# The Rnw inserts these values with Sexpr, so no sample-size prose is hand-edited.
paper_counts <- list(
  completed_respondents = nrow(analysis_people),
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
  source_entrants = nrow(recruitment_people),
  screened_out = sum(recruitment_people$screened_out),
  navigation_excluded = sum(recruitment_people$completion_status == "navigation_incomplete")
)

## ---- 

## ---- analysis-save
# Save MAIN FIELDWORK frames even when empty, so old pre-test rows are not reused.
# Raw downloads and the historical pre-test snapshot are never deleted or changed.
private_umask <- Sys.umask("0077")
write_csv(analysis_people, file.path(project_dir, "data_exports", "analysis_participants.csv"))
write_csv(cohort_audit, file.path(project_dir, "data_exports", "completion_status.csv"))
write_csv(incomplete_people, file.path(project_dir, "data_exports", "incomplete_participants.csv"))
write_csv(incomplete_tasks, file.path(project_dir, "data_exports", "incomplete_tasks.csv"))
write_csv(tasks, file.path(project_dir, "data_exports", "analysis_tasks.csv"))
write_csv(conjoint_dat, file.path(project_dir, "data_exports", "analysis_candidates.csv"))
write_csv(candidate_profiles, file.path(project_dir, "data_exports", "analysis_candidate_profiles.csv"))
write_csv(candidate_id_coverage, file.path(output_dir, "candidate_id_coverage.csv"))

# Preserve earlier exploratory outputs in a clearly labelled archive ONCE.
# They must not remain presented as current main-fieldwork treatment estimates.
pretest_archive <- file.path(output_dir, "excluded_test_outputs")
if (!has_model_data && !dir.exists(pretest_archive)) {
  dir.create(pretest_archive)
  old_results <- file.path(output_dir, c(
    "primary_process_effects.csv", "primary_gender_effects.csv",
    "manipulation_checks.csv", "task_duration_completes.csv",
    "candidate_trait_summary.csv", "candidate_trait_associations.csv",
    "respondent_gender_scrutiny.csv", "respondent_gender_scrutiny.png",
    "respondent_gender_scrutiny.pdf", "candidate_trait_associations.png",
    "task_duration_completes.png", "figure-treatment-means-1.pdf",
    "figure-process-1.pdf", "figure-gender-effects-1.pdf",
    "figure-task-duration-completes-1.pdf",
    "figure-candidate-trait-associations-1.pdf", "figure-respondent-scrutiny-1.pdf"))
  old_results <- old_results[file.exists(old_results)]
  stopifnot(all(file.rename(old_results,
    file.path(pretest_archive, basename(old_results)))))
  message("Earlier pre-test result files were preserved in: ", pretest_archive)
}

if (has_main_data) {
  write_csv(manipulation_checks, file.path(output_dir, "manipulation_checks.csv"))
  write_csv(task_duration_completes, file.path(output_dir, "task_duration_completes.csv"))
  write_csv(candidate_trait_summary, file.path(output_dir, "candidate_trait_summary.csv"))
  ggsave(file.path(output_dir, "task_duration_completes.png"),
    plot_task_duration_completes, width = 6.7, height = 4.5, dpi = 300, bg = "white")
}
if (has_model_data) {
  write_csv(process_effects, file.path(output_dir, "primary_process_effects.csv"))
  write_csv(gender_effects, file.path(output_dir, "primary_gender_effects.csv"))
  write_csv(candidate_trait_effects, file.path(output_dir, "candidate_trait_associations.csv"))
  write_csv(respondent_scrutiny, file.path(output_dir, "respondent_gender_scrutiny.csv"))
  ggsave(file.path(output_dir, "respondent_gender_scrutiny.png"),
    plot_respondent_scrutiny, width = 7.2, height = 4.4, dpi = 300, bg = "white")
  ggsave(file.path(output_dir, "respondent_gender_scrutiny.pdf"),
    plot_respondent_scrutiny, width = 7.2, height = 4.4, bg = "white")
  ggsave(file.path(output_dir, "candidate_trait_associations.png"),
    plot_candidate_traits, width = 6.7, height = 5.2, dpi = 300, bg = "white")
}
writeLines(c(
  "Substantive analysis cohort: MAIN FIELDWORK ONLY; PRE-TEST EXCLUDED.",
  paste("Pre-test completed interviews excluded:", pretest$n_respondents),
  paste("Main-fieldwork eligible completes:", nrow(analysis_people)),
  paste("Treatment models available:", has_model_data),
  paste("Fresh export timestamp:", export_time), paste("Export MD5:", export_checksum),
  paste("Candidate catalogue MD5:", candidate_file_checksum),
  capture.output(sessionInfo())), file.path(output_dir, "analysis_provenance.txt"))
Sys.umask(private_umask)
message("MAIN FIELDWORK: ", nrow(analysis_people), " eligible completes; ",
  nrow(tasks), " analytical tasks. PRE-TEST: ", pretest$n_respondents,
  " completes retained ONLY for calibration and Figure A1.")
if (!has_model_data) message(
  "Substantive model outputs are omitted until main-fieldwork data cover all three arms.")


## ---- 

# The Rnw contains only matching labelled callers for these displays. Keeping
# the code here means table formatting and figures share the SAME R analysis.
# The guard prevents printing tables or opening graphics devices when the whole
# R file is sourced. During knitting the matching chunk prints its own output.

## ---- table-flow
if (render_in_paper) {
  knitr::kable(flow_table, format = "latex", booktabs = TRUE, row.names = FALSE)
}
## ---- 

## ---- table-arm-flow
if (render_in_paper) {
  knitr::kable(arm_flow |> rename(Condition = arm), format = "latex",
                booktabs = TRUE, row.names = FALSE)
}
## ---- 

## ---- table-sample
if (render_in_paper) {
  knitr::kable(sample_table_print, format = "latex", booktabs = TRUE, row.names = FALSE,
    align = c("P{1.2in}", "P{1.1in}", "r", "r", "r", "r", "r"))
}
## ---- 

## ---- table-task-description
if (render_in_paper) {
  knitr::kable(task_mean_print, format = "latex", booktabs = TRUE,
                digits = 2, row.names = FALSE)
}
## ---- 

## ---- figure-treatment-means
if (render_in_paper) print(plot_treatment_means)
## ---- 

## ---- table-manipulation
if (render_in_paper) {
  knitr::kable(manipulation_print, format = "latex", booktabs = TRUE,
                digits = 2, row.names = FALSE)
}
## ---- 

## ---- table-hurry-check
if (render_in_paper) {
  knitr::kable(hurry_check_print, format = "latex", booktabs = TRUE,
                digits = 3, row.names = FALSE)
}
## ---- 

## ---- table-process
if (render_in_paper) {
  knitr::kable(process_print, format = "latex", booktabs = TRUE, digits = 3,
    row.names = FALSE, align = c("P{1.65in}", "P{0.95in}", "r", "r", "r", "r"))
}
## ---- 

## ---- figure-process
if (render_in_paper) print(plot_process)
## ---- 

## ---- table-gender
if (render_in_paper) {
  knitr::kable(gender_print, format = "latex", booktabs = TRUE, digits = 3,
    row.names = FALSE, align = c("P{1.65in}", "P{0.95in}", "r", "r", "r", "r"))
}
## ---- 

## ---- figure-gender-effects
if (render_in_paper) print(plot_gender)
## ---- 

## ---- table-gamma
if (render_in_paper) {
  knitr::kable(gamma_print, format = "latex", booktabs = TRUE, digits = 3,
    row.names = FALSE, align = c("P{1.55in}", "l", "r", "r", "r", "r"))
}
## ---- 

## ---- table-sample-additional
if (render_in_paper) {
  knitr::kable(supplement_table_print, format = "latex", booktabs = TRUE, row.names = FALSE,
    align = c("P{1.2in}", "P{1.3in}", "r", "r", "r", "r", "r"))
}
## ---- 

## ---- figure-task-duration-completes
if (render_in_paper) print(plot_task_duration_completes)
## ---- 

## ---- figure-pretest-task-duration
if (render_in_paper) print(pretest$plot)
## ---- 

## ---- table-candidate-trait-composition
if (render_in_paper) {
  knitr::kable(candidate_trait_summary_print, format = "latex", booktabs = TRUE,
    row.names = FALSE, digits = 1,
    col.names = c("Attribute", "Level", "Condition", "Shown", "Chosen",
                  "Chosen / shown", "Among chosen"),
    align = c("P{0.85in}", "P{0.7in}", "P{0.7in}", "r", "r",
              "P{0.8in}", "P{0.8in}"))
}
## ---- 

## ---- table-candidate-trait-associations
if (render_in_paper) {
  knitr::kable(candidate_trait_effects_print, format = "latex", booktabs = TRUE,
    row.names = FALSE, digits = 2,
    align = c("P{0.85in}", "P{1.35in}", "P{0.7in}", "r", "r", "r"))
}
## ---- 

## ---- figure-candidate-trait-associations
if (render_in_paper) print(plot_candidate_traits)
## ---- 

## ---- figure-respondent-scrutiny
if (render_in_paper) print(plot_respondent_scrutiny)
## ---- 

## ---- build-paper
# Knit the matching Rnw manuscript with the named chunks in THIS R file.
# Knitting reuses the export downloaded above; it does not contact Render again.
previous_refresh_option <- options(colombia.refresh_data = FALSE)
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
