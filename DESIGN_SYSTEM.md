# Design system - Jurassic Park dashboard (`docs/`)

Applies only to the static site in `docs/`. The agents are headless CLIs with no UI.
Each page carries its own inline `<style>`; there is no shared stylesheet or CSS framework.
Dark theme only. These pages are the newer copy of the `ken-fleet-site` repo's pages and use
the same tokens.

## Colour tokens - park pages

`docs/index.html` `:root`: `--bg #07100a`, `--bg2 #0a0a10`, `--panel #101018`,
`--panel2 #0c0c14`, `--line rgba(255,255,255,.08)`, `--line2 rgba(255,255,255,.13)`,
`--green #00e5a0`, `--violet #8b7cf6`, `--amber #ffd166`, `--red #ff6b6b`, `--grey #7d8494`,
`--txt #e8eaf0`, `--dim #9aa1b2`.

Per-page drift (as in the source): `teams.html` uses `--fg`/`--border` and swaps the panel
values; `analytics.html` uses `--fg #e8e8f0`, `--dim #8f8fa8`, `--faint #5a5a70`;
`process.html` / `runbook.html` declare only the accents plus `--border #1e1e28`.

**Species (model tier) colours** (`docs/analytics.html`): `--sp-flash #ffd166`,
`--sp-pro #bc8cff`, `--sp-frontier #ffd9a0`, `--sp-local #3fb950`, `--sp-groq #f0883e`,
`--sp-nvidia #9ecb3c`, `--sp-free #f778ba`, `--sp-openrouter #39c5cf`.

## Colour tokens - routing diagrams

`docs/fleet-routing-diagram.html` and `docs/ken-routing-diagram.html` (about 15,000 lines each,
generated) use a separate slate palette: `--bg #020617`, `--grid #1e293b`, `--text #ffffff`,
`--text-muted #94a3b8`, `--panel rgba(15,23,42,0.5)`, `--arrow #64748b`,
`--arrow-emphasis #34d399`, plus per-lane fills.

## Typography

Google Fonts on the park pages: **Unbounded** (`--disp`), **Space Grotesk** (`--body`),
**VT323** (`--mono`), **Bebas Neue** (brand wordmark).

## Components

Same class vocabulary as `docs/index.html`: `.topbar` / `.brand`, `.sec-head` / `.sec-title`,
`.panel`, `.stats-grid` / `.stat-cell`, `.tier-row` / `.tier-bar`, `.sp-legend`,
`.crew-card` / `.member-chip`, `.terminal` / `.term-*`. Charts are hand-written SVG.

## Content rules

- Park metaphor: staff = bots, species = model tiers, DNA = tokens (`README.md`).
- No em-dashes in page copy (`docs/generate_site.py` warns).
- Real data only.

## Verified against

`:root` blocks of all seven `docs/*.html` files, Google Fonts links, `docs/index.html` CSS,
`README.md`, `docs/generate_site.py`, `wc -l docs/*.html`.
