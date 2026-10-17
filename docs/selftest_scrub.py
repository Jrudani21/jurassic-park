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

# spaces/apostrophes in folder names, git-bash user paths, spaced project folder (fake names only)
space_cases = {
    "home-space-apos": (r"C:\Users\Jane's Box\AppData\x.json", "<user-home>", ("Jane", "Box", "AppData")),
    "home-space": (r"C:\Users\Some One\AppData\x.json", "<user-home>", ("Some", "One", "AppData")),
    "gitbash-home": ("/c/Users/Jane's Box/AppData/x.json", "<user-home>", ("Jane", "Box", "AppData")),
    "gitbash-local": ("/e/Local/projects/x/y.json", "<local-path>", ("Local", "projects")),
    "spaced-project": (r"E:\Local\projects\my dir\f", "<local-path>", ("my", "dir", "projects", "Local")),
}
for k, (raw, ph, bad) in list(space_cases.items()):
    for label, r in ((k, raw), (k + "-json", json.dumps(raw)[1:-1])):
        out = g.scrub('{"p": "%s", "q": "ok"}' % r)
        assert ph in out, (label, out)
        assert not any(x in out for x in bad), (label, out)
        if label.endswith("-json"):
            json.loads(out)
        assert '"q": "ok"' in out, (label, out)
    rt = g.scrub(json.dumps({"p": raw, "q": "ok"}))
    assert json.loads(rt)["q"] == "ok" and ph in rt, (k, rt)
print("OK", len(space_cases), "space/git-bash cases")

# two paths in one string, sentence boundaries, long runs (fake names only)
multi = [
    (r"log: C:\Users\Jane Doe went home, bye. Then C:\Users\Jane Doe\x", ("Doe", "Jane"), 2),
    (r"C:\Users\Jane Doe and C:\Users\Bob Roe", ("Doe", "Roe", "Jane", "Bob"), 2),
    (r"see (C:\Users\Jane Doe) now", ("Doe", "Jane"), 1),
    (r"seen C:\Users\Jane Doe, then more", ("Doe", "Jane"), 1),
]
for raw, bad, n in multi:
    for label, r in (("raw", raw), ("json", json.dumps(raw)[1:-1])):
        out = g.scrub(r)
        assert out.count("<user-home>") == n, (label, out)
        assert not any(x in out for x in bad), (label, out)
    json.loads(g.scrub(json.dumps({"p": raw})))
long_raw = r"open C:\Users\Jane Doe " + "and then a long sentence that goes on " * 3 + "ENDMARK"
assert "ENDMARK" in g.scrub(long_raw) and "<user-home>" in g.scrub(long_raw)
nxt = g.scrub(r"open C:\Users\Jane Doe and more" + "\nnext line")
assert "next line" in nxt and "Doe" not in nxt, nxt
import random
rnd = random.Random(1)
bits = ["Jane", "Doe", "Bob's", "x", "a b", ",", ")", " and ", "C:\\Users\\", "E:\\Local\\projects\\", "/c/Users/", "/e/Local/", "\\", "/", '"', "\n", " ", "q"]
for _ in range(3000):
    s = "".join(rnd.choice(bits) for _ in range(rnd.randint(1, 14)))
    json.loads(g.scrub(json.dumps({"p": s, "q": "ok"})))
print("OK multi-path/sentence/fuzz")
