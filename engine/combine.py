#!/usr/bin/env python3
"""
combine.py — the combination space of 821 connectors, described honestly. Stdlib only.

    python3 engine/combine.py --all          # everything, -> out/combine_<model>.json
    python3 engine/combine.py --pairs        # exhaustive, all 673,220 ordered pairs
    python3 engine/combine.py --triples      # exhaustive, all 91,894,530 unordered triples
    python3 engine/combine.py --motifs       # the nine patterns, counted
    python3 engine/combine.py --questions    # donors, sinks, isolates, cheapest upgrades
    python3 engine/combine.py --diff         # inherited model vs harvested model
    python3 engine/combine.py --model inherited|harvested|evidence   (default harvested)

Three regimes, because brute force dies at four
------------------------------------------------
  pairs    673,220 ordered      exhaustive, every pair classified
  triples   91,894,530 unordered exhaustive, connected ones classified by shape
  N > 3    4-subsets alone are 7.5e10   NOT enumerated -- motif census instead

That last line is the honest part and it is worth saying plainly rather than
burying: you cannot enumerate every combination of 821 connectors and you do not
need to. A 10-subset is past 1e20. What is computable, and what actually answers
"how does everything combine", is exhaustive pairs, exhaustive connected triples,
and then a census of which *patterns* the larger space contains and how many
instantiations of each exist. Nothing here claims to have walked the space.

How the exhaustive claims are true
-----------------------------------
821 connectors collapse to a few hundred distinct join profiles, so pair and
triple structure is computed exactly over profile CLASSES and then expanded by
class size. Every connector pair and triple is accounted for; none is sampled.
The class matrix is the pair matrix, losslessly compressed -- 236x236 instead of
821x821 -- and out/pairs_<model>.json ships the class index so any of the 673,220
pairs can be resolved in two lookups.
"""

import argparse, collections, itertools, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import graph as G  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")


# --------------------------------------------------------------------- scaffold

def build(model, include_weak=False):
    arches, conns = G.load(model)
    classes, cindex = G.profile_classes(conns, include_weak)
    n = len(classes)
    sizes = [len(m) for _, m in classes]
    # Dense boolean adjacency plus the join keys, both at class level.
    adj = [[False] * n for _ in range(n)]
    keys = {}
    for i, ((ei, _), _) in enumerate(classes):
        for j, ((_, cj), _) in enumerate(classes):
            k = ei & cj
            if k and not (i == j and not k):
                adj[i][j] = bool(k)
                if k:
                    keys[(i, j)] = sorted(k)
    return arches, conns, classes, cindex, sizes, adj, keys


# ------------------------------------------------------------------ 1. PAIRS

def pairs(classes, sizes, adj, keys, blocked=frozenset()):
    """Every ordered pair classified: direct (with keys) / k hops / unreachable."""
    n = len(classes)
    adj_list = {i: [j for j in range(n) if adj[i][j]] for i in range(n)}
    dist = G.bfs_all_pairs(adj_list, n, blocked)
    hist = collections.Counter()
    total = sum(sizes)
    for i in range(n):
        for j in range(n):
            d = dist[i][j]
            if i == j:
                # Two DIFFERENT connectors that share a profile class: they are
                # joined iff the class has a self-edge. n*(n-1) such ordered pairs.
                d = 1 if adj[i][i] else -1
                cnt = sizes[i] * (sizes[i] - 1)
            else:
                cnt = sizes[i] * sizes[j]
            hist[d] += cnt
    return dist, hist, total * (total - 1)


# ----------------------------------------------------------------- 2. TRIPLES

# The four shapes PROJECT.md names. Their fingerprints are DERIVED from canonical
# instances below rather than written out by hand: the first version hand-wrote
# them, got the tuple ordering wrong (sorted() is lexicographic, so a chain is
# [(0,1),(1,0),(1,1)] and not [(0,1),(1,1),(1,0)]), and silently matched nothing.
# Building them from the same function that classifies makes that class of bug
# impossible. Anything outside the four is reported by its own fingerprint rather
# than forced into a bucket it does not fit.
_CANON = {
    "chain   A->B->C":   (1, 0, 0, 0, 1, 0),
    "fan-in  A,B->C":    (0, 0, 1, 0, 1, 0),
    "fan-out A->B,C":    (1, 0, 1, 0, 0, 0),
    "cycle   A->B->C->A": (1, 0, 0, 1, 1, 0),
}


def triple_shape(a01, a10, a02, a20, a12, a21):
    """Return (n_arcs, canonical degree fingerprint) or None if disconnected.

    Three nodes are connected iff the underlying undirected graph has >= 2 edges:
    with two edges every node is incident to one, with one edge a node is isolated.
    """
    u01, u02, u12 = a01 or a10, a02 or a20, a12 or a21
    if (u01 + u02 + u12) < 2:
        return None
    out = (a01 + a02, a10 + a12, a20 + a21)
    ind = (a10 + a20, a01 + a21, a02 + a12)
    arcs = a01 + a10 + a02 + a20 + a12 + a21
    return arcs, tuple(sorted(zip(ind, out)))


SHAPE_NAMES = {}


def _init_shapes():
    for name, arcs in _CANON.items():
        SHAPE_NAMES[triple_shape(*arcs)] = name


def triples(classes, sizes, adj):
    """Exhaustive over all C(821,3) unordered triples, via class combinations.

    Every triple of connectors falls into exactly one of three cases -- three
    distinct classes, two from one class, or all three from one class -- and each
    case is counted with the right binomial. Nothing is sampled.
    """
    n = len(classes)
    A = adj
    census = collections.Counter()
    connected = 0
    checked = 0

    # case 1: three distinct classes
    rng = range(n)
    for i in rng:
        Ai, s_i = A[i], sizes[i]
        for j in range(i + 1, n):
            a01, a10 = Ai[j], A[j][i]
            sij = s_i * sizes[j]
            Aj = A[j]
            for k in range(j + 1, n):
                sh = triple_shape(a01, a10, Ai[k], A[k][i], Aj[k], A[k][j])
                cnt = sij * sizes[k]
                checked += cnt
                if sh:
                    census[sh] += cnt
                    connected += cnt

    # case 2: two connectors from class i, one from class j (i != j)
    for i in rng:
        si = sizes[i]
        if si < 2:
            continue
        pair_i = si * (si - 1) // 2
        self_i = A[i][i]
        for j in rng:
            if j == i or not sizes[j]:
                continue
            sh = triple_shape(self_i, self_i, A[i][j], A[j][i], A[i][j], A[j][i])
            cnt = pair_i * sizes[j]
            checked += cnt
            if sh:
                census[sh] += cnt
                connected += cnt

    # case 3: all three from one class
    for i in rng:
        si = sizes[i]
        if si < 3:
            continue
        s = A[i][i]
        sh = triple_shape(s, s, s, s, s, s)
        cnt = si * (si - 1) * (si - 2) // 6
        checked += cnt
        if sh:
            census[sh] += cnt
            connected += cnt

    return census, connected, checked


# ------------------------------------------------------------------ 3. MOTIFS

def motifs(conns, classes, cindex, sizes, adj):
    """Census of the nine composition patterns over the harvested graph.

    A motif is a design pattern, not a graph primitive, so each one is given an
    explicit structural encoding below and the encoding is reported alongside the
    count. Disagreeing with an encoding is then a specific, checkable objection
    rather than a vague one.

    Counts for the fan-shaped motifs are subset counts and are astronomically
    large by construction: a sink with in-degree d admits 2^d - d - 1 distinct
    Enrich instantiations of size >= 2. That is the point -- these numbers are
    what "the combination space beyond triples" actually means, and they are
    exact, not estimated.
    """
    n = len(classes)
    strong = G.STRONG
    prof = [(e, c) for (e, c), _ in classes]
    rank = G.SIDE_RANK

    # Connector-level in/out degree, computed via classes then expanded.
    out_deg, in_deg = [0] * n, [0] * n
    for i in range(n):
        for j in range(n):
            if adj[i][j]:
                out_deg[i] += sizes[j] - (1 if i == j else 0)
                in_deg[j] += sizes[i] - (1 if i == j else 0)

    def subsets_ge2(d):
        """Every subset of size >= 2 of a d-element neighbourhood."""
        return (1 << d) - d - 1 if d >= 2 else 0

    def bounded(d, lo=2, hi=5):
        """Subsets of size lo..hi. The unbounded count for a sink with in-degree
        700 is a 200-digit number: exact, and useless. composition.md's own advice
        for Digest is 'cap the sources', so the practical census caps them too and
        reports the unbounded magnitude separately rather than pretending a
        700-source Enrich is a thing anyone would build."""
        return sum(math.comb(d, r) for r in range(lo, min(hi, d) + 1))

    def fan_report(degs, weights=None):
        """degs: per-connector degree list. Returns a readable census."""
        unb = sum(subsets_ge2(d) for d in degs)
        return {
            "instantiations_size_2_to_5": sum(bounded(d) for d in degs),
            "instantiations_all_sizes_log10": round(math.log10(unb), 1) if unb else None,
            "max_degree": max(degs, default=0),
            "nodes_with_degree_ge_2": sum(1 for d in degs if d >= 2),
        }

    # Class-level side-effect maxima, for the motifs that care about writes.
    cls_writes = [any(rank[c["side_effects"]] >= rank["create"] for c in m)
                  for _, m in classes]
    cls_mutates = [any(rank[c["side_effects"]] >= rank["mutate"] for c in m)
                   for _, m in classes]
    cls_irrev = [any(c["side_effects"] == "irreversible" for c in m) for _, m in classes]
    # Third axis: how many members of each profile class can be polled for change.
    n_pollable = [sum(1 for c in m if c.get("runtime", "unmeasured") not in
                      ("poll_blind", "unmeasured")) for _, m in classes]
    n_writes = [sum(1 for c in m if rank[c["side_effects"]] >= rank["create"])
                for _, m in classes]
    n_mut = [sum(1 for c in m if rank[c["side_effects"]] >= rank["mutate"]) for _, m in classes]
    n_irr = [sum(1 for c in m if c["side_effects"] == "irreversible") for _, m in classes]

    hub_cls = [any(c["archetype"] in G.HUB_ARCHES for c in m) for _, m in classes]

    M = {}

    # 1. Pipeline — A -> B -> C, a linear two-hop with a real transform between.
    n_pipe = 0
    for i in range(n):
        for j in range(n):
            if not adj[i][j]:
                continue
            for k in range(n):
                if adj[j][k]:
                    n_pipe += sizes[i] * sizes[j] * sizes[k]
    M["pipeline"] = {"encoding": "ordered A->B->C, any three connectors (repeats allowed: "
                                 "two members of one class are two different connectors)",
                     "count": n_pipe}

    # 2. Enrich — one sink, >=2 distinct sources. Fan IN.
    in_per_conn = [in_deg[i] for i in range(n) for _ in range(sizes[i])]
    M["enrich"] = dict({"encoding": "for each connector S, subsets of its in-neighbourhood "
                                    "of size >= 2; summed over all S"},
                       **fan_report(in_per_conn))

    # 3. Reconcile — A <-> B, both directions exist, compared not synced.
    recon = 0
    for i in range(n):
        for j in range(i, n):
            if adj[i][j] and adj[j][i]:
                recon += (sizes[i] * (sizes[i] - 1) // 2) if i == j else sizes[i] * sizes[j]
    M["reconcile"] = {"encoding": "unordered pairs with edges in BOTH directions",
                      "count": recon}

    # 4. Fan-out — one source, >=2 distinct sinks.
    out_per_conn = [out_deg[i] for i in range(n) for _ in range(sizes[i])]
    M["fan_out"] = dict({"encoding": "for each connector A, subsets of its out-neighbourhood "
                                     "of size >= 2; summed over all A"},
                        **fan_report(out_per_conn))

    # 5. Digest — fan-in whose sink can actually produce an artifact.
    dig_degs = [in_deg[i] for i in range(n) for _ in range(n_writes[i])]
    M["digest"] = dict({"encoding": "Enrich, restricted to sinks whose side-effect class is "
                                    "create or above -- the sink must be able to emit an artifact"},
                       **fan_report(dig_degs))

    # 6. Trigger -> Action — needs something that fires it, and Phase 3 replaced
    #    the proxy for that with a measurement.
    #
    #    Through Phase 2 this was "A -> HUB -> B where HUB is an automation_hub",
    #    i.e. the firing mechanism was assumed to be a property of an ARCHETYPE.
    #    The runtime axis makes it a property of the SOURCE: a trigger needs the
    #    A end to answer "what changed since I last looked". Connectors whose
    #    reads take no time filter cannot, at any polling frequency, so a chain
    #    starting at one is not self-triggering however many hubs follow it.
    #
    #    Both counts are reported because they answer different questions.
    #    hub_fired is the buildable-today number and needs a hub account.
    #    self_fired needs no hub at all but needs A to be pollable for change.
    trig_hub = 0
    for h in range(n):
        if not hub_cls[h]:
            continue
        srcs = sum(sizes[i] for i in range(n) if adj[i][h])
        sinks = sum(n_writes[k] for k in range(n) if adj[h][k])
        trig_hub += srcs * sizes[h] * sinks
    trig_self = 0
    for i in range(n):
        if not n_pollable[i]:
            continue
        sinks = sum(n_writes[k] for k in range(n) if adj[i][k])
        trig_self += n_pollable[i] * sinks
    M["trigger_action"] = {"encoding": "hub_fired: A -> HUB -> B, HUB an automation_hub "
                                       "and B a writer. self_fired: A -> B where A is "
                                       "pollable for change (runtime != poll_blind) and "
                                       "B can write — no hub required.",
                           "count": trig_hub + trig_self,
                           "hub_fired": trig_hub,
                           "self_fired": trig_self,
                           "caveat": "runtime is name-derived for all but the 11 "
                                     "schema-measured connectors, and scored 8/11 "
                                     "against them — see engine/schema.py --delta"}

    # 7. Mirror — Reconcile where both sides can write back.
    mir = 0
    for i in range(n):
        for j in range(i, n):
            if adj[i][j] and adj[j][i]:
                if i == j:
                    mir += n_mut[i] * (n_mut[i] - 1) // 2
                elif cls_mutates[i] and cls_mutates[j]:
                    mir += n_mut[i] * n_mut[j]
    M["mirror"] = {"encoding": "Reconcile pairs where BOTH connectors are mutate or above",
                   "count": mir}

    # 8. Materialize — an edge into a durable artifact sink.
    mat = 0
    for j in range(n):
        if "file" not in prof[j][1]:
            continue
        if not cls_writes[j]:
            continue
        mat += sum(sizes[i] for i in range(n) if adj[i][j]) * n_writes[j]
    M["materialize"] = {"encoding": "edges A->B where B consumes `file` and B can write, "
                                    "i.e. the output lands somewhere durable",
                        "count": mat}

    # 9. Escalate — an irreversible sink for which a safer sink sharing a join key
    #    also exists, so a threshold policy is actually available.
    esc = 0
    for i in range(n):
        if not sizes[i]:
            continue
        risky = [j for j in range(n) if adj[i][j] and cls_irrev[j]]
        if not risky:
            continue
        safe_keys = set()
        for j in range(n):
            if adj[i][j] and n_writes[j] > n_irr[j]:
                safe_keys |= (prof[i][0] & prof[j][1]) & strong
        for j in risky:
            if (prof[i][0] & prof[j][1]) & strong & safe_keys:
                esc += sizes[i] * n_irr[j]
    M["escalate"] = {"encoding": "A->B with B irreversible, where A also reaches a "
                                 "non-irreversible sink on the same join key -- so a "
                                 "'automate below the threshold' policy has somewhere to go",
                     "count": esc}
    return M


# --------------------------------------------------------------- 4. QUESTIONS

def questions(conns, classes, cindex, sizes, adj, keys):
    n = len(classes)
    strong = G.STRONG
    prof = [(e, c) for (e, c), _ in classes]

    out_deg, in_deg = [0] * n, [0] * n
    for i in range(n):
        for j in range(n):
            if adj[i][j]:
                out_deg[i] += sizes[j] - (1 if i == j else 0)
                in_deg[j] += sizes[i] - (1 if i == j else 0)

    def top(vec, k=8):
        order = sorted(range(n), key=lambda i: -vec[i])
        res = []
        for i in order:
            if not sizes[i] or vec[i] == 0:
                continue
            ex = classes[i][1][0]
            res.append({"example": ex["name"], "tier": ex.get("tier", "DIRECTORY"),
                        "class_size": sizes[i],
                        "emits": sorted(prof[i][0]), "consumes": sorted(prof[i][1]),
                        "degree": vec[i]})
            if len(res) >= k:
                break
        return res

    # "Isolated" here means isolated on STRONG keys: a connector emitting only
    # text/person/vendor_id has no strong join to anything and is unreachable in
    # the regime every other number on this page is computed in.
    isolates = [c["name"] for i in range(n) if out_deg[i] == 0 and in_deg[i] == 0
                for c in classes[i][1]]

    # Cheapest profile upgrade: for each single strong key, how many NEW ordered
    # pairs would become directly connected if one connector gained it?
    consumers = {k: sum(sizes[j] for j in range(n) if k in prof[j][1]) for k in strong}
    emitters = {k: sum(sizes[i] for i in range(n) if k in prof[i][0]) for k in strong}

    upgrade = []
    for i in range(n):
        if not sizes[i]:
            continue
        cur_out = {j for j in range(n) if adj[i][j]}
        best = None
        for k in strong:
            if k in prof[i][0]:
                continue
            gained = sum(sizes[j] for j in range(n)
                         if j not in cur_out and k in prof[j][1])
            if best is None or gained > best[1]:
                best = (k, gained)
        if best and best[1]:
            upgrade.append({"connector": classes[i][1][0]["name"], "class_size": sizes[i],
                            "add_key": best[0], "new_out_edges_each": best[1]})
    upgrade.sort(key=lambda r: -r["new_out_edges_each"])

    # Which single NEW connector, added to the directory, creates the most new
    # pair-connections? A new connector is a choice of (emits, consumes) subsets;
    # the best one is the full strong vocabulary on both sides, so the interesting
    # question is which single key pays most, which is the table below.
    key_pay = sorted(
        ({"key": k, "reaches_as_emitter": consumers[k], "reachable_as_consumer": emitters[k],
          "new_pairs_if_universal_bridge": consumers[k] + emitters[k]} for k in strong),
        key=lambda r: -r["new_pairs_if_universal_bridge"])

    return {
        "universal_donors": top(out_deg),
        "universal_sinks": top(in_deg),
        "isolates": {"count": len(isolates), "definition": "no strong-key edge in "
                     "either direction; weak keys (text/person/vendor_id) excluded",
                     "sample": sorted(isolates)[:25]},
        "cheapest_profile_upgrade": upgrade[:12],
        "key_leverage": key_pay,
    }


# -------------------------------------------------------------------- 5. DIFF

def diff():
    """Inherited vs harvested, connector for connector. The headline result."""
    a_arch, a_conns = G.load("inherited")
    b_arch, b_conns = G.load("harvested")
    A = {c["name"]: c for c in a_conns}
    B = {c["name"]: c for c in b_conns}
    shared = sorted(set(A) & set(B))

    moved = {"emits": 0, "consumes": 0, "side_effects": 0}
    lost_consume, gained_read = [], []
    sev_up = sev_down = 0
    for nme in shared:
        a, b = A[nme], B[nme]
        if set(a["emits"]) != set(b["emits"]):
            moved["emits"] += 1
        if set(a["consumes"]) != set(b["consumes"]):
            moved["consumes"] += 1
        if a["side_effects"] != b["side_effects"]:
            moved["side_effects"] += 1
            if G.SIDE_RANK[b["side_effects"]] > G.SIDE_RANK[a["side_effects"]]:
                sev_up += 1
            else:
                sev_down += 1
        if a["consumes"] and not b["consumes"]:
            lost_consume.append(nme)
        if a["side_effects"] != "read" and b["side_effects"] == "read":
            gained_read.append(nme)

    ra = G.analyze(False, "inherited")["reachability"]
    rb = G.analyze(False, "harvested")["reachability"]

    _, _, ca, ia, sa, ada, ka = build("inherited")
    _, _, cb, ib, sb, adb, kb = build("harvested")

    def strong_edges(classes, sizes, adj):
        tot = 0
        for i in range(len(classes)):
            for j in range(len(classes)):
                if adj[i][j]:
                    tot += sizes[i] * (sizes[i] - 1) if i == j else sizes[i] * sizes[j]
        return tot

    ea, eb = strong_edges(ca, sa, ada), strong_edges(cb, sb, adb)
    return {
        "connectors_compared": len(shared),
        "profiles_changed": moved,
        "side_effect_severity": {"increased": sev_up, "decreased": sev_down},
        "connectors_that_now_consume_nothing": {
            "count": len(lost_consume),
            "meaning": "every inbound edge these connectors had in the inherited model "
                       "was fictional -- the archetype gave them a consumes set their "
                       "tool list does not support",
            "sample": lost_consume[:25]},
        "connectors_now_read_only": len(gained_read),
        "distinct_join_profiles": {"inherited": len(ca), "harvested": len(cb)},
        "direct_ordered_pairs": {"regime": "with hubs; a direct edge is a direct edge",
                                 "inherited": ea, "harvested": eb,
                                 "delta": eb - ea,
                                 "pct_of_inherited_surviving": round(100.0 * eb / ea, 1) if ea else 0},
        "reachability": {k: {"inherited": ra[k], "harvested": rb[k]} for k in ra},
    }


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=("inherited", "harvested", "evidence"), default="harvested")
    for f in ("pairs", "triples", "motifs", "questions", "diff", "all"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    want = {f: getattr(a, f) or a.all for f in ("pairs", "triples", "motifs", "questions", "diff")}
    if not any(want.values()):
        ap.print_help(); return 0

    _init_shapes()
    arches, conns, classes, cindex, sizes, adj, keys = build(a.model)
    n, N = len(classes), len(conns)
    res = {"model": a.model, "connectors": N, "distinct_join_profiles": n}
    print(f"model={a.model}  connectors={N}  distinct join profiles={n}")
    os.makedirs(OUT, exist_ok=True)

    if want["pairs"]:
        hub = {i for i, (_, m) in enumerate(classes)
               if all(c["archetype"] in G.HUB_ARCHES for c in m)}
        fb = {i for i, (_, m) in enumerate(classes)
              if all(c["archetype"] in G.FALLBACK_ARCHES for c in m)}
        dist, hist, total = pairs(classes, sizes, adj, keys, hub | fb)
        _, hist_h, _ = pairs(classes, sizes, adj, keys, frozenset())
        res["pairs"] = {
            "ordered_pairs_total": total,
            "exhaustive": True,
            "native_only": {str(k): v for k, v in sorted(hist.items())},
            "with_hubs": {str(k): v for k, v in sorted(hist_h.items())},
            "direct_pct": round(100.0 * hist[1] / total, 2),
        }
        print(f"  PAIRS   {total:,} ordered, exhaustive")
        for lbl, h in (("native only", hist), ("with hubs ", hist_h)):
            print(f"          {lbl}: {h[1]:>7,} direct ({100.0*h[1]/total:5.2f}%)  "
                  f"{h[2]:>7,} at 2 hops  {h[-1]:>7,} unreachable")
        json.dump({"model": a.model,
                   "note": "class_of maps every connector to a row/col of the class matrix; "
                           "matrix[i][j] is the hop distance, -1 unreachable. This is the "
                           "full 821x821 pair matrix, losslessly compressed.",
                   "class_of": {c["name"]: cindex[c["name"]] for c in conns},
                   "class_profiles": [{"emits": sorted(e), "consumes": sorted(cc),
                                       "size": len(m)} for (e, cc), m in classes],
                   "keys": {f"{i},{j}": v for (i, j), v in keys.items()},
                   "matrix": dist},
                  open(os.path.join(OUT, f"pairs_{a.model}.json"), "w"), separators=(",", ":"))
        print(f"          -> out/pairs_{a.model}.json")

    if want["triples"]:
        census, connected, checked = triples(classes, sizes, adj)
        exp = math.comb(N, 3)
        named = collections.Counter()
        for (arcs, fp), cnt in census.items():
            named[SHAPE_NAMES.get((arcs, fp), f"other  arcs={arcs} deg={fp}")] += cnt
        res["triples"] = {
            "unordered_triples_total": exp,
            "accounted_for": checked,
            "exhaustive": checked == exp,
            "connected": connected,
            "connected_pct": round(100.0 * connected / exp, 2),
            "by_shape": dict(named.most_common()),
        }
        print(f"  TRIPLES {exp:,} unordered, accounted for {checked:,} "
              f"({'EXHAUSTIVE' if checked == exp else 'MISMATCH'}): "
              f"{connected:,} connected ({100.0*connected/exp:.2f}%)")
        for k, v in named.most_common(6):
            print(f"          {k:34} {v:,}")

    if want["motifs"]:
        res["motifs"] = motifs(conns, classes, cindex, sizes, adj)
        print("  MOTIFS  (nine patterns; structural encoding for each is in the JSON)")
        for k, v in res["motifs"].items():
            if "count" in v:
                print(f"          {k:16} {v['count']:>18,}")
            else:
                print(f"          {k:16} {v['instantiations_size_2_to_5']:>18,}  "
                      f"(sizes 2-5; all sizes ~1e{v['instantiations_all_sizes_log10']:.0f}, "
                      f"max degree {v['max_degree']})")

    if want["questions"]:
        res["questions"] = questions(conns, classes, cindex, sizes, adj, keys)
        q = res["questions"]
        fmt = lambda rows: ", ".join("{} {} [{}]".format(d["example"], d["degree"], d["tier"][:4]) for d in rows)
        print(f"  DONORS   {fmt(q['universal_donors'][:4])}")
        print(f"  SINKS    {fmt(q['universal_sinks'][:4])}")
        print(f"  ISOLATES {q['isolates']['count']}")
        print("  KEY LEVERAGE " + ", ".join(
            "{}={}".format(r["key"], r["new_pairs_if_universal_bridge"])
            for r in q["key_leverage"][:5]))

    if want["diff"]:
        res["diff"] = diff()
        d = res["diff"]
        print(f"  DIFF    profiles changed: emits {d['profiles_changed']['emits']}, "
              f"consumes {d['profiles_changed']['consumes']}, "
              f"side_effects {d['profiles_changed']['side_effects']}")
        print(f"          direct ordered pairs {d['direct_ordered_pairs']['inherited']:,} -> "
              f"{d['direct_ordered_pairs']['harvested']:,} "
              f"({d['direct_ordered_pairs']['pct_of_inherited_surviving']}% survive)")
        print(f"          now consume nothing: "
              f"{d['connectors_that_now_consume_nothing']['count']}")

    p = os.path.join(OUT, f"combine_{a.model}.json")
    json.dump(res, open(p, "w", encoding="utf-8"), indent=1)
    print(f"-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
