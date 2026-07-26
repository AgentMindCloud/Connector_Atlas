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


def build(include_weak=False):
    arches, conns = G.load()
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

    cjs = []
    for c in conns:
        v = c.get("confidence") == "VERIFIED"
        rec = {"n": c["name"], "a": c["archetype"], "r": (c.get("role") or "")[:200],
               "cf": c.get("confidence", "DIRECTORY"), "s": c.get("side_effects", "read"),
               "v": 1 if v else 0, "p": c.get("popular_rank")}
        if v and c["name"] in cur:
            src = cur[c["name"]]
            rec["vb"] = {"verbs": src.get("verbs", []), "dead_ends": src.get("dead_ends", [])}
        cjs.append(rec)

    edges = G.arch_edges(arches, include_weak)
    ejs = [{"s": a, "t": b, "k": keys[0], "keys": keys,
            "h": 1 if (a in G.HUB_ARCHES or b in G.HUB_ARCHES) else 0}
           for (a, b), keys in sorted(edges.items())]

    analysis = G.analyze(include_weak)
    analysis["counts"]["verified"] = sum(1 for c in conns if c.get("confidence") == "VERIFIED")

    sysdoc = json.load(open(os.path.join(ROOT, "data", "systems.json"), encoding="utf-8"))
    systems = []
    for s in sysdoc["systems"]:
        s = dict(s)
        s["score"] = S.evaluate(s, None)
        systems.append(s)
    systems.sort(key=lambda s: -s["score"]["LEVERAGE"])

    return {
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "atlas_v5.html"))
    ap.add_argument("--include-weak", action="store_true")
    a = ap.parse_args()

    data = build(a.include_weak)
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)

    n = data["analysis"]["counts"]
    print(f"atlas v5 -> {a.out}  ({len(html)/1024:.0f} KB)")
    print(f"  {n['connectors']} connectors · {n['archetypes']} archetypes · "
          f"{len(data['edges'])} derived edges · {n['distinct_join_profiles']} join profiles")
    print(f"  {n['verified']} VERIFIED · {len(data['systems'])} systems scored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
