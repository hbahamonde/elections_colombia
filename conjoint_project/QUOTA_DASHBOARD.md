# Live quota dashboard

The dashboard is part of oTree's password-protected session admin area. It
queries the same database as the experiment, so it works with local SQLite and
with the PostgreSQL database used by a deployed Render service.

## Open it

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

- assigned and started participants;
- participants with a complete demographic profile;
- counts and percentages for every current demographic and political question;
- the age-by-gender intersection; and
- each participant's current page and round.

The demographic and political questions are shown immediately after consent in
round 1, before the conjoint instructions and tasks. The dashboard reads those
answers as each page is submitted. For compatibility, it also falls back to
round-20 answers from sessions created before the questionnaire was moved.

## Optional numeric targets

Targets can be added to a session config in `settings.py`. Category keys are
stable and are defined in `conjoint/models.py`.

```python
dict(
    name='conjoint_random',
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

Create a new oTree session after changing session-config targets. The report
marks a configured category as **Llena** when its count reaches its target.

## Render data requirement

Do not collect production study data in a SQLite file on a free Render web
service. The service filesystem is ephemeral, so the database can disappear
after a restart, spin-down, or deploy. Connect the oTree service to PostgreSQL
through Render's `DATABASE_URL` environment variable and set
`OTREE_ADMIN_PASSWORD` and `OTREE_AUTH_LEVEL=STUDY`.

The local `db.sqlite3` is separate from the database used by Render. The live
dashboard on Render reads Render's database, not this local file.
