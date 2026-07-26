#!/usr/bin/env python3
"""
render.py — builds the single-file Atlas v5 tool. Stdlib only.

    python3 engine/render.py [--out out/atlas_v5.html] [--include-weak]

Everything on the page is generated from data/. Nothing is hand-drawn, so the picture
cannot drift from the registry: change a profile, re-render, the map changes with it.
"""

import argparse, colorsys, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import graph as G      # noqa: E402
import score as S      # noqa: E402
import combine as X    # noqa: E402

KEY_COLORS = {
    "email": "#E64A2E", "url": "#35A481", "timestamp": "#E0B13E", "file": "#7D9BD2",
    "rows": "#B678D4", "money": "#5BC0BE", "code": "#D2789B", "geo": "#8FD478",
    "image": "#D49A78", "media": "#78C3D4", "phone": "#C9D478", "ticker": "#D4788F",
    "domain": "#9B78D4", "company": "#78D4A5", "project": "#D4C378",
    "person": "#8A8A93", "text": "#6A6A72", "vendor_id": "#55555C",
}


def palette(n):
    """Golden-angle hue walk — distinguishable neighbours, consistent luminance."""
    out = []
    for i in range(n):
        h = (i * 0.61803398875) % 1.0
        s = 0.36 + 0.16 * ((i % 3) / 2)
        v = 0.72 + 0.12 * ((i % 2))
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        out.append("#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255)))
    return out


def build(include_weak=False, model="harvested"):
    arches, conns = G.load(model)
    errs, empty = G.validate(arches, conns)
    if errs:
        raise SystemExit("refusing to render with key-vocabulary errors:\n  " + "\n  ".join(errs))

    # connectors sorted by archetype so the sphere groups them into constellations
    conns.sort(key=lambda c: (c["archetype"], c["name"].lower()))

    cur = {}
    cur_path = os.path.join(ROOT, "data", "registry.json")
    if os.path.exists(cur_path):
        for c in json.load(open(cur_path, encoding="utf-8"))["connectors"]:
            cur[c["name"]] = c

    # Per-connector profiles: the harvested model gives every connector its own
    # emits/consumes, so the detail panel must stop reading the archetype's.
    pf = {}
    pp = os.path.join(ROOT, "data", "profiles.json")
    if os.path.exists(pp):
        for rec in json.load(open(pp, encoding="utf-8"))["connectors"].values():
            pf[rec["name"]] = rec

    cjs = []
    for c in conns:
        v = c.get("confidence") == "VERIFIED"
        rec = {"n": c["name"], "a": c["archetype"], "r": (c.get("role") or "")[:200],
               "cf": c.get("confidence", "DIRECTORY"), "s": c.get("side_effects", "read"),
               "v": 1 if v else 0, "p": c.get("popular_rank"),
               "e": sorted(set(c.get("emits", [])) - G.WEAK),
               "cn": sorted(set(c.get("consumes", [])) - G.WEAK),
               "ti": c.get("tier", "DIRECTORY"), "au": 1 if c.get("authless") else 0,
               "nt": c.get("n_tools", 0)}
        q = pf.get(c["name"])
        if q:
            rec["tl"] = q.get("tools", [])[:12]
            rec["tt"] = q.get("tools_truncated", 0)
            rec["ie"] = sorted(set(q["inherited"]["emits"]) - G.WEAK)
            rec["ic"] = sorted(set(q["inherited"]["consumes"]) - G.WEAK)
            rec["is_"] = q["inherited"]["side_effects"]
        if v and c["name"] in cur:
            src = cur[c["name"]]
            rec["vb"] = {"verbs": src.get("verbs", []), "dead_ends": src.get("dead_ends", [])}
        cjs.append(rec)

    edges = G.arch_edges(arches, include_weak)
    ejs = [{"s": a, "t": b, "k": keys[0], "keys": keys,
            "h": 1 if (a in G.HUB_ARCHES or b in G.HUB_ARCHES) else 0}
           for (a, b), keys in sorted(edges.items())]

    analysis = G.analyze(include_weak, model)
    analysis["counts"]["verified"] = sum(1 for c in conns if c.get("confidence") == "VERIFIED")

    sysdoc = json.load(open(os.path.join(ROOT, "data", "systems.json"), encoding="utf-8"))
    sctx = S.build_ctx(arches, conns)
    systems = []
    for s in sysdoc["systems"]:
        s = dict(s)
        s["score"] = S.evaluate(s, sctx)
        systems.append(s)
    systems.sort(key=lambda s: -s["score"]["ROBUSTNESS"])

    # The combinatorial layer: the pair matrix (class-compressed but lossless),
    # the motif census, the triple census, and the inherited-vs-harvested diff.
    X._init_shapes()
    _, xconns, xclasses, xindex, xsizes, xadj, xkeys = X.build(model)
    hub = {i for i, (_, m) in enumerate(xclasses)
           if all(cc["archetype"] in G.HUB_ARCHES for cc in m)}
    fb = {i for i, (_, m) in enumerate(xclasses)
          if all(cc["archetype"] in G.FALLBACK_ARCHES for cc in m)}
    dist, hist, tot = X.pairs(xclasses, xsizes, xadj, xkeys, hub | fb)
    census, tconnected, tchecked = X.triples(xclasses, xsizes, xadj)
    tnamed = {}
    for (arcs, fp), cnt in census.items():
        nm = X.SHAPE_NAMES.get((arcs, fp), "other · %d arcs" % arcs)
        tnamed[nm] = tnamed.get(nm, 0) + cnt

    return {
        "pairs": {
            "classOf": {cc["name"]: xindex[cc["name"]] for cc in xconns},
            "matrix": dist,
            "keys": {"%d,%d" % k: v for k, v in xkeys.items()},
            "classProfiles": [{"e": sorted(e), "c": sorted(cc), "n": len(m)}
                              for (e, cc), m in xclasses],
            "hist": {str(k): v for k, v in sorted(hist.items())},
            "total": tot,
        },
        "motifs": X.motifs(xconns, xclasses, xindex, xsizes, xadj),
        "triples": {"total": tchecked, "connected": tconnected,
                    "byShape": dict(sorted(tnamed.items(), key=lambda t: -t[1]))},
        "questions": X.questions(xconns, xclasses, xindex, xsizes, xadj, xkeys),
        "diff": X.diff(),
        "schema": schema_payload(),
        "model": model,
        "archetypes": {k: {"label": v["label"], "emits": sorted(set(v["emits"]) - G.WEAK),
                           "consumes": sorted(set(v["consumes"]) - G.WEAK),
                           "side": v["side_effects"], "note": v["note"]}
                       for k, v in arches.items()},
        "connectors": cjs,
        "edges": ejs,
        "systems": systems,
        "analysis": analysis,
        "keyColors": KEY_COLORS,
        "palette": palette(len(arches)),
        "strongKeys": sorted(G.STRONG),
        "hubArches": sorted(G.HUB_ARCHES),
        "fallbackArches": sorted(G.FALLBACK_ARCHES),
    }


def schema_payload():
    """Phase 3's parameter-schema layer, for the fifth lab view.

    Returns None when the delta has not been computed, so the view can say the
    measurement is missing rather than render an empty table that reads as a
    finding. Regenerate with: python3 engine/schema.py --derive --delta
    """
    dp = os.path.join(ROOT, "out", "schema_delta.json")
    sp = os.path.join(ROOT, "data", "schema_profiles.json")
    if not (os.path.exists(dp) and os.path.exists(sp)):
        return None
    delta = json.load(open(dp, encoding="utf-8"))
    prof = json.load(open(sp, encoding="utf-8"))["connectors"]
    return {
        "agreement": delta["agreement"],
        "sideEffects": delta["side_effects"],
        "connectors": delta["connectors"],
        "selectors": delta["selectors"],
        "preconditions": delta["preconditions"],
        "runtime": delta.get("runtime", {}),
        "profiles": {v["name"]: {"nTools": v["n_tools"], "nParams": v["n_params"],
                                 "consumes": v["consumes"], "selectors": v["selectors"],
                                 "runtime": v["runtime"],
                                 "clsName": v["side_effects_name"],
                                 "clsSchema": v["side_effects_schema"]}
                     for v in prof.values()},
    }


# `template.html` is a body FRAGMENT — it opens on <title> and has never carried a
# doctype, an <html>/<head>/<body>, a charset or a viewport. Through Phase 3 it was
# written straight out as if it were a whole document, which is a real defect with
# three separate consequences:
#
#   no charset   the page holds 417 non-ASCII characters (155 em dashes, 38 arrows,
#                Japanese connector names). Loaded over file:// with nothing
#                declared, a browser guesses, and every one of them mojibakes.
#   no viewport  a phone lays the page out at ~980px and scales down, so everything
#                is tiny AND the max-width:1100px/640px rules never fire — the
#                responsive design in the CSS never reaches a real device.
#   no doctype   quirks mode, so the box model is not the one the CSS was written for.
#
# The browser test did not catch any of it, which is the more useful half of the
# lesson: it set a 390px layout viewport directly, which is exactly what a missing
# viewport meta prevents a phone from doing. It tested a state the bug made
# unreachable. engine/browsertest.js now asserts the scaffolding itself.
#
# Two outputs, because the two destinations want opposite things: a downloaded file
# needs the whole document, and an Artifact supplies its own skeleton and must not
# be double-wrapped.
HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
"""


def document(fragment):
    """Body fragment -> complete standalone HTML document.

    <title> and <style> come from the fragment and belong in <head>, so the split
    point is the first tag that does not: everything from there is body content.
    """
    cut = fragment.index("</style>") + len("</style>")
    return HEAD + fragment[:cut] + "\n</head>\n<body>\n" + fragment[cut:] + "\n</body>\n</html>\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "atlas_v5.html"))
    ap.add_argument("--fragment-out", default=os.path.join(ROOT, "out", "atlas_artifact.html"),
                    help="body-only copy for Artifact publishing, which adds its own skeleton")
    ap.add_argument("--include-weak", action="store_true")
    ap.add_argument("--model", choices=("inherited", "harvested"), default="harvested")
    a = ap.parse_args()

    data = build(a.include_weak, a.model)
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    frag = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    html = document(frag)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)
    open(a.fragment_out, "w", encoding="utf-8").write(frag)

    n = data["analysis"]["counts"]
    print(f"atlas v5 -> {a.out}  ({len(html)/1024:.0f} KB, standalone document)")
    print(f"          -> {a.fragment_out}  ({len(frag)/1024:.0f} KB, body fragment for Artifact)")
    print(f"  {n['connectors']} connectors · {n['archetypes']} archetypes · "
          f"{len(data['edges'])} derived edges · {n['distinct_join_profiles']} join profiles")
    d = data["diff"]
    print(f"  model={data['model']} · tiers={data['analysis']['tiers']}")
    print(f"  pair matrix {len(data['pairs']['matrix'])}^2 (all {data['pairs']['total']:,} "
          f"ordered pairs) · triples {data['triples']['total']:,} "
          f"({data['triples']['connected']:,} connected)")
    print(f"  direct pairs {d['direct_ordered_pairs']['inherited']:,} -> "
          f"{d['direct_ordered_pairs']['harvested']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
