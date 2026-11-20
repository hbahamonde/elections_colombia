# Elections Colombia

*Faces or Facts?* — a preregistered visual conjoint experiment on time pressure,
information costs and gender in candidate choice (AEARCTR-0017574). The oTree
app runs on Render; the paper is a live knitr document that downloads the latest
export, re-estimates everything and rebuilds itself.

- Latest paper (PDF): `conjoint_project/visual_conjoint_design.pdf`
- Local and Render deployment: `conjoint_project/RUNNING_AND_DEPLOYING.md`
- Live quota dashboard: `conjoint_project/QUOTA_DASHBOARD.md`
- Render infrastructure definition: `render.yaml`

## What is where

| Purpose | Files (in `conjoint_project/` unless noted) |
|---|---|
| **Collect** — oTree app | `settings.py`, `conjoint/` (models, pages, templates), `_templates/`, `_static/conjoint/` (candidate photos, `navigation_integrity.js`, `survey.css`, candidate data), `completion_rules.py`, `migrate_screening_fields.py`, `requirements.txt`, `participant_recruitment_notice.txt`, `Start Experiment.command` (local test server) |
| **Monitor** — live HTML dashboard on Render | `monitor_server.py`, `monitor_routes.py`, `quota_monitor_data.py`, `monitor_dashboard.html/.css/.js` |
| **Monitor** — daily check in RStudio | `monitor_data_collection.R` |
| **Analyze and write** | `visual_conjoint_design.R` (download, cleaning, estimation, figures, tables), `visual_conjoint_design.Rnw` (the paper), `visual_conjoint_task_example.jpg`; aggregate estimates and figure PDFs in `analysis_outputs/` |
| **Stimulus provenance** | `merge_candidate_data.R` (repo root) builds `_static/conjoint/data/base_final_merged.csv` from the source spreadsheets in the same folder |
| **Tests** | `test_*.py`, `conjoint/tests.py` (local simulations against disposable SQLite) |

Private response downloads live in `conjoint_project/data_exports/` and never
reach GitHub.

## Rebuilding the paper

Knit `visual_conjoint_design.Rnw` (or run `Rscript visual_conjoint_design.R`
from `conjoint_project/`). Either route downloads the current official export
with the oTree admin login saved in macOS Keychain, reruns every analysis and
writes the PDF. Set `options(colombia.refresh_data = FALSE)` in R for an
explicit offline build from the last saved export.
