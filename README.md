# Léo KPI Dashboard

A public snapshot dashboard for **Léo**, the Tavus-powered conversational AI travel
assistant for [LEVEL](https://flylevel.com) (PAL `pb31d1a81759`). Published via
GitHub Pages from `index.html`.

## Setup (one-time)

1. **Add the Tavus API key as a repo secret.**
   Settings → Secrets and variables → Actions → New repository secret →
   name it `TAVUS_API_KEY`, paste your Tavus API key as the value. (Optional:
   also add `TAVUS_PAL_ID` if you ever point this at a different PAL — it
   defaults to `pb31d1a81759`.)
   GitHub secrets are encrypted and never exposed in logs — this is the only
   place the key should ever be entered.

2. **Turn on GitHub Pages with "GitHub Actions" as the source.**
   Settings → Pages → Build and deployment → Source → **GitHub Actions**.
   (The included workflow's `deploy` job publishes via
   `actions/deploy-pages`, which requires this setting — not the older
   "Deploy from a branch" option.)

3. **Run the workflow once by hand** to confirm it works before trusting the
   hourly schedule: Actions tab → "Refresh Léo KPI dashboard" → Run workflow.
   Check the run's logs and the resulting diff to `index.html`.

## How it stays current

`.github/workflows/refresh-kpis.yml` runs hourly (and on manual dispatch). It
calls `scripts/refresh_dashboard.py`, which hits the Tavus API and rewrites
only the sections of `index.html` wrapped in
`<!-- DYNAMIC:X:START --> ... <!-- DYNAMIC:X:END -->` comments, then commits
and pushes the change and republishes via Pages.

**Important caveat:** `scripts/refresh_dashboard.py` was written against
Tavus's *documented* API shape (`docs.tavus.io`), without a live API key to
test against. It deliberately only auto-updates the timestamp/"last
refreshed" sections out of the box, and logs (but doesn't yet apply) the
sessions/duration numbers it computes — search the script for
`GUARDRAILS_PLACEHOLDER` and `SEE-MANUAL` for the exact spots that need a
verification pass once you can run it against real data. Treat the first few
runs as a review step, not "fire and forget."

Two sections are **never** touched by the script and are meant to be edited
by hand in `index.html` (search for `MANUAL:`):

- **"What people are asking Léo"** — intent per session, read from
  transcripts. There's no Tavus API field for this.
- **"Real customer tasks" KPI tile** — whether a session represents a
  completed traveler task vs. internal QA. Also a judgment call, not an API
  field.

## Files

- `index.html` — the dashboard page GitHub Pages serves.
- `scripts/refresh_dashboard.py` — pulls fresh data from Tavus, rewrites the
  `DYNAMIC:*` sections of `index.html`.
- `.github/workflows/refresh-kpis.yml` — schedules the refresh and deploys
  to Pages.
