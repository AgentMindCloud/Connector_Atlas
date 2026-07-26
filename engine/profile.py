#!/usr/bin/env python3
"""
profile.py — derive real join profiles from real tool names. Stdlib only.

    python3 engine/profile.py --derive       # -> data/profiles.json  (+ rule firing counts)
    python3 engine/profile.py --rules        # rule table with firing counts, dead rules flagged
    python3 engine/profile.py --heldout      # run the derivation against known ground truth
    python3 engine/profile.py --explain NAME # per-tool trace for one connector

The claim, stated exactly
-------------------------
A tool NAME is evidence about a tool's behaviour. It is not a schema. Everything
this module produces is inference over real evidence, which is a genuinely
different thing from both the archetype guess it replaces and the parameter
schemas it does not have. That tier is called HARVESTED and it is never promoted
to VERIFIED.

Three tiers, and which one a connector gets is recorded per connector:

  VERIFIED   tool list observed live in a session (data/verified_tools.json)
  HARVESTED  tool list from SearchMcpRegistry     (data/harvest/index.json)
  DIRECTORY  no tool list; archetype profile inherited, unchanged from session 1

The two rules that do the work
------------------------------
1. Side-effect class comes from the tool's verb. A connector's class is the
   MAXIMUM over its tools -- one buy_domain makes the whole connector irreversible.

2. Read tools contribute to `emits`. Write tools contribute to `consumes`.
   Nothing else does. This is what kills the fictional edges: a connector with no
   write tools consumes nothing, so no edge can point into it. Fireflies is the
   worked example -- three read tools, therefore zero in-edges, where the
   archetype claimed it consumed url/timestamp/media.

Every rule below is counted, not read. Session 1's lesson was that a subagent
reported two routing rules dead and measurement showed one firing 13 times, so
--rules prints a firing count for every verb and every noun and flags the dead
ones. A rule you cannot count is a rule you are guessing about.
"""

import argparse, json, os, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out")

VOCAB = {
    "code", "company", "domain", "email", "file", "geo", "image", "media", "money",
    "person", "phone", "project", "rows", "text", "ticker", "timestamp", "url", "vendor_id",
}
SIDE_RANK = {"read": 0, "create": 1, "mutate": 2, "irreversible": 3}


# ---------------------------------------------------------------- tokenisation

def tokens(tool):
    """Split a tool name into lowercase word tokens across every convention seen
    in the corpus: snake_case, kebab-case, camelCase, PascalCase, dotted, and
    `vendor__tool` / `Namespace-tool` prefixes."""
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", tool)
    return [w for w in re.split(r"[^A-Za-z0-9]+", t.lower()) if w]


# ------------------------------------------------------------------ verb rules
# A tool's class comes from the FIRST verb-shaped token in its name, scanning left
# to right. Not the first token -- roughly a fifth of harvested tools carry a
# vendor prefix (kpler_get_ais_historical, apollo_enrich_person, hibp_get_breach)
# that would mask the verb. And not the maximum over all verb tokens either: that
# was the first implementation, and counting the firings killed it. `order` was in
# the irreversible list, so Shopify's `get-order` and Razorpay's `fetch_all_orders`
# scored irreversible, and AngelList's `get_close` -- a funding close, a noun --
# scored irreversible too. First-verb-wins reads a tool name the way English does:
# the leading verb governs, later words are its object. `order` is now a noun.

VERBS = {
    "read": [
        "get", "list", "search", "read", "fetch", "query", "find", "lookup", "describe",
        "show", "view", "check", "analyze", "analyse", "explore", "discover", "load",
        "retrieve", "ask", "browse", "compare", "count", "validate", "estimate", "preview",
        "status", "whoami", "me", "download", "diff", "resolve", "match", "predict",
    ],
    "create": [
        "create", "add", "new", "post", "upload", "generate", "compose", "draft", "insert",
        "import", "submit", "build", "render", "make", "start", "launch", "run", "execute",
        "book", "duplicate", "copy", "clone", "export", "save", "publish", "deploy",
        "trigger", "invite", "share", "assign", "apply",
    ],
    "mutate": [
        "update", "edit", "patch", "move", "label", "rename", "set", "change", "modify",
        "amend", "manage", "reorder", "resize", "merge", "complete", "approve", "reject",
        "archive", "pause", "unpause", "activate", "deactivate", "restore", "reset",
        "mark", "tag", "untag", "unlabel", "reschedule", "upsert", "sync", "write",
    ],
    "irreversible": [
        "delete", "remove", "destroy", "purchase", "buy", "pay", "charge", "send", "cancel",
        "refund", "transfer", "close", "terminate", "revoke", "disqualify", "discard",
        "trash", "forget", "clear", "drop", "wipe", "checkout", "sign",
    ],
}
VERB_CLASS = {v: cls for cls, vs in VERBS.items() for v in vs}


# ------------------------------------------------------------------ noun rules
# One dict, as PROJECT.md asks, so the whole key model is auditable in one screen.
# A token maps to exactly one key; ambiguity is resolved once, here, and the
# firing counts below make a bad choice visible rather than invisible.

NOUNS = {
    # email
    "email": "email", "mail": "email", "inbox": "email", "thread": "email",
    "threads": "email", "recipient": "email", "sender": "email", "senders": "email",
    "draft": "email", "drafts": "email", "subscriber": "email", "subscribers": "email",
    # file
    "file": "file", "files": "file", "document": "file", "documents": "file",
    "doc": "file", "docs": "file", "attachment": "file", "asset": "file",
    "assets": "file", "folder": "file", "pdf": "file", "upload": "file",
    "bucket": "file", "template": "file", "templates": "file",
    # timestamp
    "event": "timestamp", "events": "timestamp", "calendar": "timestamp",
    "meeting": "timestamp", "meetings": "timestamp", "schedule": "timestamp",
    "availability": "timestamp", "appointment": "timestamp", "deadline": "timestamp",
    "deadlines": "timestamp", "date": "timestamp", "history": "timestamp",
    "reminder": "timestamp", "reminders": "timestamp", "timeseries": "timestamp",
    "activity": "timestamp", "activities": "timestamp",
    # money
    "invoice": "money", "invoices": "money", "payment": "money", "payments": "money",
    "payout": "money", "transaction": "money", "transactions": "money",
    "price": "money", "prices": "money", "rate": "money", "rates": "money",
    "billing": "money", "cost": "money", "spend": "money", "revenue": "money",
    "refund": "money", "refunds": "money", "card": "money", "cards": "money",
    "budget": "money", "budgets": "money", "expense": "money", "expenses": "money",
    "balance": "money", "balances": "money", "payroll": "money", "tax": "money",
    "subscription": "money", "cart": "money", "order": "money", "orders": "money",
    "deal": "money", "deals": "money", "opportunity": "money", "opportunities": "money",
    # rows
    "row": "rows", "rows": "rows", "table": "rows", "tables": "rows", "sql": "rows",
    "dataset": "rows", "datasets": "rows", "record": "rows", "records": "rows",
    "database": "rows", "databases": "rows", "schema": "rows", "metric": "rows",
    "metrics": "rows", "report": "rows", "reports": "rows", "dashboard": "rows",
    "dashboards": "rows", "analytics": "rows", "stats": "rows", "chart": "rows",
    "charts": "rows", "column": "rows", "columns": "rows", "sheet": "rows",
    "spreadsheet": "rows", "warehouse": "rows",
    # Added after measuring the unmapped-token frequencies: these are the domain
    # nouns that were falling through. Structural words (by/to/from/details/info/
    # data/all) outrank them in the corpus and are deliberately left unmapped --
    # they say nothing about payload.
    "product": "rows", "products": "rows", "inventory": "rows", "item": "rows",
    "items": "rows", "object": "rows", "objects": "rows", "catalog": "rows",
    # url
    "url": "url", "urls": "url", "link": "url", "links": "url", "page": "url",
    "pages": "url", "site": "url", "sites": "url", "website": "url",
    "websites": "url", "endpoint": "url", "endpoints": "url",
    # company
    "company": "company", "companies": "company", "organization": "company",
    "organizations": "company", "organisation": "company", "org": "company",
    "account": "company", "accounts": "company", "business": "company",
    "businesses": "company", "brand": "company", "brands": "company",
    "merchant": "company", "vendor": "company", "vendors": "company",
    "supplier": "company", "entity": "company", "entities": "company",
    "workspace": "company", "workspaces": "company",
    # person
    "person": "person", "people": "person", "contact": "person",
    "contacts": "person", "user": "person", "users": "person",
    "employee": "person", "employees": "person", "candidate": "person",
    "candidates": "person", "member": "person", "members": "person",
    "customer": "person", "customers": "person", "lead": "person",
    "leads": "person", "prospect": "person", "prospects": "person",
    "athlete": "person", "profile": "person", "attendee": "person",
    "contributor": "person", "collaborator": "person", "contacts": "person",
    # image
    "image": "image", "images": "image", "photo": "image", "picture": "image",
    "screenshot": "image", "thumbnail": "image", "figure": "image",
    "logo": "image", "logos": "image", "design": "image", "designs": "image",
    "diagram": "image", "slide": "image", "slides": "image", "shape": "image",
    "shapes": "image", "svg": "image",
    # media
    "video": "media", "videos": "media", "audio": "media", "recording": "media",
    "recordings": "media", "media": "media", "track": "media", "tracks": "media",
    "playlist": "media", "song": "media", "songs": "media", "call": "media",
    "calls": "media", "voice": "media", "sound": "media", "podcast": "media",
    # code
    "code": "code", "repo": "code", "repos": "code", "repository": "code",
    "commit": "code", "commits": "code", "branch": "code", "branches": "code",
    "function": "code", "snippet": "code", "sdk": "code", "api": "code",
    "worker": "code", "workers": "code", "deployment": "code", "script": "code",
    # project
    "project": "project", "projects": "project", "board": "project",
    "boards": "project", "task": "project", "tasks": "project",
    "issue": "project", "issues": "project", "ticket": "project",
    "tickets": "project", "workflow": "project", "workflows": "project",
    "sprint": "project", "milestone": "project", "epic": "project",
    "todo": "project", "todos": "project", "matter": "project",
    "matters": "project", "case": "project", "cases": "project",
    "job": "project", "jobs": "project", "pipeline": "project",
    "campaign": "project", "campaigns": "project",
    # geo
    "location": "geo", "locations": "geo", "address": "geo", "addresses": "geo",
    "city": "geo", "cities": "geo", "place": "geo", "region": "geo",
    "regions": "geo", "country": "geo", "countries": "geo", "geo": "geo",
    "coordinates": "geo", "trail": "geo", "trails": "geo", "route": "geo",
    "weather": "geo", "hotel": "geo", "hotels": "geo", "flight": "geo",
    "map": "geo", "maps": "geo",
    "flights": "geo", "airport": "geo", "shipment": "geo", "tracking": "geo",
    # phone
    "phone": "phone", "sms": "phone", "number": "phone",
    # ticker
    "ticker": "ticker", "stock": "ticker", "stocks": "ticker", "equity": "ticker",
    "equities": "ticker", "security": "ticker", "securities": "ticker",
    "symbol": "ticker", "quote": "ticker", "fund": "ticker", "funds": "ticker",
    "instrument": "ticker", "instruments": "ticker", "bond": "ticker",
    "portfolio": "ticker", "holdings": "ticker",
    # domain
    "domain": "domain", "domains": "domain", "dns": "domain", "hostname": "domain",
    # text
    "note": "text", "notes": "text", "summary": "text", "transcript": "text",
    "transcripts": "text", "comment": "text", "comments": "text",
    "content": "text", "article": "text", "articles": "text", "post": "text",
    "posts": "text", "description": "text", "answer": "text", "message": "text",
    "messages": "text", "paper": "text", "papers": "text", "text": "text",
    "insight": "text", "insights": "text", "review": "text", "reviews": "text",
    "feedback": "text", "highlight": "text", "highlights": "text",
    "opinion": "text", "guidance": "text", "docs": "text",
    # vendor_id
    "identifier": "vendor_id", "identifiers": "vendor_id",
}
assert set(NOUNS.values()) <= VOCAB, sorted(set(NOUNS.values()) - VOCAB)

# A search-shaped tool with no recognisable noun still returns prose. This is the
# only rule that invents a key from nothing, so it is isolated here and counted
# separately; without it, single-tool connectors like Consensus ("search") would
# be scored as total isolates on no evidence either way.
SEARCH_VERBS = {"search", "query", "ask", "fetch", "find", "explore", "answer"}


# -------------------------------------------------------------- the derivation

class Counter:
    """Firing counts for every rule, so dead and overfiring rules are visible."""

    def __init__(self):
        self.verb = collections.Counter()
        self.noun = collections.Counter()
        self.fallback_text = 0
        self.unclassified = 0


def classify_tool(tool, counts):
    """-> (side_effect_class, {keys}). Returns ('read', set()) for an unparseable name."""
    toks = tokens(tool)
    cls, keys = None, set()
    for w in toks:
        c = VERB_CLASS.get(w)
        if c and cls is None:
            counts.verb[w] += 1
            cls = c
        k = NOUNS.get(w)
        if k:
            counts.noun[w] += 1
            keys.add(k)
    if cls is None:
        # No verb anywhere in the name (ARPA, WolframAlpha, EconomicData, Cortex
        # Search). Default to read: it is the choice that cannot manufacture an
        # in-edge, which is the failure mode this whole exercise exists to fix.
        counts.unclassified += 1
        cls = "read"
    if not keys and any(w in SEARCH_VERBS for w in toks):
        counts.fallback_text += 1
        keys.add("text")
    return cls, keys


def derive(tool_list, counts):
    """Reads feed `emits`, writes feed `consumes`. Nothing else feeds either."""
    emits, consumes, per_tool = set(), set(), []
    worst = "read"
    for t in tool_list:
        cls, keys = classify_tool(t, counts)
        per_tool.append({"tool": t, "class": cls, "keys": sorted(keys)})
        if SIDE_RANK[cls] > SIDE_RANK[worst]:
            worst = cls
        (emits if cls == "read" else consumes).update(keys)
    return {
        "side_effects": worst,
        "emits": sorted(emits),
        "consumes": sorted(consumes),
        "n_tools": len(tool_list),
        "_per_tool": per_tool,
    }


# ------------------------------------------------------------------ data loads

def norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def load_all():
    full = json.load(open(os.path.join(DATA, "registry_full.json"), encoding="utf-8"))
    hv_path = os.path.join(DATA, "harvest", "index.json")
    harvest = json.load(open(hv_path, encoding="utf-8"))["matched"] if os.path.exists(hv_path) else {}
    ver = json.load(open(os.path.join(DATA, "verified_tools.json"), encoding="utf-8"))["connectors"]
    return full, harvest, ver


def build(counts):
    full, harvest, ver = load_all()
    verified = {norm(k): v for k, v in ver.items()}
    profiles, tiers = {}, collections.Counter()

    for c in full["connectors"]:
        key = norm(c["name"])
        arche = full["archetypes"][c["archetype"]]
        rec = {
            "id": c["id"], "name": c["name"], "archetype": c["archetype"],
            "inherited": {
                "emits": sorted(c["emits"]), "consumes": sorted(c["consumes"]),
                "side_effects": c["side_effects"],
            },
        }
        if key in verified:
            v = verified[key]
            rec.update(derive(v["tools"], counts))
            rec["tier"] = "VERIFIED"
            rec["tools"] = v["tools"]
            rec["tools_truncated"] = 0
            rec["authless"] = bool(harvest.get(key, {}).get("authless"))
        elif key in harvest and harvest[key]["tools"]:
            h = harvest[key]
            rec.update(derive(h["tools"], counts))
            rec["tier"] = "HARVESTED"
            rec["tools"] = h["tools"]
            rec["tools_truncated"] = h["tools_truncated"]
            rec["authless"] = h["authless"]
            rec["harvested_on"] = h["harvested_on"]
        else:
            # No tool evidence at all: keep session 1's archetype profile, but say so.
            rec.update({
                "side_effects": c["side_effects"],
                "emits": sorted(c["emits"]), "consumes": sorted(c["consumes"]),
                "n_tools": 0, "_per_tool": [],
            })
            rec["tier"] = "DIRECTORY"
            rec["tools"] = []
            rec["tools_truncated"] = 0
            rec["authless"] = bool(harvest.get(key, {}).get("authless"))
        # A connector in the harvest whose tool list came back empty is a distinct
        # state from one never returned at all -- flag it rather than blurring it.
        if key in harvest and not harvest[key]["tools"]:
            rec["no_tools_listed"] = True
        tiers[rec["tier"]] += 1
        profiles[c["id"]] = rec
    return profiles, tiers, full


# -------------------------------------------------------------------- commands

def cmd_derive(args):
    counts = Counter()
    profiles, tiers, _ = build(counts)
    os.makedirs(DATA, exist_ok=True)
    slim = {k: {kk: vv for kk, vv in v.items() if kk != "_per_tool"} for k, v in profiles.items()}
    json.dump(
        {"_schema": {
            "tiers": "VERIFIED = live session observation; HARVESTED = derived from real "
                     "registry tool names (names only, no schemas); DIRECTORY = archetype "
                     "inherited, no tool evidence",
            "rule": "read tools -> emits, write tools -> consumes, nothing else",
         },
         "generated": __import__("datetime").date.today().isoformat(),
         "tiers": dict(tiers), "connectors": slim},
        open(os.path.join(DATA, "profiles.json"), "w", encoding="utf-8"),
        indent=1, sort_keys=True,
    )

    ev = collections.Counter(p["side_effects"] for p in profiles.values())
    iv = collections.Counter(p["inherited"]["side_effects"] for p in profiles.values())
    no_consume = [p for p in profiles.values() if not p["consumes"]]
    isolates = [p for p in profiles.values() if not p["emits"] and not p["consumes"]]
    print("tiers        :", dict(tiers))
    print("side effects : derived", dict(ev))
    print("               inherit", dict(iv))
    print(f"consumes = 0 : {len(no_consume)} connectors  "
          f"({sum(1 for p in no_consume if p['tier'] != 'DIRECTORY')} of them on real tool evidence)")
    print(f"isolates     : {len(isolates)} emit nothing and consume nothing")
    print(f"unclassified : {counts.unclassified} tool names contained no known verb")
    print(f"text fallback: {counts.fallback_text} search-shaped tools with no noun")
    print("-> data/profiles.json")


def cmd_rules(args):
    counts = Counter()
    build(counts)
    print("VERB RULES  (firings)")
    for cls in ("read", "create", "mutate", "irreversible"):
        live = [(v, counts.verb[v]) for v in VERBS[cls] if counts.verb[v]]
        dead = [v for v in VERBS[cls] if not counts.verb[v]]
        live.sort(key=lambda x: -x[1])
        print(f"  {cls:13} {sum(n for _, n in live):5} firings over {len(live)} live verbs")
        print(f"    top   : {', '.join(f'{v}={n}' for v, n in live[:10])}")
        print(f"    DEAD  : {', '.join(dead) if dead else '(none)'}")
    print()
    print("NOUN RULES  (firings, grouped by key)")
    by_key = collections.defaultdict(list)
    for tok, key in NOUNS.items():
        by_key[key].append((tok, counts.noun[tok]))
    for key in sorted(by_key, key=lambda k: -sum(n for _, n in by_key[k])):
        toks = sorted(by_key[key], key=lambda x: -x[1])
        total = sum(n for _, n in toks)
        dead = [t for t, n in toks if not n]
        print(f"  {key:10} {total:5} firings   top: "
              f"{', '.join(f'{t}={n}' for t, n in toks[:6] if n)}")
        if dead:
            print(f"             DEAD: {', '.join(dead)}")
    print()
    print(f"  search->text fallback : {counts.fallback_text}")
    print(f"  unclassified (no verb): {counts.unclassified}")


def cmd_explain(args):
    counts = Counter()
    profiles, _, _ = build(counts)
    want = norm(args.explain)
    hit = [p for p in profiles.values() if norm(p["name"]) == want or p["id"] == args.explain]
    if not hit:
        raise SystemExit(f"no connector matching {args.explain!r}")
    p = hit[0]
    print(f"{p['name']}   [{p['tier']}]  archetype={p['archetype']}  tools={p['n_tools']}"
          + (f" (+{p['tools_truncated']} hidden)" if p.get("tools_truncated") else ""))
    print(f"  derived  : {p['side_effects']:12} emits={p['emits']}  consumes={p['consumes']}")
    i = p["inherited"]
    print(f"  inherited: {i['side_effects']:12} emits={i['emits']}  consumes={i['consumes']}")
    print("  per tool:")
    for t in p["_per_tool"]:
        print(f"    {t['class']:13} {t['tool'][:44]:46} {t['keys']}")


def cmd_heldout(args):
    """Run the derivation against connectors whose behaviour is independently known.

    This is the only honest way to price the method. If name-based inference
    cannot recover facts we already have, it should not be trusted on the 460
    connectors where we have nothing to check it against."""
    counts = Counter()
    profiles, _, _ = build(counts)
    ver = json.load(open(os.path.join(DATA, "verified_tools.json"), encoding="utf-8"))["connectors"]
    by_name = {norm(p["name"]): p for p in profiles.values()}

    print("HELD-OUT TEST — derivation vs. independently known behaviour\n")
    hits = misses = 0

    checks = [
        # The claim is about a missing tool, so test for the missing tool. An
        # earlier version of this check asserted class <= create and failed, but
        # it was the check that was wrong, not the derivation: see the note printed
        # below the table.
        ("gmail", "exposes no send tool",
         lambda p: not any("send" in tokens(t["tool"]) for t in p["_per_tool"]),
         lambda p: f"verbs present: {sorted({c for c in (t['class'] for t in p['_per_tool'])})}; "
                   f"no tool token 'send' in {p['n_tools']} tools"),
        ("google calendar", "read-only, one search tool",
         lambda p: p["side_effects"] == "read" and p["consumes"] == [],
         lambda p: f"derived {p['side_effects']}, consumes={p['consumes']}; "
                   f"inherited said {p['inherited']['side_effects']}, "
                   f"consumes={p['inherited']['consumes']}"),
        ("vercel", "spends real money (buy_*)",
         lambda p: p["side_effects"] == "irreversible"
                   and any(t["tool"].startswith("buy") for t in p["_per_tool"]),
         lambda p: f"derived {p['side_effects']}; "
                   f"buy_* tools seen: {[t['tool'] for t in p['_per_tool'] if t['tool'].startswith('buy')]}"),
        ("google drive", "creates files, cannot delete",
         lambda p: p["side_effects"] == "create" and "file" in p["consumes"],
         lambda p: f"derived {p['side_effects']}, consumes={p['consumes']}"),
        ("supabase", "destructive project operations",
         lambda p: p["side_effects"] == "irreversible",
         lambda p: f"derived {p['side_effects']}"),
    ]
    for key, claim, test, note in checks:
        p = by_name.get(norm(key))
        if not p:
            print(f"  SKIP  {key}: not in registry"); continue
        ok = test(p)
        hits, misses = hits + ok, misses + (not ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {p['name']} — {claim}\n        {note(p)}")

    # Cloudflare is a family-level claim, not a connector-level one: the connector
    # really is irreversible (r2/d1/kv delete), and the interesting fact lives one
    # level down. Test it where it actually is.
    p = by_name.get(norm("Cloudflare Developer Platform"))
    if p:
        fam = [t for t in p["_per_tool"] if t["tool"].startswith("workers_")]
        worst = max((t["class"] for t in fam), key=lambda c: SIDE_RANK[c], default="read")
        ok = worst == "read"
        hits, misses = hits + ok, misses + (not ok)
        print(f"  {'PASS' if ok else 'FAIL'}  Cloudflare — workers_* family is read-only "
              f"(cannot deploy a Worker)\n        family class = {worst} over "
              f"{[t['tool'] for t in fam]}\n        connector class = {p['side_effects']} "
              f"(correct: d1/kv/r2 do delete)")

    # And one case the method is expected to fail, stated up front rather than
    # discovered later. tldraw's `exec` runs arbitrary canvas JavaScript.
    p = by_name.get(norm("tldraw"))
    if p:
        print(f"\n  KNOWN FAILURE  tldraw — derived {p['side_effects']}, "
              f"emits={p['emits']}, consumes={p['consumes']}")
        print("        `exec` runs arbitrary JavaScript against the canvas. The name "
              "carries no\n        noun and no destructive verb, so the derivation "
              "cannot see that this one\n        tool subsumes create, mutate and delete. "
              "Name-based inference has a floor,\n        and this is it.")

    print(f"\n  {hits} passed, {misses} failed of {hits + misses} checkable claims.")
    print("  Ground truth for each is recorded in data/verified_tools.json.")

    # One banked constraint did not survive re-measurement. Say so here rather
    # than quietly carrying it forward.
    g = by_name.get(norm("Gmail"))
    if g:
        dele = [t["tool"] for t in g["_per_tool"] if t["class"] == "irreversible"]
        print(f"\n  CORRECTION to a banked constraint — Gmail's side-effect class")
        print(f"        PROJECT.md records 'registry says irreversible; reality is create'.")
        print(f"        The live tool list now contains {dele}, so the connector really is")
        print(f"        irreversible and the registry was right for the wrong reason. The")
        print(f"        specific claim that survives is the narrow one: no send tool exists.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--derive", action="store_true")
    ap.add_argument("--rules", action="store_true")
    ap.add_argument("--heldout", action="store_true")
    ap.add_argument("--explain")
    a = ap.parse_args()
    if a.derive:
        cmd_derive(a)
    elif a.rules:
        cmd_rules(a)
    elif a.heldout:
        cmd_heldout(a)
    elif a.explain:
        cmd_explain(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
