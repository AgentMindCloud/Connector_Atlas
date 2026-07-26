#!/usr/bin/env python3
"""
harvest.py — resumable, cached harvest of real per-connector tool lists.

    python3 engine/harvest.py --plan --batch 8 --calls 6   # what to query next
    python3 engine/harvest.py --ingest                     # rebuild index from raw drops
    python3 engine/harvest.py --coverage                   # N of 821, miss list

Why the agent is in the loop
----------------------------
`SearchMcpRegistry` is an agent tool, not an HTTP endpoint, so this module cannot
call it. It owns the two things that actually matter for cost: the *queue* (what
has not been asked yet) and the *cache* (what came back). The agent runs the
queries and drops raw results into data/harvest/raw/*.tsv.

All state is derived from those raw drop files. Delete the index, rebuild it for
free. Lose the index mid-session, lose nothing. The one rule from PROJECT.md --
never re-harvest what is already cached -- is enforced by --plan, which only ever
emits names that have neither been returned nor been asked for.

Raw drop format (one file per agent turn, append-only, never edited):

    # ASKED: Fireflies | Strava | Shopify
    Fireflies<TAB>839a0ae2-...<TAB>0<TAB>get_user,get_transcript,get_transcripts
    Shopify<TAB>80917cb7-...<TAB>0<TAB>search_products,get-product,+17 more

Column 3 is isAuthless as 0/1. A trailing "+N more" element in the tool list is a
truncation sentinel: the count is recoverable, the names are not. Kept verbatim
so downstream code can see that it is looking at a sample.
"""

import argparse, json, os, re, glob, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
HARVEST = os.path.join(DATA, "harvest")
RAW = os.path.join(HARVEST, "raw")
INDEX = os.path.join(HARVEST, "index.json")

MORE_RE = re.compile(r"^\+(\d+)\s+more$")


def norm(name):
    """Fold a display name to a join key. 'Aha!' -> 'aha', 'Blaze SQL' -> 'blazesql'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


# Display names that differ from the registry's spelling by more than punctuation.
# Populated from the unmatched report, never guessed -- a speculative alias silently
# fabricates a match, which is worse than an honest miss.
ALIASES = {}


def alias(key):
    return ALIASES.get(key, key)


def load_registry():
    full = json.load(open(os.path.join(DATA, "registry_full.json"), encoding="utf-8"))
    return full["connectors"]


# ------------------------------------------------------------------ raw parsing

def read_raw():
    """Parse every raw drop. Returns (records_by_key, asked_keys, asked_display)."""
    records, asked, asked_display = {}, set(), {}
    for path in sorted(glob.glob(os.path.join(RAW, "*.tsv"))):
        stamp = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
        for line in open(path, encoding="utf-8"):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("# ASKED:"):
                for nm in line[len("# ASKED:"):].split("|"):
                    nm = nm.strip()
                    if nm:
                        asked.add(alias(norm(nm)))
                        asked_display.setdefault(alias(norm(nm)), nm)
                continue
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                raise SystemExit(f"malformed raw line in {path}: {line[:80]!r}")
            name, uuid, authless, tools = parts[0], parts[1], parts[2], parts[3]
            key = alias(norm(name))
            tool_list = [t.strip() for t in tools.split(",") if t.strip()]
            truncated = 0
            clean = []
            for t in tool_list:
                m = MORE_RE.match(t)
                if m:
                    truncated = int(m.group(1))
                else:
                    clean.append(t)
            # First write wins: raw drops are append-only and earlier files are
            # not less true than later ones. Re-querying a name is a no-op.
            if key in records:
                continue
            records[key] = {
                "name": name,
                "directory_uuid": uuid,
                "authless": authless.strip() in ("1", "true", "True"),
                "tools": clean,
                "tools_truncated": truncated,
                "tool_count": len(clean) + truncated,
                "harvested_on": stamp,
            }
    return records, asked, asked_display


# ------------------------------------------------------------------- operations

def cmd_ingest(_args):
    records, asked, _ = read_raw()
    conns = load_registry()
    reg_keys = {norm(c["name"]): c["id"] for c in conns}

    matched, unmatched = {}, {}
    for key, rec in records.items():
        if key in reg_keys:
            rec = dict(rec, connector_id=reg_keys[key])
            matched[key] = rec
        else:
            unmatched[key] = rec

    os.makedirs(HARVEST, exist_ok=True)
    json.dump(
        {
            "_schema": {
                "note": "Real tool names from SearchMcpRegistry. Names only -- no "
                        "parameter schemas. Profiles derived from these are HARVESTED, "
                        "a tier between DOCUMENTED and DIRECTORY, never VERIFIED.",
                "tools_truncated": "count of names hidden behind the '+N more' sentinel",
            },
            "generated": datetime.date.today().isoformat(),
            "matched": matched,
            "unmatched": unmatched,
            "asked": sorted(asked),
        },
        open(INDEX, "w", encoding="utf-8"),
        indent=1,
        sort_keys=True,
    )
    print(f"raw drops     : {len(glob.glob(os.path.join(RAW, '*.tsv')))}")
    print(f"records       : {len(records)}")
    print(f"matched       : {len(matched)} / {len(conns)} registry connectors")
    print(f"unmatched     : {len(unmatched)} (in directory, not in our registry)")
    print(f"names asked   : {len(asked)}")
    print(f"-> {os.path.relpath(INDEX, ROOT)}")


def cmd_coverage(args):
    records, asked, _ = read_raw()
    conns = load_registry()
    have, miss, never_asked = [], [], []
    for c in conns:
        k = norm(c["name"])
        if k in records:
            have.append(c)
        else:
            miss.append(c)
            if k not in asked:
                never_asked.append(c)

    n = len(conns)
    print(f"coverage      : {len(have)}/{n}  ({100.0*len(have)/n:.1f}%)")
    print(f"missing       : {len(miss)}   of which never asked: {len(never_asked)}")
    print(f"asked-but-miss: {len(miss) - len(never_asked)}  (not in the directory, or "
          f"named differently)")
    calls = -(-len(never_asked) // max(1, args.batch))
    print(f"calls to go   : >= {calls} at {args.batch} names/call, perfect efficiency")

    # Truncation is a data-quality fact worth reporting alongside coverage.
    trunc = [r for r in records.values() if r["tools_truncated"]]
    if records:
        tot = sum(r["tool_count"] for r in records.values())
        print(f"tools seen    : {sum(len(r['tools']) for r in records.values())} names, "
              f"{tot} total tools claimed, {len(trunc)} records truncated")
        print(f"authless      : {sum(1 for r in records.values() if r['authless'])}")

    if args.list_missing:
        print("\n-- miss list --")
        for c in miss:
            print(f"  {'ASKED ' if norm(c['name']) in asked else '      '}{c['name']}")


def cmd_plan(args):
    """Emit the next batches of names to query. Only ever names never asked before."""
    records, asked, _ = read_raw()
    conns = load_registry()

    todo = [c for c in conns if norm(c["name"]) not in records and norm(c["name"]) not in asked]
    # Group by archetype so each call's keywords are semantically clustered: the
    # registry ranks results, and a coherent query keeps all 10 slots on-topic
    # instead of spending them on one strong keyword's neighbours.
    by_arch = collections.defaultdict(list)
    for c in todo:
        by_arch[c["archetype"]].append(c["name"])

    queue = []
    for arch in sorted(by_arch, key=lambda a: -len(by_arch[a])):
        names = by_arch[arch]
        for i in range(0, len(names), args.batch):
            queue.append(names[i:i + args.batch])

    for batch in queue[:args.calls]:
        print(json.dumps(batch, ensure_ascii=False))
    print(f"# {len(queue)} batches queued, {len(todo)} names outstanding", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--calls", type=int, default=6)
    ap.add_argument("--list-missing", action="store_true")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    if a.plan:
        cmd_plan(a)
    elif a.ingest:
        cmd_ingest(a)
    elif a.coverage:
        cmd_coverage(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
