#!/usr/bin/env python3
"""
score.py — the evaluator model. Stdlib only.

    python3 engine/score.py            # score data/systems.json -> out/scored.json

Every number here is derived from fields authored in data/systems.json plus the graph in
data/. Nothing is hand-assigned a tier: tiers fall out of the weights below, and the raw
inputs travel with the score so a tier can be argued with rather than taken on faith.

Two composites, deliberately kept apart (they disagree, and the disagreement is the point):

  ROBUSTNESS  — will this combination keep running? Fires without a human, survives a
                connector failing, few auth surfaces, bounded blast radius, few
                mandatory tool preconditions.
  CAPABILITY  — how much of the connector graph does it genuinely exploit?

Phase 3 removed the operator-payback lens
-----------------------------------------
The first composite was called LEVERAGE and its heaviest axis (0.30) was `payback`:
hours reclaimed per month, valued at an assumed hourly rate, against an assumed
build cost. Phase 2 removed that framing from the UI and this file kept computing
it anyway, so the scores in data/systems.json were still ranked by one person's
notional hourly rate. The unit of work here is the DIRECTORY, not an account, and
a number that changes when you change your salary is not a fact about a
composition.

What replaced it is not a rescale of the same idea. `payback` and `cold_start`
are gone outright, along with HOURLY_RATE_USD and VALUE_PER_HOUR_USD; the four
axes that were always properties of the composition rather than of its owner --
trigger, degradation, auth surface, blast radius -- are kept and reweighted, and
one new axis is added that Phase 3 made measurable:

  preconditions   mandatory intra-connector tool ordering, read from
                  data/schema_profiles.json. Vercel's buy_* cannot be called
                  without a quote; Supabase's create_project needs a cost
                  confirmation. Every such edge is a step that must succeed
                  before the system can act, and none of them are visible in a
                  tool name.

`trigger_reality` is also no longer taken purely on the author's word: the claim
is now checked against the runtime axis of the system's own source connectors,
and a system claiming to be scheduled while every source it reads is poll_blind
is flagged rather than scored as if the claim held.

build_hours, monthly_run_cost_usd and cold_start_days survive as DESCRIPTIVE
fields. Nothing scores on them.
"""

import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import graph as G  # noqa: E402


def _nrm(x):
    return re.sub(r"[^a-z0-9]", "", (x or "").lower())

# ------------------------------------------------------------------ tunables
# One dict. Change scoring policy here and nowhere else.
WEIGHTS = {
    "robustness": {
        "trigger":        0.30,   # does it run without a human, and can it tell what changed
        "degradation":    0.22,   # survives a connector failing
        "auth_surface":   0.18,   # every extra account is another thing that can expire
        "blast_radius":   0.18,   # risk drag on leaving it running unattended
        "preconditions":  0.12,   # mandatory tool ordering that must succeed first
    },
    "capability": {
        "key_coverage":   0.26,   # how many strong join keys flow through it
        "fan_in":         0.24,   # breadth of independent sensors
        "closure":        0.20,   # does it read its own output (cybernetic loop)
        "cross_cluster":  0.18,   # does it join archetypes that rarely meet
        "ceiling":        0.12,   # headroom to scale without redesign
    },
}
TIER_CUTS = [("S", 78), ("A", 64), ("B", 50), ("C", 0)]
TRIG_MARK = {"supported": "ok", "not_claimed": "-", "blind": "BLIND", "unmeasurable": "?"}

TRIGGER_REALITY = {           # evaluator #3
    "none": 0, "on-demand": 1, "hub-scheduled": 2, "scheduled": 3, "event": 3,
}
DEGRADATION = {               # evaluator #9
    "dies": 0, "partial": 1, "degrades": 2, "self-heals": 3,
}


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _band(x, points):
    """Piecewise-linear map with explicit, arguable breakpoints."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            if x <= x0:
                return y0
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0
            return y0 + t * (y1 - y0)
    return points[-1][1]


# ------------------------------------------------------------------ evaluators

def evaluate(sysdef, ctx):
    ribs = sysdef.get("ribs", [])
    n_conn = sysdef.get("connector_count") or len(sysdef.get("connectors", []))
    auths = sysdef.get("required_auths", n_conn)

    # 1. blast radius — worst side effect anywhere in the system
    blast = max([G.SIDE_RANK.get(r.get("side_effect", "read"), 0) for r in ribs] or [0])

    # 2. auth surface
    auth_surface = auths

    # 3. trigger reality
    trig = TRIGGER_REALITY.get(sysdef.get("trigger", "on-demand"), 1)

    # 4. fan-in : chain-depth ratio — the metric that licenses big N
    depth = max([r.get("hops", 2) for r in ribs] or [1])
    fan_in = max([r.get("fan_in", 1) for r in ribs] or [1])
    fid = fan_in / depth

    # 5. mandatory tool preconditions across the system's connectors — Phase 3.
    #    Read from measured schemas, not authored. Only the 11 schema-covered
    #    connectors can contribute, so this axis is scored on what is known and
    #    the coverage is reported alongside it rather than assumed complete.
    pre_edges, pre_known = 0, 0
    for cname in sysdef.get("connectors", []):
        sp = ctx["schema"].get(_nrm(cname))
        if sp is not None:
            pre_known += 1
            pre_edges += len(sp.get("preconditions", []))

    # 6. marginal cost per run — descriptive only, not scored
    run_cost = sysdef.get("cost_per_run_usd", 0.0)

    # 7. state gravity — durable state accumulated
    gravity = sysdef.get("state_tables", 0) + (2 if sysdef.get("uses_memory") else 0)

    # 8. judgment share — Claude ribs vs deterministic ribs
    judgment = (sum(1 for r in ribs if r.get("claude")) / len(ribs)) if ribs else 0.0

    # 9. degradation grace
    degr = DEGRADATION.get(sysdef.get("degradation", "partial"), 1)

    # ---- does the authored trigger claim survive the runtime measurement?
    #      A system that claims to be scheduled or event-driven has to be reading
    #      something that can be asked what changed. If every source connector is
    #      poll_blind, the schedule still fires but it re-reads the same
    #      undifferentiated set every time and the dedupe burden moves into the
    #      system's own state tables. That is a real design cost and it was
    #      previously invisible, because `trigger` was simply believed.
    srcs = [ctx["runtime"].get(_nrm(c), "unmeasured") for c in sysdef.get("connectors", [])]
    pollable = [r for r in srcs if r not in ("poll_blind", "unmeasured")]
    measured = [r for r in srcs if r != "unmeasured"]
    claims_auto = sysdef.get("trigger") in ("scheduled", "event", "hub-scheduled")
    # Three outcomes, not two. The mesh systems are specified at archetype level and
    # carry no connector list at all, so an empty `srcs` says nothing about them --
    # reporting that as a failed trigger claim would be inventing a finding. Only a
    # system with measured sources, none of which are pollable, is actually blind.
    if not claims_auto:
        trigger_verdict = "not_claimed"
    elif not measured:
        trigger_verdict = "unmeasurable"
    elif pollable:
        trigger_verdict = "supported"
    else:
        trigger_verdict = "blind"
        trig = min(trig, 2)      # it fires, but it cannot tell what is new
    trigger_supported = trigger_verdict in ("supported", "not_claimed")

    # ---- ROBUSTNESS subscores
    s_trigger = trig / 3 * 100
    s_degr = degr / 3 * 100
    s_auth = _band(auth_surface, [(1, 100), (3, 88), (5, 72), (8, 52), (15, 28), (40, 10), (300, 0)])
    s_blast = (3 - blast) / 3 * 100
    s_pre = _band(pre_edges, [(0, 100), (2, 82), (5, 60), (10, 35), (20, 10), (50, 0)])

    robustness = (
        WEIGHTS["robustness"]["trigger"] * s_trigger +
        WEIGHTS["robustness"]["degradation"] * s_degr +
        WEIGHTS["robustness"]["auth_surface"] * s_auth +
        WEIGHTS["robustness"]["blast_radius"] * s_blast +
        WEIGHTS["robustness"]["preconditions"] * s_pre
    )

    # ---- CAPABILITY subscores
    keys = set(sysdef.get("join_keys", []))
    s_keys = len(keys & G.STRONG) / len(G.STRONG) * 100
    s_fan = _band(n_conn, [(1, 5), (6, 25), (15, 45), (40, 65), (100, 85), (200, 97), (293, 100)])
    s_closure = 100 if sysdef.get("feedback_closure") else 25
    arch_span = len(set(sysdef.get("archetypes", [])))
    s_cross = _band(arch_span, [(1, 5), (3, 30), (6, 55), (10, 75), (16, 90), (25, 100)])
    s_ceiling = _band(sysdef.get("ceiling_connectors", n_conn),
                      [(1, 5), (15, 35), (50, 60), (150, 85), (293, 100)])

    capability = (
        WEIGHTS["capability"]["key_coverage"] * s_keys +
        WEIGHTS["capability"]["fan_in"] * s_fan +
        WEIGHTS["capability"]["closure"] * s_closure +
        WEIGHTS["capability"]["cross_cluster"] * s_cross +
        WEIGHTS["capability"]["ceiling"] * s_ceiling
    )

    # Deliberately NOT a single blended tier. Averaging the two lenses hides the
    # most useful fact in the model: the systems that are safest to leave running
    # and the systems that exploit the graph hardest are almost disjoint sets.
    # Each lens gets its own tier; COMBINED is kept only as a stable sort key.
    combined = 0.5 * robustness + 0.5 * capability
    tier_rob = next(t for t, cut in TIER_CUTS if robustness >= cut)
    tier_cap = next(t for t, cut in TIER_CUTS if capability >= cut)

    return {
        "evaluators": {
            "blast_radius": blast,
            "auth_surface": auth_surface,
            "trigger_reality": trig,
            "fan_in_depth_ratio": round(fid, 2),
            "precondition_edges": pre_edges,
            "state_gravity": gravity,
            "judgment_share": round(judgment, 2),
            "degradation_grace": degr,
        },
        "trigger_check": {
            "claimed": sysdef.get("trigger"),
            "source_runtimes": srcs,
            "verdict": trigger_verdict,
            "supported": trigger_supported,
            "note": {
                "blind": "claims an unattended trigger but every measured source "
                         "connector is poll_blind — the schedule fires and re-reads "
                         "the same undifferentiated set, so dedupe moves into the "
                         "system's own state tables",
                "unmeasurable": "specified at archetype level with no named "
                                "connectors, so the runtime axis has nothing to "
                                "check the trigger claim against",
            }.get(trigger_verdict),
        },
        "descriptive_not_scored": {
            "build_hours": sysdef.get("build_hours", 0),
            "monthly_run_cost_usd": sysdef.get("monthly_run_cost_usd", 0.0),
            "cost_per_run_usd": run_cost,
            "cold_start_days": sysdef.get("cold_start_days", 0),
            "note": "vendor pricing and build hours are ASSUMED estimates. Phase 3 "
                    "removed them from scoring; they are kept because they describe "
                    "the build, not because they rank it.",
        },
        "precondition_coverage": f"{pre_known}/{len(sysdef.get('connectors', []))} "
                                 f"connectors have measured schemas",
        "subscores": {
            "robustness": {"trigger": round(s_trigger), "degradation": round(s_degr),
                           "auth_surface": round(s_auth), "blast_radius": round(s_blast),
                           "preconditions": round(s_pre)},
            "capability": {"key_coverage": round(s_keys), "fan_in": round(s_fan),
                           "closure": round(s_closure), "cross_cluster": round(s_cross),
                           "ceiling": round(s_ceiling)},
        },
        "ROBUSTNESS": round(robustness, 1),
        "CAPABILITY": round(capability, 1),
        "COMBINED": round(combined, 1),
        "tier_robustness": tier_rob,
        "tier_capability": tier_cap,
        "tier": tier_rob,
    }


def build_ctx(arches, conns):
    """Phase 3 inputs: measured tool preconditions, and the runtime axis used to
    check each system's authored trigger claim against evidence."""
    sp_path = os.path.join(ROOT, "data", "schema_profiles.json")
    schema = {}
    if os.path.exists(sp_path):
        schema = json.load(open(sp_path, encoding="utf-8"))["connectors"]
    runtime = {}
    pp = os.path.join(ROOT, "data", "profiles.json")
    if os.path.exists(pp):
        for p in json.load(open(pp, encoding="utf-8"))["connectors"].values():
            runtime[_nrm(p["name"])] = p.get("runtime", "unmeasured")
    # Schema-measured runtime overrides the name-derived guess wherever it exists.
    for k, v in schema.items():
        runtime[k] = v.get("runtime", runtime.get(k, "unmeasured"))
    return {"arches": arches, "conns": conns, "schema": schema, "runtime": runtime}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default=os.path.join(ROOT, "data", "systems.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "scored.json"))
    a = ap.parse_args()

    ctx = build_ctx(*G.load())
    doc = json.load(open(a.systems, encoding="utf-8"))
    scored = []
    for s in doc["systems"]:
        s = dict(s)
        s["score"] = evaluate(s, ctx)
        scored.append(s)
    scored.sort(key=lambda s: -s["score"]["ROBUSTNESS"])

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"weights": WEIGHTS, "tier_cuts": TIER_CUTS,
               "_schema": {"note": "Phase 3 removed the operator-payback lens. "
                                   "LEVERAGE is gone; ROBUSTNESS replaces it and "
                                   "scores nothing on assumed rates or reclaimed "
                                   "hours. See engine/score.py for what changed."},
               "systems": scored},
              open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    print(f"{'ROB':>6} {'t':<2}{'CAP':>6} {'t':<2} {'conns':>5} {'auth':>4} "
          f"{'pre':>4} {'trig?':>6}  name")
    for s in scored:
        sc = s["score"]
        print(f"{sc['ROBUSTNESS']:>6} {sc['tier_robustness']:<2}"
              f"{sc['CAPABILITY']:>6} {sc['tier_capability']:<2} "
              f"{s.get('connector_count', len(s.get('connectors', []))):>5} "
              f"{sc['evaluators']['auth_surface']:>4} "
              f"{sc['evaluators']['precondition_edges']:>4} "
              f"{TRIG_MARK[sc['trigger_check']['verdict']]:>6}  {s['name']}")
    unsupported = [s for s in scored
                   if s["score"]["trigger_check"]["verdict"] == "blind"]
    if unsupported:
        print(f"\n  {len(unsupported)} system(s) claim an unattended trigger while every")
        print(f"  MEASURED source connector is poll_blind — the schedule fires but")
        print(f"  cannot tell what is new, so dedupe moves into their own state tables:")
        for s in unsupported:
            print(f"    {s['name']} — trigger={s['trigger']}, "
                  f"sources={s['score']['trigger_check']['source_runtimes']}")
    unk = [s for s in scored if s["score"]["trigger_check"]["verdict"] == "unmeasurable"]
    if unk:
        print(f"\n  {len(unk)} marked '?': specified at archetype level with no named")
        print(f"  connectors, so there is nothing to check the trigger claim against.")
        print(f"  That is missing evidence, not a failed check: "
              f"{', '.join(s['name'] for s in unk)}")
    print(f"\n-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
