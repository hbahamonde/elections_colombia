# Daily monitoring of the Colombia experiment. Run this file with Source in RStudio.
# It downloads fresh responses, excludes pre-test cases, keeps eligible main-study
# completed interviews, opens dat,
# displays Figure A1 in Plots, and prints respondent counts by treatment/gender.
# It does not fit models, compile the paper, or change the experiment/database.
#
# Objects left in your Environment:
#   dat                  one row per respondent and main task (15 per complete)
#   respondents          one row per completed respondent
#   treatment_by_gender  counts of PEOPLE, not tasks or candidate presentations
#   figure_A1            mean seconds per task, with pointwise 95% intervals
#   task_times           the numbers plotted in figure_A1
#
# The full candidate characteristics, text, choices and behavioral records remain
# in dat. Respondent questionnaire answers are repeated on every task row.
# Pre-test cases remain in the private raw downloads but do not enter dat,
# respondents, treatment counts, or this current main-study timing figure.
# A complete reaches the final screen, submits all 15 main tasks, and records
# at least 13 valid choices. Up to two missing choices remain NA, not invented votes.
# Detected reload/history violations also make an interview incomplete. Missing
# historical navigation records remain unknown, not invented violations.
# Fail-fast terminations remain incomplete even if a saved Task POST preceded
# the stop. New completed nine-second-version cases enter analysis automatically;
# no guessed launch date is needed. Raw and incomplete records are preserved.
# Intentionally skipped follow-up questions also remain NA.
#
# Downloads are private local files in data_exports/monitoring, with dated raw
# snapshots. The master analysis, paper outputs and its latest.csv are untouched.
# The saved macOS Keychain ADMIN login is reused. No password belongs in this file.

## ---- monitoring-settings
# Leave TRUE for a new download every time. FALSE is an explicit offline option
# that uses this monitoring script's last successful download, NOT the paper's.
refresh_data <- TRUE
project_dir <- "/Users/hectorbahamonde/research/elections_colombia/conjoint_project"

# Install missing packages once, if necessary:
# install.packages(c("readr", "dplyr", "tidyr", "ggplot2", "knitr",
#                    "httr", "xml2", "keyring", "askpass"))
library(readr)
library(dplyr)
library(tidyr)
library(ggplot2)
library(knitr)
## ---- 

# Keep raw downloads and intermediate/incomplete cases inside local(), so only
# the completed-case data and requested monitoring outputs reach your Environment.
monitor <- local({

  ## ---- monitoring-download
  # Read the master's named chunks without sourcing the whole master script.
  # This reuses its verified download and completion rules, not its models/build.
  master_file <- file.path(project_dir, "visual_conjoint_design.R")
  monitoring_dir <- file.path(project_dir, "data_exports", "monitoring")
  knitr::read_chunk(master_file)
  eval(parse(text = knitr::knit_code$get("download-functions")))

  if (refresh_data) {
    download <- download_study_data(output_dir = monitoring_dir)
    raw_dat <- as_tibble(download$all_allocated)
    downloaded_at <- download$downloaded_at_utc
  } else {
    input_file <- file.path(monitoring_dir, "latest.csv")
    if (!file.exists(input_file)) {
      stop("No monitoring download exists yet. Run with refresh_data <- TRUE first.")
    }
    raw_dat <- read_csv(input_file, col_types = cols(.default = col_character()),
      na = "", trim_ws = FALSE, name_repair = "minimal", show_col_types = FALSE)
    downloaded_at <- format(file.info(input_file)$mtime, tz = "UTC", usetz = TRUE)
    message("OFFLINE: displaying the monitoring download saved at ", downloaded_at)
  }

  stopifnot(!anyDuplicated(raw_dat$participant.code),
    all(raw_dat$session.code == "fhcmy7rf"),
    all(raw_dat$session.config.official_data_collection %in% c("1", "True", "TRUE")))
  ## ---- 

  ## ---- monitoring-completes
  # These three shared chunks determine task counts, eligibility, actual task
  # submissions and the >=13/15 completion rule. They do not save paper outputs.
  # Do not replace this with complete.cases(): valid conditional blanks are normal.
  eval(parse(text = knitr::knit_code$get("analysis-report-parameters")))
  eval(parse(text = knitr::knit_code$get("analysis-participants")))
  eval(parse(text = knitr::knit_code$get("analysis-tasks")))

  if (nrow(analysis_people) == 0L) {
    message("No eligible main-fieldwork completions yet; pre-test cases are excluded. ",
            "The latest raw download has been retained.")
  }
  ## ---- 

  ## ---- monitoring-questionnaire
  # Questionnaire answers are saved in round 1, whereas main tasks begin later.
  # Join those ORIGINAL answers onto every main-task row so they do not look lost.
  baseline_variables <- c(
    "consent_accepted", "country_of_residence", "nationality", "lived_in_colombia",
    "screening_excluded", "screening_exclusion_reason", "age_years",
    "gender_identity", "gender_identity_other", "occupation_status",
    "occupation_status_other", "education_level", "voted_last_municipal",
    "political_interest", "politics_frequency", "left_right_self_placement")

  baseline_answers <- raw_dat |>
    semi_join(analysis_people, by = c("participant.code" = "respondent_id")) |>
    select(respondent_id = participant.code, session_code = session.code,
      participant_label = participant.label,
      treatment_arm = conjoint.1.player.treatment_arm,
      all_of(paste0("conjoint.1.player.", baseline_variables))) |>
    rename_with(~ sub("^conjoint\\.1\\.player\\.", "", .x),
      starts_with("conjoint.1.player.")) |>
    mutate(age_years = as.integer(age_years),
      political_interest = as.integer(political_interest))

  # Keep readable labels AND original questionnaire responses, including other
  # descriptions and nonnumeric ideology answers. Treatment is a label, not new data.
  respondents <- analysis_people |>
    select(-any_of(baseline_variables)) |>
    left_join(baseline_answers, by = "respondent_id", relationship = "one-to-one") |>
    mutate(treatment = factor(arm, levels = c("Baseline", "Time", "Cost"),
      labels = c("Control", "Time", "Math"))) |>
    relocate(respondent_id, treatment, gender, age, started_utc,
      study_complete, n_tasks, n_choices, n_missing_choices)
  ## ---- 

  ## ---- monitoring-dataset
  # Keep ALL original task fields: both candidate IDs and all 41 attributes each,
  # text, metadata backups, final choice, openings, timing, changes, mouse/hover,
  # arithmetic operands/attempts, and conditional follow-up answers.
  # Replace empty later-round questionnaire cells with the stored round-1 answers.
  dat <- tasks |>
    select(-all_of(baseline_variables), -any_of(c("is_pretest", "data_phase",
      "navigation_monitoring_started", "navigation_violation",
      "navigation_reload_count", "navigation_history_count", "navigation_events",
      "navigation_partial_task", "navigation_record_status", "study_terminated", "study_termination_reason",
      "study_terminated_at_utc", "study_termination_page_index",
      "study_termination_submitted_round"))) |>
    left_join(respondents |> select(-arm, -page_index, -sequence_started),
      by = "respondent_id", relationship = "many-to-one") |>
    arrange(started_utc, respondent_id, task) |>
    relocate(respondent_id, treatment, gender, age, task, round,
      left_candidate_id, right_candidate_id, decision_candidate_id, decision_side,
      recorded_choice, terminal_timeout, left_ideology_opened, right_ideology_opened,
      time_spent_seconds, time_to_first_choice_seconds)

  stopifnot(all(dat$study_complete), !anyNA(dat$gender_identity),
    !any(dat$navigation_violation %in% TRUE),
    !any(dat$study_terminated %in% TRUE),
    nrow(dat) == n_main_tasks * nrow(respondents),
    !anyDuplicated(dat[c("respondent_id", "task")]))
  ## ---- 

  ## ---- monitoring-counts
  # Count each completed person ONCE. Preserve every respondent gender category.
  treatment_by_gender <- with(respondents, addmargins(table(treatment, gender)))
  ## ---- 

  ## ---- monitoring-figure-a1
  # Same timing calculation as Figure A1, but for MAIN-STUDY cases only:
  # average FULL choice-task duration in seconds at each main task, with
  # pointwise 95% t intervals. Keep timed nonresponses. Pre-test cases are excluded.
  # No cap is imposed on Control/Math; loading, practice and follow-ups are excluded.
  arm_colors <- c(Baseline = "#3A526B", Time = "#B35236", Cost = "#347F78")
  if (nrow(respondents) > 0L) {
    eval(parse(text = knitr::knit_code$get("analysis-duration-completes")))
    figure_A1 <- plot_task_duration_completes +
      labs(title = "Mean time per choice task",
        subtitle = paste(nrow(respondents), "eligible completed interviews"),
        caption = paste("Downloaded:", downloaded_at,
          "\nPointwise 95% confidence intervals. Dotted line: timed-condition deadline.")) +
      theme(plot.title = element_text(face = "bold"),
        plot.caption = element_text(hjust = 0))
  } else {
    task_duration_completes <- tibble(
      arm = factor(levels = c("Baseline", "Time", "Cost")), task = integer(),
      n_respondents = integer(), mean_seconds = numeric(), sd_seconds = numeric(),
      se_seconds = numeric(), critical_t = numeric(),
      conf.low = numeric(), conf.high = numeric())
    figure_A1 <- ggplot() +
      annotate("text", x = 0, y = 0,
        label = "No eligible main-fieldwork completions yet;\npre-test cases excluded.",
        size = 4) +
      theme_void()
  }
  ## ---- 

  list(dat = dat, respondents = respondents, treatment_by_gender = treatment_by_gender,
    figure_A1 = figure_A1, task_times = task_duration_completes,
    downloaded_at = downloaded_at)
})

## ---- monitoring-display
# These ordinary data.frame objects are ready to inspect and work with in RStudio.
dat <- as.data.frame(monitor$dat)
respondents <- as.data.frame(monitor$respondents)
treatment_by_gender <- monitor$treatment_by_gender
figure_A1 <- monitor$figure_A1
task_times <- as.data.frame(monitor$task_times)

cat("\nData downloaded:", monitor$downloaded_at, "\n")
cat("Eligible main-study completes (pre-test excluded):", nrow(respondents), "\n")
cat("Main-task rows:", nrow(dat), "\n")
cat("\nCompleted MAIN-STUDY RESPONDENTS by treatment and respondent gender:\n")
print(treatment_by_gender)
print(figure_A1)
if (interactive()) View(dat, title = "Latest completed interviews - task data")
rm(monitor)
## ---- 
