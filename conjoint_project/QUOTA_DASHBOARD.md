# Live recruitment dashboard

## Shared, read-only dashboard

Open <https://colombia-conjoint.onrender.com/monitor>. This is the dashboard to
share with the panel company and researchers. Its separate login is controlled
by `MONITOR_USERNAME` and `MONITOR_PASSWORD` on the paid `colombia-conjoint`
service in Alejandra's Render workspace. Retrieve the password from Render's
**Environment** page and share it securely with authorized collaborators.
Never give the company the oTree administrator password or database credentials.

The browser requests the dashboard login through HTTP Basic authentication over
HTTPS. The same credentials can retrieve aggregate JSON from `/monitor/data`
for an authorized Python viewer. No MySQL connection is required. Do not put
credentials in URLs. Use a private browser window on shared computers and
close it after use, because browsers retain Basic authentication until the
browser session ends. Rotate the dashboard password when access should end.

The dashboard is read-only. It cannot change quotas, modify or delete responses,
download individual data, or access the administrator interface. Neither
participant identifiers nor political answers nor candidate choices are sent
to it. It uses the experiment's PostgreSQL database over its existing private
connection. There is no second database or extra dashboard service to maintain.

### Session and testing scope

By default the dashboard follows the session currently connected to the
`colombia_study` Room. `MONITOR_ROOM` selects that room. An optional
`MONITOR_SESSION_CODE` environment variable instead pins the view to one
session, and takes precedence over the room. These selections can only be made
in the server configuration, not by dashboard viewers.

`MONITOR_MODE=testing` requires a testing session.
`MONITOR_MODE=official` requires `official_data_collection=True` in the active
session. Official mode excludes demo sessions and bots. If there is no active
session, a mode mismatch, or an incompatible page sequence, the dashboard
displays that state instead of presenting it as zero recruitment. Sessions are
never pooled. Switching to official collection does not require deleting tests.

### What the counts mean

- **Plazas creadas en la sesión** are preallocated participant slots. These are
  not starts and do not imply recruitment or filled quotas.
- **Iniciaron** means the participant visited their survey link.
- **Excluidos** counts participants screened out by the study's existing filters.
- **Elegibles en curso** means screening was passed and the initial demographic
  questionnaire submitted, but the final completion screen has not been reached.
- **Completadas** means eligible respondents with a submitted baseline who
  reached the final completion screen. Excluded respondents are not counted,
  even though they also see a final screen. This is not a payment or manual
  data-quality validation decision.
- Demographic and treatment tables distinguish completed responses from eligible
  responses in progress. Only completed responses fill configured numeric targets.
- Submitted main tasks include choices and expired tasks without a choice. The
  dashboard displays no-selection and timeout totals separately. It does not
  silently discard an otherwise completed survey for an unanswered timed task.

Counts update every 10 seconds while the tab is visible, or immediately with
**Actualizar**. Data appear after a page is submitted, not while someone types.
A failed refresh leaves the previous figures visibly marked as stale. This is
near-real-time monitoring, not a guaranteed instantaneous feed.

The six demographic dimensions are age, gender, residence, nationality,
education, and occupation. An additional age-by-gender table supports joint
quota monitoring. Numeric targets are optional. Without targets, the dashboard
shows counts and states that targets have not been configured. It never
automatically rejects participants or closes recruitment.

### Local technical verification

The shared routes are installed by the project launcher, while preserving
oTree's production server, transaction middleware, and timeout worker:

```bash
python monitor_server.py 127.0.0.1:8000
```

Set separate monitor credentials and the matching mode in the environment
first. Missing monitor credentials disable access with HTTP 503. Incorrect or
absent credentials receive HTTP 401. Only GET and HEAD are accepted. HTML,
assets, and JSON are authenticated and marked `no-store`. Database reads use
a read-only PostgreSQL transaction and roll back after the snapshot. No schema
or questionnaire changes are required.

The existing one-click local launcher continues to use oTree's development
server and does not expose these additional production-monitor routes.

## Researcher-only administrative report

This older, more detailed report is part of oTree's password-protected session
admin area. It is not the panel-company dashboard.

### Open the administrative report

1. Open the oTree admin page.
2. Open the session you want to monitor.
3. Select **Report**.
4. Select the `conjoint` app. The selected round does not affect the counts;
   the dashboard always counts each participant once.

Deploy this code before creating the data-collection session. If the session
was created before the report existed, create a new session so oTree adds the
**Report** tab.

The questionnaire now changes the study's page order. Do not continue an
already-active data-collection session after deploying this change; create a
fresh session so every participant receives the same page sequence.

The page refreshes every 10 seconds while its browser tab is visible. It shows:

- whether the session contains test data or official fieldwork data;
- assigned and started participants;
- participants excluded by the Colombia eligibility filter and the exclusion reason;
- participants with a complete demographic profile;
- counts and percentages for every current demographic and political question;
- the age-by-gender intersection; and
- each participant's current page and round.

The three Colombia eligibility questions are shown immediately after consent.
The demographic and political questions follow in round 1, before the conjoint
instructions and tasks. The dashboard reads those answers as each page is
submitted. Excluded participants are sent directly to the final page and are
not counted in the quota distributions. For compatibility, the report also
falls back to round-20 answers from sessions created before the questionnaire
was moved.

## Optional numeric targets for the shared dashboard

Targets can be added to a session config in `settings.py`. Category keys are
stable and are defined in `conjoint/models.py`.

```python
dict(
    name='colombia_conjoint',
    # ...existing settings...
    quota_targets=dict(
        age_band={
            '18_29': 50,
            '30_44': 50,
            '45_59': 50,
            '60_plus': 50,
        },
        gender_identity=dict(
            mujer=100,
            hombre=100,
        ),
        age_gender={
            '60_plus__mujer': 30,
        },
    ),
)
```

The numbers above are illustrative, not the study's agreed recruitment plan.
Create a new oTree session after changing session-config targets. The shared
dashboard marks a configured category as full only when its **completed** count
reaches its target. The older admin report uses different counting conventions
and should not be substituted for the shared dashboard when checking completion.

## Render data requirement

Do not collect production study data in a SQLite file on a free Render web
service. The service filesystem is ephemeral, so the database can disappear
after a restart, spin-down, or deploy. Connect the oTree service to PostgreSQL
through Render's `DATABASE_URL` environment variable and set
`OTREE_ADMIN_PASSWORD` and `OTREE_AUTH_LEVEL=STUDY`.

The local `db.sqlite3` is separate from the database used by Render. The live
dashboard on Render reads Render's database, not this local file.
