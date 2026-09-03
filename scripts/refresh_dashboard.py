#!/usr/bin/env python3
"""
Refresh the DYNAMIC:* sections of index.html from the Tavus API.

Reads:
  TAVUS_API_KEY   (required) - repo secret, passed as env var by the workflow
  TAVUS_PAL_ID    (optional) - defaults to Léo's PAL id below

Only touches the sections wrapped in <!-- DYNAMIC:X:START --> ... <!-- DYNAMIC:X:END -->.
Sections wrapped in <!-- MANUAL:X:START/END --> are left completely alone, since
they require a human reading transcripts (intent classification, whether a
session represents a real completed customer task) that the API can't give us.

This script is intentionally defensive: Tavus's exact list-endpoint response
shape wasn't verified against a live key while writing this (no credentials
were available in the environment that authored it). If a field is missing
from the API response, the script logs a warning and leaves that piece of the
page unchanged rather than writing garbage or crashing the whole run.

IMPORTANT: the first time you wire up TAVUS_API_KEY, trigger this workflow
manually (Actions tab -> Refresh Léo KPI dashboard -> Run workflow) and check
the run's logs/diff before trusting the hourly schedule.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

TAVUS_BASE = "https://tavusapi.com"
DEFAULT_PAL_ID = "pb31d1a81759"
INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "index.html")


def log(msg):
    print(f"[refresh] {msg}", file=sys.stderr)


def api_get(path, api_key, params=None):
    url = f"{TAVUS_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        if qs:
            url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"x-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log(f"HTTP {e.code} calling {path}: {e.read().decode('utf-8', 'replace')[:500]}")
        return None
    except Exception as e:
        log(f"error calling {path}: {e}")
        return None


def replace_section(html, name, new_inner):
    """Replace content between DYNAMIC:{name}:START/END comments. No-op if markers absent."""
    pattern = re.compile(
        rf"(<!-- DYNAMIC:{name}:START -->)(.*?)(<!-- DYNAMIC:{name}:END -->)",
        re.DOTALL,
    )
    if not pattern.search(html):
        log(f"WARNING: markers for {name} not found — skipping")
        return html
    return pattern.sub(lambda m: m.group(1) + new_inner + m.group(3), html)


def fmt_duration(seconds):
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    return f"{m}m {s:02d}s"


def main():
    api_key = os.environ.get("TAVUS_API_KEY")
    pal_id = os.environ.get("TAVUS_PAL_ID", DEFAULT_PAL_ID)

    if not api_key:
        log("TAVUS_API_KEY not set — nothing to do (add it in Settings > Secrets > Actions).")
        sys.exit(0)

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # ---- fetch conversations -------------------------------------------------
    convo_list = api_get("/v2/conversations", api_key, {"limit": 100})
    conversations = []
    if convo_list and isinstance(convo_list.get("data"), list):
        conversations = convo_list["data"]
    elif convo_list is not None:
        log("WARNING: unexpected shape from /v2/conversations, expected {'data': [...]}")

    # Filter to this PAL if the list response carries a pal id field.
    def belongs_to_pal(c):
        for key in ("pal_id", "persona_id"):
            if key in c:
                return c[key] == pal_id
        return True  # can't tell — keep it rather than silently dropping data

    conversations = [c for c in conversations if belongs_to_pal(c)]

    # Enrich each with verbose detail (duration / end reason) if not already present.
    enriched = []
    for c in conversations:
        conv_id = c.get("conversation_id") or c.get("id")
        if not conv_id:
            continue
        detail = api_get(f"/v2/conversations/{conv_id}", api_key, {"verbose": "true"})
        enriched.append({"id": conv_id, "summary": c, "detail": detail or {}})

    if enriched:
        # ---- KPI strip: sessions logged, avg length --------------------------
        durations = []
        for item in enriched:
            d = item["detail"].get("duration") or item["summary"].get("duration")
            if isinstance(d, (int, float)):
                durations.append(d)
        session_count = len(enriched)
        avg_len = fmt_duration(sum(durations) / len(durations)) if durations else "—"
        shortest = fmt_duration(min(durations)) if durations else "—"
        longest = fmt_duration(max(durations)) if durations else "—"

        kpi_note = (
            f'<!-- auto: sessions_logged={session_count}, avg={avg_len} -->\n'
            f'  <div class="kpi-strip">\n'
            f'    <div class="kpi"><div class="kpi-label">Status</div>'
            f'<div class="kpi-value" style="color:var(--good); font-size:20px;">Live</div>'
            f'<div class="kpi-sub">1 deployment channel</div></div>\n'
            f'    <div class="kpi"><div class="kpi-label">Sessions logged</div>'
            f'<div class="kpi-value accent">{session_count}</div>'
            f'<div class="kpi-sub">as of {datetime.now(timezone.utc):%d %b %Y}</div></div>\n'
            f'    <!-- MANUAL KPI (see MANUAL:INTENT_BARS block) -->\n'
            f'    <div class="kpi"><div class="kpi-label">Real customer tasks</div>'
            f'<div class="kpi-value" style="color:var(--critical);">SEE-MANUAL'
            f'<span style="font-size:14px; color:var(--ink-3); font-family:\'IBM Plex Sans\';">'
            f'&nbsp;/ {session_count}</span></div>'
            f'<div class="kpi-sub">update by hand after reading transcripts</div></div>\n'
            f'    <!-- MANUAL KPI -->\n'
            f'    <div class="kpi"><div class="kpi-label">No user engagement</div>'
            f'<div class="kpi-value" style="color:var(--warning);">SEE-MANUAL</div>'
            f'<div class="kpi-sub">update by hand</div></div>\n'
            f'    <div class="kpi"><div class="kpi-label">Guardrails active</div>'
            f'<div class="kpi-value teal">GUARDRAILS_PLACEHOLDER</div>'
            f'<div class="kpi-sub">org guardrails assigned</div></div>\n'
            f'    <div class="kpi"><div class="kpi-label">Avg. session length</div>'
            f'<div class="kpi-value teal">{avg_len}</div>'
            f'<div class="kpi-sub">{shortest} shortest, {longest} longest</div></div>\n'
            f'  </div>\n  '
        )
        # NOTE: left SEE-MANUAL / GUARDRAILS_PLACEHOLDER markers rather than
        # silently guessing — see README "First run" section before relying
        # on this in production. Replace this whole block once you've
        # validated the real /v2/conversations response shape.
        log("Computed session_count=%s avg=%s — KPI strip write is left as a manual "
            "verification step (see comments in this script) until the API "
            "response shape has been confirmed against a live key." % (session_count, avg_len))
    else:
        log("No conversations returned — leaving KPI strip and table untouched.")

    # ---- last baked timestamp -------------------------------------------------
    now = datetime.now(timezone.utc)
    html = replace_section(
        html, "LAST_BAKED",
        f"Refreshed automatically {now:%d %b %Y, %H:%M} UTC by refresh_dashboard.py."
    )
    html = replace_section(
        html, "REVIEWED_PILL",
        f'<span class="pill pill-neutral">Refreshed {now:%d %b %Y}</span>'
    )

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    log("Wrote index.html (timestamp sections updated; KPI/table sections need "
        "the verification pass described in this script's docstring before "
        "they're wired up to write automatically).")


if __name__ == "__main__":
    main()
