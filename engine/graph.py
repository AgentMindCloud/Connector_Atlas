#!/usr/bin/env python3
"""
graph.py — the composition graph over the whole connector directory. Stdlib only.

    python3 engine/graph.py --validate     # key-vocabulary check, fail loudly on drift
    python3 engine/graph.py --analyze      # all-pairs + centrality -> out/analysis.json
    python3 engine/graph.py --path A B     # cross-check against skill's atlas.py

Model
-----
Every connector has an `emits` set and a `consumes` set. A directed edge A -> B exists
iff emits(A) & consumes(B) is non-empty; the intersection is the edge's join keys.
Edges are DERIVED, never drawn, so the graph cannot drift from the registry.

The honest scale caveat
-----------------------
Connectors inherit emits/consumes from their archetype unless a curated profile overrides
them. So 820 connectors collapse into a much smaller number of distinct *join profiles*.
All-pairs is computed exactly over those profile classes and then expanded by class size,
which gives the true 820x819 answer without materialising 671k redundant edges.
"""

import argparse, json, os, collections, itertools

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out")

# Same semantics as the skill's atlas.py, kept identical on purpose so the two agree.
WEAK = {"text", "person", "vendor_id"}
HUB_ARCHES = {"automation_hub"}
FALLBACK_ARCHES = {"browser_automation", "desktop_local"}

# The full key vocabulary. Anything outside this set is a typo that would silently
# produce zero edges -- which is exactly the `project_name` bug this validator exists
# to prevent from recurring.
VOCAB = {
    "code", "company", "domain", "email", "file", "geo", "image", "media", "money",
    "person", "phone", "project", "rows", "text", "ticker", "timestamp", "url", "vendor_id",
}
STRONG = VOCAB - WEAK

SIDE_RANK = {"read": 0, "create": 1, "mutate": 2, "irreversible": 3}
TIER_RANK = {"VERIFIED": 0, "DOCUMENTED": 1, "DIRECTORY": 2, "ASSUMED": 3}


# ---------------------------------------------------------------- load / validate

def load(model="inherited"):
    """Merge registry_full (archetype-inherited) with registry.json (curated wins).

    Three models, and the third exists because the second is a mixture:

      inherited  every profile from its archetype. Session 1's model, kept as the
                 baseline every harvested number is diffed against.
      harvested  data/profiles.json overlaid. 464 connectors get profiles derived
                 from real tool names; the other 357 still carry the archetype
                 guess and are tagged DIRECTORY. Comparable connector-for-connector
                 with `inherited`, which is what makes the diff meaningful.
      evidence   DIRECTORY connectors DROPPED, not downgraded. Only connectors with
                 real tool evidence are in the graph at all.

    `harvested` mixes measured and inherited rows, so every aggregate over it
    carries an asterisk. `evidence` is the model with no fiction in it: smaller,
    and the only one whose numbers need no caveat about where they came from.
    Neither supersedes the other -- `harvested` answers "what does the directory
    look like", `evidence` answers "what do we actually know".
    """
    full = json.load(open(os.path.join(DATA, "registry_full.json"), encoding="utf-8"))
    arches = full["archetypes"]
    conns = {c["name"].lower(): dict(c) for c in full["connectors"]}

    cur_path = os.path.join(DATA, "registry.json")
    if os.path.exists(cur_path):
        cur = json.load(open(cur_path, encoding="utf-8"))
        for c in cur.get("connectors", []):
            k = c["name"].lower()
            base = conns.get(k, {})
            base.update({kk: vv for kk, vv in c.items() if vv not in (None, [], "")})
            base.setdefault("badges", [])
            base.setdefault("popular_rank", None)
            base.setdefault("archetype", "ai_tools")
            a = arches[base["archetype"]]
            base.setdefault("emits", a["emits"])
            base.setdefault("consumes", a["consumes"])
            base.setdefault("side_effects", a["side_effects"])
            base.setdefault("confidence", "DOCUMENTED")
            base.setdefault("role", base.get("name", ""))
            base["curated"] = True
            conns[k] = base

    if model in ("harvested", "evidence"):
        pp = os.path.join(DATA, "profiles.json")
        if not os.path.exists(pp):
            raise SystemExit("data/profiles.json missing — run engine/profile.py --derive")
        prof = json.load(open(pp, encoding="utf-8"))["connectors"]
        # Match on normalised NAME, not id. registry.json's curated entries
        # overwrite `id` for the connectors they override, which silently dropped
        # 5 of the 11 VERIFIED profiles when this keyed on id. Names are the one
        # field both files agree on.
        def nrm(s):
            return "".join(ch for ch in (s or "").lower() if ch.isalnum())
        by_name = {nrm(c.get("name")): c for c in conns.values()}
        for cid, p in prof.items():
            c = by_name.get(nrm(p["name"]))
            if c is None:
                continue
            c["emits"] = list(p["emits"])
            c["consumes"] = list(p["consumes"])
            c["side_effects"] = p["side_effects"]
            c["tier"] = p["tier"]
            c["n_tools"] = p["n_tools"]
            c["authless"] = p.get("authless", False)
            c["runtime"] = p.get("runtime", "unmeasured")
    else:
        for c in conns.values():
            c.setdefault("tier", "DIRECTORY")
            c.setdefault("n_tools", 0)
            c.setdefault("authless", False)
            c.setdefault("runtime", "unmeasured")

    out = list(conns.values())
    if model == "evidence":
        for c in out:
            c.setdefault("tier", "DIRECTORY")
        out = [c for c in out if c["tier"] in ("VERIFIED", "HARVESTED")]
    return arches, out


def validate(arches, conns):
    """Hard-fail on any join key outside the vocabulary.

    Always returns the real empty-archetype list. Whether an empty archetype is a
    defect depends on the model -- under `evidence` whole archetypes legitimately
    vanish because they have zero tool evidence -- so that judgement belongs to
    the caller. Suppressing the list here would have made --validate print
    "empty archetypes: none" while archetypes were in fact missing."""
    errs = []
    for name, prof in arches.items():
        for field in ("emits", "consumes"):
            for k in prof[field]:
                if k not in VOCAB:
                    errs.append(f"archetype '{name}'.{field}: unknown key '{k}'")
    for c in conns:
        for field in ("emits", "consumes"):
            for k in c.get(field, []):
                if k not in VOCAB:
                    errs.append(f"connector '{c['name']}'.{field}: unknown key '{k}'")
    empty = [a for a, p in arches.items()
             if not any(c["archetype"] == a for c in conns)]
    return errs, empty


# ---------------------------------------------------------------- profile classes

def profile_of(c, include_weak=False):
    """A connector's join identity: what it emits and what it consumes."""
    e = frozenset(c["emits"]) if include_weak else frozenset(c["emits"]) - WEAK
    n = frozenset(c["consumes"]) if include_weak else frozenset(c["consumes"]) - WEAK
    return (e, n)


def profile_classes(conns, include_weak=False):
    """Group the 820 connectors by distinct join profile. Returns (classes, index)."""
    groups = collections.OrderedDict()
    for c in conns:
        groups.setdefault(profile_of(c, include_weak), []).append(c)
    classes = list(groups.items())          # [((emits,consumes), [connectors]), ...]
    index = {}
    for i, (_, members) in enumerate(classes):
        for m in members:
            index[m["name"]] = i
    return classes, index


def class_edges(classes):
    """Directed adjacency between profile classes, with join keys."""
    adj = collections.defaultdict(dict)
    for i, ((ei, _), _) in enumerate(classes):
        for j, ((_, cj), _) in enumerate(classes):
            if i == j:
                continue
            keys = ei & cj
            if keys:
                adj[i][j] = sorted(keys)
    return adj


# ---------------------------------------------------------------- all-pairs

def bfs_all_pairs(adj, n, blocked=frozenset()):
    """Unweighted BFS from every node. Returns dist[i][j] (-1 = unreachable)."""
    dist = []
    for s in range(n):
        d = [-1] * n
        d[s] = 0
        q = collections.deque([s])
        while q:
            u = q.popleft()
            for v in adj.get(u, {}):
                if v in blocked and v != s:
                    continue
                if d[v] == -1:
                    d[v] = d[u] + 1
                    q.append(v)
        dist.append(d)
    return dist


def expand_pairs(dist, classes):
    """Expand class-level distances into true connector-pair counts."""
    sizes = [len(m) for _, m in classes]
    total = sum(sizes)
    hist = collections.Counter()
    for i, row in enumerate(dist):
        for j, d in enumerate(row):
            pairs = sizes[i] * (sizes[i] - 1) if i == j else sizes[i] * sizes[j]
            if i == j:
                # a class reaches itself only if it has a real self-edge
                _, ci = classes[i][0]
                ei, _ = classes[i][0]
                d = 1 if (ei & ci) else -1
            hist[d] += pairs
    return hist, total * (total - 1)


# ---------------------------------------------------------------- centrality

def brandes(adj, n):
    """Exact betweenness centrality (Brandes). Cheap at this node count."""
    cb = [0.0] * n
    for s in range(n):
        stack, preds = [], {v: [] for v in range(n)}
        sigma = [0] * n; sigma[s] = 1
        d = [-1] * n; d[s] = 0
        q = collections.deque([s])
        while q:
            v = q.popleft(); stack.append(v)
            for w in adj.get(v, {}):
                if d[w] < 0:
                    d[w] = d[v] + 1; q.append(w)
                if d[w] == d[v] + 1:
                    sigma[w] += sigma[v]; preds[w].append(v)
        delta = [0.0] * n
        while stack:
            w = stack.pop()
            for v in preds[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    return cb


def key_scarcity(arches, include_weak=False):
    """If this join key vanished, how many archetype pairs would lose their direct edge?"""
    names = list(arches)
    def edges_with(exclude):
        n = 0
        for a in names:
            ea = set(arches[a]["emits"]) - (set() if include_weak else WEAK) - {exclude}
            for b in names:
                if a == b:
                    continue
                cb_ = set(arches[b]["consumes"]) - (set() if include_weak else WEAK) - {exclude}
                if ea & cb_:
                    n += 1
        return n
    base = edges_with(None)
    return {k: base - edges_with(k) for k in sorted(STRONG)}, base


# ---------------------------------------------------------------- archetype view

def arch_edges(arches, include_weak=False):
    """Directed archetype edges -- identical logic to the skill's atlas.py."""
    out = {}
    for a, pa in arches.items():
        ea = set(pa["emits"]) if include_weak else set(pa["emits"]) - WEAK
        for b, pb in arches.items():
            if a == b:
                continue
            cb_ = set(pb["consumes"]) if include_weak else set(pb["consumes"]) - WEAK
            keys = ea & cb_
            if keys:
                out[(a, b)] = sorted(keys)
    return out


# ---------------------------------------------------------------- analysis

def analyze(include_weak=False, model="inherited"):
    arches, conns = load(model)
    errs, empty = validate(arches, conns)
    if errs:
        raise SystemExit("KEY VOCABULARY ERRORS:\n  " + "\n  ".join(errs))

    classes, cindex = profile_classes(conns, include_weak)
    adj = class_edges(classes)
    n = len(classes)

    regimes = {}
    hub_classes = {i for i, (_, m) in enumerate(classes)
                   if all(c["archetype"] in HUB_ARCHES for c in m)}
    fb_classes = {i for i, (_, m) in enumerate(classes)
                  if all(c["archetype"] in FALLBACK_ARCHES for c in m)}
    for label, blocked in (("native_only", hub_classes | fb_classes),
                           ("with_fallbacks", hub_classes),
                           ("with_hubs", frozenset())):
        dist = bfs_all_pairs(adj, n, blocked)
        hist, total = expand_pairs(dist, classes)
        regimes[label] = {
            "hop_histogram": {str(k): v for k, v in sorted(hist.items())},
            "total_ordered_pairs": total,
            "pct_direct": round(100.0 * hist[1] / total, 2) if total else 0,
            "pct_within_2": round(100.0 * (hist[1] + hist[2]) / total, 2) if total else 0,
            "unreachable": hist[-1],
            "diameter": max((d for row in dist for d in row if d >= 0), default=0),
        }

    ae = arch_edges(arches, include_weak)
    anames = list(arches)
    aidx = {a: i for i, a in enumerate(anames)}
    aadj = collections.defaultdict(dict)
    for (a, b), k in ae.items():
        aadj[aidx[a]][aidx[b]] = k
    bt = brandes(aadj, len(anames))
    deg = collections.Counter()
    for (a, b) in ae:
        deg[a] += 1; deg[b] += 1

    scarcity, base_edges = key_scarcity(arches, include_weak)
    side = collections.Counter(c["side_effects"] for c in conns)
    conf = collections.Counter(c.get("confidence", "DIRECTORY") for c in conns)

    tiers = collections.Counter(c.get("tier", "DIRECTORY") for c in conns)
    return {
        "model": model,
        "generated_from": "data/registry_full.json + data/registry.json"
                          + (" + data/profiles.json" if model == "harvested" else ""),
        "tiers": dict(tiers),
        "counts": {
            "connectors": len(conns),
            "archetypes": len(arches),
            "distinct_join_profiles": n,
            "archetype_edges": len(ae),
            "curated_overrides": sum(1 for c in conns if c.get("curated")),
            "empty_archetypes": empty,
        },
        "side_effects": dict(side),
        "confidence": dict(conf),
        "read_only_ceiling": side.get("read", 0),
        "reachability": regimes,
        "archetype_degree": dict(deg.most_common()),
        "betweenness": {anames[i]: round(v, 1)
                        for i, v in sorted(enumerate(bt), key=lambda t: -t[1])},
        "key_scarcity": dict(sorted(scarcity.items(), key=lambda t: -t[1])),
        "archetype_edge_baseline": base_edges,
        "members_per_archetype": dict(
            collections.Counter(c["archetype"] for c in conns).most_common()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--include-weak", action="store_true")
    ap.add_argument("--model", choices=("inherited", "harvested", "evidence"), default="inherited")
    ap.add_argument("--path", nargs=2, metavar=("SRC", "DST"))
    a = ap.parse_args()

    if a.validate:
        arches, conns = load(a.model)
        errs, empty = validate(arches, conns)
        print(f"model: {a.model}   connectors: {len(conns)}   archetypes: {len(arches)}")
        if errs:
            print(f"FAIL — {len(errs)} key-vocabulary error(s):")
            for e in errs[:20]:
                print("  " + e)
            return 1
        print("key vocabulary: OK (0 unknown keys)")
        if a.model == "evidence":
            # Expected here, and worth naming: these archetypes have no connector
            # with tool evidence at all, which is itself a finding.
            print(f"archetypes with no evidence-backed member: {len(empty)}"
                  + (f" — {', '.join(sorted(empty))}" if empty else ""))
            return 0
        print(f"empty archetypes: {empty or 'none'}")
        return 0 if not empty else 1

    if a.path:
        arches, conns = load(a.model)
        by = {c["name"].lower(): c for c in conns}
        def find(q):
            q = q.lower()
            if q in by: return by[q]
            m = sorted((c for c in conns if q in c["name"].lower()),
                       key=lambda c: len(c["name"]))
            return m[0] if m else None
        A, B = find(a.path[0]), find(a.path[1])
        if not A or not B:
            print("not found"); return 1
        ea = set(A["emits"]) - WEAK
        cb_ = set(B["consumes"]) - WEAK
        keys = sorted(ea & cb_)
        print(f"{A['name']} [{A['archetype']}] -> {B['name']} [{B['archetype']}]")
        print(f"DIRECT EDGE: {'yes — ' + ', '.join(keys) if keys else 'none'}")
        return 0

    if a.analyze:
        res = analyze(a.include_weak, a.model)
        os.makedirs(OUT, exist_ok=True)
        p = os.path.join(OUT, f"analysis_{a.model}.json")
        json.dump(res, open(p, "w", encoding="utf-8"), indent=1)
        c = res["counts"]
        print(f"model: {res['model']}   tiers: {res['tiers']}")
        print(f"connectors {c['connectors']} | archetypes {c['archetypes']} | "
              f"distinct join profiles {c['distinct_join_profiles']} | "
              f"archetype edges {c['archetype_edges']}")
        for k, v in res["reachability"].items():
            print(f"  {k:16s} direct {v['pct_direct']:6.2f}%   <=2 hops {v['pct_within_2']:6.2f}%   "
                  f"unreachable {v['unreachable']:,}  diameter {v['diameter']}")
        print(f"read-only ceiling: {res['read_only_ceiling']} connectors")
        print(f"-> {p}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
