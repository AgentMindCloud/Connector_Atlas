# Method — how the numbers were produced, and what they are worth

Every figure in the atlas is derived from `data/` by code in `engine/`. This file records how,
and — more usefully — where the model is weak. Read the caveats before quoting the numbers.

---

## 1. The scale caveat that shapes everything

**All 820 directory connectors inherit `emits`/`consumes` from their archetype.** A curated profile
in `data/registry.json` overrides that, but only 17 connectors have one.

So the honest statement of scale is:

| Claim | Number |
|---|---|
| Connectors in the graph | 821 (820 directory + 1 curated-only) |
| Archetypes | 47 |
| **Distinct join profiles** | **62** |
| Derived archetype edges | 1,610 |
| Ordered connector pairs | 673,220 |

A literal 821 × 820 all-pairs expansion would produce 673,220 edges encoding **62 × 62 distinct
facts**. Materialising that would be ~50 MB of redundancy and zero extra information.

`engine/graph.py` therefore computes all-pairs **exactly, over profile classes**, then expands by
class size. The answer is the true 673,220-pair answer; only the storage is compressed. What it is
*not* is 821 independently-known connectors — it is 62 known shapes worn by 821 names.

**What follows from this:** more connectors do not produce more insight. Better profiles do. The
verification backlog (813 still at `DIRECTORY`) is the real bottleneck, not registry size.

## 2. Reachability — measured, not asserted

Directed BFS over profile classes, three regimes:

| Regime | Direct (1 hop) | ≤2 hops | Unreachable | Diameter |
|---|---|---|---|---|
| Native only (no hubs, no fallbacks) | 67.69% | 92.60% | 47,960 | 3 |
| + browser/desktop fallbacks | 70.11% | 95.12% | 31,052 | 3 |
| + automation hubs | 72.02% | **97.30%** | 18,172 | 2 |

**The skill's claim that "no pair is more than ~2 hops apart in bridge mode" is very nearly true
but not exactly true.** 18,172 ordered pairs (2.70%) remain unreachable even through hubs.

The reason is specific and worth knowing: **21 connectors consume no strong key at all.**

- 13 `education` connectors and 6 `forms_surveys` connectors, whose archetypes consume only `text`
- `Anthropic Economic Index` and `Superhuman Docs` (curated profiles)

21 × 820 = 17,220 ordered pairs, essentially the whole residual. These are **pure sources** —
nothing can reach them, they only emit.

For forms this is correct modelling: a survey tool is an inbound bridge, not a sink
(`composition.md`: "forms bridge inward"). For `education` it is probably **under-modelling** —
MagicSchool advertises "save teaching materials directly to your Resource Library", which is a
`file`/`text` sink. Fixing it is a profile change, not a code change.

## 3. Key scarcity — which join keys carry the graph

Removing one key and recounting archetype edges (baseline 1,610):

| Key removed | Edges lost | Share |
|---|---|---|
| `url` | 389 | **24.2%** |
| `file` | 181 | 11.2% |
| `email` | 126 | 7.8% |
| `timestamp` | 115 | 7.1% |
| `rows` | 75 | 4.7% |
| `geo` | 23 | 1.4% |

`url` alone carries a quarter of the graph. This is the empirical form of `composition.md` §4's
claim that "a URL in a text field is the cheapest integration in existence" — it is not a
rhetorical flourish, it is the single most load-bearing primitive in the directory.

## 4. Centrality

Exact Brandes betweenness over the 47-archetype graph. Top bridges: `automation_hub` (48.1),
`browser_automation` (23.1), `email` (21.7), `chat_messaging` (21.7), `ecommerce_logistics` (20.8).

Degree cross-checks exactly against the skill's `atlas.py hubs` (automation_hub 90; email,
chat_messaging, ecommerce_logistics 87; browser_automation 84). The two implementations agree,
which is the point of keeping them separate.

## 5. Data defects fixed

| Defect | Effect | Fix |
|---|---|---|
| `identity_verification` archetype had **0 members** — no routing rule reached it | A defined archetype was a dead node; KYC/auth/privacy vendors were misfiled under `security` and `cloud_infra` | Added a pin ahead of both. Now 6 members (Sumsub, Clerk, Stytch, WorkOS, BigID, DataGrail). `cloud_infra` 26→23, `security` 25→22 |
| `project_name` vs `project` vocabulary drift | Edges are literal string intersections, so **5 curated connectors silently produced zero `project` edges** — Google Drive, Todoist, Supabase, Canva, Craft. The most-trusted layer was the most broken | Normalised to `project`; added a hard-fail validator (`graph.py --validate`) so it cannot recur |
| One dead duplicate `chat_messaging` rule | Nothing — measured 0 firings | Removed |
| `profile-template.md` referenced `render_atlas.py` | Broken pointer | → `atlas.py` |

The second one is the instructive failure. It was invisible: no error, no warning, just missing
edges in exactly the connectors most likely to be used. **A rule-firing count and a vocabulary
validator would each have caught it in seconds.** Both now exist.

A claimed defect that turned out **not** to be one: a second `prospecting_enrichment` rule was
reported as dead. Measurement showed it fires 13 times, catching connectors the first pin misses.
It was left alone. Rule-firing counts beat reading the regexes.

## 6. Confidence

Tiers per `SKILL.md`. 8 connectors were promoted to `VERIFIED` this session by loading real tool
schemas; Supabase additionally answered a live read-only `list_projects` call.

Verification **removed** edges rather than adding them — reachability fell from 97.42% to 97.30%
when Google Calendar's real profile (consumes a query string only) replaced its inherited one.
That is verification working: it deletes edges that were never real.

Findings that changed designs:

| Connector | Assumed | Verified |
|---|---|---|
| **Gmail** | `irreversible` (can send) | `create` — **no send tool exists.** Draft-only by construction |
| **Google Calendar** | reads events, maybe writes | `search_events` only. **Cannot enumerate a date range**; semantic query required |
| **Cloudflare** | the scheduler | **Cannot deploy a Worker.** `workers_*` are read-only; cron code ships out of band |
| **Vercel** | deploy platform | Also `buy_domain` / `buy_pro` / `buy_credits` — **spends real money** |
| **Supabase** | the spine | Works, but **all 5 projects observed `INACTIVE`**. A paused spine is not a spine |

Two of these killed ribs outright (calendar scheduling, Cloudflare-deployed cron). They would have
shipped as confident fiction.

**Confidence decays.** A `VERIFIED` profile is a statement about one session. Vendors change tools
without notice. `data/systems.json` → *The Atlas as a Running System* exists to age these tiers
automatically; without it the badges rot into decoration within months.

## 7. The scoring model

`engine/score.py`. All weights in one `WEIGHTS` dict; all breakpoints explicit and arguable.

Requested axes map on as: technical difficulty → `build_hours` + `judgment_share` + `blast_radius`;
cost → build + monthly run; time → `build_hours`, `cold_start_days`; automation vs human →
`trigger_reality` + `human_minutes_per_week`; Claude vs human → `judgment_share`.

Nine added evaluators, chosen because each one predicts a failure the other axes miss:

1. **Blast radius** — worst side-effect class. Sets confirmation policy.
2. **Auth surface** — accounts required. Compounds against adoption harder than anything else.
3. **Trigger reality** (0–3) — is "automatic" real? `recipes.md` names this the dominant factor.
4. **Fan-in : chain-depth ratio** — breadth is additive, depth is multiplicative. Licenses the 150+ tier.
5. **Cold-start latency** — days to first value.
6. **Marginal cost per run** — decides hourly vs weekly cadence.
7. **State gravity** — durable state accumulated; proxy for compounding value.
8. **Judgment share** — Claude ribs vs code ribs. The central placement decision.
9. **Degradation grace** — on one connector failing: degrade or die?

### Two lenses, deliberately not averaged

`LEVERAGE` (cost recovery) and `CAPABILITY` (graph exploitation) get **separate tiers**. Blending
them hides the most useful result in the exercise:

> The systems that pay back fastest and the systems that exploit the graph hardest are almost
> disjoint sets.

- Highest LEVERAGE: *Inbox → Commitment Ledger* (81.3, tier S) — capability tier **C**. 4 connectors.
- Highest CAPABILITY: *Maximum Safe Mesh* (95.6, tier S) — leverage tier **C**, and it **never
  breaks even**: $5,000/mo of vendor licences against ~$4,950/mo of reclaimed time.
- Only *Personal Operating System* scores well on both (75.2 / 61.6) — which is why it is the one
  to build first.

### Economics disclaimer

Build at $60/h, reclaimed time at $45/h — both **ASSUMED**, both tunable in `WEIGHTS`. Vendor
subscription figures are estimates, not quotes; the *Competitive Intelligence Desk*'s $900/mo and
the meshes' four-figure lines are the least reliable numbers here and the most likely to decide
whether a system is worth building. Verify before committing.

## 8. Why a 150+ connector system is coherent

Connector count is safe when it scales by **fan-in breadth** and dangerous when it scales by
**chain depth**. Sequential hops multiply failure probability; independent read-only ribs on a
shared spine are additive. `composition.md` §7.3 states ribs are independent — this is that taken
to its conclusion:

> A 200-sensor read-only mesh has a smaller blast radius than a 7-hop write chain.

**293 connectors carry `side_effects: read`.** That is the hard ceiling on a system that cannot
break anything it touches — a fact about the registry, not a judgment about a design. The 294th
connector is a write, and the blast-radius argument collapses.

The honest coda: the *architecture* scales to 293, the *value* does not. Marginal information from
sensor #150 is near zero. `Market Omniscience Mesh` (205) is included because it is real and
because it proves the topology — not because anyone should build it at that width. Pick the 20–30
sensors with the highest marginal information and stop.

## 9. What this model does not do

- **No runtime verification of the 813 `DIRECTORY` connectors.** Their join profiles are archetype
  guesses. Right about the category, unverified on specifics.
- **No pricing API.** Every dollar figure is an estimate.
- **No measurement of whether the systems work.** They are designed against verified constraints
  and cross-checked for graph validity; none has been built.
- **Discovery is a proposal engine.** `engine/discover.py` ranks archetype sets; the 14 shipped
  systems are hand-authored. Machine-found and human-authored are labelled separately in the tool,
  never merged.

---

# Phase 2 — the harvest, and what it cost the graph

Everything above section 9 describes the **inherited** model. This section describes what happened
when the inheritance was replaced with evidence. Both models are still computable
(`--model inherited|harvested`) because the diff *is* the result.

## 10. Harvest — real tool names, no auth

`SearchMcpRegistry` returns per-connector tool names for connectors that are not installed, with no
authentication. `engine/harvest.py` runs a cached, resumable loop over it: raw responses are appended
to `data/harvest/raw/*.tsv`, all state is derived from those files, and `--plan` only ever emits
names that have neither been returned nor been asked for. Re-running costs nothing.

| | |
|---|---|
| Registry names asked | 679 (every one of the 820, plus alternates) |
| Connectors with a real tool list | **475 / 820 — 57.9%** |
| Distinct tool names collected | 2,828 |
| Total tools claimed (incl. truncated tails) | 7,194 |
| Records truncated by the `+N more` sentinel | 242 |
| Authless connectors found | 73 |
| Directory entries not in our registry | 2 (HealthEx, and one other) |

**Coverage stopped at 57.9%, not the 90% the plan targeted.** That is a property of the source, not
of the effort, and it was tested rather than assumed: eight names from the miss list were re-queried
**one name per call**, eliminating any chance that 8-keyword batching had diluted them. Zero of the
eight returned an exact match and three returned an empty array. `registry_full.json` is a dump of a
wider or older directory than the live registry search covers. The negative control is recorded in
`data/harvest/raw/b014.tsv`.

Three archetypes have **zero** coverage — `desktop_local`, `browser_automation`, `ai_tools`. These
are local extensions, not hosted MCP servers, so the registry cannot see them. Every claim about
those 100+ connectors is still inherited, and they are tagged `DIRECTORY` wherever they appear.

## 11. Derivation — names are evidence, not schemas

`engine/profile.py`. Two rules do the work:

1. **Side-effect class** = the *first* verb-shaped token in the tool name. The connector's class is
   the maximum over its tools.
2. **Read tools feed `emits`; write tools feed `consumes`. Nothing else feeds either.**

Rule 2 is what deletes the fictional edges. A connector with no write tools consumes nothing, so
nothing can point into it.

Rule 1 was wrong in its first form and *counting caught it*. The original took the maximum over all
verb tokens anywhere in the name; `order` was in the irreversible list; so Shopify's `get-order`,
Razorpay's `fetch_all_orders` and AngelList's `get_close` all scored **irreversible**. Reading the
regex would never have surfaced that. `--rules` prints a firing count for every verb and every noun
and flags dead ones; three corrections came out of it (`order` and `map` reclassified as nouns, `id`
dropped as a lookup idiom firing 29 times on nothing).

**Tiers, never blurred:**

| Tier | Basis | Count |
|---|---|---|
| `VERIFIED` | tool list observed live in a session | 11 |
| `HARVESTED` | real tool names from the registry | 453 |
| `DIRECTORY` | no tool evidence; archetype inherited | 357 |

## 12. The held-out test

The five constraints banked in session 1 were run against the derivation as a test set
(`profile.py --heldout`). Ground truth lives in `data/verified_tools.json`.

**6 of 6 checkable claims recovered**, including the family-level one: Cloudflare's `workers_*` tools
are read-only (it cannot deploy a Worker) *while the connector as a whole is correctly irreversible*
because `d1_*`/`kv_*`/`r2_*` do delete. A connector-level test would have missed that; the check runs
at the level the claim is actually about.

Two honest results came out of this rather than a clean sweep:

- **One banked constraint did not survive.** PROJECT.md records "Gmail: registry says irreversible,
  reality is `create`". The live tool list now contains `delete_label`, so Gmail really is
  irreversible and the registry was right for the wrong reason. The narrow claim that survives is
  the specific one: **no send tool exists.**
- **One documented failure of the method.** tldraw's `exec` runs arbitrary canvas JavaScript. The
  name carries no verb and no noun, so the derivation scores it `read`/`emits text` when the single
  tool actually subsumes create, mutate and delete. Name-based inference has a floor and this is it.

## 13. The diff — how wrong was the inherited model?

| | inherited | harvested |
|---|---|---|
| Distinct join profiles | 62 | **236** |
| Direct ordered pairs | 484,859 | **174,801  (36.1% survive)** |
| Direct, native only | 67.69% | **23.82%** |
| ≤2 hops, native only | 92.60% | **49.04%** |
| Unreachable through hubs | 18,172 | **319,826** |
| Connected triples (of 91,894,530) | 92.91% | **30.13%** |
| Read-only connectors | 293 | 362 |

- **465 connectors** changed their `emits`, **466** their `consumes`, **278** their side-effect class
  (81 more severe than the archetype claimed, 197 less).
- **293 connectors consume nothing at all.** Every inbound edge they had in the inherited model was
  fictional. Fireflies is the worked example: three read tools, so **0 in-edges**, where the
  archetype claimed it consumed `url`, `timestamp` and `media`.

**A prediction the measurement overturned.** PROJECT.md expected `Fireflies → Todoist` to survive as
a direct edge. It does not. Fireflies' real tools support only `person` and `text`, both of which are
weak keys, so it has no strong join to anything. The inherited model gave it `email/timestamp/url`
from its archetype and that is where the old edge came from. Fireflies is a weak-key source, and
reaching a task manager from it needs a bridge.

Two thirds of the graph was fiction. That is the headline, and it is a result about the *method*,
not a defect: deleting edges that were never there is the model getting more true.

## 14. The combination space, described without lying about it

`engine/combine.py`. Three regimes, because brute force dies at four.

| Regime | Size | Treatment |
|---|---|---|
| Pairs | 673,220 ordered | **Exhaustive.** Every pair classified: direct / k hops / unreachable |
| Triples | 91,894,530 unordered | **Exhaustive.** Every triple accounted for, connected ones classified by shape |
| N > 3 | 4-subsets ≈ 7.5 × 10¹⁰ | **Not enumerated.** Motif census instead |

Both exhaustive claims are checked, not asserted: the triple pass reports `accounted_for` against
`C(821,3)` and they are equal. This works because structure is computed over the 236 profile classes
and expanded by class size with the right binomials — the class matrix *is* the pair matrix,
losslessly compressed, and `out/pairs_harvested.json` ships the class index so any of the 673,220
pairs resolves in two lookups.

Connected triples by shape (of 27,691,870 connected): fan-in 4,197,686 · chain 2,431,859 · the rest
are denser mixed shapes reported by their own degree fingerprint rather than forced into a bucket.

**Beyond three, the honest answer is a census, not a list.** A 4-subset is 75 billion; a 10-subset is
past 10²⁰. `--motifs` counts instantiations of the nine patterns from `composition.md`, each under an
explicit structural encoding recorded next to its count, so disagreeing with a number means
disagreeing with a written-down definition:

| Motif | Instantiations (size 2–5) | All sizes |
|---|---|---|
| pipeline | 53,093,841 | — |
| enrich | 58,818,929,530,166 | ~10²¹⁵ |
| digest | 50,760,620,246,727 | ~10²¹⁵ |
| fan-out | 18,397,966,345,983 | ~10¹⁵⁰ |
| trigger → action | 2,030,181 | — |
| materialize | 89,171 | — |
| escalate | 61,582 | — |
| reconcile | 49,610 | — |
| mirror | 22,590 | — |

The fan-shaped totals are exact and useless as headline integers — a sink with in-degree 711 admits
2⁷¹¹ − 712 distinct Enrich instantiations. `composition.md`'s own advice for Digest is "cap the
sources", so the census caps them at five and reports the unbounded magnitude separately. **The
ordering is the finding:** the cheap patterns are astronomically abundant and the patterns that
require a *writer on both ends* — mirror, reconcile, escalate — are four to nine orders of magnitude
rarer. Composition is not limited by what can be read. It is limited by what can be written into.

## 15. What Phase 2 still does not do

- **42% of the directory has no tool evidence.** Those connectors carry archetype profiles and are
  tagged `DIRECTORY`. Any aggregate on this page is a mix of measured and inherited, and the tier
  split is printed everywhere it matters so the mix is visible.
- **Tool names, not schemas.** No parameter types, no required fields, no auth scopes, no rate
  limits. `HARVESTED` is a real tier between `DOCUMENTED` and `DIRECTORY` and it is never promoted.
- **242 tool lists are truncated.** The count is recovered from the `+N more` sentinel; the names in
  the tail are not, and nothing here invents them.
- **13.7% of tool names contain no recognisable verb** (386 of 2,818) and default to `read` —
  the choice that cannot manufacture an in-edge.
- **`engine/discover.py` was not rewritten.** `combine.py` supersedes its purpose; the old
  beam search over 47 archetypes is now dead code and should be deleted, not repaired.
- **`data/systems.json` is demoted, not rewritten.** The 14 authored systems were scored under an
  operator-payback framing this project has dropped. The payback numbers are gone from the UI and
  the tab is labelled *examples*; the file itself still carries the old scores.

## 16. The evidence-only model — and what it overturns

`--model evidence` drops the 357 `DIRECTORY` connectors from the graph entirely rather than
downgrading them. `harvested` mixes measured and inherited rows, so every aggregate over it carries
an asterisk; `evidence` is the model with no fiction in it. Neither supersedes the other —
`harvested` answers *what does the directory look like*, `evidence` answers *what do we actually
know*. All three are computable from the same loader.

| | inherited | harvested | **evidence** |
|---|---|---|---|
| Connectors | 821 | 821 | **464** |
| Distinct join profiles | 62 | 236 | **190** |
| Direct, native only | 67.69% | 23.82% | **5.73%** |
| ≤2 hops, native only | 92.60% | 49.04% | **20.83%** |
| Diameter | 3 | 3 | **4** |
| Connected triples | 92.91% | 30.13% | **4.87%** |

Three archetypes have **no evidence-backed member at all** — `ai_tools`, `browser_automation`,
`desktop_local`. `--validate --model evidence` names them rather than passing silently.

### The `url` result

This is the finding that most damages the original model. Under inheritance, `url` was the single
most load-bearing key in the graph: removing it destroyed **389 of 1,610 archetype edges (24%)**, and
it ranked first on leverage by a wide margin.

| Model | `url` leverage rank | Top key |
|---|---|---|
| inherited | **1st** (1,036) | url |
| harvested | 1st (531) | url |
| evidence | **7th** (48) | **rows** (152) |

`url` was never load-bearing. It was *plausible* — nearly every archetype had it written into both
emits and consumes because almost any web tool could conceivably hand back a link, and that guess
propagated to 820 connectors. Real tool names barely mention urls. They mention rows, companies and
projects. The keys that actually carry the graph are the ones that name records, not the ones that
name locations.

The same correction applies to the centrality results in §4: `automation_hub` topped betweenness and
`CodeWords` topped out-degree in both earlier models, and both are `DIRECTORY` tier — they ranked on
an inherited profile, not on evidence. Under `evidence` the top donors are Supabase and Todoist
(both `VERIFIED`) and the top sink is Lucid. Every degree table now prints a tier badge for exactly
this reason.

## 17. Phase 3 — the schema question, answered

**Parameter schemas are obtainable, but only for connected connectors.** `ToolSearch` returns the
full JSONSchema for any deferred tool — parameter names, types, required fields, descriptions, and
stated limitations. Verified live this session on two of the calibration connectors:

- `Gmail.create_draft` — parameters `to`/`cc`/`bcc`, `subject`, `body`, `htmlBody`, `attachments`,
  `replyToMessageId`. **No send parameter of any kind**, and the description states
  "Creating drafts with attachments is not supported yet." The banked Gmail constraint now holds at
  *schema* depth, not just name depth.
- `GoogleCalendar.search_events` — required parameter `query`, plus `pageSize`/`pageToken`. **No
  date-range parameters**, confirming the "semantic search only, no enumeration" constraint exactly.

**Why this matters more than it looks.** `create_draft`'s parameters reveal that it consumes
`email` (to/cc/bcc), `file` (attachments) and `text` (body) — none of which the tool *name*
contains. Name-based derivation gets side-effect class right and gets `consumes` only
approximately; parameters give `consumes` directly and precisely. That is the single biggest
available quality upgrade to the profile model.

**The scope limit is hard.** `ToolSearch` only covers tools in the current session's deferred list,
which means connected connectors — about a dozen — not the 800+ directory. So schemas are a *depth*
upgrade for a handful of connectors, not a *coverage* upgrade for the directory. Phase 3 should
therefore be scoped as: extend `verified_tools.json` into a schema-carrying format, derive
`consumes` from parameters for every connector the session can reach, and use the result as a
second, sharper held-out test of the name-based rules that must still cover the other 450.

## 18. Removed

`engine/discover.py` (beam search over 47 archetypes) is deleted. `engine/combine.py` supersedes it
and searches the real space; keeping a second, weaker searcher around would only invite someone to
run it.

---

# Phase 3 — parameter schemas, and the bill for tool names

## 19. What was harvested, and the ceiling that replaced the old ceiling

`ToolSearch` returns the full JSONSchema for any deferred tool: parameter names, types,
required flags, enum values, and the description prose including stated limitations. **178 tool
schemas were read across the 11 connectors this session is connected to** and transcribed into
`data/schemas/raw/*.jsonl`, an append-only cache in the same spirit as the Phase 2 harvest.

| | count |
|---|---|
| Tool schemas read | 178 |
| Connectors covered | 11 of 820 (**1.3%**) |
| Parameters | 481 top-level, 680 readings including nested object fields |
| Coverage vs the Phase 2 tool lists | 178 of 180 |

The two missing tools are Cloudflare's `accounts_list` and `set_active_account`. They were in the
Phase 2 observation and are **not** in this session's deferred list. That is session-to-session
drift in what a connector exposes, it is recorded rather than smoothed over, and `--delta` prints a
caveat because it is exactly the gap that makes Cloudflare's `company` key look invented.

**This is a different ceiling from Phase 2's and it does not move it.** Phase 2 capped at 475/820
because `SearchMcpRegistry` had diverged from the live registry — a *source* limit, proven with a
one-name-per-call negative control. Phase 3 caps at 11/820 because `ToolSearch` only sees
connectors the session is *connected to*, and connecting 800 accounts is not a thing a session can
do. Neither ceiling is beaten by the other. Schemas are a **depth** upgrade for eleven connectors
and a sharper held-out test for the other 453.

## 20. What parameters upgrade, and what they cannot

**Upgraded: `consumes`.** A tool's input parameters *are* the things that can be written into it.
`Gmail.create_draft` takes `to`/`cc`/`bcc`, `subject`, `body`, `htmlBody`, `attachments` and
`replyToMessageId` — so it consumes `email`, `text` and `file`, and the tool *name* contains none
of those three nouns.

**Not upgraded: `emits`.** MCP tool schemas describe **inputs only**. There is no output schema to
read, so `emits` is still derived from tool names everywhere in this atlas, including on these
eleven. Any `emits` figure quoted anywhere is a Phase 2 figure.

Two things fall out that names cannot express at all:

- **`selectors`** — the keys a *read* tool can be addressed by. `Google Calendar.search_events`
  accepts `query`, `pageSize` and `pageToken`: the calendar is addressable by free text and
  nothing else. A connector whose reads take only its own opaque ids cannot be entered from
  outside by anyone not already holding an id, which is a join constraint the edge model never had
  a way to say.
- **`preconditions`** — mandatory ordering *inside* one connector. **15 of them across 4
  connectors.** Two vendors independently guard money the same way: `get_purchase_quote` is the
  only source of the `idempotencyKey` that every Vercel `buy_*` requires, and Supabase's
  `create_project` needs a `confirm_cost_id` that comes from `confirm_cost`, which itself says to
  call `get_cost` first. Canva has four more, including `read-design` → `edit-design`. None of
  these are visible in a tool name, and each one is a step that must succeed before a composed
  system can act.

## 21. The second held-out test — what a name costs

Phase 2's held-out test was six hand-picked claims and it passed 6/6. This is the harder version:
on the 11 connectors where a name-derived and a parameter-derived `consumes` both exist,
parameters are the reference and names are the estimate.

| | value |
|---|---|
| (connector, key) claims compared | 59 |
| Both agree | 21 |
| Names claim, parameters do not — **invented** | 4 |
| Parameters claim, names do not — **missed** | 34 |
| **Precision** | **0.840** |
| **Recall** | **0.382** |
| F1 | 0.525 |

**Read it this way: when a tool name claims a key it is right 84% of the time, but it sees under
40% of what the connector actually accepts.** The name-based model is not noisy, it is *blind* —
it errs overwhelmingly by omission, not by invention. Every one of the 34 misses is a real inbound
edge that the 453-connector harvested graph does not draw.

Because parameters improve two things at once — which keys a tool takes, and whether it is a
writer at all — `--delta` also reports the comparison with the read/write split pinned to Phase
2's name-derived version. **30 of the 34 misses come from key extraction alone; the other 4 need
the tool reclassified as a writer first.**

Side-effect class agrees on 8 of 11. The three disagreements are all schema-only findings:

1. **Canva is `irreversible`, not `mutate`.** `edit-design`'s operations include `delete_element`
   and its description says commit is IRREVERSIBLE; `merge-designs` carries `delete_pages` and
   "CANNOT BE UNDONE". `data/verified_tools.json` recorded "no delete" as ground truth. **That
   ground truth was wrong**, and only the schema shows it.
2. **tldraw is `mutate`, not `read`** — and this retires Phase 2's documented failure case.
   `exec` carries no verb and no noun, so name inference could only ever score it `read`. Its
   schema has a required `code` string. Phase 2 said "name-based inference has a floor, and this
   is it"; the floor is where it was, but schemas are underneath it.
3. **Three.js is `mutate`, not `read`**, by the same `code`-parameter rule.

## 22. Rules that were removed by measurement, not by argument

Three rules in `engine/schema.py` were cut or narrowed after being counted. Recording them because
the counting is the method, and a rule that survives only because nobody measured it is the
failure mode this project keeps re-learning.

- **Verb-scanning prose: removed.** Reading tool descriptions for verbs pushed Google Drive from
  `create` to `mutate` — its description cross-references other tools by name, and Gmail's
  read-only `list_labels` names three mutate verbs the same way. Prose is now scanned only for a
  seven-word irreversibility list (`irreversible`, `undone`, `permanently`, `destroys`, …) which
  has no other meaning.
- **Verb-scanning every type string: narrowed to action parameters.** It fired 30 times, changed
  **zero** connector classes, and at tool level was right 3 times and wrong twice — reading
  `LabelColor` as the verb "label" and `DRAFT_VIEW_FULL` as the verb "draft". Restricted to
  parameters whose *value selects what the tool does* (`action`, `operation`, `labelOption`,
  `finalize`), it keeps both real wins and drops both false positives. `eventType` is pointedly
  excluded: `find-activity`'s enum lists `deleted` as something to filter for, not to do.
- **Bag-of-tokens parameter mapping: replaced by phrase-first.** Canva's mandatory `user_intent`
  telemetry string fires 30 times and its `user` token was being read as the `person` key, giving
  Canva a person sink that does not exist.

Two silent-drop bugs in the nested-type reader are worth the same treatment. The first matched
only bracket groups containing no further delimiters, so Todoist's
`object{type:absolute,taskId,due{date,…},…}` never matched and the whole outer level vanished —
which showed up as `PARAM_KEYS["due"]` reading as a dead rule. The second stripped `[...]` as a
numeric range annotation and swallowed every `oneOf[...]` union whole, taking all three Todoist
reminder variants with it. **Both were found by reading the dead-rule list, not the code.**
`--rules` now reports 0 dead entries in both dictionaries and 1 unmapped parameter of 680.

## 23. The third profile axis — runtime

The graph had no notion of *how a connector runs*, and `trigger_action` was standing in for it
with "is the middle node an `automation_hub`" — an archetype guess doing a capability's job.

Measuring it against 178 schemas immediately deletes the interesting category. **There is no
subscribe, webhook, callback or notification-target parameter in any of the 178 tools.** Nothing
here is event-emitting; "schedulable" is therefore not a property of a connector either, because
anything readable can be put behind a cron. The axis that *is* real, and is visible in parameters,
is whether a poll can ask **what changed**:

| mode | count | meaning |
|---|---|---|
| `poll_windowed` | 2 | a read tool takes a typed time-range parameter — Todoist, Vercel |
| `poll_windowed_dsl` | 2 | the time filter exists only inside a query-string language — Gmail's `newer_than:`, Drive's `modifiedTime >` |
| `poll_blind` | 7 | every poll returns the same undifferentiated set |
| `event_push` | **0** | measured, not assumed |

**Google Calendar is `poll_blind`, and it is the sharp case:** `search_events` has no date
parameter of any kind, so "when a meeting is booked, do X" is not buildable from the calendar at
any polling frequency. The dedupe burden has to move into the composing system's own state.

An earlier version of this rule matched name tokens and scored Calendar the *most* pollable
connector in the directory, because `search_events` contains the token `events` — the domain noun,
not a change log. Deriving a schema-grade axis from names is self-defeating; the rule reads
parameters and parameter descriptions only.

`profile.py` approximates the same axis from names for the 453 connectors with no schemas, and
these 11 are the only place that approximation can be scored. **It gets 8 of 11** — barely better
than chance on a two-way split. It misses Gmail (DSL operators are invisible in names), over-claims
Supabase (`get_logs` has no time parameter at all — it is fixed at 24 hours), and under-claims
Vercel (`get_web_analytics` takes `since`/`until` but its name has no temporal token). Directory-
wide runtime figures carry that error bar.

### What it does to `trigger_action`

The motif now counts two ways, and the ratio is the finding:

| model | hub-fired | self-fired |
|---|---|---|
| harvested | 2,030,181 | **5,306** |
| evidence | 27,924 | **1,572** |

**Self-fired trigger→action chains are 0.26% of hub-fired ones.** Almost nothing in this directory
can notice its own change, so almost every unattended pattern needs an automation hub in the
middle — not for routing, but purely to supply the firing. This extends Phase 2's ordering result:
composition is limited by what can be written into, and *automation* is limited by what can be
noticed changing.

Note that `runtime` is name-derived for all but 11 connectors, so both columns carry the 8/11 error
bar above. `engine/combine.py` prints that caveat next to the count rather than in a footnote.

## 24. The operator-payback lens is gone from the scorer

Phase 2 removed the payback framing from the UI. `engine/score.py` kept computing it, so the 14
authored systems were still *ranked* by a composite whose heaviest axis (0.30) was hours reclaimed
per month, valued at an assumed hourly rate against an assumed build cost. A number that changes
when you change your salary is not a fact about a composition, and the unit of work here is the
directory, not an account.

`LEVERAGE` is deleted, not rescaled. `payback` and `cold_start` are gone along with
`HOURLY_RATE_USD` and `VALUE_PER_HOUR_USD`; `hours_reclaimed_per_month` and
`human_minutes_per_week` are deleted from all 14 systems in `data/systems.json`. What replaces it
is **`ROBUSTNESS`** — will this combination keep running — built from the four axes that were
always properties of the composition rather than its owner, plus one Phase 3 made measurable:

| axis | weight |
|---|---|
| trigger | 0.30 |
| degradation | 0.22 |
| auth_surface | 0.18 |
| blast_radius | 0.18 |
| **preconditions** | **0.12** |

`build_hours`, `monthly_run_cost_usd`, `cost_per_run_usd` and `cold_start_days` survive as
descriptive fields. Nothing scores on them, and the UI labels that block "described, not scored".

**`trigger_reality` is also no longer taken on the author's word.** Each system's claimed trigger
is checked against the measured runtime of its own source connectors, with three outcomes rather
than two — the third exists because getting it wrong the first time invented a finding. *Support
Signal → Roadmap* claims `scheduled` while all six of its named sources are `poll_blind`: it fires,
but re-reads the same set every time, and its dedupe burden is real. The three mesh systems are
specified at archetype level with **no named connectors at all**, so there is nothing to check
their claim against; they are reported `unmeasurable`, not failed. Flagging missing evidence as a
failure would have been a fabricated result in exactly the shape this project keeps warning about.

## 25. What Phase 3 still does not do

- **`emits` is untouched.** Input schemas cannot see return shapes. Every emits-derived figure —
  key scarcity, out-degree, donor rankings — is still name-grade.
- **809 connectors have no schemas and will not get them from a session.** The `evidence` model
  remains the honest one to quote, and it is still name-grade for 453 of its 464 members.
- **Preconditions are recorded but not yet enforced in path-finding.** `graph.py` will still route
  through `buy_domain` without noting that `get_purchase_quote` has to precede it. The data is in
  `data/schema_profiles.json`; the pathfinder does not read it.
- **`selectors` are not yet edges.** The fact that Calendar is addressable only by free text is
  reported, not modelled — the edge model still says an edge exists if `emits(A) ∩ consumes(B)` is
  non-empty, with no check that B can actually be *addressed* with what A holds.
- **The 11 are not a random sample.** They are the connectors this account happens to have
  connected, skewed toward developer tools. The 84%/38% precision/recall figures are measured on
  them and generalise only as far as that skew allows.
