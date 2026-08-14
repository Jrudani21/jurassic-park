#!/usr/bin/env python3
"""Fix the 4 CrewAI agents to use CrewAI 1.x LLM (not langchain ChatOpenAI)."""
import re
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "agents"
CREWAI_AGENTS = [
    "05-email-drafting-agent",
    "12-travel-planner-agent",
    "14-social-media-agent",
    "18-job-application-agent",
]

LLM_PAT = re.compile(
    r'ChatOpenAI\(model=os\.getenv\("DEEPSEEK_MODEL", "deepseek-v4-flash"\),\s*'
    r'temperature=([0-9.]+),\s*base_url="https://api\.deepseek\.com",\s*'
    r'api_key=os\.getenv\("DEEPSEEK_API_KEY"\)\)'
)

for name in CREWAI_AGENTS:
    f = AGENTS / name / "agent.py"
    orig = f.read_text(encoding="utf-8")
    new = orig
    new = new.replace(
        "from crewai import Agent, Crew, Process, Task",
        "from crewai import Agent, Crew, Process, Task, LLM",
    )
    new = new.replace("from langchain_openai import ChatOpenAI\n", "")
    new = LLM_PAT.sub(
        r'LLM(model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"), '
        r'temperature=\1, base_url="https://api.deepseek.com", '
        r'api_key=os.getenv("DEEPSEEK_API_KEY"), provider="openai")',
        new,
    )
    if new != orig:
        f.write_text(new, encoding="utf-8")
        print("FIXED", name)
    else:
        print("NO CHANGE", name)
