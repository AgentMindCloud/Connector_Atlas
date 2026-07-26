# PHASE3.md — read this first

Handoff for a fresh Claude Code chat. The container is ephemeral; this file and `docs/METHOD.md`
are the memory. `docs/PROJECT.md` is the Phase 2 brief and is now **history** — read it only for
the framing, not for the numbers.

## What this project is

**Map what every connector in the directory can actually do, then work out how all of them
combine.** The unit of work is the *directory*, not any person's account. Personal connections are
irrelevant except as a source of ground truth. Do not score by operator payback — that framing was
removed in Phase 2 and should not come back.

## Where Phase 2 got to

The Phase 2 blocker was that all 820 directory connectors inherited `emits`/`consumes` from one of
47 archetypes, so 821 connectors collapsed to **62 distinct join profiles**. That is fixed for the
57.9% of the directory where evidence was obtainable.

| | inherited | harvested | evidence |
|---|---|---|---|
| Connectors in graph | 821 | 821 | **464** |
| Distinct join profiles | 62 | **236** | 190 |
| Direct pairs, native only | 67.69% | 23.82% | **5.73%** |
| ≤2 hops, native only | 92.60% | 49.04% | **20.83%** |
| Direct ordered pairs | 484,859 | 174,801 | — |
| Connected triples (of 91,894,530) | 92.91% | 30.13% | **4.87%** |

**Two thirds of the graph was fiction.** 293 connectors consume nothing at all — every inbound edge
they had was invented by archetype inheritance.

### Three models, and when to quote which

`--model inherited|harvested|evidence` on `graph.py` and `combine.py`.

- `inherited` — the Phase 1 baseline. Only for diffing.
- `harvested` — 464 measured connectors mixed with 357 still-inherited ones. Quote it for
  *"what does the directory look like"*. Every aggregate carries an asterisk.
- `evidence` — inherited rows dropped entirely. Quote it for *"what do we actually know"*. This is
  the only model whose numbers need no caveat.

### Tiers, never blurred

| Tier | Basis | Count |
|---|---|---|
| `VERIFIED` | tool list observed live in a session | 11 |
| `HARVESTED` | real tool names from `SearchMcpRegistry` | 453 |
| `DIRECTORY` | no tool evidence; archetype inherited | 357 |

## What exists — reuse it, do not rebuild

| Path | What it does |
|---|---|
| `engine/harvest.py` | cached, resumable registry harvest. `--plan --ingest --coverage` |
| `engine/profile.py` | tool-name → profile derivation. `--derive --rules --heldout --explain NAME` |
| `engine/graph.py` | merge, validate, all-pairs, Brandes, key scarcity. `--model` aware |
| `engine/combine.py` | pairs + triples exhaustive, motif census, derived questions, model diff |
| `engine/render.py` + `template.html` | single-file tool: constellation map + 4 new lab views |
| `engine/score.py` | 9 evaluators. **Payback framing stripped from the UI; file untouched** |
| `data/harvest/raw/*.tsv` | append-only harvest cache. **Never re-harvest these 679 names** |
| `data/profiles.json` | derived profiles, all 821, tiered |
| `data/verified_tools.json` | live-observed tool lists + ground truth. The held-out test set |
| `data/systems.json` | 14 authored systems, **demoted to examples**, old scores still inside |
| `docs/METHOD.md` | §1–9 Phase 1, **§10–18 Phase 2**. The caveats live here |

`engine/discover.py` was deleted — `combine.py` supersedes it.

## Phase 3 — the work

### Step 1: schema harvesting (the actual unlock)

**`ToolSearch` returns full JSONSchema for deferred tools** — parameter names, types, required
fields, descriptions, stated limitations. Verified live in Phase 2:

- `Gmail.create_draft` has **no send parameter of any kind** → the banked constraint now holds at
  schema depth, not just name depth.
- `Calendar.search_events` has **no date parameters**, only a required `query`.

Why this matters more than it looks: `create_draft`'s parameters reveal it consumes `email`
(to/cc/bcc), `file` (attachments) and `text` (body) — **none of which the tool name contains**.
Tool names give side-effect class well and `consumes` only approximately. **Parameters give
`consumes` directly.**

**The scope limit is hard and must not be papered over.** `ToolSearch` only sees the *current
session's* connectors — roughly a dozen, not the 800+ directory. This is a depth upgrade for a
handful, not a coverage upgrade. So the right framing is:

1. Extend `data/verified_tools.json` into a schema-carrying format (params per tool, not just names).
2. Derive `consumes` from parameters for every connector the session can reach.
3. Use that as a **second, stricter held-out test** of the name-based rules that still have to
   cover the other 450. Report where names and parameters disagree — that delta prices the whole
   name-based method.

### Step 2: things Phase 2 left open

- **`score.py` / `systems.json`** — evaluators are fine, the authored systems still carry
  operator-payback scores in the file. Either rescore them on combination quality or delete the
  scores.
- **The third profile axis.** The skill (`references/capability-model.md`) models *how a connector
  runs* — on-demand / schedulable / event-emitting. The graph has no notion of this at all, and
  `trigger_action` is the one motif that genuinely depends on it. Currently approximated by
  "is it an `automation_hub`".
- **`out/*.json` are committed build artifacts.** Fine for now; if they get noisy, gitignore them
  and keep only `atlas_v5.html`.

## Numbers already established — do not re-derive

Harvest: 679 names asked · **475/820 (57.9%)** with real tool lists · 2,828 tool names · 7,194 tools
claimed · 242 records truncated by the `+N more` sentinel · 73 authless · 2 directory entries not in
our registry.

**Coverage caps at 58% and this was proven, not assumed.** Eight misses were re-queried *one name
per call*; zero returned a match, three returned empty arrays. `registry_full.json` and the live
registry have diverged. Negative control is in `data/harvest/raw/b014.tsv`. **Do not spend a budget
trying to beat 58% from this source.**

Zero coverage on three archetypes — `ai_tools`, `browser_automation`, `desktop_local`. Local
extensions; the registry cannot see them.

Derivation: held-out test **6/6**. 386 of 2,818 tool names (13.7%) contain no recognisable verb and
default to `read`. Diff: 465 connectors changed `emits`, 466 `consumes`, 278 side-effect class (81
more severe, 197 less).

Motif census, harvested model: pipeline 53,093,841 · trigger→action 2,030,181 · materialize 89,171 ·
escalate 61,582 · reconcile 49,610 · mirror 22,590. Fan-shaped motifs (enrich/digest/fan-out) run
past 10²¹⁵ unbounded and are reported capped at size 2–5. **The ordering is the finding:** patterns
needing a *writer on both ends* are 4–9 orders of magnitude rarer. Composition is limited by what
can be written into, not by what can be read.

## Findings that overturned earlier predictions — do not quietly revert them

1. **`Fireflies → Todoist` is no longer a direct edge.** Its real tools emit only `person` and
   `text`, both weak. PROJECT.md predicted this check would pass; it does not. (The other half held:
   Fireflies has **0** in-edges.)
2. **Gmail really is `irreversible`** — `delete_label` exists. The surviving claim is the narrow one:
   no send tool.
3. **`url` was never load-bearing.** Rank 1 on leverage under inheritance (1,036), rank **7** under
   evidence (48). `rows` leads on real evidence. PROJECT.md's "removing `url` destroys 24% of edges"
   is an artifact of the archetype guess and is flagged as such.
4. **Top-degree connectors were ranking on inherited profiles.** `CodeWords` topped out-degree in
   both earlier models at DIRECTORY tier. Under `evidence` it is Supabase and Todoist, both VERIFIED.

## Traps

Carried forward from Phase 2, all of which cost real time:

1. **Count rule firings; do not read regexes.** The first side-effect rule took the max over all
   verb tokens, so `get-order` and `fetch_all_orders` scored **irreversible**. Reading the table
   would never have caught it. `profile.py --rules` prints a count per verb and per noun.
2. **Derive fingerprints from canonical instances, never hand-write them.** The triple-shape table
   was written by hand, got `sorted()`'s lexicographic tuple order wrong, and silently matched zero
   triples.
3. **Match connectors on normalised name, not `id`.** `registry.json`'s curated entries overwrite
   `id`, which silently dropped 5 of 11 VERIFIED profiles from the overlay.
4. **Never suppress a diagnostic to make a check pass.** `validate()` briefly returned an empty
   archetype list under `--model evidence`, so it printed "empty archetypes: none" while three had
   in fact vanished. Report the truth; let the caller judge.
5. **Test whether a miss is your fault before blaming the source.** The one-name-per-call negative
   control is what makes the 58% ceiling a finding instead of an excuse.
6. **`SearchMcpRegistry` returns `tools:[]` for already-connected connectors** — that is a distinct
   state from "has no tools", and conflating them will silently zero out real profiles.
7. **Do not re-harvest cached data.** `harvest.py --plan` only emits names never asked.
8. **Do not promote name-derived profiles to VERIFIED.** Names are evidence, not schemas.
9. **Do not claim to have enumerated beyond triples.** Pairs and triples are exhaustive *and
   checked* (`accounted_for` == `C(821,3)`). Past that it is a motif census, and saying so is the
   more interesting answer.
10. **Do not spawn subagents unless asked.**

## Verification

```bash
python3 engine/graph.py --validate --model harvested   # 0 unknown keys, 0 empty archetypes
python3 engine/graph.py --validate --model evidence    # names the 3 evidence-free archetypes
python3 engine/harvest.py --coverage                   # 475/820, 0 never-asked
python3 engine/profile.py --heldout                    # 6/6, + the documented tldraw failure
python3 engine/profile.py --rules                      # firing counts, dead rules flagged
python3 engine/combine.py --all --model evidence       # triples must report EXHAUSTIVE
python3 engine/render.py                               # -> out/atlas_v5.html
```

Browser test: Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`, `playwright-core`
into the scratchpad. Last run: **0 console errors, no horizontal scroll at 1440px or 390px**, all
four lab views render. Keep the Residual Frequencies identity — cinnabar `#E64A2E`, jade `#35A481`,
ink `#0E0C0B`, Instrument Serif + IBM Plex Mono, single dark theme by choice, fonts stack-fallback
because the artifact CSP blocks font CDNs.

## Git

Repo `/home/user/Connector_Atlas`. Phase 2 work is on `claude/phase-2-continuation-5diogk`, pushed,
**no PR opened**. Two commits: `e76a1c0` (Phase 2) and `1a78732` (evidence model, discover.py
deletion, Phase 3 scoping). Start Phase 3 on a fresh branch from that one unless it has merged, in
which case branch from the default.

## The one-paragraph version, if the rest scrolled away

Phase 2 replaced archetype-inherited join profiles with profiles derived from real tool names
harvested out of `SearchMcpRegistry`, which needs no auth. Coverage capped at 475/820 (58%) — proven
a source limit, not an effort limit, by a one-name-per-call negative control. Read tools feed
`emits`, write tools feed `consumes`, nothing else, which deleted two thirds of the graph's edges as
fiction: direct reachability fell 67.69% → 23.82%, and 293 connectors turned out to consume nothing
at all. Three models are now computable (`inherited|harvested|evidence`); quote `evidence` for what
is known and `harvested` for what the directory looks like. Pairs and triples are exhaustive and
checked, everything larger is a motif census. Phase 3's unlock is that `ToolSearch` returns full
parameter schemas, which give `consumes` directly where names only approximate it — but only for
connectors connected in-session, so it is a depth upgrade for a dozen and a sharper held-out test
for the other 450, not a way past the 58% ceiling.
