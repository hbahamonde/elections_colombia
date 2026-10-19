# Running and deploying the conjoint experiment

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

### Testing-to-fieldwork transition

1. In **Admin > Rooms**, open **Estudio Colombia — enlace maestro** and create a
   testing session with the `colombia_conjoint` configuration. Leave
   `official_data_collection` unchecked under **Configure session**.
2. Test only through the permanent Room link above. Use a private/incognito
   browser window for each new test participant so an existing participant
   cookie is not reused.
3. When testing is complete, close the Room.
4. In **Admin > Sessions**, select and delete the testing session. This deletes
   that session's participant and response records; it does not require
   `otree resetdb` and does not remove the PostgreSQL service.
5. Return to **Admin > Rooms** and create a completely new session with the
   intended fieldwork capacity. Under **Configure session**, check
   `official_data_collection`. After creation, you may use the session's
   **Edit properties** page to give it an unmistakable label such as
   `OFFICIAL_2026_DO_NOT_DELETE`.
6. Confirm that its monitoring report starts at zero and displays
   **RECOLECCIÓN OFICIAL** before the marketing company distributes the
   permanent Room link. The official/testing flag is also included in oTree
   data exports as part of the session configuration.

Deleting test sessions is optional during development: creating a new official
session already separates official responses from all earlier sessions. Never
run `otree resetdb` on Render as a routine cleanup step; it erases every session
and all collected responses.

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

The timed condition allows 20 seconds per task, including practice. Practice
uses the participant's assigned condition throughout: the countdown, the
addition before opening information, or unrestricted access to information.
The decision clock starts after both candidate photos are loaded and visible.

The data export includes `stimulus_load_seconds` for photo-loading time and
`time_spent_seconds` for elapsed decision time. Existing information-opening,
click, hover, and timeout measures are retained. A timeout without a choice
leaves the choice and follow-up fields missing and advances to the next task.

The political self-placement question now uses the requested 1–10 scale
(1 = left, 10 = right). Earlier test responses used 0–10 and are left unchanged.
The project migration adds the loading-time column without deleting responses;
the local launcher and Render's pre-deployment command run it automatically.
