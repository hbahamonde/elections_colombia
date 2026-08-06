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

Do not run `otree resetdb` unless you intentionally want to erase the local
test database.

## What an online deployment means

Local testing and online deployment are different:

- Local testing runs `devserver`, uses the local `db.sqlite3`, and is available
  only on this Mac.
- An online study runs `prodserver`, uses PostgreSQL, and has a public HTTPS
  address.

For DigitalOcean App Platform, use one application service and one managed
PostgreSQL database for all the oTree experiments in this project.

### DigitalOcean configuration

1. Push the project to its existing GitHub repository.
2. Create a DigitalOcean managed PostgreSQL database.
3. Create an App Platform application from the GitHub repository.
4. Set the source directory to `conjoint_project`.
5. Use `pip install -r requirements.txt` as the build command.
6. Use `otree prodserver 0.0.0.0:$PORT` as the run command.
7. Connect the database's `DATABASE_URL` to the application.
8. Add these encrypted environment variables:

   - `OTREE_ADMIN_PASSWORD`: a long unique password
   - `OTREE_AUTH_LEVEL`: `STUDY`
   - `OTREE_PRODUCTION`: `1`
   - `OTREE_SECRET_KEY`: a long random secret

9. Deploy the application.
10. Open its oTree admin page and create a fresh data-collection session.

Never upload `db.sqlite3` to the online service. oTree will use PostgreSQL when
`DATABASE_URL` is set.

Before inviting respondents, verify the complete participant flow, the admin
quota report, data export, and database backup/restore procedure.
