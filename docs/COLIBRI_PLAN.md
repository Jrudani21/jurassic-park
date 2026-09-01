# Colibri local-inference test plan

Status: **not installed**. Written 2026-08-19; §2 updated after the operator
supplied the project URL. Everything below is either (a) measured on this
machine, (b) quoted from the project's own pages, or (c) an explicitly-labelled
assumption still to be verified.

**Headline after checking the source:** the concept is sound and Colibri is a
real, permissively-licensed project with a Windows build and an
OpenAI-compatible server. But **DeepSeek V4 Flash is ~167 GB on disk, not
40 GB**, the constraint is **disk and RAM rather than VRAM**, and the project's
own single-GPU benchmark is **1.07 tok/s on a card stronger than this one** —
so expect to land *below* the 1.5 tok/s gate this plan sets. Ken needs no code
change to use it (§3b, tested). Proceed as a **batch-only** tier, and start
with the 4 GB OLMoE model rather than the 167 GB one.

---

## 1. Hardware — measured, not assumed

| Item | Measured value |
|---|---|
| GPU | NVIDIA GeForce RTX 4060, **8188 MiB** VRAM, driver 610.88 |
| CPU | i7-12700K, 12 cores / 20 threads |
| RAM | 34,114,617,344 bytes = **31.8 GiB** usable |
| Disk | **One** WD_BLACK SN770 2TB, MediaType SSD, BusType NVMe |
| C: | 620 GiB total, **194.8 GiB free** |
| E: | 1242 GiB total, **232.0 GiB free** |

### Correction to the original brief

The brief said "2TB NVMe = ~50GB OS + ~40GB model + **1.9TB free**".
That is not what is on the machine. The 2TB drive is a single physical disk
split into C: and E:, and it is already roughly 72% full. Actual free space is
**~427 GiB total** (195 GiB on C:, 232 GiB on E:).

This does not block a 40 GB model — it fits on E: with ~190 GiB to spare.
It does mean the "we could later grow into 744B / 2.8T models" storage
assumption is dead on this drive without a second SSD.

### Drive caveat worth knowing before benchmarking

The SN770 is a **DRAM-less** (HMB) drive. Sequential read is fine
(~5 GB/s class, PCIe 4.0 x4), but sustained *random* read of weight shards —
which is what streaming inference actually does — degrades more on DRAM-less
drives than on DRAM-cached ones once the SLC cache is exhausted. Expect the
first benchmark run (cold page cache) and the tenth run (SLC saturated) to
differ. Measure both; do not accept a single hot-run number.

Also: model weights on E: sit on the *same physical disk* as the OS on C:.
Heavy weight streaming will contend with OS paging. Watch for stutter.

---

## 2. Colibri, from the project's own pages (verified 2026-08-19)

Source supplied by the operator: <https://justvugg.github.io/colibri/> →
<https://github.com/JustVugg/colibri>. Apache 2.0, pure C, no dependencies,
~25.5k stars, native Windows 11 build documented. It exposes an
**OpenAI-compatible API**:

```
./coli web   --model <path>    # API + dashboard, opens a browser
./coli serve --model <path>    # API + dashboard, headless
```

Architecture, in their words: dense weights stay resident, experts are cached
through a **VRAM → pinned RAM → NVMe** hierarchy with prefetch. Their framing:
"A token through GLM-5.2 activates only ~40B parameters, and just ~11 GB of
those change from token to token."

### Published hardware requirements

| Model | Disk | RAM | GPU |
|---|---|---|---|
| OLMoE | ~4 GB | 8 GB | not needed |
| **DeepSeek V4 Flash** | **~167 GB** | **16 GB min, 22 GB comfortable** | not needed |
| GLM-5.2 | ~372 GB | 16 GB min, 24 GB comfortable | not needed |
| Inkling | ~469 GB | 25 GB with int4 dense; ~120 GB without | not needed |
| Kimi K3 | ~1.6 TB | 32 GB+ | not needed |

### Published throughput

| Hardware | Decode |
|---|---|
| 6× RTX 5090, full residency | 5.8–6.8 tok/s |
| 128 GB CPU-only desktop | ~1.8 tok/s warm |
| Single RTX 5070 Ti, laptop-class | **1.07 tok/s** |
| 25 GB dev box (NVMe-only) | 0.05–0.1 tok/s |

### What this does to the brief

**(a) Storage is off by 4x — 167 GB, not 40 GB.** This is the single biggest
correction. It still fits: E: has **232 GiB free**, so a 167 GB model leaves
about **65 GiB**. That is tight but workable. It is *not* workable on C:
(195 GiB free, and it is the OS drive). The "40GB storage" line in the brief
should be struck.

The earlier 1.13-bits-per-parameter objection is resolved and I was wrong to
weight it: 167 GB across 284B params is ~4.7 bits, which matches the stated
"native fp4 routed experts, fp8-e4m3 dense weights". The format is coherent;
the size in the brief simply wasn't.

**(b) The GPU is not the gate — and 8 GB VRAM was never the constraint.**
Every model lists GPU as "not needed". The brief's framing ("8GB VRAM limits
me to models under ~400GB", "GLM-5.2 needs 24GB VRAM") does not match the
project's own table: GLM-5.2 lists **16 GB RAM, no GPU required**, and is
gated by its ~372 GB disk footprint, which is what actually rules it out here
(232 GiB free). Same for Kimi K3 — ~1.6 TB of disk, not VRAM, is what stops it.
So the correct statement is **"disk-limited, not VRAM-limited."**

**(c) 2-3 tok/s is optimistic for this box.** Their own single-GPU figure is
**1.07 tok/s on an RTX 5070 Ti**, which is a materially stronger card than an
RTX 4060. The 128 GB CPU-only desktop hits ~1.8 tok/s — and RAM is exactly
where this machine is weakest at 31.8 GiB. Realistically this box lands
**somewhere between 0.1 and 1.0 tok/s**, i.e. **below the 1.5 tok/s Phase 2
gate, before installing anything**.

Caveat on that table: the pages do not say which model each row was measured
on, so these are engine-level figures, not DeepSeek-V4-Flash-specific ones.
That is precisely why Phase 2 measures rather than assumes.

**(d) Resolved — V4 Flash shipped in v1.5.0 (2026-08-05).** The two entries are
different models, as suspected. From the v1.5.0 release notes: DeepSeek V4 Flash
is "A fifth engine ... MLA + DSA sparse attention, 43 layers, 256 routed experts
plus one shared, top-6", and critically:

> "The official checkpoint streams **with no conversion**: routed experts stay
> native fp4, dense stays fp8-e4m3 with UE8M0 block scales."

So there is no Colibri-specific weight repackaging to wait for and no conversion
step — it reads DeepSeek's own published checkpoint directly. The separate
"DeepSeek 671B–1T MoE (Planned)" entry on the models page is a different family.
**Phase 0 is clear on this point.** Latest release is v1.6.2 (2026-08-14), with
Windows/Linux/macOS binaries in every release since v1.0.0.

### Four things learned from the README and v1.5.0 notes

**1. My page-cache reasoning in §6(b2) was mechanically wrong.** v1.5.0 added
"**O_DIRECT expert reads**", which deliberately *bypasses* the OS page cache.
So RAM does not help by letting the OS cache the model — Colibri manages its own
pinned-RAM tier explicitly. The conclusion is unchanged (more RAM = more resident
experts = fewer NVMe hits) but the mechanism is Colibri's cache, not the kernel's.
This also means free RAM must be genuinely *available* to Colibri, not merely
uncommitted.

**2. There is a learned cache, so first-run numbers will understate it.**
`.coli_usage` "warm pins" and an LRU with "learned pinning" automatically pin hot
experts based on workload. Throughput should therefore *improve* over repeated
similar prompts. The Phase 2 protocol must run long enough for this to warm, and
should report first-run and settled numbers separately — a single cold run will
undersell the engine, the opposite of the benchmarking error this plan was
originally worried about.

**3. Dual-SSD support makes a second NVMe doubly worth it.** From the README:
"Mirror the full model across two drives to double read bandwidth." A second
drive was already on the upgrade list for capacity (§5). It also directly buys
throughput on a disk-bound workload, which promotes it above the RAM upgrade for
this specific engine.

**4. The i7-12700K lands on the good code path.** v1.5.0 notes that before its
AVX2 backend, "on most laptops and desktops sold since 2021 every routed expert
fell back to the scalar path. **Measured: 601 s for 8 tokens**" — 0.013 tok/s.
Alder Lake has AVX2, so this box gets the fast path, and that catastrophic figure
does not apply. Worth confirming in `coli info` output anyway.

### Useful commands found

```
python3 coli info                       # verify the unpacked build
./coli plan  --model <path>             # inspect tier placement WITHOUT running
COLI_MODEL=<path> ./coli chat           # interactive TUI
./coli serve --model <path>             # OpenAI-compatible API, headless
```

`coli plan` is the best pre-flight check this project offers: it reports how the
model would be placed across VRAM/RAM/NVMe on *this* hardware, before committing
to a long run. Use it as the first thing after the model finishes downloading.

---

## 3. The finding that changes the decision

**The cost premise does not survive contact with the ledger.**

`data/cost_ledger.jsonl` over the last 30 days:

```
TOTAL            26 calls              $0.003721
by tier:
  flash            8 calls  $0.003721
  local            2 calls  $0.000000
  groq             6 calls  $0.000000
  openrouter       1 calls  $0.000000
  free             2 calls  $0.000000
  nvidia           7 calls  $0.000000
```

Logged flash spend for the month is **$0.0037** — not $50-200. Projected
monthly saving from replacing it is therefore roughly four tenths of a cent,
against $5-10/month of electricity for 24/7 inference.

Caveat, stated plainly: this ledger starts 2026-08-13 and holds 26 calls, so
it is a young sample and may not capture spend that flows through Hermes/Ken
rather than through `_shared/llm.py`. I looked for a Hermes-side usage ledger
under `~/.hermes` and `~/.ken` and found none. **Before Phase 1, pull the real
number from the DeepSeek billing dashboard.** If actual monthly spend really is
$50-200, the ROI case is live and this section is wrong. If it is single-digit
dollars, it is not.

**Second problem: the free tiers already do this job.** The router already
carries four probe-verified $0 cloud tiers — `openrouter`
(nemotron-3-ultra-550b-a55b:free), `groq` (llama-3.3-70b, fastest),
`nvidia` (NIM), `free` (Bluesminds) — plus `local` on Ollama qwen3:8b. A
550B-class free model at cloud speed already costs $0. Colibri at 2-3 tok/s
would be **slower than the $0 option it is meant to replace**.

**Third problem: latency versus the fleet's shape.** Flash-tier agents emit
roughly 500-1500 output tokens per call. At 2.5 tok/s that is **3.3 to 10
minutes of wall clock per single call**, before prefill. Twelve flash bots,
multi-step LangGraph loops, and the supervisor / escalation path in
`_shared/llm.py` all assume calls return in seconds. Wiring Colibri into the
default `flash` fallback chain would blow agent timeouts and trip the circuit
breakers in `_shared/breaker.py`.

### So what is Colibri actually for, here?

Not cost. The honest case is:

1. **Unmetered offline capacity** — no rate limits, no daily caps (Bluesminds
   is capped at 600 req/day), no dependency on four free tiers that can each
   revoke access without notice. That is real resilience value.
2. **PII / sensitivity** — ROUTING.md already says PII never leaves local, and
   local today is an 8B model. A 284B-class local model raises the ceiling on
   what can be done under that rule.
3. **Batch / overnight work** — 2-3 tok/s is fine for jobs nobody waits on:
   nightly digests, corpus labelling, bulk re-summarization of the vault.
4. **A portfolio artifact** — "I run a 284B MoE on an 8GB consumer GPU via
   NVMe weight streaming, benchmarked, with a routing tier and a fallback"
   is a strong AI-Engineer talking point on its own.

Recommendation: **build it as a `batch-local` tier, not a `Flash-Local`
replacement.** Same install, same benchmark, different position in the router —
never in the interactive fallback chain.

---

## 4. Phased plan, with kill gates

Each phase has an explicit gate. If a gate fails, stop — do not proceed on
optimism.

### Phase 0 — verification (mostly done 2026-08-19)
- [x] Colibri's canonical source confirmed: <https://github.com/JustVugg/colibri>
      (Apache 2.0, pure C, Windows 11 build documented, OpenAI-compatible server).
- [x] On-disk size confirmed from the project's own table: **~167 GB**, not 40 GB.
- [x] §2(d) resolved: V4 Flash shipped in **v1.5.0 (2026-08-05)** and streams
      DeepSeek's **official checkpoint with no conversion**. Latest is v1.6.2.
- [x] Checkpoint located and **measured via the HuggingFace API** (not estimated):

      | Repo | Shards | Size | License | Gated |
      |---|---|---|---|---|
      | `deepseek-ai/DeepSeek-V4-Flash` | 46 | **159.6 GB / 148.7 GiB** | MIT | no |
      | `deepseek-ai/DeepSeek-V4-Flash-DSpark` | 48 | **166.9 GB / 155.4 GiB** | MIT | no |

      **Colibri's "~167 GB" is the DSpark variant**, to the decimal — DSpark is
      the same checkpoint plus a speculative-decoding (MTP) module. That
      resolves where their number came from and tells us which artifact they
      sized against.

      Both are **MIT-licensed, public, and not gated** — no access request, no
      approval wait, and commercially usable, which matters for the portfolio
      angle in §3.

      **Take DSpark.** It is the variant Colibri's own requirements match, and
      the 7.3 GB premium is noise against the free space here. Note that
      Colibri's speculative drafting is currently "implemented, verified, and
      **off**" (v1.5.0 notes, low acceptance rates), so the MTP head buys
      nothing today — but it is there when they turn drafting on, and matching
      their tested artifact is worth more than saving 7 GB.

      **Revised disk maths:** E: has 232.0 GiB free. After DSpark's 155.4 GiB,
      about **76.6 GiB remains** — more comfortable than the ~65 GiB estimated
      from Colibri's decimal figure.

- [ ] Pull real 30-day DeepSeek spend from the billing dashboard.
- **Gate:** none outstanding on the engine. Still start with **OLMoE (~4 GB)**
      to validate the toolchain before a 155 GiB download.

### Phase 1 — install and smoke test (~30 min + a long download)
- [ ] **Start with OLMoE (~4 GB), not the 167 GB model.** It exercises the exact
      same build, server, and API path for 1/40th the download. Do not spend
      167 GB of disk and hours of transfer to discover the binary doesn't build.
- [ ] Build from source (`./setup.sh`, needs gcc/clang with OpenMP) or take the
      prebuilt Windows release; verify with `python3 coli info`.
- [ ] Install to **E:**, not C:. Suggested: `E:\Local\models\colibri\`.
      After DSpark lands (155.4 GiB), E: drops from 232 GiB free to **~77 GiB**.
- [ ] Fetch weights with `hf download` (resumable) rather than a browser — 46-48
      shards over a long transfer will hit at least one interruption:
      `hf download deepseek-ai/DeepSeek-V4-Flash-DSpark --local-dir E:\Local\models\deepseek-v4-flash`
      `hf.exe` is already present in the Ken venv (`.venv/Scripts/hf.exe`).
- [ ] Launch headless: `coli serve --model <path>`; record the port.
- [ ] `ollama stop qwen3:8b` first — see §6(b).
- **Gate:** one successful completion through the OpenAI-compatible endpoint on
      OLMoE. Only then download DeepSeek V4 Flash.

### Phase 2 — benchmark before integrating (~1 hr, mostly waiting)
Run `./coli plan --model <path>` FIRST — it reports tier placement on this
hardware without a full run, and will say more in ten seconds than an hour of
guessing. Then `scripts/bench_local_llm.py` (see §7) for the throughput numbers.
- [ ] `coli plan` output recorded (how much lands in VRAM / RAM / NVMe)
- [ ] `coli info` — confirm it reports the **AVX2** path, not scalar (see §2.4)
- [ ] Cold run (fresh boot)
- [ ] Warm run (immediately after)
- [ ] **Settled run — at least 20 prompts.** Colibri's `.coli_usage` learned
      cache pins hot experts over time, so throughput should *climb*. Report
      first-run and settled separately; a short benchmark undersells this engine.
- [ ] 4096-token-context run (streaming cost scales with context)
- [ ] Note GPU temp, and whether the box stays usable during inference
- **Gate:** judge on the **settled** number, not the cold one. If settled decode
      is **below 1.5 tok/s**, or the machine becomes unusable while it runs, this
      is batch-only at best — skip Phase 3 and go straight to Phase 4.

### Phase 3 — router integration (~30 min)
A `batch-local` tier was pre-added to `agents/_shared/llm.py` tonight. It is
**inert by default**: it only activates when `COLIBRI_BASE_URL` is set, and it
is deliberately **not** in any existing fallback chain, so no current agent
behavior changes.
- [ ] Set `COLIBRI_BASE_URL` and `COLIBRI_MODEL` in the repo `.env`
- [ ] Smoke it:
      `python -c "from _shared.llm import chat; print(chat('batch-local','Reply with exactly: ok',max_tokens=8))"`
- [ ] Trial **one** non-interactive agent — `06-news-summarizer` is the best
      candidate (already local tier, nobody waits on it)
- **Gate:** the trial agent completes end to end without tripping a timeout.

### Phase 3b — Ken integration (tested 2026-08-19, ready)

Ken needs **no code change**. Its `custom` provider profile
(`plugins/model-providers/custom/__init__.py`) already exists for exactly this
case — its own docstring names "OpenAI-compatible reasoning endpoints (GLM-5.2
on Volcengine ARK, vLLM, llama.cpp)". Colibri's `coli serve` is the same shape.

Verified end to end tonight that Ken really can drive a local
OpenAI-compatible endpoint, using the existing Ollama provider as the stand-in:

```
HERMES_HOME=E:\Local\ken-home ./.venv/Scripts/hermes.exe \
    chat -q "Reply with exactly: ok" -Q -m "ollama-launch/qwen3:8b"
->  session_id: 20260819_073008_c719ab
    ok
```

So the Colibri wiring is a config addition in `E:\Local\ken-home\config.yaml`,
mirroring the `ollama-launch` block already there:

```yaml
providers:
  colibri:
    api: http://127.0.0.1:<port>/v1
    default_model: deepseek-v4-flash
    name: Colibri (local, batch only)
```

Two cautions specific to Ken:

- **Do not add it to `fallback_providers`.** That list currently reads
  `deepseek` → `nvidia`. A tier that answers in minutes must never sit in a
  failover path that exists to keep interactive chat responsive.
- **Set `reasoning_config.effort: none` on this provider** if V4 Flash thinks by
  default. The custom profile already emits both `reasoning_effort="none"` and
  `extra_body.think=False` for that case. At sub-1 tok/s an unbounded thinking
  budget is the difference between a two-minute reply and a twenty-minute one.

Note while in there: the fork still ships the binary as `hermes.exe` and reads
`HERMES_HOME`, so the rebrand is still incomplete on the CLI entrypoint.

### Phase 4 — decide
- [ ] Compare Phase 2 numbers against the free tiers already wired up.
- [ ] Keep it only for the reasons in §3 (offline / PII / batch / portfolio),
      not for cost — unless Phase 0's billing number contradicts the ledger.

### Phase 5 — future, not now
Revised now that the requirements table is known. GLM-5.2 (744B) does **not**
need 24 GB of VRAM — it needs **~372 GB of disk** and 16-24 GB of RAM, with no
GPU required. So the blocker for bigger models is **storage, then RAM** — never
the GPU. Ranked by actual leverage:

1. **A second NVMe** — promoted to first after reading the README. It buys
   capacity (372 GB for GLM-5.2, 1.6 TB for Kimi K3 will not fit alongside the
   OS on this 2 TB drive) *and* throughput: "Mirror the full model across two
   drives to double read bandwidth." Two wins on a disk-bound workload.
2. **RAM to 64/128 GB** — their 128 GB CPU-only box beats their single-GPU box
   (1.8 vs 1.07 tok/s). Note this feeds Colibri's own pinned-RAM tier, not the
   OS page cache, since expert reads use O_DIRECT.
3. **Free first: enable XMP.** The installed Corsair kit
   (`CMH32GX5M2E6000C36`) is rated 6000 MT/s and is running at **4800** —
   XMP/EXPO is off in BIOS. That is ~25% of memory bandwidth left unused on a
   bandwidth-sensitive workload, for zero cost. Do this before buying anything.
4. **GPU last.** The RTX 4070 in the brief is 12 GB, and the engine lists GPU as
   not required for any model.

Buy nothing until Phase 2 produces a measured settled tok/s on the current
hardware.

---

## 5. Power note

The brief cites a 650W PSU with "safe margin for 24/7 inference". PSU wattage
is not exposed to software, so I could not verify it. A 12700K (125W base,
190W PL2) plus a 4060 (115W) plus drives sits comfortably inside 650W, so the
conclusion is very likely right — it is just not a measured claim.

Worth flagging: this workload is NVMe-heavy, continuously, for hours. Consumer
SSD endurance is rated in TBW, and streaming weights is a *read* workload, so
endurance is probably fine. But if Colibri writes cache or spill files, watch
write amplification.

---

## 6. Baseline measured tonight — the number Colibri has to beat

`scripts/bench_local_llm.py --tier local --sustained 5 --long-context`
(raw: `data/bench_baseline_ollama_qwen3-8b.json`)

```
== bench local | model=qwen3:8b | http://localhost:11434/v1 ==
  run 1:  ttft 2.947s | 256 tok in 8.323s | decode 47.62 tok/s | peak VRAM 5932 MiB
  run 5:  ttft 2.449s | 256 tok in 7.865s | decode 47.26 tok/s | peak VRAM 5932 MiB
  long:   ttft 2.541s | 228 tok in 7.969s | decode 42.00 tok/s | peak VRAM 5932 MiB
  median decode 47.26 tok/s | drift across warm runs +0.5%
```

Three things fall out of this.

**(a) The existing local tier runs at ~47 tok/s.** A 1500-token agent reply
takes ~32 seconds. If Colibri lands at the predicted 2-3 tok/s, it is
**16-24x slower than what is already installed and working**, for a model that
is admittedly far more capable. That is the actual trade being made — capability
against a 20x latency penalty — and it should be stated that way, not as a cost
saving.

**(b) VRAM contention is a Phase 1 nuisance, not the ceiling.** Colibri lists
GPU as "not needed" for every model, so the 8 GB card is not what limits this.
It still matters operationally: qwen3:8b alone holds **5932 MiB of the
8188 MiB** on the card, leaving ~2.2 GiB. Colibri's VRAM tier is the top of its
cache hierarchy, so with Ollama resident it gets almost nothing to work with
and will fall back to RAM/NVMe — which would read as "Colibri is slow" when it
is really "Colibri was given no VRAM". `ollama stop` before benchmarking.

**(b2) RAM is the real bottleneck, and it is worse than first written.**
Colibri wants **22 GB RAM "comfortable"** for DeepSeek V4 Flash, against
**31.8 GiB** on this box — so it clears the bar, but with little room for the
fleet's other processes. More importantly, RAM is the *pinned-cache* tier
sitting between VRAM and NVMe: the more of the **167 GB** of experts that stay
in RAM, the fewer tokens pay disk latency. At 31.8 GiB the box can hold under
20% of the model, so nearly every token hits NVMe.

Their own numbers make the case: a **128 GB CPU-only desktop reaches ~1.8
tok/s** — faster than their single-GPU 5070 Ti row at 1.07 tok/s. That
strongly suggests this engine scales with RAM, not with GPU.

**So the highest-leverage upgrade is RAM, not the RTX 4070 in the brief.**
64 GB (or 128 GB, since the board takes 4 DIMMs) is cheaper than the GPU
upgrade and targets the actual constraint. Do not buy either until Phase 2
produces a real number on the current config.

**(c) The long-context result is reassuring but not transferable.** qwen3:8b
holds its speed at 4k context (42 vs 47 tok/s) because the whole model is
resident. A weight-streaming engine has no such guarantee — that is exactly why
`--long-context` is in the Phase 2 checklist.

### Data point on the "284B" question

The local Ollama registry already lists `deepseek-v4-flash:cloud` with
`parameter_size: 158B`, `quantization_level: FP8` (it is a remote-hosted
pointer to `deepseek-v4-flash:preview` on ollama.com, not a local weight file).
That does not settle what Colibri serves under the same name, but **158B FP8 is
a different artifact from the 284B in the brief**, and the discrepancy is worth
resolving in Phase 0 before storage and throughput are planned around 284B.

---

## 7. Unrelated bug found while benchmarking (fixed)

The machine has a system-level `OLLAMA_BASE_URL=http://localhost:11434` — the
bare host, which is correct for Ollama's *native* API but wrong for its
OpenAI-compatible one, which lives under `/v1`. `_shared/llm.py` read that env
var directly, so in any process inheriting it **every `local`-tier call
returned `404 page not found`**.

Because `local` is the last entry in almost every fallback chain, the failure
mode was quiet: the tier that exists to guarantee "never error" was itself
erroring, and only after all the cloud tiers had already been tried.

Fixed in `agents/_shared/llm.py` by normalizing the value (`_ollama_base()`)
rather than trusting it — the bare host now gets `/v1` appended. The system env
var was left alone, since other tools may depend on the native-API form.

Verified after the fix:

```
chat('local', 'Reply with exactly: ok', max_tokens=512)  ->  ('ok /think', 'local')
```

### Related, not fixed — flagging only

The same check surfaced a second issue I did not change, because the right fix
is a judgment call. `chat('local', ..., max_tokens=16)` raises
`ALL_TIERS_FAILED (local): None`. qwen3:8b is a *thinking* model: with a small
output cap it spends the entire budget on reasoning tokens and returns empty
`content`, which `chat()` correctly treats as a tier failure — but the error
carries `last_err=None`, so it reads like a mystery outage rather than "budget
too small for a reasoning model."

It matters for Colibri because DeepSeek V4 is also a reasoning model, and at
2-3 tok/s a wasted thinking budget costs minutes, not milliseconds. Options,
for you to pick: raise the floor of `prompts.max_tokens_for()` for
thinking-capable local models; send `chat_template_kwargs={"enable_thinking":
False}` on the local tier; or at minimum make the empty-completion path report
which tier returned empty and at what cap.

---

## 7b. Install log — 2026-08-19

Phase 1 executed. Colibri v1.6.2 is installed; the model side is still in progress.

### What went in

- **Engine:** `E:\Local\colibri` — prebuilt `colibri-v1.6.2-windows-x86_64.zip`
  (2.9 MB). **SHA256 verified against the project's published `SHA256SUMS.txt`
  before unpacking** (`12d4cb059a8d…1043a1596`, matched). Built from source was
  not an option: no `gcc`, `clang`, `cl`, `make`, or `cmake` on this machine.
- **Source checkout:** `E:\Local\colibri-src` — needed because the release ships
  only `tools/k3_tokenizer.py`. The conversion tooling
  (`c/tools/convert_olmoe_merged.py`, `c/tools/convert_fp8_to_int4.py`,
  `c/tools/mirror_plan.py`) lives only in the repo.
- **Conversion venv:** `E:\Local\colibri-src\.venv-convert` (torch 2.13.0+cpu,
  safetensors 0.8.0, hub 1.28.0). Isolated deliberately — the system Python has
  torch 2.3.1, below the converter's `torch>=2.4` floor, and transformers had
  already auto-disabled it. Upgrading in place would have touched the
  interpreter all 22 fleet agents run on, for a one-off conversion.

The release contains one engine binary per family: `colibri.exe` (GLM-5.2),
`deepseek_v4.exe`, `olmoe.exe`, `inkling.exe`, `kimi_k3.exe`.

### Two corrections that would have cost debugging time

Both are now fixed in the staged Ken block in `E:\Local\ken-home\config.yaml`.

1. **The port is 8000, not 8080.** From `coli` v1.6.2: `coli serve` defaults to
   `--host 127.0.0.1 --port 8000`. The 8080 in the earlier draft was a guess and
   was wrong.
2. **The served model id is `deepseek-v4-colibri`, not `deepseek-v4-flash`.**
   `coli` derives it per architecture (`cmd_chat`: `kimi-k3-colibri`,
   `inkling-colibri`, `olmoe-colibri`, `deepseek-v4-colibri`) and passes it as
   `--model-id`. Pointing Ken at the upstream DeepSeek name would have 404'd
   against the local server.

### The conversion picture is the reverse of what §4 assumed

Phase 1 was written as "start with OLMoE because it is small". That is still
right, but for a different reason than assumed — the two models sit on opposite
sides of the conversion boundary:

| Model | Source | Conversion |
|---|---|---|
| **DeepSeek V4 Flash** | `deepseek-ai/DeepSeek-V4-Flash` (155.4 GiB) | **none** — routed experts stay native fp4, dense stays fp8-e4m3 |
| **OLMoE** | `allenai/OLMoE-1B-7B-0125-Instruct` (13.8 GB, Apache 2.0) | **required** — `c/tools/convert_olmoe_merged.py` merges gate/up/down into one tensor per expert so `olmoe.c` loads an expert in a single disk read |
| Kimi K3 | `moonshotai/Kimi-K3` | none (QAT MXFP4 streamed straight) |

So OLMoE is the cheap download but the *only* one of the two needing a
conversion step, and DeepSeek is the expensive download that runs as-is. OLMoE
remains the right smoke test — it proves engine, server, and API for 13.8 GB
instead of 155 GiB — but note the conversion exercises a code path DeepSeek will
never use, so a clean OLMoE run does not fully de-risk DeepSeek.

The converter streams and deletes one source shard at a time and is resumable,
so peak extra disk is one shard rather than the full checkpoint.

### Three corrections from `docs/deepseek-v4.md` (read after install)

**1. Use `deepseek-ai/DeepSeek-V4-Flash-0731` — NOT the DSpark variant.**
Earlier I recommended DSpark because its size matched Colibri's "~167 GB". That
reasoning was wrong. The engine docs are explicit:

> "DSpark speculative decoding is intentionally excluded and belongs in a
> separate stacked follow-up."

and give the download verbatim:

```bash
hf download deepseek-ai/DeepSeek-V4-Flash-0731 --local-dir /path/to/DeepSeek-V4-Flash
```

Verified against the HuggingFace API: `-0731` is **48 shards, 166.9 GB /
155.4 GiB, MIT, ungated** — the same size as DSpark, which is why the size match
was not the discriminator I treated it as. `--no-dspark` is documented as "a
compatibility no-op", so the DSpark weights buy nothing on this engine today.

**2. `coli mirror` does NOT reduce the download.** I speculated it might let a
model run from a partial expert set. It does not. `COLI_MODEL_MIRROR` is a
byte-identical read-only *copy on a second drive*, so expert reads split across
both spindles for bandwidth. "Partial mirror is fine" means only that a smaller
second SSD holding a subset still helps — the primary still needs the whole model.

**But a genuinely useful neighbour exists:** `COLI_MODEL_DIRS` **splits** the
model across drives — "each holding a **distinct** subset of the `.safetensors`
shards (no duplication) … combined capacity is used." That matters here: C: has
195 GiB free and E: has 232 GiB, and a split can draw on both. It also
parallelises expert loads across drives. Pairs with `PIPE=1` and `DIRECT=1`.

**3. Resident footprint is comfortable.** For a typical checkpoint — 43 layers,
hidden 4096, 256 routed experts, top-6 — the docs give dense weights at
**~6.27 GiB** plus a resident BF16 output head at **~1.06 GiB**, so roughly
**7.3 GiB resident** against 31.8 GiB of RAM. Everything above that is expert
cache, which is exactly the "more RAM = fewer NVMe hits" argument in §6(b2).
`--ram GiB` is a planner budget, not an enforced limit.

**Download integrity warning, quoted because it will bite:**

> "A download can finish with a truncated shard even when the client reports
> success. If `st.h` rejects a shard as out of bounds, compare every local shard
> size with the Hugging Face repository before treating it as an engine failure."

Over 48 shards and 155 GiB, verify sizes against the HF API before concluding
anything is wrong with Colibri.

## 7c. MEASURED — OLMoE running under Colibri, 2026-08-19

Phase 1 gate **passed**. Converted, served, and benchmarked end to end.

```
coli info  ->  OLMoE · 7B · 7.4 GB on disk · 5 shards · engine ready
run        ->  resident weights loaded in 0.6s | RSS after load: 1.79 GB
serve      ->  OpenAI-compatible API on http://127.0.0.1:8000/v1
               model id: "olmoe-colibri"
```

Throughput, non-streaming, 200 generated tokens per run, 26-token prompt:

| run | gen tok | secs | tok/s |
|---|---|---|---|
| 1 | 200 | 38.17 | 5.24 |
| 2 | 200 | 38.17 | 5.24 |
| 3 | 200 | 38.10 | 5.25 |
| 4 | 200 | 38.24 | 5.23 |
| 5 | 200 | 44.50 | 4.49 |
| 6 | 200 | 37.36 | 5.35 |

**median 5.24 tok/s** (min 4.49, max 5.35). Raw:
`data/bench_colibri_olmoe.json`.

### The GPU is not used — measured, not inferred

VRAM sampled every 2s across every run: **464–546 MiB, GPU utilization 0%**.
That is idle desktop baseline. Corroborated statically — the prebuilt Windows
binaries contain **no `LoadLibrary`** and import only `KERNEL32.dll` plus the
CRT:

```
deepseek_v4.exe / colibri.exe / olmoe.exe
  cuda symbols: 0 | vulkan: 0 | metal: 0 | openmp: 375
```

`backend_loader.c` loads GPU support at runtime via
`LoadLibraryExA("coli_cuda.dll")` — that code is **not compiled into the shipped
binaries**, and no `coli_cuda.dll` ships in the release.

Note that **`coli plan` claims otherwise**: it reports
`VRAM 5.8 GB hot tier · ~915 experts · 0:NVIDIA GeForce RTX 4060` and suggests
`COLI_CUDA_PIPE=1`. The planner is Python and describes what a CUDA build
*would* do; it does not check whether the engine binary can. **Do not trust
`coli plan`'s VRAM line on a prebuilt Windows install.**

Enabling the GPU requires building `coli_cuda.dll` via `c/build_cuda.bat`, which
needs the **CUDA Toolkit (nvcc)** and **MSVC/VS 2022 build tools** — neither is
installed. `CUDA_ARCH=sm_89` for the Ada-generation 4060.

### Streaming is broken in this build — blocks Ken integration

Reproducible on multiple prompts, HTTP 200 every time, **zero content**:

```
data: {"delta":{"role":"assistant","content":""},"finish_reason":null}
data: {"delta":{},"finish_reason":"stop"}
data: [DONE]
```

Three SSE chunks, no text. Non-streaming on the identical prompt returns the
full 77-token answer correctly. `openai_server.py` has an elaborate streaming
implementation (`start_stream`, think-splitters, tool-call marker suppression),
so this is a defect or an unfinished path in the engine's DATA-frame emission,
not a missing feature.

**Consequence for Ken:** `display.streaming: true` is set in
`E:\Local\ken-home\config.yaml`, and most OpenAI clients stream by default.
Against this build Ken would receive **empty replies**. The staged provider block
must disable streaming, or Colibri stays unusable from Ken regardless of speed.

### The number that matters is NOT transferable to DeepSeek

OLMoE is **7.4 GB on disk with RSS 1.79 GB after load** — it fits in RAM
entirely. **This benchmark never exercised the NVMe expert-streaming path**,
which is the whole mechanism DeepSeek V4 Flash depends on at 155.4 GiB. So
5.24 tok/s is a *CPU-compute ceiling* on a tiny model, not evidence about
DeepSeek. Treat it as proof the toolchain works, nothing more.

For scale: Ollama's qwen3:8b on the same box does **47.3 tok/s** (§6) — but on
the GPU, against a comparable-size model. CPU-only Colibri at 5.24 tok/s on a 7B
is roughly consistent with their published "~1.8 tok/s on a 128 GB CPU-only
desktop" figure for a *744B* model.

### Two smaller operational findings

- **`coli stop` does not stop a server it did not launch.** It reported
  "nothing running — no serve on port 8000, no SERVE engines" while the server
  was still answering requests on port 8000. It tracks its own launcher's PIDs.
  Kill the `python.exe` running `openai_server.py` directly.
- **Default context is 4096.** A ~4.8k-token prompt returns HTTP 500 with
  `context exceeds CTX (4824 + 256 > 4096)` in the server log. Raise with
  `--ctx`. The earlier long-context bench failure was this, not an engine fault.

### Still outstanding

- OLMoE conversion running; no measured tok/s yet.
- DeepSeek V4 Flash (155.4 GiB) not started — gated on the OLMoE smoke test, per
  the Phase 1 gate.
- Whether to split DeepSeek across C: and E: via `COLI_MODEL_DIRS` rather than
  putting all 155.4 GiB on E:. Splitting leaves more headroom on both drives and
  parallelises expert reads — but both partitions are on the *same physical*
  SN770, so the bandwidth half of the win does not apply here. Capacity relief is
  real; throughput relief needs a genuinely separate drive.

---

## 8. What was already built tonight

- `agents/_shared/llm.py` — added an inert `batch-local` tier (activates only
  on `COLIBRI_BASE_URL`; not in any fallback chain; no API key required).
- `scripts/bench_local_llm.py` — a provider-agnostic benchmark harness that
  measures prefill latency, decode tok/s, cold/warm/sustained behavior, and
  peak VRAM against any OpenAI-compatible endpoint. Already run against Ollama
  to capture the §6 baseline.
  - It counts `reasoning_content` chunks toward TTFT, not just `content`.
    Without that, a thinking model's entire reasoning phase lands inside the
    "prefill" window and decode tok/s reads ~10x too high (the first draft
    reported 486 tok/s for a model actually doing 42).
  - Drift is computed across warm runs only, so cold-start speed-up does not
    mask the gradual SLC-cache falloff the check exists to catch.
- `agents/_shared/llm.py` — `_ollama_base()`, the §7 fix.

The `batch-local` tier changes no existing agent unless `COLIBRI_BASE_URL` is
set. The `_ollama_base()` fix does change behavior — it repairs the local tier
in environments where it was silently 404ing.

### Phase 1 pre-flight, from the baseline

Before the first Colibri run, free the GPU:

```
ollama stop qwen3:8b
nvidia-smi --query-gpu=memory.used --format=csv
```

Expect to see VRAM drop from ~5900 MiB to a few hundred. Benchmark Colibri from
that state, otherwise a contention OOM will be misread as a Colibri failure.

---

## 9. GPU enablement and the MiMo pivot (2026-08-19)

### 9.1 Prebuilt binaries are CPU-only

The published Colibri Windows binaries ship without any GPU backend. Enabling
CUDA is a two-step build, not a flag:

1. `coli_cuda.dll` compiled with nvcc + MSVC
2. the host engine rebuilt with `CUDA_DLL=1` so `backend_loader.c` is compiled
   in at all

Step 2 is easy to miss. Without it the host has no loader code and will never
attempt to open the DLL, so a correctly built DLL sits unused next to a binary
that cannot see it.

### 9.2 Two Windows toolchain traps

Both cost real time and produce no useful diagnostics.

- **nvcc dies silently on an apostrophe in TEMP.** The Windows username here is
  `Janak's PC`, so `TEMP` contains `'`. nvcc exits 1 with zero output — no error
  text at all. Every sub-tool (cicc, cudafe++, ptxas) works when invoked
  directly, which sends you looking in the wrong place. Fix: point `TEMP`/`TMP`
  at a clean path such as `E:\nvcc_tmp`.
- **MinGW's ld.exe splits paths at the same apostrophe**, trying to resolve
  `C:/Users/Janak's` and `PC/AppData/...` as two separate directories. Fix:
  copy the MinGW tree to `C:\mingw64`.

Also: CUDA 13.3's nvcc crashes against VS 2025 (v18 / MSVC 19.51), and
`-allow-unsupported-compiler` does not help because the crash precedes any
diagnostic. VS 2022 (v17 / MSVC 19.44) works.

### 9.3 CUDA support is per-engine, not global

Verified against the Makefiles rather than assumed:

| Engine | CUDA | Evidence |
|---|---|---|
| `colibri.exe` (GLM) | yes | links `$(CUDA_OBJ)` |
| `inkling.exe` | yes | links `$(INK_CUDA_OBJ)` |
| `kimi_k3.exe` | yes | links `$(CUDA_OBJ)` |
| `olmoe.exe` | **no** | built with `NOCUDA_CFLAGS` |
| `deepseek_v4.exe` | **no** | separate Makefile, no CUDA anywhere |

This kills two plans at once. The OLMoE model already on disk can never
exercise the GPU, and DeepSeek V4 Flash — the one large model that fits the
disk budget — has no GPU path without upstream work.

The Windows GPU build was completed and verified regardless:
`colibri.exe` (1,038,427 bytes, `CUDA_DLL=1`) and `coli_cuda.dll` (602,624
bytes, sm_89) in `E:\Local\colibri\`, with the CPU-only original preserved as
`colibri.exe.cpu-only-backup`. A standalone loader test confirmed the DLL
resolves its exports and `coli_cuda_init` returns 1 against the RTX 4060.

### 9.4 Model selection under real constraints

Box: 32 GB RAM, RTX 4060 8 GB, ~225 GB free on E: at the time of the survey.

| Model | Disk | RAM | Engine | CUDA | Verdict |
|---|---|---|---|---|---|
| MiMo-V2.5 | 152 GB | ~32 GB | `peng-mimo` | yes | **chosen** |
| GLM-5.2 | 372 GB | 16-24 GB | `colibri.exe` | yes | disk short by 147 GB |
| DeepSeek V4 | 167 GB | 16-22 GB | `deepseek_v4.exe` | no | no GPU path |
| Laguna-S 2.1 | 63 GB | 128 GB+ | sabrewing fork | yes | RAM short |
| Inkling-Small | 131 GB | 187 GB | sabrewing fork | ? | RAM short |
| Inkling | 469 GB | 25 GB | `inkling.exe` | yes | disk short |
| Kimi K3 | 1.6 TB | 32 GB | `kimi_k3.exe` | yes | disk short |

MiMo-V2.5 (311B total / 15B active) is the only entry satisfying disk, RAM, and
GPU simultaneously. Weights: `fivetech/MiMo-V2.5-colibri-peng-int4`.

### 9.5 WSL2 instead of Windows

`peng-mimo` links `backend_cuda.o` directly in the Linux manner and has no
`backend_loader.c`; its CUDA ABI is 28 functions against upstream's 51, so
neither the Windows DLL nor its loader transfers. Rather than port the loader,
the build moved to WSL2 Ubuntu 26.04, where GPU passthrough works and
`make mimo CUDA=1 CUDA_ARCH=sm_89` succeeds first try — none of the §9.2
friction applies.

### 9.6 Measured results

Prompt `la capital de Francia es`, `NGEN=20`, model on `/mnt/e`.

| Config | Time (20 tok) | tok/s | expert-disk | expert-matmul | hit-rate |
|---|---|---|---|---|---|
| CPU only | 282.8s | 0.07 | 178.3s | 86.2s | 2.1% |
| + GPU | 254.6s | 0.08 | 145.0s | 88.3s | 30.7% |
| **+ PILOT=1** | **227.9s** | **0.09** | **130.1s** | **71.3s** | 30.7% |
| + CUDA_EXPERT_GB=2 | 252.9s | 0.08 | 134.6s | 89.3s | 29.0% |

Best: `COLI_CUDA=1 CUDA_DENSE=1 CUDA_ATTN=1 PILOT=1`, 24% over CPU baseline.

**The GPU gain is indirect.** GPU matmul is not faster than CPU matmul here
(88.3s vs 86.2s) — batch-1 decode GEMV is memory-bound and gives an RTX 4060
nothing to exploit. The win comes from moving 4.69 GB of dense weights into
VRAM, which frees host RAM, which lets the expert cache grow from 1 to 9
experts per layer, which lifts hit-rate from 2% to 31% and cuts disk time.
Anything that frees host RAM would produce the same effect.

`CUDA_EXPERT_GB=2` regressed: the VRAM resident set stayed at 99 tensors /
4.69 GB, so no experts were actually cached on device, and the reservation cost
host cache instead (RSS 10.25 → 9.71 GB).

### 9.7 The real bottleneck is 9p, not the GPU

Expert streaming is 57% of wall time even in the best configuration. The model
sits on `/mnt/e`, which WSL exposes over 9p, and the engine warns about this
directly — `fadvise` is ineffective there. Upstream measured **0.31 tok/s** on
the same model from ext4 using weaker hardware (Xeon 8C, 23 GB RAM), roughly 4x
what we see.

Next step is therefore storage, not compute: a dynamic VHDX on E: attached to
WSL as a bare block device, formatted ext4, with the model migrated shard by
shard so peak overhead stays near one shard rather than a second full copy.
`setup-wsl-model-disk.ps1` does the elevated half; the rest needs no elevation.

Secondary: WSL is capped at 15 GB of the host's 32 GB. Raising it grows the
expert cache directly, but `wsl --shutdown` would kill the running
`hermes-*` and `n8n` containers, so it waits for an idle Docker window.

### 9.8 Viability

At 0.09 tok/s — and even at a projected 0.31 tok/s on ext4 — this is batch-only.
It is not viable for any interactive Ken tier, and the staged Colibri provider
block in `ken-home/config.yaml` should stay commented out until the ext4 number
is actually measured.

---

## 10. ext4 migration — the 9p hypothesis confirmed (2026-08-20)

### 10.1 Result

A dynamic VHDX on E:, attached to WSL as a bare block device and formatted ext4,
replaced the 9p-mounted `/mnt/e` path. Same hardware, same engine, same flags,
same prompt — only the filesystem changed.

| | 9p (`/mnt/e`) | ext4 (VHDX) | Δ |
|---|---|---|---|
| Throughput | 0.09 tok/s | **0.16 tok/s** | +78% |
| Wall (20 tok) | 227.9s | 123.0s | −105s |
| expert-disk | 130.1s | **17.8s** | −86% |
| expert-matmul | 71.3s | 72.4s | ~0 |
| attention | 13.7s | 19.8s | +6.1s |
| hit-rate | 30.7% | 30.7% | 0 |

Hit-rate is identical, which is what makes this clean: the cache behaved the
same, so the disk-time collapse is attributable to the filesystem alone and not
to a luckier expert distribution.

Cumulative: **0.07 → 0.16 tok/s, 2.3x**, across CPU → GPU → PILOT → ext4.

### 10.2 The bottleneck has moved

Expert streaming was 57% of wall time on 9p; it is 14% on ext4. Matmul is now
59% and dominant. Any further gain has to come from making decode matmul
faster, which the GPU currently does not do — batch-1 GEMV is memory-bound and
the RTX 4060 measures no better than the CPU at it (§9.6). Storage tuning is
finished; the remaining levers are RAM (expert cache size) and batching.

Still roughly half of upstream's 0.31 tok/s. Two plausible causes, neither
investigated: a faster NVMe on their side, and WSL here being capped at 15 GB
of the host's 32 GB, which pins the expert cache at 9/layer.

### 10.3 Operational cost, and a mistake worth not repeating

**A `wsl --mount` attachment does not survive the WSL VM stopping**, and WSL
stops the VM on an idle timeout. The disk must be re-attached, with
administrator rights, after every WSL restart or reboot. An `/etc/fstab` entry
(`LABEL=wslmodels /models ext4 defaults,nofail 0 0`) handles the *mount* once
the disk is attached, but cannot attach it.

The mistake: the disk was mounted in one `wsl` invocation and the migration
launched in a separate one. The distro terminated in between, silently dropping
the mount, so `/models` was an ordinary directory on the root filesystem and
~117 GB was written into the root VHDX — which is backed by C:. C: fell from
173.7 GB to 26 GB free.

What prevents it: mount and work in the *same* process, verify with
`mountpoint -q` rather than trusting an earlier command, and refuse to run if
the check fails. All three are in `finish-migration.sh` and
`relocate-to-ext4.sh`.

No data was lost — every copy step verified size before releasing its source,
and that check held throughout the recovery.

### 10.4 Reclaiming a grown WSL VHDX

Freeing space inside the Linux filesystem does not shrink the VHDX; it stays at
its high-water mark. `fstrim` reported trimming 994 GiB and the file did not
move, because sparse mode is disabled and WSL only enables it behind
`--allow-unsafe` (its own warning: potential data corruption). Not worth it.

The safe route is an offline compact, which needs the VHDX closed — meaning
`wsl --shutdown`, which stops every distro and therefore every container:

```
wsl --shutdown
Mount-VHD -Path <ext4.vhdx> -ReadOnly -NoDriveLetter
Optimize-VHD -Path <ext4.vhdx> -Mode Full
Dismount-VHD -Path <ext4.vhdx>
```

Result here: 144.2 GB → 13.4 GB, **130.8 GB reclaimed**, C: back to 156.8 GB.
`fix-c-drive.ps1` does this end to end, with a diskpart fallback for hosts
without the Hyper-V role, and re-attaches the model disk afterwards.

Container note: Ken's `hermes-*` sandboxes are ephemeral `sleep infinity`
holders on `ken-terminal:latest`. Some are removed outright when stopped rather
than left in an exited state, so "restart the containers you stopped" is not
reliable advice — check `docker ps -a` for what actually survived. All their
state is in `E:\Local\ken-home\*` bind mounts and is unaffected either way.

### 10.5 Viability, revised

0.16 tok/s is 2.3x the starting point but still batch-only. A 500-token reply
takes ~52 minutes. Nothing here changes the §9.8 conclusion: not viable for an
interactive Ken tier, and the Colibri provider block in `ken-home/config.yaml`
stays commented out. It is a credible option for genuinely asynchronous batch
work — overnight summarisation, bulk classification — where a frontier-class
311B model at zero marginal cost beats a fast small model.

---

## 11. Scheduled automation (2026-08-20)

At 0.16 tok/s this tier is only useful when nobody is waiting on it. The first
design gated it on user presence; that turned out to be unworkable here, and the
replacement gates on a clock plus GPU contention instead.

### 11.1 Presence detection does not work on this machine

Three signals were tried and measured:

- **Task Scheduler "On Idle"** — needs sustained sub-10% CPU. The fleet (hermes
  sandboxes, n8n, cron) prevents that indefinitely.
- **`GetLastInputInfo`** — reported 2144s idle *while the user was actively
  working*. This host is headless, normally locked (LogonUI resident), and driven
  remotely through agents: keystrokes land on a client device and only API calls
  reach here. Local input idle reads "idle" permanently.
- **`query user`** — agreed, showing session 2 idle 36 minutes at the same moment.

Consequence had this shipped: the engine would have started and never stopped,
holding 4.7 GB of VRAM around the clock. It was in fact observed doing so.

### 11.2 What replaced it

A fixed window, which needs no detection to be correct, plus a yield check so the
batch tier gets out of the way of the latency-sensitive one.

| Task | Trigger | Does |
|---|---|---|
| `ColibriAttachDisk` | At logon, elevated | `wsl --mount --vhd E:\wsl-models.vhdx --bare` |
| `ColibriIdleRunner` | At logon, elevated | Runs the watcher indefinitely |

Window **01:00-08:00**. Yield is by asking Ollama's `/api/ps` whether it holds a
model; if so the engine drains (SIGTERM, up to 5 min for an in-flight
generation) and backs off 15 minutes. Server binds loopback only.

### 11.3 Why the yield asks Ollama rather than the GPU

Two more direct-looking signals were measured and rejected:

- **Per-process VRAM** — `nvidia-smi --query-compute-apps=used_memory` returns
  `[N/A]` for every process under WDDM, and the engine runs inside WSL so it
  never appears in that list regardless.
- **Free-VRAM headroom** — with the engine resident plus the desktop, free VRAM
  on this 8 GB card measures **127-449 MB**. There is no headroom in which to
  observe a newcomer, so any drop-below-baseline test can never fire.

Ollama's own API is unambiguous, cheap, and names the competing model. A
non-responding Ollama counts as no contention rather than a reason to stay off.

### 11.4 Four silent bugs, all caught by testing rather than review

Every one of these fails quietly, and three of them fail in the direction of
"looks healthy, does nothing".

1. **`&` backgrounding inside `wsl.exe` does not survive.** Exit 0, no process,
   log file never created — WSL reaps the child when the last client exits.
   Needs `setsid --fork ... < /dev/null`.
2. **`pgrep -f openai_server.py` matches its own `bash -c` command line**, so the
   liveness check always said "alive" and the drain loop would have run its full
   window every time. Bracket it: `pgrep -f '[o]penai_server'`.
3. **Free-VRAM yield could never fire** (§11.3) — the arithmetic
   `now < (449 - 1500)` is unsatisfiable.
4. **`return ,@($bool, $text)` inverted the yield.** The extra wrapping made
   `$c[0]` the inner array rather than the boolean, and a two-element array is
   always truthy — so the *not*-contended case read as contended and the engine
   would never have started. Returns a `[pscustomobject]` now.

### 11.5 Verified

- Window logic correct at boundary hours and across a midnight wrap (22->6).
- Outside the window: watcher runs, engine stays down.
- Inside the window: engine starts, ready in 20-40s warm (~180s cold).
- Window close: drained cleanly in 5s.
- Contention: `True` + model name with `deepseek-r1-16k:7b` loaded, `False` after
  `ollama stop`, truthiness correct in both directions.
- Chat completion from Windows returned correctly through the API.

To use it from the fleet, set `COLIBRI_BASE_URL=http://localhost:8080/v1` — that
activates the existing inert `batch-local` tier in `agents/_shared/llm.py`, which
never falls back to a paid tier. Leave it unset for anything latency-sensitive.

---

## 12. MTP speculative decoding — a win at DRAFT=1, a disaster at DRAFT=2 (2026-08-21)

### 12.1 The lead

Every benchmark logged `[MTP] assente (fallback n-gram)` and
`speculazione: 1.05 token/forward`, i.e. speculation was doing nothing. The
engine's own comment sets out the prize:

> With the native MTP head in the container, draft comes from that head (37-64%
> acceptance on the real model); without it, n-gram lookup (~5%). LOSSLESS:
> verified output is byte-identical to pure greedy.

The `fivetech` container ships without the head. Crucially the head is **not**
part of the 316 GB checkpoint: MiMo-V2.5 keeps it in its own
`model_mtp.safetensors` shard, **1.19 GB**, and the converter has a `--mtp` mode
that takes only `model.mtp.layers.0.*`.

```
python3 tools/convert_fp8_to_int4.py --arch mimo \
    --repo XiaomiMiMo/MiMo-V2.5 --mtp --outdir /models/mimo-v2.5
```

1.19 GB downloaded in 36s, producing `out-mtp-00000.safetensors`, 330 MB,
18 tensors, dropped into the existing container with no re-download.

Note the converter's built-in default repo (`XiaomiMiMo/MiMo-V2.5-FP8`) 401s.
The live repo is `XiaomiMiMo/MiMo-V2.5`.

### 12.2 Draft depth is sharply non-linear

| | DRAFT=0 | **DRAFT=1** | DRAFT=2 |
|---|---|---|---|
| Throughput | 0.16 tok/s | **0.19 tok/s** | 0.04 tok/s |
| Wall (20 tok) | 123.0s | **105.8s** | 470.4s |
| Forward passes | 19 | 11 | 10 |
| token/forward | 1.05 | 1.82 | 2.00 |
| MTP acceptance | n/a (n-gram) | **72.7%** | 50.0% |
| expert-matmul | 71.3s | **65.7s** | 314.3s |
| expert-disk | 17.8s | **11.3s** | 45.6s |

One draft position pays for itself and then some: **+19% throughput**, lossless
(output byte-identical to greedy), with matmul *falling* slightly rather than
rising. Two draft positions cost 4.4x the matmul and lose 3.8x overall.

Acceptance was also higher at depth 1 (72.7%, above the documented 37-64% band)
than at depth 2 (50.0%) — the second speculated position is both individually
less likely to be accepted and much more expensive to produce.

### 12.3 The reasoning that nearly discarded this

The hypothesis motivating the experiment was: the source disables DRAFT because
"on disk-bound hosts each draft position pays its own experts from disk", and
§10 moved this host off disk-bound, so the warning no longer applies.

That was wrong about the mechanism. Each draft position pays for its own expert
**matmuls**, not merely its own disk reads, so being compute-bound is not the
condition that makes DRAFT safe. DRAFT=2 demonstrates this directly.

But the conclusion drawn from DRAFT=2 alone — "MTP is not worth enabling" — was
also wrong, and would have thrown away a free 19%. The cost is per draft
position and the benefit saturates fast, so the useful setting sits at depth 1,
between "no speculation" and "too much". Testing a single depth and generalising
from it is what produced both errors.

### 12.4 Disposition

**Enable `DRAFT=1`.** Lossless, +19%, and it lowers both matmul and disk time.
The head costs 330 MB and is inert at DRAFT=0, so nothing is lost by keeping it
even if a future host prefers it off.

Do **not** use DRAFT=2 on this class of hardware. It becomes plausible only
where the GPU genuinely accelerates expert matmul, which an RTX 4060 running
batch-1 GEMV does not (§9.6).

Nightly ceiling rises from ~4,000 to ~4,800 tokens. That does not change any
downstream conclusion — distillation from this model still measures in months
against cents for an API teacher (§13) — but it is free throughput on work that
does run here.

---

## 13. Can Colibri and the fine-tuning project combine? No (2026-08-21)

The obvious pairing is distillation: use the free 311B model overnight to
generate training data for a small fast local model. `soup distill-prompt`
exists for exactly this shape of work. The arithmetic kills it.

At 0.16 tok/s over a 7-hour window the ceiling is **4,032 tokens/night**
(4,800 with DRAFT=1, §12).

| Producing 1000 examples x 300 tok | Time | Cost |
|---|---|---|
| MiMo as teacher | **74 nights** | free |
| MiMo + DRAFT=1 | ~62 nights | free |
| DeepSeek API | minutes | **$0.13** |

A teacher that needs two months to produce what an API produces for thirteen
cents is not a teacher. The student half was independently ruled out too:
`soup advise` scored RAG 0.600 against SFT 0.338 on the 240-pair stats dataset,
classifying the task as factual lookup — the shape SFT is worst at.

Two parked projects, and combining them rescues neither.

### 13.1 What did come out of the investigation

`soup advise run <data> --goal "..." --probe` is worth keeping in the toolkit.
It ranks PROMPT_ENG / RAG / SFT / DPO / GRPO against real data and returns a
verdict with an ROI table and an explicit "flip when" condition, in under a
minute. Running it before a training job is much cheaper than running the job.

`soup distill-prompt --traces --teacher --student --provider ollama|anthropic`
targets a genuinely different problem from the one above: compressing
prompt-heavy *agent traces* into a fine-tuned small model. That suits the fleet
— 22 agents, long system prompts, repetitive lanes — with the existing API tier
as teacher and a small Ollama model as student. It needs no Colibri involvement,
and it fits the one durable lesson from the advise verdict: SFT is wrong for
factual lookup but right for behavioural imitation. Not investigated further;
would need per-agent token spend measured first.

### 13.2 Where Colibri actually stands

One niche survives: **work that cannot leave the machine.** A frontier-class
311B locally at zero marginal cost justifies the whole build the day something
must be processed without sending it to an API. For everything else the API
wins on latency, cost, and effort simultaneously.
