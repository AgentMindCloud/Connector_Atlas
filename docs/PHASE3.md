# PHASE3.md — read this first

Handoff for a fresh Claude Code chat. The container is ephemeral; this file and `docs/METHOD.md`
are the memory. **Phase 3 is complete.** `docs/PROJECT.md` is the Phase 2 brief and is history.

## What this project is

**Map what every connector in the directory can actually do, then work out how all of them
combine.** The unit of work is the *directory*, not any person's account. Personal connections are
irrelevant except as a source of ground truth. Do not score by operator payback — that framing was
removed from the UI in Phase 2 and from `score.py` in Phase 3, and should not come back.

## Where Phase 3 got to

Phase 2 replaced archetype-inherited join profiles with profiles derived from real tool **names**.
Phase 3 read real tool **parameter schemas** for the 11 connectors a session can reach, and used
them to price the name-based method carrying the other 453.

**The headline: names are 84% precise and 38% complete.** When a tool name claims a join key it is
usually right; it simply cannot see most of what a connector actually accepts. The name-based graph
errs by omission, not invention.

| | count |
|---|---|
| Tool schemas read | 178 (of 180 known tools, 11 connectors) |
| Parameters | 481 top-level, 680 readings incl. nested |
| (connector, key) claims compared | 59 |
| both agree / names invented / names missed | 21 / **4** / **34** |
| precision · recall · F1 | **0.840 · 0.382 · 0.525** |
| side-effect class agreement | 8 of 11 |
| mandatory tool preconditions found | 15 across 4 connectors |

Phase 2's numbers are unchanged and still quotable — see §10–18 of METHOD.md. Nothing in Phase 3
moved the graph's edges; it measured how wrong they are.

### Four tiers now, never blurred

| Tier | Basis | Count |
|---|---|---|
| `SCHEMA` | full parameter schemas read live | **11** |
| `VERIFIED` | tool list observed live, names only | 11 |
| `HARVESTED` | real tool names from `SearchMcpRegistry` | 453 |
| `DIRECTORY` | no tool evidence; archetype inherited | 357 |

`SCHEMA` and `VERIFIED` are the same 11 connectors at two different evidence depths.
`data/schema_profiles.json` is the schema layer; it does **not** overwrite `data/profiles.json`.

### Three models, unchanged

`--model inherited|harvested|evidence` on `graph.py` and `combine.py`. Quote `harvested` for
"what does the directory look like", `evidence` for "what do we actually know". `evidence` is
still name-grade for 453 of its 464 members.

## What exists — reuse it, do not rebuild

| Path | What it does |
|---|---|
| `engine/harvest.py` | cached registry harvest. `--plan --ingest --coverage` |
| `engine/profile.py` | tool-name → profile. `--derive --rules --heldout --explain` |
| **`engine/schema.py`** | **parameter-schema → profile. `--ingest --derive --rules --delta --coverage --explain`** |
| `engine/graph.py` | merge, validate, all-pairs, Brandes, key scarcity. `--model` aware |
| `engine/combine.py` | pairs + triples exhaustive, motif census, model diff |
| `engine/render.py` + `template.html` | single-file tool: map + **5** lab views |
| `engine/score.py` | ROBUSTNESS + CAPABILITY. **Payback lens deleted, not rescaled** |
| `data/harvest/raw/*.tsv` | append-only name cache. **Never re-harvest these 679 names** |
| **`data/schemas/raw/*.jsonl`** | **append-only schema cache, 178 tools. Never re-read these** |
| `data/profiles.json` | name-derived profiles, all 821, tiered, now carrying `runtime` |
| **`data/schema_profiles.json`** | **parameter-derived profiles, 11, + selectors + preconditions** |
| `data/verified_tools.json` | live tool lists + ground truth. Carries a `correction_log` |
| `data/systems.json` | 14 authored systems, examples only, ROI fields deleted |
| `docs/METHOD.md` | §1–9 Phase 1, §10–18 Phase 2, **§19–25 Phase 3** |

## Findings that overturned earlier claims — do not quietly revert them

Carried forward from Phase 2, plus Phase 3's own:

1. **`Fireflies → Todoist` is not a direct edge** (Phase 2). Fireflies has 0 in-edges.
2. **Gmail really is `irreversible`** (`delete_label`). The surviving claim is narrow: no send tool.
3. **`url` was never load-bearing.** Rank 1 under inheritance, rank 7 under evidence.
4. **Top-degree connectors were ranking on inherited profiles.** Under `evidence`: Supabase, Todoist.
5. **NEW — Canva's ground truth was wrong.** `data/verified_tools.json` said "no delete". The
   schemas show `delete_element`, `delete_pages` and "IRREVERSIBLE". Corrected in the file, with a
   `correction_log` entry. A held-out set with a wrong answer in it silently rewards the wrong
   derivation.
6. **NEW — tldraw's documented failure is resolved one level down.** Phase 2 said "name-based
   inference has a floor, and this is it". True, and parameters are underneath it: `exec` has a
   required `code` string. `profile.py --heldout` still fails this case *and should* — it tests
   names.
7. **NEW — nothing in MCP is event-emitting.** No subscribe, webhook or callback parameter exists
   in any of the 178 tools. The skill's third capability state is empty by measurement.
8. **NEW — self-fired triggers are 0.26% of hub-fired ones** (5,306 vs 2,030,181, harvested).
   Almost nothing can notice its own change, so unattended patterns need a hub purely to fire.
9. **NEW — Google Calendar cannot trigger anything.** `search_events` takes no date parameter at
   any depth, so "when a meeting is booked, do X" is not buildable from the calendar at any
   polling frequency.

## Traps

Phase 2's ten still apply in full. Phase 3 added five, all of which cost real time:

11. **Do not derive a schema-grade axis from names.** The runtime axis first matched name tokens
    and scored Google Calendar the *most* pollable connector in the directory, on the strength of
    `search_events` containing `events` — the domain noun, not a change log.
12. **Prose is not evidence of side effects.** Scanning descriptions for verbs pushed Google Drive
    to `mutate`, because descriptions cross-reference other tools by name. Only a seven-word
    irreversibility list is read from prose now.
13. **Ablate before keeping a rule.** The type-string verb scan fired 30 times, changed **zero**
    connector classes, and was 3-right/2-wrong at tool level. Measuring that is what turned it from
    "keep or delete" into "restrict to action-selecting parameters", which is right on all five.
14. **Match parameters as phrases before tokens.** `user_intent` fires 30 times and its `user`
    token was being read as `person`, giving Canva a person sink that does not exist.
15. **"Unmeasurable" is not "failed".** The trigger check first reported three mesh systems as
    making false trigger claims when they simply have no named connectors to check against. Report
    missing evidence as missing.

Both nested-type parser bugs — the delimiter-free bracket match and the greedy `[...]` strip that
ate every `oneOf[...]` — were found by **reading the dead-rule list, not the code**. `--rules` now
shows 0 dead entries in both dictionaries and 1 unmapped parameter of 680.

## Numbers already established — do not re-derive

Phase 2: 679 names asked · **475/820 (57.9%)** with real tool lists · 2,828 tool names · 242
truncated · 73 authless. **The 58% ceiling is a source limit, proven by a one-name-per-call
negative control.** Zero coverage on `ai_tools`, `browser_automation`, `desktop_local`.

Phase 3: **178 schemas · 11/820 (1.3%)**. This is a *session* limit, not a source limit, and it is
a different axis from the 58%. Neither beats the other. Two Cloudflare tools present in Phase 2
(`accounts_list`, `set_active_account`) are absent from this session's deferred list — session drift,
recorded, and it is why Cloudflare's `company` key scores as "invented".

Motif census, harvested: pipeline 53,093,841 · trigger→action 2,035,487 (hub 2,030,181 / self
5,306) · materialize 89,171 · escalate 61,582 · reconcile 49,610 · mirror 22,590.

## Phase 4 — what is actually left

Ordered by value, and each is a real gap rather than polish:

1. **`emits` is still name-grade everywhere, including the 11.** MCP has no output schema, so this
   cannot be fixed the way `consumes` was. It would need response-shape observation from actual
   tool calls, which is a different and more invasive method. Every emits-derived figure — key
   scarcity, out-degree, donor rankings — currently rests on names.
2. **Preconditions are recorded but not enforced.** `graph.py` will route through `buy_domain`
   without noting `get_purchase_quote` must precede it. The data is in `data/schema_profiles.json`;
   the pathfinder does not read it.
3. **`selectors` are not edges.** An edge exists iff `emits(A) ∩ consumes(B)` is non-empty, with no
   check that B can be *addressed* with what A holds. Calendar being addressable only by free text
   is reported, not modelled.
4. **The 11 are not a random sample** — they are whatever this account connected, skewed to
   developer tools. The 84%/38% figures generalise only that far. A differently-connected session
   would be the cheapest way to test it.
5. **`out/*.json` are committed build artifacts.** Fine so far; gitignore them if they get noisy.

### Phase 4 candidate, requested but explicitly deferred

**`github.com/AgentMindCloud/abm-research`** — a multi-AI project of Jani's. The ask is to point this
composition model at it and see whether it helps design a superior system: which connectors that
project actually needs, where the join keys are, which patterns are instantiable, and what the
`trigger_action` and precondition results say about automating it.

**Not yet.** Jani has basic decisions to make on that project first, and pointing an atlas at a
design that is still moving would produce confident answers to the wrong questions. Recorded here
because the container is ephemeral and this file is the memory. Wait to be asked.

Note when it happens: that repo is not in this session's GitHub scope, so it needs `add_repo` first.

## The output, and how it is delivered

`python3 engine/render.py` writes **two** files from one template:

| file | shape | for |
|---|---|---|
| `out/atlas_v5.html` | complete standalone document | downloading, opening from disk |
| `out/atlas_artifact.html` | body fragment, no doctype | Artifact publishing, which adds its own skeleton |

`engine/template.html` is a **fragment** and always has been — it opens on `<title>`. Do not add a
doctype to it; `render.py`'s `document()` wrapper supplies one for the standalone build, and adding
a second would double-wrap the Artifact. Run `node engine/browsertest.js` after any change to
either.

## Verification

```bash
python3 engine/graph.py   --validate --model harvested   # 0 unknown keys, 0 empty archetypes
python3 engine/graph.py   --validate --model evidence    # names the 3 evidence-free archetypes
python3 engine/harvest.py --coverage                     # 475/820, 0 never-asked
python3 engine/profile.py --heldout                      # 6/6 + the tldraw case, now cross-referenced
python3 engine/profile.py --rules                        # firing counts, dead rules flagged
python3 engine/schema.py  --coverage                     # 178/180, 11/820
python3 engine/schema.py  --rules                        # 0 dead rules, 1 unmapped param of 680
python3 engine/schema.py  --delta                        # the second held-out test
python3 engine/score.py                                  # ROBUSTNESS/CAPABILITY, trigger check
python3 engine/combine.py --all --model evidence         # triples must report EXHAUSTIVE
python3 engine/render.py                                 # -> out/atlas_v5.html + atlas_artifact.html
node engine/browsertest.js                               # doctype/charset/viewport + all 5 views
```

Browser test is now **in the repo**: `node engine/browsertest.js` (needs `npm i playwright-core`;
Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`). Last run: **all assertions pass,
0 console errors, 0 page errors** on desktop and on an emulated phone.

**It was moved out of the scratchpad because it was passing while three real defects shipped.**
`out/atlas_v5.html` had no doctype, no `<meta charset>` and no `<meta viewport>` — the page rendered
in quirks mode and a phone laid it out at 980px, so every responsive rule under `max-width:1100px`
was inert on the device it was written for. The test missed it because passing
`viewport:{width:390}` to Playwright sets the layout viewport *directly*, which is exactly what a
missing viewport meta prevents a phone from doing: it asserted against a state the bug made
unreachable. The phone case now uses `isMobile` + `deviceScaleFactor`, and the scaffolding is
asserted directly (`document.doctype`, `compatMode === 'CSS1Compat'`, `characterSet`, the viewport
meta, and a non-ASCII round-trip on `textContent` — not `innerText`, which only sees visible text).

Verified as a negative control by running the test against the un-wrapped fragment: it fails with
`compatMode=BackCompat` and `innerWidth=980`. **Test the mechanism, not only the outcome** — a bug
can hold the outcome and the test steady together. The side rail is `display:none` under 1100px by
Phase 2 design; that is not a regression and the test asserts it.
Keep the Residual Frequencies identity — cinnabar `#E64A2E`, jade `#35A481`, ink `#0E0C0B`,
Instrument Serif + IBM Plex Mono, single dark theme by choice, fonts stack-fallback because the
artifact CSP blocks font CDNs.

## Git

Repo `/home/user/Connector_Atlas`. Phase 3 is on `claude/phase-3-continuation-k8qf98`, branched
from Phase 2's `claude/phase-2-continuation-5diogk`. No PR opened. Start Phase 4 on a fresh branch
from this one unless it has merged, in which case branch from the default.

## The one-paragraph version, if the rest scrolled away

Phase 2 built the graph from real tool names. Phase 3 read the full JSONSchema of 178 tools across
the 11 connectors a session can actually reach, and used them as a second, stricter held-out test
of that graph. Parameters give `consumes` directly where names only approximate it, and the verdict
is that names are **84% precise but only 38% complete** — the harvested graph errs by omission, not
invention, and 34 of 59 real inbound keys were never drawn. `emits` is unimprovable this way,
because MCP schemas describe inputs only. Three things fell out that names cannot express: the keys
a read tool can be *addressed* by, 15 mandatory tool preconditions (both Vercel and Supabase
independently gate money behind a quote-then-confirm handshake), and a runtime axis showing that
**nothing in MCP is event-emitting** and self-fired triggers are 0.26% of hub-fired ones. Phase 3
also deleted the operator-payback lens from `score.py` outright and replaced it with ROBUSTNESS,
which checks each system's claimed trigger against measured evidence instead of believing it. The
scope limit is hard and unmovable: 11 of 820 connectors, a session limit rather than a source
limit, and a different axis from Phase 2's 58% registry ceiling.
