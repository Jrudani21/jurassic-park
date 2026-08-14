#!/usr/bin/env python3
"""Remove stray tracing=False from Agent/Task; keep it only in Crew()."""
import re
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "agents"
CREWAI_AGENTS = [
    "05-email-drafting-agent",
    "12-travel-planner-agent",
    "14-social-media-agent",
    "18-job-application-agent",
]

for name in CREWAI_AGENTS:
    f = AGENTS / name / "agent.py"
    t = f.read_text(encoding="utf-8")

    # 1. Remove every tracing=False line
    t = re.sub(r"^[ \t]*tracing=False,[ \t]*\n", "", t, flags=re.M)

    # 2. Re-add tracing=False only inside the Crew(...) constructor,
    #    right after its verbose=False line.
    def add_to_crew(m):
        return m.group(1) + "        tracing=False,\n"

    # Match: process=Process.xxx, <newline> verbose=False, <newline> )
    t = re.sub(
        r"(process=Process\.\w+,\n[ \t]*verbose=False,\n)",
        add_to_crew,
        t,
    )

    f.write_text(t, encoding="utf-8")
    print("CLEANED", name)

print("\nFinal tracing=False locations (should be exactly 1 per file):")
for name in CREWAI_AGENTS:
    f = AGENTS / name / "agent.py"
    lines = [i + 1 for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines()) if "tracing=False" in ln]
    print(f"  {name}: lines {lines}")
