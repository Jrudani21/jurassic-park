window.FLEET_DATA = {
 "generated_at": "2026-08-14T16:06:36",
 "fleets": [
  {
   "id": "ops",
   "name": "Operations",
   "coordinator": "ops-boss",
   "members": [
    "ops-boss",
    "health-watch",
    "health-watch-standby",
    "issue-triager",
    "meeting-scribe",
    "sql-agent",
    "kb-agent",
    "doc-qa"
   ],
   "notes": "Fleet oversight + provider health."
  },
  {
   "id": "qa",
   "name": "Quality Assurance",
   "coordinator": "qa-lead",
   "members": [
    "qa-lead",
    "qa-tester",
    "qa-tester-standby",
    "code-reviewer",
    "test-writer",
    "doc-writer",
    "data-analyst"
   ],
   "notes": "Deterministic testing, silent unless new bugs."
  },
  {
   "id": "research",
   "name": "Research & Intelligence",
   "coordinator": "research-lead",
   "members": [
    "research-lead",
    "research-general",
    "weather-sweep",
    "fable-stats",
    "fable-watch",
    "career-ops",
    "career-ops-standby",
    "web-researcher",
    "news-digest",
    "market-watch",
    "arb-debate"
   ],
   "notes": "Orchestrator-worker deep research, off-peak."
  },
  {
   "id": "career",
   "name": "Career Ops",
   "coordinator": "career-lead",
   "members": [
    "career-lead",
    "career-parser",
    "career-applier",
    "career-outreach",
    "career-brand",
    "career-researcher",
    "career-pii"
   ],
   "notes": "Job-search pipeline: parse CV -> tailor applications -> outreach. Runs on demand."
  }
 ],
 "bots": [
  {
   "id": "ops-boss",
   "type": "coordinator",
   "name": "Ops Boss",
   "fleet": "ops",
   "schedule": "daily:06:20",
   "runner": "qa/fleet_boss.py",
   "target": "fleet",
   "model": "deepseek-v4-flash",
   "enabled": true,
   "capabilities": [
    "oversight",
    "escalation",
    "planning"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 2000
   },
   "needs_approval": false,
   "can_approve": true,
   "approval_levels": [
    "routine"
   ],
   "notes": "Fleet overseer: checks every bot's freshness, provider health, QA state; daily fleet report + escalates anomalies. May pre-approve routine fleet actions.",
   "tier": "flash"
  },
  {
   "id": "health-watch",
   "type": "health",
   "name": "Health Watch",
   "fleet": "ops",
   "schedule": "daily:05:00",
   "runner": "qa/provider_health.py",
   "target": "all",
   "model": null,
   "enabled": true,
   "capabilities": [
    "health-checks"
   ],
   "budget": {
    "max_runs_per_day": 3,
    "max_cost_est": 0
   },
   "notes": "Pings all LLM providers; alerts only on status change.",
   "tier": "none"
  },
  {
   "id": "health-watch-standby",
   "type": "health",
   "name": "Health Watch (standby)",
   "fleet": "ops",
   "schedule": "daily:05:30",
   "runner": "qa/provider_health.py",
   "target": "all",
   "model": null,
   "enabled": true,
   "standby_for": "health-watch",
   "capabilities": [
    "health-checks"
   ],
   "budget": {
    "max_runs_per_day": 3,
    "max_cost_est": 0
   },
   "notes": "Standby for health-watch \u2014 only runs if the primary misses its window.",
   "tier": "none"
  },
  {
   "id": "qa-lead",
   "type": "coordinator",
   "name": "QA Lead",
   "fleet": "qa",
   "schedule": "daily:06:30",
   "runner": "qa/fleet_boss.py",
   "target": "qa-fleet",
   "model": "deepseek-v4-flash",
   "enabled": true,
   "capabilities": [
    "qa-oversight"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 1500
   },
   "needs_approval": false,
   "can_approve": true,
   "approval_levels": [
    "routine"
   ],
   "notes": "QA fleet lead: reviews QA Tester's buglog, decides what needs the fix crew. May pre-approve routine QA actions.",
   "tier": "flash"
  },
  {
   "id": "qa-tester",
   "type": "qa",
   "name": "QA Tester",
   "fleet": "qa",
   "schedule": "hourly",
   "runner": "qa/qa_runner.py",
   "target": "sandbox:8766",
   "model": null,
   "enabled": true,
   "capabilities": [
    "testing",
    "bug-reporting"
   ],
   "budget": {
    "max_runs_per_day": 24,
    "max_cost_est": 0
   },
   "notes": "Deterministic Playwright + probes; silent unless new bugs.",
   "tier": "none"
  },
  {
   "id": "qa-tester-standby",
   "type": "qa",
   "name": "QA Tester (standby)",
   "fleet": "qa",
   "schedule": "hourly",
   "runner": "qa/qa_runner.py",
   "target": "sandbox:8766",
   "model": null,
   "enabled": true,
   "standby_for": "qa-tester",
   "capabilities": [
    "testing",
    "bug-reporting"
   ],
   "budget": {
    "max_runs_per_day": 24,
    "max_cost_est": 0
   },
   "notes": "Standby for qa-tester \u2014 only runs if the primary misses its window.",
   "tier": "none"
  },
  {
   "id": "research-lead",
   "type": "coordinator",
   "name": "Research Lead",
   "fleet": "research",
   "schedule": "daily:06:40",
   "runner": "qa/fleet_boss.py",
   "target": "research-fleet",
   "model": "deepseek-v4-flash",
   "enabled": true,
   "capabilities": [
    "research-oversight"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 1500
   },
   "needs_approval": false,
   "can_approve": true,
   "approval_levels": [
    "routine"
   ],
   "notes": "Research fleet lead: reviews research outputs, links reports to brain, prioritizes topics. May pre-approve routine research actions.",
   "tier": "groq"
  },
  {
   "id": "research-general",
   "type": "research",
   "name": "Research Generalist",
   "fleet": "research",
   "schedule": "manual",
   "topic": "",
   "depth": "medium",
   "subagents": 3,
   "model": "deepseek-v4-flash",
   "sources": [
    "web_search",
    "web_extract",
    "arxiv"
   ],
   "output": "data/research/",
   "enabled": true,
   "capabilities": [
    "research",
    "synthesis"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 15000
   },
   "notes": "Orchestrator-worker deep research on any topic.",
   "tier": "groq"
  },
  {
   "id": "weather-sweep",
   "type": "research",
   "name": "Weather Sweep",
   "fleet": "research",
   "schedule": "weekly:mon:18:30",
   "topic": "Latest prediction-market and forecast-science papers relevant to the weather-arbitrage bot",
   "depth": "medium",
   "subagents": 2,
   "model": "deepseek-v4-flash",
   "sources": [
    "arxiv",
    "web_search"
   ],
   "output": "data/research/weather/",
   "enabled": true,
   "capabilities": [
    "literature-sweep"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 8000
   },
   "notes": "Weekly literature sweep for weather-arbitrage.",
   "tier": "flash",
   "time_sensitive": true
  },
  {
   "id": "fable-stats",
   "type": "research",
   "name": "Fable Stats",
   "fleet": "research",
   "schedule": "manual",
   "topic": "",
   "depth": "deep",
   "subagents": 4,
   "model": "deepseek-v4-pro",
   "sources": [
    "web_search",
    "code"
   ],
   "output": "data/research/fable/",
   "enabled": true,
   "capabilities": [
    "statistical-review"
   ],
   "budget": {
    "max_runs_per_day": 3,
    "max_cost_est": 40000
   },
   "notes": "Deep statistical review of weather-arbitrage Fable rounds.",
   "tier": "pro"
  },
  {
   "id": "fable-watch",
   "type": "watch",
   "name": "Fable Watch",
   "fleet": "research",
   "schedule": "weekly:mon:18:45",
   "topic": "Claude Fable 5 (Anthropic) subscription expires 2026-09-19. Check whether it has been extended, replaced, or deprecated; verify the free-tier fallbacks (OpenRouter nemotron, SambaNova DeepSeek-V3.2, Gemini flash) still work; if expiry is within 30 days, escalate with a reminder.",
   "depth": "medium",
   "subagents": 1,
   "model": "deepseek-v4-flash",
   "sources": [
    "web_search"
   ],
   "output": "data/research/fable-expiry/",
   "enabled": true,
   "capabilities": [
    "watchdog"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 6000
   },
   "notes": "Tracks Fable 5 expiry + fallback health.",
   "tier": "flash"
  },
  {
   "id": "career-ops",
   "type": "research",
   "name": "Career Ops",
   "fleet": "research",
   "schedule": "daily:18:20",
   "topic": "Resume and career-ops pipeline research: best ATS-friendly resume formats and templates 2026, job application tracking workflow, resume keyword optimization for ATS, cover letter generation best practices, interview prep tracking, and how to structure a personal career-ops pipeline (resume versions, job boards, application tracker, follow-up cadence).",
   "depth": "medium",
   "subagents": 3,
   "model": "deepseek-v4-flash",
   "sources": [
    "web_search",
    "web_extract"
   ],
   "output": "data/research/career-ops/",
   "enabled": true,
   "capabilities": [
    "career-ops"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 12000
   },
   "notes": "Off-peak research feeding the resume & career-ops pipeline.",
   "tier": "flash"
  },
  {
   "id": "career-ops-standby",
   "type": "research",
   "name": "Career Ops (standby)",
   "fleet": "research",
   "schedule": "daily:18:50",
   "topic": "Resume and career-ops pipeline research (standby rerun): ATS-friendly resume formats 2026, job application tracking, keyword optimization, cover letter generation, interview prep, career-ops pipeline structure.",
   "depth": "medium",
   "subagents": 2,
   "model": "deepseek-v4-flash",
   "sources": [
    "web_search",
    "web_extract"
   ],
   "output": "data/research/career-ops/",
   "enabled": true,
   "standby_for": "career-ops",
   "capabilities": [
    "career-ops"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 8000
   },
   "notes": "Standby for career-ops \u2014 only runs if the primary missed its window.",
   "tier": "flash"
  },
  {
   "id": "career-lead",
   "type": "coordinator",
   "name": "Career Lead",
   "fleet": "career",
   "schedule": "manual",
   "runner": "qa/fleet_boss.py",
   "target": "career-fleet",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "career-ops",
    "oversight"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 1500
   },
   "needs_approval": false,
   "can_approve": true,
   "approval_levels": [
    "routine"
   ],
   "notes": "Career fleet lead: reviews pipeline outputs, links to brain, prioritizes applications.",
   "tier": "flash"
  },
  {
   "id": "career-parser",
   "type": "agent",
   "name": "Career Parser",
   "fleet": "career",
   "schedule": "manual",
   "agent_dir": "09-resume-parser-agent",
   "agent_args": "--resume \"<local-path>\"",
   "model": "qwen3:8b",
   "tier": "local",
   "env": {
    "DEEPSEEK_API_BASE": "http://localhost:11434/v1",
    "DEEPSEEK_MODEL": "qwen3:8b"
   },
   "capabilities": [
    "career-ops",
    "resume-parse"
   ],
   "budget": {
    "max_runs_per_day": 5,
    "max_cost_est": 0
   },
   "notes": "Parse cv.md -> structured profile JSON + ATS fit (LOCAL tier \u2014 zero tokens; extraction is local-capable)."
  },
  {
   "id": "career-applier",
   "type": "agent",
   "name": "Career Applier",
   "fleet": "career",
   "schedule": "manual",
   "agent_dir": "18-job-application-agent",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "career-ops",
    "cover-letter",
    "interview-prep"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 8000
   },
   "verify": "review",
   "output": "the drafted cover letter/application",
   "notes": "Tailored cover letter + resume bullets + interview Qs (FLASH tier). Pass --job-desc and --candidate. Output is flash-reviewed before use.",
   "tier": "flash"
  },
  {
   "id": "career-outreach",
   "type": "agent",
   "name": "Career Outreach",
   "fleet": "career",
   "schedule": "manual",
   "agent_dir": "05-email-drafting-agent",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "career-ops",
    "email"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 4000
   },
   "notes": "Draft recruiter follow-up/outreach email. Pass --context --tone --recipient.",
   "tier": "flash"
  },
  {
   "id": "career-brand",
   "type": "agent",
   "name": "Career Brand",
   "fleet": "career",
   "schedule": "manual",
   "agent_dir": "14-social-media-agent",
   "agent_args": "",
   "model": "qwen3:8b",
   "tier": "local",
   "env": {
    "DEEPSEEK_API_BASE": "http://localhost:11434/v1",
    "DEEPSEEK_MODEL": "qwen3:8b"
   },
   "capabilities": [
    "career-ops",
    "social"
   ],
   "budget": {
    "max_runs_per_day": 3,
    "max_cost_est": 0
   },
   "notes": "LinkedIn personal-brand posts for job search (LOCAL tier \u2014 template generation; zero tokens). Pass post topic/brand voice."
  },
  {
   "id": "career-researcher",
   "type": "agent",
   "name": "Career Researcher",
   "fleet": "career",
   "schedule": "manual",
   "agent_dir": "19-competitive-analysis-agent",
   "agent_args": "--company \"Winnipeg Health Authority\" --industry \"healthcare\"",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "career-ops",
    "company-research"
   ],
   "budget": {
    "max_runs_per_day": 5,
    "max_cost_est": 6000
   },
   "notes": "Company research before applying. Pass --company and --industry.",
   "tier": "openrouter"
  },
  {
   "id": "career-pii",
   "type": "agent",
   "name": "Career PII Guard",
   "fleet": "career",
   "schedule": "manual",
   "agent_dir": "21-pii-sanitization-agent",
   "agent_args": "--local",
   "model": null,
   "tier": "none",
   "capabilities": [
    "career-ops",
    "pii-redaction"
   ],
   "budget": {
    "max_runs_per_day": 20,
    "max_cost_est": 0
   },
   "notes": "Scrub PII before any LLM call (deterministic, offline regex). Pass --text or --file."
  },
  {
   "id": "web-researcher",
   "type": "agent",
   "name": "Web Researcher",
   "fleet": "research",
   "schedule": "manual",
   "agent_dir": "01-web-research-agent",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "research",
    "web-search"
   ],
   "budget": {
    "max_runs_per_day": 5,
    "max_cost_est": 6000
   },
   "notes": "Iterative web research report. Pass --query. (Tavily key needed for live search.)",
   "tier": "openrouter"
  },
  {
   "id": "news-digest",
   "type": "agent",
   "name": "News Digest",
   "fleet": "research",
   "schedule": "daily:07:00",
   "agent_dir": "06-news-summarizer-agent",
   "agent_args": "--topic \"artificial intelligence\" --count 5",
   "model": "qwen3:8b",
   "tier": "local",
   "env": {
    "DEEPSEEK_API_BASE": "http://localhost:11434/v1",
    "DEEPSEEK_MODEL": "qwen3:8b"
   },
   "capabilities": [
    "news-summary"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 0
   },
   "notes": "Daily news digest (LOCAL tier \u2014 short summarization; zero tokens). Change --topic via bot config."
  },
  {
   "id": "market-watch",
   "type": "agent",
   "name": "Market Watch",
   "fleet": "research",
   "schedule": "weekly:mon:07:30",
   "agent_dir": "11-stock-research-agent",
   "agent_args": "--ticker SPY",
   "model": "deepseek-v4-pro",
   "tier": "pro",
   "capabilities": [
    "market-research"
   ],
   "budget": {
    "max_runs_per_day": 1,
    "max_cost_est": 3000
   },
   "notes": "Weekly macro gauge for weather-arbitrage context (PRO tier \u2014 financial analysis). Pass --ticker.",
   "time_sensitive": true
  },
  {
   "id": "arb-debate",
   "type": "agent",
   "name": "Arb Debate",
   "fleet": "research",
   "schedule": "manual",
   "agent_dir": "20-multi-agent-debate",
   "agent_args": "--rounds 2",
   "model": "deepseek-v4-pro",
   "tier": "pro",
   "capabilities": [
    "hypothesis-testing"
   ],
   "budget": {
    "max_runs_per_day": 3,
    "max_cost_est": 6000
   },
   "notes": "Multi-agent debate for weather-arbitrage hypothesis testing (PRO tier \u2014 deep reasoning). Pass --topic."
  },
  {
   "id": "code-reviewer",
   "type": "agent",
   "name": "Code Reviewer",
   "fleet": "qa",
   "schedule": "manual",
   "agent_dir": "02-code-review-agent",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "code-review"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 6000
   },
   "notes": "LLM code review. Pass --file or --code.",
   "tier": "flash"
  },
  {
   "id": "test-writer",
   "type": "agent",
   "name": "Test Writer",
   "fleet": "qa",
   "schedule": "manual",
   "agent_dir": "15-unit-test-generator",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "test-generation"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 6000
   },
   "notes": "Generate unit tests. Pass --file. Run pytest after.",
   "tier": "flash"
  },
  {
   "id": "doc-writer",
   "type": "agent",
   "name": "Doc Writer",
   "fleet": "qa",
   "schedule": "manual",
   "agent_dir": "16-documentation-writer",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "documentation"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 4000
   },
   "notes": "Docstring/README writer. Pass --file.",
   "tier": "flash"
  },
  {
   "id": "data-analyst",
   "type": "agent",
   "name": "Data Analyst",
   "fleet": "qa",
   "schedule": "manual",
   "agent_dir": "08-data-analysis-agent",
   "agent_args": "",
   "model": "deepseek-v4-pro",
   "tier": "pro",
   "capabilities": [
    "data-analysis"
   ],
   "budget": {
    "max_runs_per_day": 5,
    "max_cost_est": 6000
   },
   "notes": "CSV/Excel analysis for backtests + admin analytics (PRO tier \u2014 complex analysis). Pass --file. (Sandbox the exec.)"
  },
  {
   "id": "issue-triager",
   "type": "agent",
   "name": "Issue Triager",
   "fleet": "ops",
   "schedule": "manual",
   "agent_dir": "07-github-issue-triager",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "issue-triage"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 4000
   },
   "notes": "Triage a GitHub issue. Pass --issue-url or --title/--body.",
   "tier": "flash"
  },
  {
   "id": "meeting-scribe",
   "type": "agent",
   "name": "Meeting Scribe",
   "fleet": "ops",
   "schedule": "manual",
   "agent_dir": "10-meeting-notes-agent",
   "agent_args": "",
   "model": "qwen3:8b",
   "tier": "local",
   "env": {
    "DEEPSEEK_API_BASE": "http://localhost:11434/v1",
    "DEEPSEEK_MODEL": "qwen3:8b"
   },
   "capabilities": [
    "meeting-notes"
   ],
   "budget": {
    "max_runs_per_day": 5,
    "max_cost_est": 0
   },
   "notes": "Turn a transcript into notes + action items (LOCAL tier \u2014 extraction; zero tokens). Pass transcript text."
  },
  {
   "id": "sql-agent",
   "type": "agent",
   "name": "SQL Agent",
   "fleet": "ops",
   "schedule": "manual",
   "agent_dir": "04-sql-query-agent",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "sql"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 4000
   },
   "notes": "Natural-language -> SQL. Pass --db and --query.",
   "tier": "flash"
  },
  {
   "id": "kb-agent",
   "type": "agent",
   "name": "KB Agent",
   "fleet": "ops",
   "schedule": "manual",
   "agent_dir": "13-customer-support-agent",
   "agent_args": "--query \"help\"",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "knowledge-base"
   ],
   "budget": {
    "max_runs_per_day": 20,
    "max_cost_est": 4000
   },
   "notes": "Internal KB Q&A. Pass --kb-dir and --query.",
   "tier": "flash"
  },
  {
   "id": "doc-qa",
   "type": "agent",
   "name": "Doc QA",
   "fleet": "ops",
   "schedule": "manual",
   "agent_dir": "03-pdf-qa-agent",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "capabilities": [
    "document-qa"
   ],
   "budget": {
    "max_runs_per_day": 10,
    "max_cost_est": 4000
   },
   "notes": "Ask questions over a PDF. Pass --pdf and --question.",
   "tier": "flash"
  },
  {
   "id": "brain-qa",
   "type": "agent",
   "name": "Brain QA",
   "fleet": "ops",
   "schedule": "manual",
   "agent_dir": "22-vault-rag-agent",
   "agent_args": "",
   "model": "deepseek-v4-flash",
   "tier": "flash",
   "capabilities": [
    "brain-vault",
    "rag"
   ],
   "budget": {
    "max_runs_per_day": 20,
    "max_cost_est": 4000
   },
   "notes": "Ask your brain vault (<local-path>): RAG over md files via MiniLM+FAISS. Flash by default; add --local for zero-token answers."
  }
 ],
 "bot_state": {
  "qa-bot": {
   "last_run": "2026-08-13T09:31:04.485954"
  },
  "provider-health": {
   "last_run": "2026-08-13T09:31:04.485954"
  },
  "career-ops-research": {
   "last_run": "2026-08-13T09:31:04.485954"
  },
  "ops-boss": {
   "last_run": "2026-08-14T06:31:34.181749",
   "last_heartbeat": 1786715681.588266
  },
  "health-watch": {
   "last_run": "2026-08-14T10:07:03.598821",
   "last_heartbeat": 1786702029.7027476
  },
  "qa-tester": {
   "last_run": "2026-08-14T15:18:02.527226",
   "last_heartbeat": 1786738541.886375
  },
  "career-ops": {
   "last_run": "2026-08-13T10:01:11.547838"
  },
  "testbot": {
   "last_heartbeat": 1786633992.6696076
  },
  "qa-lead": {
   "last_run": "2026-08-14T06:31:34.181749",
   "last_heartbeat": 1786707025.1552825
  },
  "research-lead": {
   "last_run": "2026-08-14T06:46:42.953830",
   "last_heartbeat": 1786707919.1359541
  },
  "news-digest": {
   "last_run": "2026-08-14T07:04:38.457076"
  },
  "qa-tester-standby": {
   "last_run": "2026-08-14T09:34:38.875106"
  },
  "weather-sweep": {
   "last_run": "2026-08-14T10:14:39.248931"
  }
 },
 "cost": [
  {
   "ts": "2026-08-13T22:49:25.497908+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 90,
   "completion_tokens": 16,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 3e-05,
   "caller": ""
  },
  {
   "ts": "2026-08-14T01:19:48.676858+00:00",
   "tier": "local",
   "model": "qwen3:8b",
   "prompt_tokens": 737,
   "completion_tokens": 533,
   "cache_hit_tokens": 0,
   "peak": true,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T01:27:41.166971+00:00",
   "tier": "groq",
   "model": "llama-3.3-70b-versatile",
   "prompt_tokens": 43,
   "completion_tokens": 5,
   "cache_hit_tokens": 0,
   "peak": true,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T01:27:54.090039+00:00",
   "tier": "openrouter",
   "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
   "prompt_tokens": 25,
   "completion_tokens": 10,
   "cache_hit_tokens": 0,
   "peak": true,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T01:27:54.620608+00:00",
   "tier": "groq",
   "model": "llama-3.3-70b-versatile",
   "prompt_tokens": 44,
   "completion_tokens": 4,
   "cache_hit_tokens": 0,
   "peak": true,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T01:27:55.602770+00:00",
   "tier": "free",
   "model": "meta/llama-3.1-70b-instruct",
   "prompt_tokens": 43,
   "completion_tokens": 3,
   "cache_hit_tokens": 0,
   "peak": true,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T12:54:28.188985+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 96,
   "completion_tokens": 15,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 3.1e-05,
   "caller": ""
  },
  {
   "ts": "2026-08-14T12:54:29.134071+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 96,
   "completion_tokens": 19,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 3.4e-05,
   "caller": ""
  },
  {
   "ts": "2026-08-14T13:29:48.725293+00:00",
   "tier": "groq",
   "model": "llama-3.3-70b-versatile",
   "prompt_tokens": 808,
   "completion_tokens": 267,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T13:32:21.194204+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 1023,
   "completion_tokens": 798,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.000752,
   "caller": ""
  },
  {
   "ts": "2026-08-14T15:00:38.950391+00:00",
   "tier": "local",
   "model": "qwen3:8b",
   "prompt_tokens": 86,
   "completion_tokens": 762,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": "cascade"
  },
  {
   "ts": "2026-08-14T15:14:24.646888+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 634,
   "completion_tokens": 711,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.000609,
   "caller": ""
  },
  {
   "ts": "2026-08-14T15:14:29.579457+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 633,
   "completion_tokens": 441,
   "cache_hit_tokens": 512,
   "peak": false,
   "est_cost_usd": 0.000321,
   "caller": ""
  },
  {
   "ts": "2026-08-14T15:19:42.323537+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 5091,
   "completion_tokens": 1200,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.001912,
   "caller": ""
  },
  {
   "ts": "2026-08-14T15:20:27.760011+00:00",
   "tier": "groq",
   "model": "llama-3.3-70b-versatile",
   "prompt_tokens": 5082,
   "completion_tokens": 256,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T15:20:57.287968+00:00",
   "tier": "groq",
   "model": "llama-3.3-70b-versatile",
   "prompt_tokens": 5083,
   "completion_tokens": 274,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T16:40:48.393565+00:00",
   "tier": "flash",
   "model": "deepseek-v4-flash",
   "prompt_tokens": 98,
   "completion_tokens": 16,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 3.2e-05,
   "caller": ""
  },
  {
   "ts": "2026-08-14T17:11:56.511665+00:00",
   "tier": "nvidia",
   "model": "meta/llama-3.3-70b-instruct",
   "prompt_tokens": 42,
   "completion_tokens": 5,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T17:15:59.391788+00:00",
   "tier": "nvidia",
   "model": "meta/llama-3.3-70b-instruct",
   "prompt_tokens": 41,
   "completion_tokens": 3,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T17:19:45.007739+00:00",
   "tier": "nvidia",
   "model": "meta/llama-3.3-70b-instruct",
   "prompt_tokens": 42,
   "completion_tokens": 4,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T17:29:40.072477+00:00",
   "tier": "nvidia",
   "model": "meta/llama-3.1-8b-instruct",
   "prompt_tokens": 42,
   "completion_tokens": 5,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T17:30:04.708070+00:00",
   "tier": "nvidia",
   "model": "meta/llama-3.3-70b-instruct",
   "prompt_tokens": 42,
   "completion_tokens": 5,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T17:42:15.699781+00:00",
   "tier": "nvidia",
   "model": "meta/llama-3.3-70b-instruct",
   "prompt_tokens": 41,
   "completion_tokens": 3,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T18:12:17.728598+00:00",
   "tier": "groq",
   "model": "llama-3.3-70b-versatile",
   "prompt_tokens": 42,
   "completion_tokens": 4,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  },
  {
   "ts": "2026-08-14T19:12:30.860740+00:00",
   "tier": "nvidia",
   "model": "meta/llama-3.1-8b-instruct",
   "prompt_tokens": 42,
   "completion_tokens": 4,
   "cache_hit_tokens": 0,
   "peak": false,
   "est_cost_usd": 0.0,
   "caller": ""
  }
 ],
 "cache_tables": [],
 "cache_stats": {}
};