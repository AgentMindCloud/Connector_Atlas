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
