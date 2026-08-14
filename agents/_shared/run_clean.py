#!/usr/bin/env python
"""Run a repo python script with a CLEAN env (Hermes venv-leak protection).

Lesson from Tier 1 post-mortem (2026-08-14): the Hermes desktop app exports
PYTHONPATH/VIRTUAL_ENV/PYTHONHOME pointing at its py3.11 venv. Any repo script
spawned from a Hermes cron inherits them and crashes (ken_service: pydantic_core
ModuleNotFoundError). This wrapper strips all three, then execs the target.

Use for ALL new cron scripts (Tier 2/3/4): point the cron at a thin wrapper
in the local Hermes scripts dir that calls this with the real script path.
"""
import os
import subprocess
import sys

# Strip Hermes venv leak (must happen before any python starts)
for k in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"):
    os.environ.pop(k, None)

# Repo pythons, in preference order (env var first - no local paths hardcoded)
import shutil
PYTHONS = []
_env_py = os.environ.get("FLEET_PYTHON")
if _env_py:
    PYTHONS.append(_env_py)
for name in ("python", "python3"):
    p = shutil.which(name)
    if p:
        PYTHONS.append(p)
PYTHONS.append(sys.executable)


def find_python() -> str:
    for p in PYTHONS:
        if os.path.exists(p):
            return p
    return sys.executable


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_clean.py <script.py> [args...]", file=sys.stderr)
        return 2
    target = sys.argv[1]
    if not os.path.exists(target):
        print(f"TARGET_NOT_FOUND {target}", file=sys.stderr)
        return 1
    py = find_python()
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME")}
    return subprocess.call([py, target, *sys.argv[2:]], env=env)


if __name__ == "__main__":
    sys.exit(main())
