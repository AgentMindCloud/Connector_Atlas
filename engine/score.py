#!/usr/bin/env python3
"""
score.py — the evaluator model. Stdlib only.

    python3 engine/score.py            # score data/systems.json -> out/scored.json

Every number here is derived from fields authored in data/systems.json plus the graph in
data/. Nothing is hand-assigned a tier: tiers fall out of the weights below, and the raw
inputs travel with the score so a tier can be argued with rather than taken on faith.

Two composites, deliberately kept apart (they disagree, and the disagreement is the point):

  LEVERAGE    — will this actually run, and is the payback real? Cost-recovery lens.
  CAPABILITY  — how much of the connector graph does it genuinely exploit? Ambition lens.

The five axes that were asked for map on as follows:
  technical difficulty -> build_hours + judgment_share + blast_radius
  cost                 -> build_cost_usd + monthly_run_cost_usd
  time to make         -> build_hours, cold_start_days
  automated vs human   -> trigger_reality + human_minutes_per_week
  Claude vs human      -> judgment_share
"""

import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import graph as G  # noqa: E402

# ------------------------------------------------------------------ tunables
# One dict. Change scoring policy here and nowhere else.
WEIGHTS = {
    "leverage": {
        "payback":        0.30,   # hours reclaimed vs cost to build+run
        "trigger":        0.22,   # does it run without a human
        "degradation":    0.15,   # survives a connector failing
        "auth_surface":   0.13,   # every extra account is friction
        "cold_start":     0.10,   # days until first value
        "blast_radius":   0.10,   # risk drag on leaving it running
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
HOURLY_RATE_USD = 60          # blended build rate; stated, not hidden
VALUE_PER_HOUR_USD = 45       # what an hour of reclaimed operator time is worth

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

    # 5. cold start
    cold = sysdef.get("cold_start_days", 0)

    # 6. marginal cost per run
    run_cost = sysdef.get("cost_per_run_usd", 0.0)

    # 7. state gravity — durable state accumulated
    gravity = sysdef.get("state_tables", 0) + (2 if sysdef.get("uses_memory") else 0)

    # 8. judgment share — Claude ribs vs deterministic ribs
    judgment = (sum(1 for r in ribs if r.get("claude")) / len(ribs)) if ribs else 0.0

    # 9. degradation grace
    degr = DEGRADATION.get(sysdef.get("degradation", "partial"), 1)

    # ---- cost model
    build_hours = sysdef.get("build_hours", 0)
    build_cost = build_hours * HOURLY_RATE_USD
    monthly_run = sysdef.get("monthly_run_cost_usd", 0.0)
    hours_saved = sysdef.get("hours_reclaimed_per_month", 0.0)
    monthly_value = hours_saved * VALUE_PER_HOUR_USD
    net_monthly = monthly_value - monthly_run
    breakeven = (build_cost / net_monthly) if net_monthly > 0 else None

    # ---- LEVERAGE subscores
    s_payback = _band(breakeven if breakeven is not None else 99,
                      [(0, 100), (1, 95), (3, 80), (6, 60), (12, 35), (24, 10), (99, 0)])
    s_trigger = trig / 3 * 100
    s_degr = degr / 3 * 100
    s_auth = _band(auth_surface, [(1, 100), (3, 88), (5, 72), (8, 52), (15, 28), (40, 10), (300, 0)])
    s_cold = _band(cold, [(0, 100), (1, 95), (7, 80), (30, 50), (90, 20), (365, 0)])
    s_blast = (3 - blast) / 3 * 100

    leverage = (
        WEIGHTS["leverage"]["payback"] * s_payback +
        WEIGHTS["leverage"]["trigger"] * s_trigger +
        WEIGHTS["leverage"]["degradation"] * s_degr +
        WEIGHTS["leverage"]["auth_surface"] * s_auth +
        WEIGHTS["leverage"]["cold_start"] * s_cold +
        WEIGHTS["leverage"]["blast_radius"] * s_blast
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

    # Deliberately NOT a single blended tier. Averaging the two lenses hides the most
    # useful fact in the whole model: the systems that pay back fastest and the systems
    # that exploit the graph hardest are almost disjoint sets. Each lens gets its own
    # tier; COMBINED is kept only as a stable sort key.
    combined = 0.5 * leverage + 0.5 * capability
    tier_lev = next(t for t, cut in TIER_CUTS if leverage >= cut)
    tier_cap = next(t for t, cut in TIER_CUTS if capability >= cut)

    return {
        "evaluators": {
            "blast_radius": blast,
            "auth_surface": auth_surface,
            "trigger_reality": trig,
            "fan_in_depth_ratio": round(fid, 2),
            "cold_start_days": cold,
            "cost_per_run_usd": run_cost,
            "state_gravity": gravity,
            "judgment_share": round(judgment, 2),
            "degradation_grace": degr,
        },
        "requested_axes": {
            "technical_difficulty": round(_clamp(
                100 - (_band(build_hours, [(0, 100), (20, 82), (80, 60), (240, 35), (800, 12), (3000, 0)]))), 1),
            "build_hours": build_hours,
            "build_cost_usd": round(build_cost),
            "monthly_run_cost_usd": round(monthly_run, 2),
            "time_to_value_days": cold,
            "automation_share": round(trig / 3, 2),
            "human_minutes_per_week": sysdef.get("human_minutes_per_week", 0),
            "claude_share": round(judgment, 2),
        },
        "economics": {
            "monthly_value_usd": round(monthly_value),
            "net_monthly_usd": round(net_monthly),
            "breakeven_months": round(breakeven, 1) if breakeven is not None else None,
            "assumptions": f"build @ ${HOURLY_RATE_USD}/h, reclaimed time @ ${VALUE_PER_HOUR_USD}/h — ASSUMED, tune in WEIGHTS",
        },
        "subscores": {
            "leverage": {"payback": round(s_payback), "trigger": round(s_trigger),
                         "degradation": round(s_degr), "auth_surface": round(s_auth),
                         "cold_start": round(s_cold), "blast_radius": round(s_blast)},
            "capability": {"key_coverage": round(s_keys), "fan_in": round(s_fan),
                           "closure": round(s_closure), "cross_cluster": round(s_cross),
                           "ceiling": round(s_ceiling)},
        },
        "LEVERAGE": round(leverage, 1),
        "CAPABILITY": round(capability, 1),
        "COMBINED": round(combined, 1),
        "tier_leverage": tier_lev,
        "tier_capability": tier_cap,
        "tier": tier_lev,          # default view is the cost-recovery lens
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default=os.path.join(ROOT, "data", "systems.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "scored.json"))
    a = ap.parse_args()

    arches, conns = G.load()
    ctx = {"arches": arches, "conns": conns}
    doc = json.load(open(a.systems, encoding="utf-8"))
    scored = []
    for s in doc["systems"]:
        s = dict(s)
        s["score"] = evaluate(s, ctx)
        scored.append(s)
    scored.sort(key=lambda s: -s["score"]["LEVERAGE"])

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"weights": WEIGHTS, "tier_cuts": TIER_CUTS,
               "rate_assumptions": {"build_hourly_usd": HOURLY_RATE_USD,
                                    "value_per_hour_usd": VALUE_PER_HOUR_USD},
               "systems": scored},
              open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    print(f"{'LEV':>6} {'t':<2}{'CAP':>6} {'t':<2} {'conns':>5} {'auth':>4} "
          f"{'B/E':>7}  name")
    for s in scored:
        sc = s["score"]
        be = sc["economics"]["breakeven_months"]
        print(f"{sc['LEVERAGE']:>6} {sc['tier_leverage']:<2}"
              f"{sc['CAPABILITY']:>6} {sc['tier_capability']:<2} "
              f"{s.get('connector_count', len(s.get('connectors', []))):>5} "
              f"{sc['evaluators']['auth_surface']:>4} "
              f"{(str(be) + 'mo') if be else 'never':>7}  {s['name']}")
    print(f"\n-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
