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
