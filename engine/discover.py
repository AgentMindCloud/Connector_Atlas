#!/usr/bin/env python3
"""
discover.py — ensemble search over the connector graph. Stdlib only.

    python3 engine/discover.py --buildable   # 6-15 connector, low-auth, real-trigger candidates
    python3 engine/discover.py --mesh        # read-only fan-in meshes (the 150+ tier)
    python3 engine/discover.py --all         # both -> out/candidates.json

Discovery proposes; judgment disposes. This produces a ranked candidate list; the systems
that ship are hand-authored into data/systems.json with build plans and cost models. Both
states are visible in the tool so machine-found and human-authored are never confused.

Two generation modes, because the two tiers obey different physics:

  BUILDABLE — chains. Failure probability compounds per hop, so these stay short and the
              search penalises auth surface and irreversible hops hard.
  MESH      — fan-in. Independent read-only ribs on a shared spine are additive, not
              multiplicative, so N can grow to the read-only ceiling without the blast
              radius growing at all. This is why a 200-sensor mesh is *safer* than a
              7-hop write chain, and it is the whole justification for the 150+ tier.
"""

import argparse, json, os, sys, collections, itertools

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import graph as G  # noqa: E402

# Spine roles — every ensemble needs state, delivery, and something that fires it.
STATE_ARCHES = {"database_warehouse", "file_storage", "memory_context"}
DELIVERY_ARCHES = {"chat_messaging", "email", "notes_docs", "task_pm", "presentations"}
SCHEDULER_ARCHES = {"cloud_infra", "automation_hub"}
MONEY_ARCHES = {"payments_banking", "accounting_billing", "market_data",
                "ecommerce_logistics", "crm_sales", "marketing_analytics"}


def ctx():
    arches, conns = G.load()
    by_arch = collections.defaultdict(list)
    for c in conns:
        by_arch[c["archetype"]].append(c)
    edges = G.arch_edges(arches, include_weak=False)
    return arches, conns, by_arch, edges


def strong(a, field):
    return set(a[field]) - G.WEAK


def marginal_gain(arches, edges, chosen, cand, allow_hubs=False):
    """What does adding `cand` buy, and what does it cost?

    A hub emits and consumes every strong key by definition, so any value function that
    rewards raw key-count hands the whole search to Zapier. That is a true statement about
    reachability and a useless one about design: a hub is another account, another auth
    surface, another vendor's failure modes. Buildable mode excludes hubs outright and
    scores *wiring depth* over key breadth, so candidates differ from each other.
    """
    if cand in chosen:
        return -1e9, {}
    if cand in G.HUB_ARCHES and not allow_hubs:
        return -1e9, {}

    have_keys = set()
    for a in chosen:
        have_keys |= strong(arches[a], "emits")
    new_keys = strong(arches[cand], "emits") - have_keys

    # does it actually wire in, or just sit there?
    inbound = sum(1 for a in chosen if (a, cand) in edges)
    outbound = sum(1 for a in chosen if (cand, a) in edges)
    wired = inbound + outbound
    if not wired:
        return -1e9, {}

    blast = G.SIDE_RANK.get(arches[cand]["side_effects"], 0)
    money = 1 if cand in MONEY_ARCHES else 0
    fb_penalty = 1.8 if cand in G.FALLBACK_ARCHES else 0

    # two-way wiring is worth much more than one-way: it is what creates closure
    gain = (0.8 * len(new_keys) + 1.4 * min(inbound, outbound) + 0.5 * wired
            + 1.6 * money - 1.1 * blast - fb_penalty - 2.0)
    return gain, {"new_keys": sorted(new_keys), "wired_to": wired,
                  "inbound": inbound, "outbound": outbound, "blast": blast}


def has_closure(edges, chosen):
    """Does the archetype set contain a directed cycle — does it read its own output?"""
    sub = {a: [b for b in chosen if (a, b) in edges] for a in chosen}
    WHITE, GREY, BLACK = 0, 1, 2
    color = {a: WHITE for a in chosen}

    def dfs(u):
        color[u] = GREY
        for v in sub[u]:
            if color[v] == GREY:
                return True
            if color[v] == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return any(color[a] == WHITE and dfs(a) for a in chosen)


def discover_buildable(limit=12, size=8):
    arches, conns, by_arch, edges = ctx()
    results = []
    seeds = sorted(MONEY_ARCHES | {"meetings_transcripts", "support_cx", "observability",
                                   "forms_surveys", "web_search", "hr_recruiting",
                                   "vertical_ops", "esignature_docs", "media_av"})
    for seed in seeds:
        for state in ("database_warehouse", "file_storage"):
            chosen = [seed, state]
            trace = []
            while len(chosen) < size:
                best, bestc, bestm = -1e9, None, None
                for cand in arches:
                    g, meta = marginal_gain(arches, edges, chosen, cand)
                    if g <= -1e8:
                        continue
                    # a buildable system must acquire a delivery channel and a scheduler
                    if cand in DELIVERY_ARCHES and not (set(chosen) & DELIVERY_ARCHES):
                        g += 3.0
                    if cand in SCHEDULER_ARCHES and not (set(chosen) & SCHEDULER_ARCHES):
                        g += 2.5
                    # keep candidates distinct: mild affinity for the seed's own neighbourhood
                    if (seed, cand) in edges and (cand, seed) in edges:
                        g += 1.2
                    if g > best:
                        best, bestc, bestm = g, cand, meta
                if bestc is None or best <= -1e8 or best < 0:
                    break
                chosen.append(bestc); trace.append({bestc: bestm})
            keys = set()
            for a in chosen:
                keys |= strong(arches[a], "emits")
            blast = max(G.SIDE_RANK.get(arches[a]["side_effects"], 0) for a in chosen)
            results.append({
                "mode": "buildable",
                "seed": seed,
                "archetypes": chosen,
                "connector_count": len(chosen),
                "join_keys": sorted(keys),
                "feedback_closure": has_closure(edges, chosen),
                "blast_radius": blast,
                "has_delivery": bool(set(chosen) & DELIVERY_ARCHES),
                "has_scheduler": bool(set(chosen) & SCHEDULER_ARCHES),
                "instantiation": {a: [c["name"] for c in sorted(
                    by_arch[a], key=lambda c: (c.get("popular_rank") or 999, c["name"]))[:3]]
                    for a in chosen},
            })
    seen, uniq = set(), []
    for r in results:
        k = tuple(sorted(r["archetypes"]))
        if k not in seen:
            seen.add(k); uniq.append(r)
    uniq.sort(key=lambda r: (-len(r["join_keys"]), r["blast_radius"], -r["connector_count"]))
    return uniq[:limit]


def discover_mesh():
    """Read-only fan-in meshes. Blast radius is 0 by construction, so N is free."""
    arches, conns, by_arch, edges = ctx()
    read_only = [c for c in conns if c["side_effects"] == "read"]
    by_arch_ro = collections.defaultdict(list)
    for c in read_only:
        by_arch_ro[c["archetype"]].append(c)

    families = {
        "market_omniscience": ["market_data", "research_science", "marketing_analytics",
                               "gov_public_data", "web_search", "bi_analytics",
                               "prospecting_enrichment", "job_search"],
        "risk_compliance_radar": ["security", "legal", "gov_public_data", "market_data",
                                  "observability", "identity_verification", "code_context"],
        "demand_signal_mesh": ["marketing_analytics", "support_cx", "web_search",
                               "bi_analytics", "market_data", "local_services",
                               "weather_geo", "job_search"],
    }
    out = []
    for name, fams in families.items():
        members = [c for f in fams for c in by_arch_ro.get(f, [])]
        keys = set()
        for c in members:
            keys |= (set(c["emits"]) - G.WEAK)
        out.append({
            "mode": "mesh",
            "name": name,
            "archetypes": fams,
            "connector_count": len(members),
            "join_keys": sorted(keys),
            "blast_radius": 0,
            "fan_in": len(members),
            "chain_depth": 3,
            "per_archetype": {f: len(by_arch_ro.get(f, [])) for f in fams},
            "sample": [c["name"] for c in members[:14]],
        })
    out.append({
        "mode": "mesh",
        "name": "maximum_safe_mesh",
        "archetypes": sorted({c["archetype"] for c in read_only}),
        "connector_count": len(read_only),
        "join_keys": sorted({k for c in read_only for k in set(c["emits"]) - G.WEAK}),
        "blast_radius": 0,
        "fan_in": len(read_only),
        "chain_depth": 3,
        "per_archetype": {a: len(v) for a, v in sorted(
            by_arch_ro.items(), key=lambda t: -len(t[1]))},
        "note": "Every read-only connector in the directory. This is the hard ceiling on a "
                "zero-blast-radius system — bounded by the registry, not by imagination.",
    })
    out.sort(key=lambda r: -r["connector_count"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buildable", action="store_true")
    ap.add_argument("--mesh", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if not (a.buildable or a.mesh or a.all):
        a.all = True

    res = {}
    if a.buildable or a.all:
        res["buildable"] = discover_buildable()
        print(f"buildable candidates: {len(res['buildable'])}")
        for r in res["buildable"][:8]:
            print(f"  [{len(r['join_keys'])} keys, blast {r['blast_radius']}, "
                  f"closure {str(r['feedback_closure']):5s}] {' -> '.join(r['archetypes'])}")
    if a.mesh or a.all:
        res["mesh"] = discover_mesh()
        print(f"\nmesh candidates: {len(res['mesh'])}")
        for r in res["mesh"]:
            print(f"  {r['connector_count']:4d} connectors, {len(r['join_keys'])} keys, "
                  f"blast {r['blast_radius']}  {r['name']}")

    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    p = os.path.join(ROOT, "out", "candidates.json")
    json.dump(res, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
