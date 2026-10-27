# Running and deploying the conjoint experiment

## Non-negotiable data preservation and current recruitment

**Never delete, reset, truncate, or replace the Render response database or its
collection session.** Preserve completed, incomplete, screened-out, abandoned,
and interrupted cases, including their recorded reasons. Do not use real
collection slots for automated tests. All simulations and bots must run against
isolated disposable local databases, with no Render credentials or connection.
Existing participant and monitoring links must remain unchanged.

The next recruitment batch is 30 additional people under the nine-second
configuration. These paid observations must be retained for analysis, not
discarded as disposable tests. The canonical R analysis now automatically
includes qualifying post-pretest respondents whose displayed tasks consistently
record the nine-second version and one treatment arm. An optional explicit UTC
launch cutoff remains available. All other records remain in the raw/audit
objects. The original October 19–20 twenty-second pre-test is kept separately
for its frozen calibration figure. Do not create a new Figure A1 comparison
panel until Hector requests it after the additional recruitment.

These local source changes do not themselves update Render. Push through the
existing GitHub workflow and confirm the deploy succeeds before recruitment
uses the revised behavior. No reset or schema change is required.

## Current source configuration: nine-second deadline

New interviews in the time-pressure arm have a **nine-second deadline** in all
five practice tasks and all fifteen main tasks. Instructions before and after
practice use the same saved deadline as the participant's tasks. The countdown
starts only when both photographs have loaded and become visible.

Control and arithmetic-cost participants remain untimed. Assignment is still
one treatment per participant for the entire interview, not a new treatment
draw on each task. Arithmetic access requirements are unchanged.

Previously started interviews retain their original deadline throughout the
remaining tasks. Historical responses keep their recorded 20-second metadata;
unused slots in an older session receive nine seconds on their first visit.
The existing `treatment_arm`, `timed_task`, `info_condition`, `countdown_seconds`,
`countdown_expired`, practice/main indices, candidate IDs and all response and
information-acquisition fields remain in the export. A deadline value alone
does not identify the timed arm: use `timed_task` and `treatment_arm`.

No database reset or schema migration is needed. Source edits become live only
after the updated code is pushed and successfully deployed. Do not run test
participants in the live collection session. The local simulation below copies
only source code into a temporary project and uses disposable SQLite, never
Render or the project's response database:

```bash
.venv/bin/python -m unittest -v test_time_pressure test_raffle_completion
```

The paper and canonical R script use a common nine-second window for prospective
timing comparisons, without truncating the stored raw response durations. The
frozen pre-test and Figure A1 retain the exploratory twenty-second condition.
Historical launch descriptions below document the earlier configuration.

## Browser-navigation rule

After acknowledging the initial instructions, participants must not reload the
page or use browser Back/Forward during practice, the main tasks or follow-ups.
The warning appears before and after practice, in all three arms. Detected
events make participation **incomplete for quotas and analysis and immediately
end participation**. The browser freezes while evidence is saved. The server
then renders a separate stopped-participation screen at the current URL, never
the normal completion screen or prize-registration link. Responses are retained.
Refreshing the initial instructions before continuing or revisiting the final
screen does not invalidate an interview.

Evidence is stored through oTree's participant-scoped live channel, retried
after reconnection, and included in normal form submissions as a backup. The
dashboard separates navigation-related incomplete interviews from completed
interviews and ordinary unfinished attempts. Navigation-excluded cases do not
fill either completed or pending quota counts.

Both standard wide and custom exports include the participant fields
`navigation_monitoring_started`, `navigation_violation`,
`navigation_reload_count`, `navigation_history_count`, and `navigation_events`.
`navigation_partial_task` retains bounded last-observed telemetry separately
from submitted answers; it never invents a submitted vote. The termination
fields record `study_terminated`, `study_termination_reason`,
`study_terminated_at_utc`, `study_termination_page_index`, and, only where an
actual task POST caused termination, `study_termination_submitted_round`.
Events record their type, page, round and server UTC using existing JSON
storage, so no SQL columns or database reset are needed. Older responses
without monitoring records remain **unknown**, not invented violations or
proof of clean behavior.

Timed tasks preserve first-visible timing and partial information records in
browser session storage, but a detected reload now stops rather than restarting
or resuming the task. Storage-disabled browsers may not preserve that clock,
but observable reloads are still reported and stopped. Browser controls cannot
reliably be disabled, and detection is
best effort rather than proof of intent. Ordinary Continue, automatic timed
advances, validation errors, reconnections and tab hiding do not themselves
create violations. Failed photographs have an in-place retry button.

Local-only tests, including real Chrome against disposable SQLite:

```bash
.venv/bin/python -m unittest -v test_navigation_backend test_navigation_frontend test_navigation_integration
```

Final local audit on 27 October 2026: `python -m unittest discover -v` passed
all 63 tests, including seven full oTree bot cases, actual Chrome reload and
Back/Forward, disconnected-live-channel fallback, final-screen GET/POST guards,
13-versus-12-choice eligibility, third-missing termination, native/custom exports,
monitor aggregation and synthetic downloader checks. Embedded checks also
covered 17 navigation JavaScript scenarios and 15 task-clock scenarios. A
separate in-memory R simulation accepted 30 complete nine-second cases across
all three arms and excluded recorded terminations while retaining their audit
records. No real participant was created and no production database was opened.
Protected local response/export checksums were unchanged. Figure A1 was not
regenerated. This audit verifies local source, not a successful Render deploy.

## Historical recruitment plan before the calibration decision

The following describes the earlier launch plan. The current analytical cohort
and preservation rules above take precedence; historical raw responses are
never deleted when analytical inclusion changes.

The first **30 eligible, completed panel surveys** constitute the soft launch
and count toward the **462 eligible completions in total**. After these 30,
the remaining target is **432 additional eligible completions**, not another
462. The total is not 492. Incomplete and screened-out attempts do not fill
either completion target.

The soft launch is official data collection, not a disposable technical test.
Keep the same active official session, participant link, dashboard link, and
credentials when continuing recruitment after the soft launch. **Do not reset
the database, replace the session, archive these responses, or subtract the
first 30 from the dashboard.** Its completion counter is cumulative across
both recruitment stages. The 600 allocated slots are capacity for attempts,
not the desired number of completions.

## Collection launch reset on 19 October 2026

The active official session is now `OFFICIAL_2026_10_19_LAUNCH_N462_CAP600`
(session code `fhcmy7rf`). The launch reset took effect at **2026-10-19
14:46:42 UTC**, equivalent to **17:46:42 Helsinki**.

- Participant link remains <https://colombia-conjoint.onrender.com/room/colombia_study>.
- Dashboard remains <https://colombia-conjoint.onrender.com/monitor>.
- Dashboard credentials are unchanged.
- Capacity remains **600** slots, with a target of **462 eligible completions**.
- Verified immediately after cutover: 600 unstarted slots and zero starts,
  completions, exclusions, and submitted analytical tasks.

This was a clean-session rollover, not a destructive database wipe. All three
earlier sessions were archived using oTree's archive flag. Their 1,601
participant slots and 32,020 player-round records remain recoverable in the
same PostgreSQL database. The predecessor `ecm7dqrb` was relabelled
`PRELAUNCH_2026_10_19_N462_CAP600` and marked
`official_data_collection=False`. Its three starts, including one completion,
do not count toward the new collection session. The reset timestamp and
predecessor are recorded in the new session's exported comment.

The dashboard follows the room's active session, so no URLs, credentials,
experiment settings, or deployment configuration changed. Older direct
participant URLs still belong to archived sessions. Use the unchanged master
room link for recruitment. Archiving is reversible through oTree's archived
session controls. The local `db.sqlite3` was not reset or modified.

## Earlier official activation (superseded)

The paid `colombia-conjoint` service in Alejandra's Render workspace now uses
the official session labelled `OFFICIAL_2026_10_19_N462_CAP600`.

- Participant link: <https://colombia-conjoint.onrender.com/room/colombia_study>
- Read-only recruitment dashboard: <https://colombia-conjoint.onrender.com/monitor>
- Available participant slots: **600**.
- Recruitment target: **462 eligible, completed surveys**, not 600 completions.
- Session flag: `official_data_collection=True`.
- Activation: **2026-10-19 12:25:39 UTC**, equivalent to **15:25:39 Helsinki**.
- Study configuration: five practice tasks and 15 main tasks, with a 20-second
  deadline in the timed condition. This activation did not change the design.

The activation timestamp and recruitment target are also recorded in the
session's exported comment. Both older sessions were retained. The activation
check confirmed that their 1,001 participant slots and 20,020 player-round
records remained present. No earlier responses were deleted or moved into
the official session.

The dashboard is configured with `MONITOR_MODE=official` and follows this
Room's active session. Capacity is not a completion quota, and no automatic
quota closure or rejection is enabled. Numeric quota targets remain to be
configured separately.

After the configuration deployment became live, the authenticated dashboard
returned `ready` in official mode with 600 unstarted slots, zero starts, and
zero completions. The participant welcome page returned HTTP 200, and the
dashboard data endpoint rejected anonymous access with HTTP 401. These checks
did not initialize any official participant.

### Distinguishing sample participants from technical checks

The standard response export already includes `participant.code`,
`participant.time_started_utc`, `session.label`, `session.comment`, and the
official-collection flag. The start timestamp is stored in UTC, even though
the exported string has no timezone suffix. Interpret it as UTC in analysis.

Soft-launch panel respondents are sample participants. Their first 30 eligible
completions must be retained and counted toward 462. Do not exclude respondents
because they joined during the soft launch, were recruited early, or participated
in the panel company's initial rollout.

Only explicitly identified non-sample technical checks by researchers or company
staff should be marked separately. For such a check, retain the participant code
visible in the survey's URL (`/p/<code>/...`) and its UTC start time. There is no
automatic technical-test flag for runs made inside the official session. Never
infer that a record is a technical test from its date or position among the first
30 responses. Retain raw records and document any analysis exclusion by an
explicitly verified participant code.

The separate PageTimes export provides per-page submission timestamps as Unix
seconds. There is no single overall completion-datetime field, and the final
screen itself has no submit action. Do not mistake a task-duration field for a
calendar timestamp.

## Downloading the collected responses

Download from the **oTree study website**, not from the Render infrastructure
dashboard. Open <https://colombia-conjoint.onrender.com/login> and sign in as
the researcher/admin account (normally `admin`). Its password is the value of
`OTREE_ADMIN_PASSWORD` under the paid `colombia-conjoint` service's Render
**Environment** settings. It is not your Render account password and not
Gabriel's read-only monitor password. Do not share researcher credentials with
the panel company.

For the current official session, use this session-specific CSV download after
signing in:

<https://colombia-conjoint.onrender.com/ExportWide?session_code=fhcmy7rf&format=csv_bom>

This wide export contains all questionnaire and task fields for this session,
including the 30-person soft launch. Do not use an unfiltered all-session export
for analysis without separating the archived technical sessions.

### Refreshing the data from R

The single `visual_conjoint_design.R` file now downloads the data, prepares the
analysis datasets, calculates descriptive statistics and simple point estimates,
and rebuilds the paper through `visual_conjoint_design.Rnw`. In R or RStudio, run:

```r
source("/Users/hectorbahamonde/research/elections_colombia/conjoint_project/visual_conjoint_design.R")
```

Or, from Terminal in this project folder:

```bash
Rscript visual_conjoint_design.R
```

On this Mac, the script retrieves the oTree administrator password from macOS
Keychain. If it has not been saved yet, a secure prompt asks once. The script
saves it only after a successful login and a validated official-session export.
Subsequent runs reuse it automatically, without browser sign-in or password
entry. macOS may request Keychain access permission, for example after an R
update or when the Keychain is locked. Passwords are never written into this
script, project files, or exported data. The required packages (`httr`, `xml2`,
`askpass`, and `keyring`) are installed on this Mac. No API key, database
connection, Render setting change, deployment, or recurring job is required.

The saved item is specific to this server and admin account. An explicit
`password` argument or `OTREE_ADMIN_PASSWORD` environment value takes precedence.
If the admin password changes, run
`download_study_data(password = .study_prompt_password())` once to verify and
update the Keychain item. Do not type the password directly into R code or its
console history. `remember_password = FALSE` disables Keychain use for that run.

Each successful run validates the current official session and saves the raw
CSV bytes in `data_exports/latest.csv`, plus a separate UTC-timestamped copy in
`data_exports/snapshots/`. Existing snapshots are never overwritten. A failed
login or invalid export leaves the previous latest copy untouched. These private
downloads are excluded from Git by `.gitignore`. The saved login resides in
macOS Keychain, outside the repository.

The original CSV has one row per **allocated slot**, so this 600-slot session
can produce 600 rows even when only 30 people have completed. `study$started`
selects only rows whose `participant.visited` flag is true. This includes
partial and screened-out attempts, not only eligible completed surveys.
`study$all_allocated` retains every original row. The downloader does not
redefine completion, exclude timed-out respondents, drop the soft-launch
cohort, or modify any server data. All imported fields remain character values,
preserving IDs and the original field names for later analysis.

Run the function again whenever you need a fresh copy. This is a point-in-time
download, not a live-linked dataframe or an ongoing background monitor.

### One R file and one Rnw manuscript

All downloading and analysis code lives in `visual_conjoint_design.R`. Its named,
commented chunks are reused by `visual_conjoint_design.Rnw`. Edit the paper prose
in the Rnw file. The TeX and PDF files are generated outputs. Running the R file
refreshes the data once and then knits and compiles the paper. Knitting alone
uses the saved local export and does not contact Render or Keychain.

The current analysis supports straightforward daily monitoring. It reports
sample characteristics, recruitment coverage, task means, perceived hurry and
effort, arithmetic-access checks, eight primary process point estimates, and
four candidate-gender interactions. It retains 95% confidence intervals and
two-sided significance tests, using respondent clustering for process outcomes
and respondent/candidate clustering for candidate outcomes. Raw and Holm-adjusted
p-values follow the proposal's separate test families. More elaborate robustness
models and mediation remain for later. Daily monitoring is not a sequential
significance-based stopping rule.

Useful R objects after a run are `dat` (visited respondents in the original wide
format), `analysis_people` (one row per eligible sequence starter), `tasks` (one
row per submitted analytical task), and `candidate_tasks` (two rows per task).
The latter three are also saved privately under `data_exports/`. Aggregate
point estimates and plot PDFs are saved under `analysis_outputs/` and included
in the paper. No individual response records enter the manuscript.

To rebuild without downloading again, set `options(colombia.refresh_data=FALSE)`
before sourcing the R file. Set it back to `TRUE` for routine fresh-data runs.
The Rnw reuses the analysis chunks but skips the live-download chunk automatically.
The existing clear-workspace command at the top of your R file is retained, so
sourcing the entire R file clears the current R workspace first.

## Prize-draw registration after completion

The panel company organizes a draw of three gift cards of 50,000 pesos each
and one surprise football shirt. This is a chance to win, not a guaranteed
payment. Consent and both instruction stages explain the draw and the separate
registration requirement.

Only eligible respondents who reach the final completion screen receive the
button linking to <https://bordedata.cl/encuestas/survey/42>. The button opens
the company registration page in a new tab. It does not appear during tasks or
on the screening-exclusion screen. Completing timed tasks without a recorded
choice does not remove the invitation from otherwise eligible completers.

Survey completion is not automatic raffle registration. Participants must
click the final button and complete the company's registration steps. The
company administers entry and awards. oTree does not receive confirmation of
external registration. Survey responses remain saved whether or not a person
enters the raffle. No participant code or response data are appended to the
external URL, and the link suppresses the referrer.

## One-click local testing on macOS

Double-click `Start Experiment.command` in Finder. It will:

1. open Terminal;
2. locate this project automatically;
3. create `.venv` if it is missing;
4. install the required Python packages when `requirements.txt` changes;
5. start oTree at <http://127.0.0.1:8000>; and
6. open that address in the default browser.

Keep the Terminal window open while testing. Press **Control+C** in that
window to stop the server.

The launcher deliberately binds to `127.0.0.1`. This makes the testing server
available only on this computer. It is not an internet deployment.

## The equivalent manual Terminal commands

```bash
cd /Users/hectorbahamonde/research/elections_colombia/conjoint_project
source .venv/bin/activate
python migrate_screening_fields.py
otree devserver 127.0.0.1:8000
```

Then open <http://127.0.0.1:8000>. Press **Control+C** to stop oTree. Run
`deactivate` if you want to leave the Python environment afterward.

If `.venv` has been removed, recreate it once:

```bash
cd /Users/hectorbahamonde/research/elections_colombia/conjoint_project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The migration command is safe to run repeatedly. It only adds missing project
columns (including screening and candidate-description fields) and preserves
existing responses. The one-click launcher runs it automatically. Do not run
`otree resetdb` unless you intentionally want to erase the local test database.

## What an online deployment means

Local testing and online deployment are different:

- Local testing runs `devserver`, uses the local `db.sqlite3`, and is available
  only on this Mac.
- An online study runs `prodserver`, uses PostgreSQL, and has a public HTTPS
  address.

For Render, the repository's `render.yaml` Blueprint defines one paid Web
Service and one paid PostgreSQL database. It connects them through Render's
private network and deploys the Web Service automatically whenever a commit is
pushed to the `main` branch.

### First Render deployment

1. Commit and push `render.yaml` and the `conjoint_project` changes to `main`.
2. In the correct Render workspace, select **New > Blueprint**.
3. Connect GitHub and select `hbahamonde/elections_colombia`.
4. Leave the Blueprint path as `render.yaml` and select the `main` branch.
5. Review the two resources before approving them:

   - `colombia-conjoint`: Starter Web Service, Virginia, one instance;
   - `colombia-conjoint-db`: Basic-256mb PostgreSQL, Virginia, 1 GB storage.

6. When Render requests `OTREE_ADMIN_PASSWORD` and `MONITOR_PASSWORD`, enter
   different long unique passwords and store them in the team's password
   manager. Set `MONITOR_MODE` to `testing` while pretesting, or `official` for
   fieldwork. Do not commit passwords to GitHub.
7. Approve the Blueprint and wait until both resources report healthy/live.
8. Open the Web Service's `onrender.com` URL and sign in to oTree as `admin`.
9. Create a new production session and test the entire participant flow.

The Blueprint intentionally disables database storage autoscaling and database
access from the public internet. This keeps billing predictable and allows only
Render services in the workspace to connect to PostgreSQL. The database can be
expanded manually later, but its storage cannot be reduced.

### Routine deployments with GitKraken

1. Test the project locally.
2. Review the changed files in GitKraken.
3. Commit only the intended source-code changes.
4. Push the commit to `origin/main`.
5. Render automatically builds and deploys that commit. The existing Web
   Service stays live if the new build or startup fails.
6. Confirm the deployed commit and status on the Web Service's **Deploys** page.

Do not use **Manual Deploy > Deploy a specific commit** for ordinary updates;
Render disables automatic deployments when that option is used.

Never upload `db.sqlite3` to the online service. oTree will use PostgreSQL when
`DATABASE_URL` is set.

Before inviting respondents, verify the complete participant flow, the admin
quota report, data export, and database backup/restore procedure.

## One permanent participant link

The project defines one oTree Room named `colombia_study` and one session
configuration named `colombia_conjoint`. All three experimental arms are
assigned randomly inside that single configuration. The permanent public link
is:

<https://colombia-conjoint.onrender.com/room/colombia_study>

Use the same Room link for internal testing and fieldwork. The Room points to
whichever session is currently active behind it, so the public URL does not
change when a testing session is replaced with the official session.

### Development testing to fieldwork (not the soft-launch transition)

The procedure below applies only to disposable development tests conducted
before official recruitment. It must not be used between the 30-completion
soft launch and the remaining 432 completions. Both recruitment stages use
the same official session.

1. In **Admin > Rooms**, open **Estudio Colombia — enlace maestro** and create a
   testing session with the `colombia_conjoint` configuration. Leave
   `official_data_collection` unchecked under **Configure session**.
2. Test only through the permanent Room link above. Use a private/incognito
   browser window for each new test participant so an existing participant
   cookie is not reused.
3. When testing is complete, close the Room.
4. In **Admin > Sessions**, archive the development-testing session to preserve
   its responses recoverably. Do not archive the official soft-launch session.
5. Return to **Admin > Rooms** and create a completely new session with the
   intended fieldwork capacity. Under **Configure session**, check
   `official_data_collection`. After creation, you may use the session's
   **Edit properties** page to give it an unmistakable label such as
   `OFFICIAL_2026_DO_NOT_DELETE`.
6. Confirm that its monitoring report starts at zero and displays
   **RECOLECCIÓN OFICIAL** before the marketing company distributes the
   permanent Room link. The official/testing flag is also included in oTree
   data exports as part of the session configuration.

Deleting test sessions is unnecessary: creating a new official session before
recruitment already separates official responses from earlier development
tests. Never run `otree resetdb` on Render as a routine cleanup step; it erases
every session and all collected responses. Never create a replacement session
merely because the soft launch has finished.

Closing a Room does not delete its session or its responses. It only disconnects
the permanent link from that session. Delete a testing session separately from
**Admin > Sessions** if its records should be removed.

## Monitoring access

The panel-company dashboard is available at
<https://colombia-conjoint.onrender.com/monitor>. It has a separate read-only
login, using `MONITOR_USERNAME` and `MONITOR_PASSWORD` from the paid service's
Render **Environment** page. Share only these dashboard credentials with
authorized collaborators, through a secure channel. Do not share the oTree
administrator password, database password, or connection string.

The dashboard refreshes every 10 seconds while visible. It shows aggregate
counts from the session connected to the permanent `colombia_study` Room. It
does not expose participant identifiers, political answers, individual records,
candidate choices, or raw-data downloads. Answers appear after a participant
submits the relevant page, not while they are typing. See
[QUOTA_DASHBOARD.md](QUOTA_DASHBOARD.md) for count definitions and configuration.

Before fieldwork, set `MONITOR_MODE=official` in Render and deploy the saved
configuration. The Room's active session must also have
`official_data_collection=True`. A mismatch displays an explicit warning and
no recruitment counts. Earlier test sessions are never pooled into fieldwork.
Changing this dashboard setting neither deletes data nor changes the study's
mode. For pretesting, use `MONITOR_MODE=testing` with a testing session.

The original researcher-only report remains at **Admin > session > Report >
conjoint**. It contains more detailed administrative information and is not
the link to give the panel company. Numeric quota targets must be agreed and
configured separately. The dashboard reports progress but does not close
quotas or screen out participants automatically.

## Final pretest adjustments

The original pre-test timed condition allowed 20 seconds per task, including practice. Practice
uses the participant's assigned condition throughout: the countdown, the
addition before opening information, or unrestricted access to information.
The decision clock starts after both candidate photos are loaded and visible.

The data export includes `stimulus_load_seconds` for photo-loading time and
`time_spent_seconds` for elapsed decision time. Existing information-opening,
click, hover, and timeout measures are retained. A timeout without a choice
leaves the choice and follow-up fields missing. The first two such missing main
choices advance normally; a third now ends participation immediately because
the 13-of-15 completion threshold can no longer be reached. Practice omissions
do not count toward this threshold.

The political self-placement question now uses the requested 1–10 scale
(1 = left, 10 = right). Earlier test responses used 0–10 and are left unchanged.
The project migration adds the loading-time column without deleting responses;
the local launcher and Render's pre-deployment command run it automatically.

### Completion rule and analytical sample

An eligible completed interview must reach the final study screen, submit all
15 main tasks, contain at least 13 valid candidate selections, and have no
detected prohibited browser navigation. Up to two
main tasks may have no candidate choice. Practice responses and intentionally
inapplicable follow-up questions are not completion failures. A deadline expiry
after a valid choice still counts as a valid choice.

The public recruitment monitor and the oTree custom data export share the
read-only rule in `completion_rules.py`. The monitor counts only qualifying
interviews toward quotas. Finished interviews below the threshold are reported
separately from participants who are still in progress. Navigation-excluded
interviews are also reported separately and never fill quotas. Under the current
rule, detected navigation and a third missing main choice stop participation
immediately. Incomplete cases never receive the normal final screen or its
prize-registration link, even if an old URL is revisited. The third submitted
task is counted accurately without advancing the index or inventing future
submissions. No inactivity timeout is imposed by this rule.

In oTree administration, open **Data > Custom data exports > conjoint
(custom_export)** to obtain original round responses together with
`study_complete`, `eligible_final_screen_completion`, `completion_status`,
the required threshold, and submitted/valid/missing main-task counts. These
fields are computed when downloading, so existing responses are classified
without resetting, migrating, or backfilling the database. The standard wide
export also includes the participant navigation fields described above.

The single `visual_conjoint_design.R` file applies the same 13-of-15 rule before
all substantive analyses. `dat`, `analysis_people`, `tasks`, and
`candidate_tasks` include only qualifying interviews. `raw_dat` preserves the
unfiltered export. The private `data_exports/completion_status.csv` records
recruitment classifications for auditing. Recruitment Table 1 retains screened-
out counts but does not report allocated capacity.

Paper Table 5 reports choice-page duration means, medians, and the 75th, 90th,
and 95th percentiles. Its untimed baseline is the unrestricted timing benchmark.
These durations do not include the full questionnaire, instructions, practice,
or follow-up pages. Figure A1 reports mean main-task duration by task and arm
among the same completed respondents. Completion-conditioned comparisons are
not automatically full-sample intention-to-treat effects.

### Candidate characteristics and conjoint-format analysis

The same R file reads `_static/conjoint/data/base_final_merged.csv` as the
candidate reference. It checks every recorded left/right candidate ID against
that file, rejects duplicate or unmatched IDs, and verifies that the exported
main classifications and information text match the corresponding source row.
The current CSV contains 72 profiles, of which 71 have the text required for
inclusion. All 71 candidate IDs recorded in the study match the reference.

After running the script, use `conjoint_dat` for candidate-level analyses.
It contains two rows per respondent/task, identified by `choice_set_id` and
`side`, with the candidate ID, all original candidate metadata, readable
gender/ideology/dominance/age categories, numerical facial measurements,
information opening, condition, timing, and respondent characteristics.
Only qualifying completed interviews enter this dataframe.

`chosen` is the conventional 1/0 candidate-choice outcome and remains missing
for both alternatives when no choice was registered. `selected` is the
proposal's registered-selection event, with two zeros in such a submitted task.
The original decision ID remains missing. These two variables answer different
questions and must not be silently interchanged.

`candidate_catalogue` retains the source CSV. `candidate_profiles` gives one row
per presented candidate, all source metadata, and descriptive selection and
information-opening rates. The existing private `analysis_candidates.csv`
contains `conjoint_dat`; `analysis_candidate_profiles.csv` contains the lookup.

Appendix B reports shown/chosen counts and rates, plus an exploratory joint
four-characteristic model and coefficient plot. The model uses the registered-
selection event and permits associations to differ across conditions. Estimates
have two-way respondent/candidate clustered confidence intervals and unadjusted
exploratory p-values. Because whole profiles, not their component attributes,
were randomized, these are adjusted associations rather than causal AMCEs.
