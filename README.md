# Connector Atlas

A composition engine over the full Claude connector directory — 821 connectors, 47 archetypes,
1,610 derived edges — plus 14 scored multi-connector systems with build plans and cost models.

Everything is generated from `data/`. Edges are **derived, never drawn**: an edge exists when a key
one connector emits is a key another consumes, so the picture cannot drift from the registry.

**Read [`docs/METHOD.md`](docs/METHOD.md) before quoting any number.** It records how each figure
was produced and where the model is weak.

---

## The deliverable

```bash
python3 engine/render.py        # -> out/atlas_v5.html  (single self-contained file)
```

One page, two halves that talk to each other:

- **The map** — 47 archetype constellations on a rotating sphere, each connector a node, edges
  coloured by join key. Search, zoom, click any node for its profile.
- **The systems** — 14 ranked systems. Pick one and its connectors light up on the map while its
  ribs draw as edges; the panel carries the full composition block, the nine evaluators, the cost
  model, and the build plan.
- **The pathfinder** — join any two of the 821 in direct or bridge mode, with the price of each
  bridge hop stated.

## Toolkit

```bash
python3 engine/graph.py --validate     # key-vocabulary check; fails loudly on drift
python3 engine/graph.py --analyze      # all-pairs, centrality, key scarcity -> out/analysis.json
python3 engine/graph.py --path A B     # direct-edge check between any two connectors
python3 engine/discover.py --all       # ensemble candidate search -> out/candidates.json
python3 engine/score.py                # score data/systems.json -> out/scored.json
python3 engine/render.py               # build the tool -> out/atlas_v5.html
```

Stdlib only. No dependencies, no build step.

## Layout

```
data/registry_full.json   entire directory (820, DIRECTORY tier)
data/registry.json        curated overrides — 8 VERIFIED against live tool schemas
data/systems.json         the findings: 14 systems, authored, machine-scored
engine/graph.py           merge, validate, all-pairs, centrality
engine/discover.py        ensemble search (buildable chains + read-only meshes)
engine/score.py           9 evaluators, LEVERAGE + CAPABILITY, tiering
engine/render.py          builds the single-file tool
engine/template.html      the page (data injected at __DATA__)
out/                      generated — atlas_v5.html, analysis.json, scored.json, candidates.json
docs/METHOD.md            method, caveats, and the defects found
```

## Three results worth knowing

**`url` carries a quarter of the graph.** Removing it destroys 389 of 1,610 archetype edges. "A URL
in a text field" is measurably the most load-bearing integration primitive in the directory.

**The two lenses disagree, and that is the finding.** The fastest-payback system (*Inbox →
Commitment Ledger*, 4 connectors, break-even 4.1 months) scores capability tier **C**. The
highest-capability system (*Maximum Safe Mesh*, 293 connectors) **never breaks even**. Only
*Personal Operating System* scores well on both — so it is the one to build first, and it is also
the only system whose every connector was verified this session.

**150+ connectors is coherent in exactly one topology.** Count scales safely by fan-in breadth and
dangerously by chain depth: a 200-sensor read-only mesh has a smaller blast radius than a 7-hop
write chain. 293 connectors carry `side_effects: read`, which is the hard ceiling on a system that
cannot break anything it touches.

## Verified constraints that killed designs

Loading real tool schemas contradicted the inherited profiles in ways that changed the systems:

- **Gmail has no send tool.** Draft-only by construction, not by policy.
- **Google Calendar exposes only semantic `search_events`** — it cannot enumerate a date range,
  which is fatal to any "what's on today" digest and to interview scheduling.
- **Cloudflare cannot deploy a Worker** — the cron that makes anything "automatic" ships out of band.
- **Vercel can spend real money** (`buy_domain`, `buy_pro`, `buy_credits`).
- **All 5 Supabase projects observed `INACTIVE`** — the spine every ensemble depends on is paused.

Verification *reduced* measured reachability (97.42% → 97.30%). That is it working: it deletes
edges that were never real.
