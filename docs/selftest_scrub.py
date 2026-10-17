"""Self-check for scrub(). Run: python selftest_scrub.py  (does not run the generator)."""
import json, os, sys
for v in ("FLEET_SITE_DIR", "FLEET_BOTS_JSON", "FLEET_LEDGER", "FLEET_CACHE_DB", "FLEET_STATE"):
    os.environ.setdefault(v, "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_site as g

P = ["<local-path>", "<user-home>"]
cases = {
    "single-backslash": (r"E:\Local\projects\x\y.json", "<local-path>"),
    "forward-slash": (r"E:/Local/projects/x/y.json", "<local-path>"),
    "git-bash": ("/e/Local/projects/x/y.json", "<local-path>"),
    "user-home": (r"C:\Users\someone\AppData\f", "<user-home>"),
    "user-home-fwd": (r"C:/Users/someone/f", "<user-home>"),
}
for k, (raw, ph) in list(cases.items()):
    cases[k + "-json"] = (json.dumps(raw)[1:-1], ph)  # JSON-escaped (doubled backslashes)
for name, (raw, ph) in cases.items():
    is_json = name.endswith("-json")
    out = g.scrub('{"p": "%s", "q": "ok"}' % raw)  # raw text; -json cases already carry doubled backslashes
    assert ph in out, (name, out)
    assert "Local" not in out and "someone" not in out and "projects" not in out, (name, out)
    if is_json:
        json.loads(out)  # still valid JSON
    assert '"q": "ok"' in out
for name, generic in g.PRIVATE_REPOS:
    assert g.scrub("x " + name + " y") == "x " + generic + " y", name
print("OK", len(cases), "path cases +", len(g.PRIVATE_REPOS), "repo names")
