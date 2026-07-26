# Connector Atlas

A composition engine over the full Claude connector directory — **821 connectors, 47 archetypes** —
that works out what each connector can actually do and how all of them combine.

Everything is generated from `data/`. Edges are **derived, never drawn**: an edge exists when a key
one connector emits is a key another consumes, so the picture cannot drift from the evidence.

**Read [`docs/METHOD.md`](docs/METHOD.md) before quoting any number.** It records how each figure
was produced, which of them carry an asterisk, and every earlier claim that measurement overturned.
Start at [`docs/PHASE3.md`](docs/PHASE3.md) if you are picking the project up cold.

---

## What the evidence is, and how good it is

Nothing here is asserted. Each connector sits in one of four tiers, and the tier travels with every
number derived from it.

| Tier | Basis | Count |
|---|---|---|
| `SCHEMA` | full parameter schemas read live from `ToolSearch` | 11 |
| `VERIFIED` | tool list observed live in a session, names only | 11 |
| `HARVESTED` | real tool names from `SearchMcpRegistry` | 453 |
| `DIRECTORY` | no tool evidence at all; archetype inherited | 357 |

`SCHEMA` and `VERIFIED` are the same 11 connectors at two evidence depths. Three graph models are
computable — `--model inherited|harvested|evidence`. Quote **`harvested`** for "what does the
directory look like" and **`evidence`** for "what do we actually know"; `evidence` drops every
inherited row rather than downgrading it.

## The deliverable

```bash
python3 engine/render.py        # -> out/atlas_v5.html  (single self-contained file)
```

One page:

- **The map** — 47 archetype constellations on a rotating sphere, each connector a node, edges
  coloured by join key. Search, zoom, click any node for its profile and tier.
- **The pathfinder** — join any two of the 821 in direct or bridge mode, with the price of each
  bridge hop stated.
- **The lab**, five views — pair explorer, connector profile, motif census, model diff, and
  **schema evidence**: the audit of the name-derived graph against real parameter schemas.
- **The examples** — 14 authored systems, kept as worked compositions rather than recommendations.

## Toolkit

```bash
python3 engine/harvest.py --coverage           # registry tool-name harvest, cached and resumable
python3 engine/profile.py --derive --rules     # tool names   -> join profiles, with firing counts
python3 engine/schema.py  --derive --delta     # parameters   -> join profiles, and what names cost
python3 engine/graph.py   --validate --model evidence
python3 engine/combine.py --all --model evidence
python3 engine/score.py                        # ROBUSTNESS + CAPABILITY over data/systems.json
python3 engine/render.py                       # build the tool
```

Stdlib only. No dependencies, no build step.

## Layout

```
data/registry_full.json     entire directory (820) + 47 archetypes
data/registry.json          curated overrides
data/harvest/raw/*.tsv      append-only tool-NAME cache (679 names asked)
data/schemas/raw/*.jsonl    append-only parameter-SCHEMA cache (178 tools)
data/profiles.json          name-derived profiles, all 821, tiered
data/schema_profiles.json   parameter-derived profiles, 11, + selectors + preconditions
data/verified_tools.json    live tool lists, ground truth, and a correction log
data/systems.json           14 authored systems, demoted to examples
engine/profile.py           tool names -> profiles       (counted rules, held-out test)
engine/schema.py            parameters -> profiles       (counted rules, second held-out test)
engine/graph.py             merge, validate, all-pairs, centrality, key scarcity
engine/combine.py           exhaustive pairs + triples, motif census, model diff
engine/score.py             ROBUSTNESS + CAPABILITY; no operator economics
engine/render.py            builds the single-file tool
engine/template.html        the page (data injected at __DATA__)
docs/METHOD.md              method and caveats — §1–9 Phase 1, §10–18 Phase 2, §19–25 Phase 3
docs/PHASE3.md              handoff: state, traps, and what Phase 4 should do
```

## Four results worth knowing

**Two thirds of the original graph was fiction.** Replacing archetype-inherited profiles with ones
derived from real tool names dropped direct reachability from 67.69% to 23.82%, and revealed that
**293 connectors consume nothing at all** — every inbound edge they had was invented by inheritance.

**Tool names are 84% precise and 38% complete.** Measured against real parameter schemas on the 11
connectors where both exist: of 59 (connector, key) claims, names got 21 right, invented 4, and
missed 34. The name-based graph errs overwhelmingly by *omission*. That is the price of the method
still carrying the other 453 connectors, and it is stated rather than estimated.

**Composition is limited by what can be written into, not by what can be read.** In the motif
census, patterns needing a writer on both ends are 4–9 orders of magnitude rarer than fan-shaped
ones. Automation is limited one step further, by what can be *noticed changing*: nothing in MCP is
event-emitting, and self-fired trigger→action chains are **0.26%** of hub-fired ones.

**Pairs and triples are exhaustive and checked** — 91,894,530 triples, `accounted_for` equals
`C(821,3)`. Everything past that is a motif census, and saying so is the more interesting answer
than pretending to have enumerated a space that passes 10²⁰ by size 10.

## Claims that measurement overturned

Kept visible on purpose, because the corrections are the most useful output.

- **`url` was never load-bearing.** It ranked #1 on leverage under archetype inheritance and **#7**
  under real evidence. The old README's "removing `url` destroys a quarter of the graph" was an
  artifact of the guess.
- **Canva's recorded ground truth was wrong.** `data/verified_tools.json` said "no delete";
  the schemas show `delete_element`, `delete_pages` and "IRREVERSIBLE". A held-out set with a wrong
  answer in it silently rewards the wrong derivation, so the correction is logged in the file.
- **Gmail really is `irreversible`** (`delete_label` exists). The claim that survives is the narrow
  one: **no send tool**, now confirmed at schema depth — `create_draft` has no send parameter.
- **Google Calendar cannot trigger anything.** `search_events` takes no date parameter at any
  depth, so "when a meeting is booked, do X" is not buildable from the calendar at any polling
  frequency.
- **The operator-payback lens is gone.** Systems were once ranked by hours reclaimed against an
  assumed hourly rate. A number that changes when you change your salary is not a fact about a
  composition; `ROBUSTNESS` replaced it and scores nothing on rates or reclaimed hours.

## The two hard ceilings

Neither is an effort limit, and neither beats the other — they are different axes.

- **58%** — `SearchMcpRegistry` returns tool names for 475 of 820 connectors. Proven a *source*
  limit by a one-name-per-call negative control: eight misses re-queried individually returned zero
  matches. Do not spend a budget trying to beat it from that source.
- **1.3%** — `ToolSearch` returns parameter schemas only for connectors the current session is
  *connected to*: 11 of 820. Connecting 800 accounts is not something a session can do. Schemas are
  a depth upgrade for eleven and a sharper test for the rest, never coverage.
