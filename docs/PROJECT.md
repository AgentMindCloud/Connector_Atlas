# PROJECT.md — read this first

> **Phase 2 is done.** Harvest, derivation, the combinatorial engine and the new views all shipped.
> The numbers below marked "inherited" are now the *baseline*, not the current state — every one of
> them moved, most of them a long way. `docs/METHOD.md` sections 10–15 carry the Phase 2 results and
> the caveats; this file is kept as the record of what Phase 2 set out to do and how that turned out.
>
> **Status against the plan:**
>
> | Step | State | Note |
> |---|---|---|
> | 1 · Harvest | done, under target | 475/820 (57.9%), not ≥90%. Source limit, proven by a one-name-per-call negative control |
> | 2 · Derive profiles | done | `engine/profile.py`; held-out test 6/6; 62 → 236 distinct join profiles |
> | 3 · Combinatorial engine | done | `engine/combine.py`; pairs and triples exhaustive and checked, motif census beyond |
> | 4 · Surface it | done | four new views in the existing tool; browser-tested, 0 console errors |
> | `discover.py` rewrite | resolved by deletion | superseded by `combine.py`; the old beam search over 47 archetypes is gone |
> | `score.py` reframing | partial | operator-payback stripped from the UI; `data/systems.json` still carries the old scores |
>
> **Four findings that contradict what this file predicted.** METHOD.md §12–13 and §16 have them in full:
> 1. `Fireflies → Todoist` is **no longer a direct edge** — its real tools emit only weak keys.
> 2. Gmail's side-effect class really is **irreversible** (`delete_label` exists); the surviving
>    claim is the narrow one, that no send tool exists — now confirmed at *schema* depth.
> 3. Harvest coverage caps at 58% because the live registry and `registry_full.json` have diverged.
> 4. **`url` was never the load-bearing key.** It ranked 1st on leverage under inheritance and 7th
>    under evidence-only. The "removing `url` destroys 24% of edges" figure below is an artifact of
>    the archetype guess, not a property of the directory. `rows` leads on real evidence.
>
> **Three models now, not two.** `--model inherited|harvested|evidence`. `harvested` mixes 464
> measured connectors with 357 inherited ones, so its aggregates carry an asterisk; `evidence` drops
> the inherited rows entirely and is the only model whose numbers need no caveat. Quote `evidence`
> when the claim is about what is known, `harvested` when it is about the directory's shape.
>
> **Phase 3 is scoped** (METHOD.md §17): parameter schemas *are* obtainable via `ToolSearch`, but
> only for connectors connected in-session — a depth upgrade for ~12 connectors, not a coverage
> upgrade for 800. Parameters give `consumes` directly, which tool names only approximate.
>
> Branch: `claude/phase-2-continuation-5diogk`.

Handoff for a fresh Claude Code chat. The container is ephemeral; this file is the memory.

## What this project is

**Map what every connector in the directory can actually do, then work out how all of them combine.**

The unit of work is the *directory*, not any person's account. 821 connectors, ~340k unordered
pairs, and a combination space far beyond pairs. The output is an understanding of which
combinations work, which don't, and why — at a scale no human can hold.

## What it is NOT (a misread that already happened once)

Session 1 spent its verification budget on the ~8 connectors that happened to be authorised in that
chat (Gmail, Drive, Todoist, Supabase, Canva, Cloudflare, Vercel, Calendar) and wrote systems around
what *that user* could run today.

**That was wrong.** Personal connections are irrelevant. They were a convenient source of ground
truth, nothing more. Do not build around "what is connected in this session," do not score systems
by what one operator would save, and do not treat the connected list as privileged. The only reason
to touch a live connector is to spot-check that a profile-derivation method is sound.

## What already exists (reuse it — do not rebuild)

Repo `/home/user/Connector_Atlas`, branch `claude/connector-atlas-mapping-lzt2c5`.

| Path | State | Verdict |
|---|---|---|
| `engine/graph.py` | merge, key-vocabulary validator, exact all-pairs over profile classes, Brandes betweenness, key scarcity | **Keep.** Solid. Profile-class compression scales to 821 real profiles unchanged |
| `engine/render.py` + `template.html` | single-file interactive map: 47 archetype constellations, derived edges, pathfinder, overlay panel | **Keep.** Needs new views, not a rewrite |
| `engine/score.py` | 9 evaluators, LEVERAGE/CAPABILITY | **Keep the evaluators, drop the framing.** Rebuild around combination quality, not operator payback |
| `engine/discover.py` | beam search over archetype sets | **Rewrite.** Searches 47 archetypes; the real job searches 821 connectors |
| `data/systems.json` | 14 authored systems | **Demote to examples.** Written under the wrong framing |
| `data/registry_full.json` | 820 connectors, archetype-inherited profiles | **The thing to replace** |
| `docs/METHOD.md` | measured findings + caveats | **Keep and extend** |

Also fixed in session 1 and worth keeping: `identity_verification` had 0 members (routing rule
added, now 6); `project_name` vs `project` drift was silently zeroing edges on 5 connectors
(normalised, plus a validator that hard-fails on unknown keys — `graph.py --validate`).

## The blocker, stated precisely

**All 820 directory connectors inherit `emits`/`consumes` from one of 47 archetypes.**

So 821 connectors collapse to **62 distinct join profiles**. Every "all-pairs" result is really
62×62 = 3,844 facts wearing 673,220 costumes. The combinatorics are not hard yet because the data
is not there yet. Everything downstream — pair analysis, ensemble search, the whole notion of
"which combos work" — is limited by this and nothing else.

**The project is 90% a data problem and 10% a graph problem.** Session 1 got that backwards.

## The unlock (found at the end of session 1, untested at scale)

`SearchMcpRegistry` returns **real per-connector tool names**, for connectors that are *not
installed*, with no auth. Verified live:

```
Fireflies  → ["get_user","get_transcript","get_transcripts"]                    3 tools, all read
Strava     → ["health","get_athlete_profile","list_activities", …]              8 tools, all read
Shopify    → ["search_products","get-product","create-product","update-product",
              "list-orders", …"+17 more"]                                       25 tools, read+write
Docusign   → ["getUserInfo","getAllAgreements","triggerWorkflow", …"+12 more"]  20 tools
Spotify    → ["create_playlist","add_to_library","search", …]  isAuthless:true  6 tools
Trivago    → 2 tools, isAuthless:true
```

Each result carries: `name`, `description`, `directoryUuid` (stable ID), `tools[]`, **`isAuthless`**,
`installState`, `connected`.

**This immediately falsifies inherited profiles.** Fireflies has no write tools at all — it consumes
nothing. Its archetype claims it consumes `url`, `timestamp`, `media`, so *every edge pointing into
Fireflies in the current graph is fictional.* Expect this across the directory: the archetype model
systematically over-connects, because it assumes every member both emits and consumes its
archetype's full key set.

`isAuthless` is a second unlock: authless connectors have **zero auth surface**, which was scored as
the single biggest practical cost of any multi-connector combination.

### Known limits of this source — label them, don't paper over them
- Tool lists are truncated at 8 with a `"+N more"` sentinel. Exact count is recoverable; the tail of
  the names is not.
- Tool **names only** — no parameter schemas. So `emits`/`consumes` derived from names is
  *inference over real evidence*, not observation. That is a genuinely new tier between DOCUMENTED
  and DIRECTORY; name it (suggest `HARVESTED`) rather than overclaiming VERIFIED.
- It is a keyword search returning ~10 results per call, not an enumeration endpoint.

## Step 1 — Harvest (the bulk of the work)

Build `engine/harvest.py` as a **resumable, cached** loop:

- Feed connector names from `registry_full.json`, up to 8 keywords per call.
- Append every result — including unrequested fuzzy matches, which are free coverage — to
  `data/harvest/*.json`, keyed by `directoryUuid`.
- Track coverage; re-query only misses. ~103 calls at perfect efficiency; budget 150–250 across
  sessions. **Never re-harvest what is already cached** — cost control is the whole design.
- Record `harvested_on` per record. This data ages.

Success = ≥90% of 821 connectors with a real tool list. Report the miss list explicitly.

Note: `SearchMcpRegistry` is a deferred tool. Load it first with
`ToolSearch(query="select:SearchMcpRegistry")`, then call it.

## Step 2 — Derive real profiles from tool names

`engine/profile.py`. Deterministic, auditable, and every rule visible:

- **Side-effect class** from verb prefix: `get_/list_/search_/read_/fetch_/query_` → `read`;
  `create_/add_/send_/upload_/post_` → `create`; `update_/edit_/patch_/move_/label_` → `mutate`;
  `delete_/remove_/purchase_/buy_/pay_` → `irreversible`. A connector's class is its **maximum**.
- **`consumes` = ∅ when a connector has no write tools.** This is the single highest-impact
  correction available and it kills a large share of the graph's fictional edges.
- **Key inference from tool nouns** — `*_email`/`*_message`→`email`, `*_file`/`*_document`→`file`,
  `*_event`/`*_calendar`→`timestamp`, `*_order`/`*_invoice`/`*_payment`→`money`, `*_row`/`*_query`/
  `*_sql`→`rows`, etc. Keep the rule table in one dict; **emit a firing count per rule** so dead and
  overfiring rules are visible. (Session 1 lesson: a subagent reported two routing rules dead;
  measurement showed one fired 13 times. Count, don't read.)
- Archetype profile stays as the **fallback** for un-harvested connectors, clearly tiered.
- Then re-run `graph.py --analyze` and **diff against the current numbers below.** The delta *is* a
  headline result: how wrong was the inherited model?

## Step 3 — The combinatorial engine

This is where "so many scenarios" gets handled honestly. Three regimes, because brute force dies:

| Regime | Size | Method |
|---|---|---|
| **Pairs** | 673,220 ordered | Exhaustive. Every pair classified: direct edge (with keys) / bridgeable in k hops / unreachable. Materialise the full matrix |
| **Triples** | ~9.2 × 10⁷ ordered | Exhaustive **with pruning** — only triples forming a connected subgraph survive; count and classify by shape (chain A→B→C, fan-in A,B→C, fan-out A→B,C, cycle) |
| **N > 3** | 4-tuples alone ≈ 7.5 × 10¹⁰ | **Do not enumerate.** Enumerate *motifs* — the nine patterns from `composition.md` — and count instantiations per motif. Classify the space instead of walking it |

The N>3 point matters and should be stated plainly in the output: **you cannot enumerate every
combination of 821 connectors, and you do not need to.** A 4-subset is 75 billion; a 10-subset is
past 10²⁰. What is computable — and what actually answers "how does everything combine" — is:
exhaustive pairs, exhaustive connected triples, then a motif census over everything larger. That is
a complete description of the combination space without a lie about having walked it.

Useful derived questions the engine should answer:
- Which connectors are **universal donors** (emit keys almost everything consumes) and **universal
  sinks**? Which are **isolates**?
- Which pairs are unreachable *even through hubs*, and is that real or a profile gap?
- Which single connector, added to the directory, would create the most new pair-connections?
- Which key, if a connector gained it, would most increase its reach? (the cheapest profile upgrade)
- How many pairs' reachability **changed** between the inherited model and the harvested model?

## Step 4 — Surface it

Extend the existing tool rather than starting over. New views:
- **Pair explorer** — pick any two of 821, see the classified relationship instantly from the
  precomputed matrix.
- **Connector profile** — real tool list, derived class, tier badge, authless flag.
- **Motif census** — the combination-space map: how many instantiations of each pattern exist.
- **Model diff** — inherited vs harvested, side by side. This is the most interesting screen.
- Keep the constellation map, pathfinder, and Residual Frequencies identity (cinnabar `#E64A2E`,
  jade `#35A481`, ink `#0E0C0B`, Instrument Serif + IBM Plex Mono, single dark theme by choice —
  fonts must be inlined or stack-fallback; artifact CSP blocks font CDNs).

## Numbers already established — do not re-derive

Under the **inherited** model. Every one of these has now been re-measured under the harvested
model; see METHOD.md §13 for the side-by-side. Direct reachability fell 67.69% → 23.82%.

- 821 connectors · 47 archetypes · **62 distinct join profiles** · 1,610 archetype edges
- Reachability, ordered pairs: native-only **67.69%** direct / 92.60% ≤2 hops / diameter 3;
  with fallbacks 70.11% / 95.12%; with hubs **72.02% / 97.30%**, diameter 2
- **18,172 ordered pairs unreachable even through hubs** — 17,220 of them from **21 connectors that
  consume no strong key** (13 `education`, 6 `forms_surveys`, 2 curated). Forms being source-only is
  correct; education is under-modelled
- **Key scarcity** (⚠ artifact — see METHOD.md §16): removing `url` destroys **389 of 1,610 edges (24%)**; `file` 181, `email` 126,
  `timestamp` 115, `rows` 75, `geo` 23
- Betweenness: `automation_hub` 48.1, `browser_automation` 23.1, `email` 21.7, `chat_messaging` 21.7
- Degree: `automation_hub` 90; `email`/`chat_messaging`/`ecommerce_logistics` 87; `browser_automation` 84
- Side-effect split: **read 293**, irreversible 244, mutate 239, create 47
- `engine/graph.py` cross-checks exactly against the skill's `atlas.py` on degrees and on
  Fireflies→Todoist (direct, `email/timestamp/url`) and Strava→Docusign (no direct edge)

**Expect harvesting to move all of these, mostly downward.** The inherited model over-connects.

## Real constraints banked from live schemas (small but load-bearing)

Keep these; they are the calibration set that shows how wrong name-based inference can be.

- **Gmail exposes no send tool** — `create_draft`/`update_draft` only. Registry says `irreversible`;
  reality is `create`.
- **Google Calendar exposes only `search_events`** — semantic, no date-range enumeration, no writes.
- **Cloudflare cannot deploy a Worker** — `workers_*` are read-only.
- **Vercel has `buy_domain`/`buy_pro`/`buy_credits`** — spends real money.
- Verification *reduced* measured reachability (97.42%→97.30%). Deleting fictional edges is the
  method working.

Use these five as a **held-out test set** for Step 2: run the name-based derivation on them and see
whether it recovers the truth. If it cannot tell that Gmail has no send tool, the derivation rules
need work before being applied to 821 connectors.

## Traps

1. **Do not score by personal utility.** No "hours reclaimed," no operator payback. Judge
   combinations by what they make possible and how the graph constrains them.
2. **Do not claim to have enumerated every combination.** Pairs and triples yes; beyond that it is a
   motif census, and saying so is the honest and more interesting answer.
3. **Do not re-harvest cached data.** Cache first, then loop.
4. **Do not promote name-derived profiles to VERIFIED.** Tool names are evidence, not schemas.
5. **Count rule firings; don't read regexes.** Both defects in session 1 were invisible to reading
   and obvious to counting.
6. **Do not spawn subagents unless asked.** One in session 1 re-derived known context and got a fact
   wrong that measurement corrected.
7. The `+N more` truncation means tool lists are samples. Recover the *count*; don't invent the tail.

## Verification for Phase 2

- `python3 engine/graph.py --validate` → 0 unknown keys, 0 empty archetypes (regression guard).
- Harvest coverage report: N of 821 with real tool lists, miss list printed.
- Derivation held-out test: the five constraints above recovered from tool names alone — report
  hits and misses honestly.
- Diff report: inherited vs harvested reachability, edges, distinct profiles. Large deltas are the
  expected result, not a bug.
- Pair matrix spot-check: Fireflies→Todoist still direct; every edge *into* Fireflies now gone.
- Re-render, browser-test with Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  (`playwright-core` installs into the scratchpad): no console errors, no horizontal scroll.

## The one-paragraph version, if the rest scrolled away

The directory has 821 connectors but only 62 distinct join profiles, because everything inherits its
profile from one of 47 archetypes. That inheritance is fiction — `SearchMcpRegistry` gives real
per-connector tool names with no auth, and they show connectors like Fireflies consume nothing the
archetype says they do. Harvest those tool lists (`engine/harvest.py`, cached/resumable), derive
real read/write profiles from verb prefixes (`engine/profile.py`), diff against the inherited
baseline, then run the combinatorial engine: exhaustive pairs, exhaustive connected triples, motif
census beyond. Keep `engine/graph.py` and the map; rewrite `discover.py`; drop the operator-payback
framing entirely. The project is a data-harvesting problem wearing a graph-theory costume.
