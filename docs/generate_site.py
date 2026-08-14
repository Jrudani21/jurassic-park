#!/usr/bin/env python3
"""KEN Fleet site generator: refresh data.js from real sources, sanity-check pages, commit+push.

Run nightly (cron) so the site reflects live fleet state. Never invents data -
if a source is missing, that field is omitted (pages handle missing gracefully).
"""
import json, os, subprocess, sys, sqlite3, datetime

# Source paths are supplied via env vars (set by the local runtime / cron).
# No local machine paths are hardcoded in this public repo.
def _env(name):
    v = os.environ.get(name)
    if not v:
        print(f"ERROR: env var {name} not set - cannot generate site")
        sys.exit(1)
    return v

REPO = _env("FLEET_SITE_DIR")
BOTS_JSON = _env("FLEET_BOTS_JSON")
LEDGER = _env("FLEET_LEDGER")
CACHE_DB = _env("FLEET_CACHE_DB")
STATE = _env("FLEET_STATE")

# Scrub private data before it reaches the public site: absolute local paths,
# Windows user dirs, and private repo names -> generic placeholders.
PRIVATE_REPOS = [
    ("personal-assistant", "the assistant app"),
    ("weather-arb", "weather-arbitrage"),
    ("janak-cave", "the cave app"),
    ("system-architecture", "the system-architecture app"),
    ("500-AI-Agents-Projects", "the fleet runtime"),
]
def scrub(text):
    import re
    # stop at quotes AND backslash (escaped-quote boundary) so JSON stays valid
    text = re.sub(r"E:[\\/]Local[^\"\\\s,)]*", "<local-path>", text)
    text = re.sub(r"C:[\\/]Users[^\"\\\s,)]*", "<user-home>", text)
    text = re.sub(r"/[ec]/[Ll]ocal[^\"\\\s,)]*", "<local-path>", text)
    for name, generic in PRIVATE_REPOS:
        text = text.replace(name, generic)
    return text
def main():
    out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds")}

    # bots + fleets
    try:
        with open(BOTS_JSON, encoding="utf-8") as f:
            d = json.load(f)
        out["fleets"] = d.get("fleets", [])
        out["bots"] = d.get("bots", [])
    except Exception as e:
        print("WARN bots:", e)

    # bot run state (last_run, status) - real freshness
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
        out["bot_state"] = st if isinstance(st, list) else st.get("bots", st)
    except Exception:
        pass

    # cost ledger (last 500 rows)
    try:
        rows = []
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try: rows.append(json.loads(line))
                    except Exception: pass
        out["cost"] = rows[-500:]
    except Exception as e:
        print("WARN cost:", e)

    # cache stats
    try:
        if os.path.exists(CACHE_DB):
            db = sqlite3.connect(f"file:{CACHE_DB}?mode=ro", uri=True)
            cur = db.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tabs = [r[0] for r in cur.fetchall()]
            stats = {}
            for t in tabs:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                    stats[t] = cur.fetchone()[0]
                except Exception: pass
            db.close()
            out["cache_tables"] = tabs
            out["cache_stats"] = stats
    except Exception as e:
        print("WARN cache:", e)

    js = "window.FLEET_DATA = " + json.dumps(out, indent=1) + ";"
    js = scrub(js)
    with open(os.path.join(REPO, "data.js"), "w", encoding="utf-8") as f:
        f.write(js)
    print(f"data.js: {len(out.get('bots', []))} bots, {len(out.get('cost', []))} cost rows, tables={out.get('cache_tables')}")

    # sanity: no em-dash creep in html pages (user rule)
    for name in ("index.html", "teams.html", "analytics.html", "process.html", "runbook.html"):
        p = os.path.join(REPO, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if "\u2014" in f.read():
                    print(f"WARN em-dash found in {name}")

    # commit + push (only if data changed or --force)
    force = "--force" in sys.argv
    if force:
        subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
        subprocess.run(["git", "commit", "-m", "nightly site refresh", "--allow-empty"], cwd=REPO, check=True)
        subprocess.run(["git", "push"], cwd=REPO, check=True)
        print("pushed (force)")
    else:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True)
        if r.stdout.strip():
            subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
            subprocess.run(["git", "commit", "-m", f"site refresh {datetime.date.today()}"], cwd=REPO, check=True)
            subprocess.run(["git", "push"], cwd=REPO, check=True)
            print("pushed changes")
        else:
            print("no changes - skipped push")

if __name__ == "__main__":
    main()
