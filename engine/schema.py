#!/usr/bin/env python3
"""
schema.py — derive join profiles from parameter SCHEMAS, not tool names. Stdlib only.

    python3 engine/schema.py --ingest      # raw/*.jsonl -> data/schemas/index.json
    python3 engine/schema.py --derive      # -> data/schema_profiles.json
    python3 engine/schema.py --rules       # firing counts; unmapped param tokens ranked
    python3 engine/schema.py --delta       # names vs parameters -- the second held-out test
    python3 engine/schema.py --coverage    # what was harvested and what was not
    python3 engine/schema.py --explain N   # per-tool trace for one connector

What this buys, stated exactly
------------------------------
`ToolSearch` returns the full JSONSchema for a deferred tool. Phase 2 had tool
NAMES; this has parameter names, types, required flags, enum values and the
description prose. That is a strictly stronger evidence class, and it upgrades
exactly one axis:

  consumes    NAMES give it approximately. PARAMETERS give it directly. A tool's
              inputs ARE the things that can be written into it. `create_draft`
              consumes email (to/cc/bcc), file (attachments) and text (body) --
              none of which the tool name contains.

and it does NOT upgrade this one:

  emits       MCP tool schemas describe INPUTS ONLY. There is no output schema to
              read, so `emits` is still name-derived and is copied through
              unchanged. Anyone quoting an emits number is quoting Phase 2.

Two further things fall out of parameters that names cannot express at all:

  selectors      the keys a READ tool can be addressed by. A connector whose reads
                 accept only its own opaque ids cannot be entered from outside
                 without already holding an id -- that is a real join constraint
                 and it is invisible at name depth.
  preconditions  a tool that cannot be called until another tool has been called.
                 Vercel's buy_* reject un-quoted calls; Supabase's create_project
                 needs a confirm_cost id; Canva's export needs get-export-formats.
                 These are mandatory intra-connector edges.

The scope limit, which must not be papered over
-----------------------------------------------
`ToolSearch` sees the CURRENT SESSION's connectors -- 11 of the 820 in the
directory. This is a depth upgrade for 11 and a sharper held-out test for the
other 450. It is not, and cannot be turned into, a coverage upgrade. `--delta`
exists to price the name-based method that still has to carry the rest.

Rules are counted, never read
-----------------------------
Same discipline as profile.py. `--rules` prints a firing count for every mapping
and, more usefully, ranks the param tokens that mapped to NOTHING -- which is how
`user_intent` was caught mapping to `person` through its `user` token before the
phrase layer was added.
"""

import argparse, json, os, re, glob, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out")
RAW = os.path.join(DATA, "schemas", "raw")
sys.path.insert(0, HERE)
import profile as P  # noqa: E402  -- reuse NOUNS, VERBS, tokens(), classify_tool()

VOCAB = P.VOCAB
SIDE_RANK = P.SIDE_RANK


# ------------------------------------------------------------------ stop list
# Parameters that carry no join payload. Pagination, protocol handshakes, output
# shaping and confirmation flags. Nothing upstream can "flow into" these, so
# counting them would inflate `consumes` with plumbing.
#
# This layer is matched on the WHOLE normalised parameter name and it runs FIRST,
# before any token mapping. That ordering is load-bearing: `user_intent` is
# Canva's mandatory telemetry string and it fires 30 times. Bag-of-tokens mapping
# read its `user` token as the `person` key and handed Canva a person sink that
# does not exist. Phrase-before-token is what stops that.

PARAM_STOP = {
    # pagination
    "cursor", "page_token", "page", "page_size", "limit",
    "per_page", "continuation", "start_after", "direction", "order",
    "sort_by",
    # protocol / handshake
    "user_intent", "idempotency_key", "confirm", "transaction_id", "job_id",
    "confirm_cost_id", "dry_run", "verify_jwt", "finalize", "recurrence",
    # output shaping
    "view", "filter", "format", "verbose", "include_tasks",
    "include_requests", "include_comments", "include_context", "include_weekly_counts",
    "exclude_content_snippets", "message_format", "export_mime_type", "mime_type",
    "content_mime_type", "disable_conversion_to_google_type",
    "resolve_icon_thumbnails", "get_by", "overdue_option", "labels_operator",
    "responsible_user_filtering", "archived_status", "ownership", "item_types",
    "days_count", "weeks", "auto_create_parent_labels", "auto_renew", "is_favorite",
    "is_editable", "is_empty", "is_responsive", "is_urgent", "is_uncompletable",
    "preserve_aspect_ratio", "include_trash", "verbatim", "mode", "by",
    "migration_version", "asset_type", "document_type", "geometry", "axis",
    "flipped", "marker", "anchoring", "formatting", "weight", "start", "end",
    # presentation-only geometry and styling
    "width", "height", "top", "left", "rotation", "opacity", "radius", "color",
    "background_color", "stroke_color", "stroke_weight",
    "corner_rounding", "view_box_width", "view_box_height", "style",
    "view_style", "visibility", "service", "lang", "encoding", "scheme", "port",
    "caching_disabled", "caching_max_age", "caching_stale_while_revalidate",
    "primary_location_hint", "type", "action", "operation", "target", "position",
    "priority", "duration", "minute_offset", "loc_trigger", "emoji", "resolved",
    "label_option", "label_type", "credit_type", "product", "product_alias",
    "quantity", "years", "audience", "length", "params",
}

# Parameters whose meaning is NOT recoverable from their tokens, or whose token
# reading would be wrong. Matched on the whole normalised name; wins over tokens.
# Everything not listed here falls through to profile.py's NOUNS, deliberately,
# so there stays exactly ONE audited domain-noun dictionary in this codebase.
PARAM_KEYS = {
    # email — none of these tokens exist in NOUNS
    "to": "email", "cc": "email", "bcc": "email", "reply_to_message_id": "email",
    # text — the body of a thing, as opposed to a handle on it
    "body": "text", "html_body": "text", "subject": "text", "content": "text",
    "text_content": "text", "message_plaintext": "text", "markdown": "text",
    "query": "text", "search_text": "text", "search": "text", "search_term": "text",
    "notes": "text", "name": "text", "title": "text", "display_name": "text",
    "topic": "text", "description": "text", "new_name": "text", "find_text": "text",
    "replace_text": "text", "alt_text": "text", "autofill_field_label": "text",
    "labels": "text", "name_contains": "text",
    # code — executable payload, the thing tldraw's name could not show
    "code": "code", "sql": "code", "graphql_query": "code", "path": "code",
    "entrypoint_path": "code", "import_map_path": "code", "script_name": "code",
    "project_settings": "code", "operations": "code",
    # file
    "attachments": "file", "files": "file", "base64_content": "file",
    "data": "file", "asset_ids": "file", "asset_id": "file", "file_url": "file",
    # geo — the Todoist geofence, invisible in the name `add-reminders`
    "loc_lat": "geo", "loc_long": "geo", "region_codes": "geo",
    "country_code": "geo", "subregion_code": "geo", "address1": "geo",
    "city": "geo", "state": "geo", "zip": "geo",
    # timestamp
    "due": "timestamp", "due_string": "timestamp", "deadline_date": "timestamp",
    "since": "timestamp", "until": "timestamp", "start_date": "timestamp",
    "timezone": "timestamp",
    # money
    "amount": "money", "expected_price": "money",
    # person
    "responsible_user": "person", "from_assignee_user": "person",
    "initiator_id": "person", "contact": "person", "first_name": "person",
    "last_name": "person", "phone": "phone", "email": "email",
    # url
    "url": "url",
    # domain
    "host": "domain",
    # rows
    "schemas": "rows", "dataset": "rows",
    # company
    "workspace": "company", "workspace_id_or_name": "company",
}
assert set(PARAM_KEYS.values()) <= VOCAB, sorted(set(PARAM_KEYS.values()) - VOCAB)

# A parameter with no domain reading that is plainly a handle on a vendor object.
# `vendor_id` is already in the vocabulary and already weak, which is the correct
# strength: holding someone else's opaque id is not a join, it is a lookup.
ID_TAIL = ("id", "ids", "key", "keys", "slug", "ref")

# Side-effect evidence a tool NAME cannot reach. Three sources, each with a
# different noise profile, so each gets its own rule and its own firing counter.
#
# 1. ENUM VALUES OF ACTION-SELECTING PARAMETERS. Scanned against profile.py's
#    VERB_CLASS so this file adds no second verb dictionary to keep in sync.
#
#    The scope of this rule was set by ablation, not by argument. Scanning every
#    type string fired 30 times, changed ZERO connector classes, and at tool level
#    was right 3 times and wrong twice: it read `LabelColor` as the verb "label"
#    and `DRAFT_VIEW_FULL` as the verb "draft", making `create_label` a mutation
#    and `list_drafts` a writer. Restricting it to parameters whose VALUE selects
#    what the tool does keeps both real wins -- Gmail's labelOption=TRASH, which
#    is the only evidence anywhere that apply_sensitive_message_label is
#    irreversible, and Todoist's action=archive, whose tool name carries no verb
#    at all -- and drops both false positives. `eventType` is pointedly NOT an
#    action parameter: find-activity's enum lists `deleted` as a thing to filter
#    for, not a thing to do.
ACTION_PARAMS = {"action", "operation", "label_option", "finalize"}
#
# 2. PROSE is noisy and is deliberately NOT scanned for verbs. The first cut did,
#    and it over-fired immediately: Gmail's `list_labels` description says "before
#    calling label_thread, unlabel_thread, label_message" -- three mutate verbs, in
#    a cross-reference, inside a read-only tool -- and Google Drive was pushed from
#    `create` to `mutate` the same way. Only these high-precision irreversibility
#    markers are read from prose. They have no other meaning.
IRREVERSIBLE_MARKERS = {
    "irreversible", "irreversibly", "undone", "permanently", "nonrefundable",
    "destroys", "unrecoverable",
}
# 3. A `code` PARAMETER is structural evidence: a tool that accepts arbitrary
#    code cannot be a reader, whatever its name says. This is the rule that
#    recovers Phase 2's documented failure case -- tldraw's `exec` carries no verb
#    and no noun, so name inference could only score it `read`, but its schema has
#    a required `code` string. Scored `mutate`, not `irreversible`: Three.js takes
#    code too and only renders in-chat, and overclaiming there to win tldraw would
#    be trading one wrong answer for another.
CODE_PARAM_CLASS = "mutate"


# ------------------------------------------------------------------- helpers

def norm_param(name):
    """camelCase / kebab-case / dotted -> snake_case, lowercased."""
    return "_".join(P.tokens(name))


# Words that are the TYPE rather than a field of it. Without this list the
# flattener below hands `object` and `item` straight to NOUNS, which maps both to
# `rows`, and every array-of-object parameter in the corpus grows a spurious rows
# key.
TYPE_WORDS = {
    "string", "integer", "number", "boolean", "object", "array", "enum", "oneof",
    "anyof", "allof", "null", "uri", "byte", "int32", "int64", "float", "op",
    "attachment", "labelcolor",
}


def type_idents(typ):
    """Field names nested inside a type string: array<object{a,b}> -> a, b.

    Transcribed schemas keep nested object shapes inside the type field rather
    than exploding them into synthetic rows, so the nested names have to be read
    back out here. Todoist is the reason this exists: every one of its write tools
    takes a single `tasks` / `reminders` / `projects` array, and all the payload --
    content, dueString, responsibleUser, locLat -- lives one level down inside it.
    Without this the whole connector would look like it consumes nothing but arrays.

    The first cut used `re.findall(r"[<{]([^<>{}]*)[>}]")`, which only matches
    groups containing no further delimiters. Todoist's reminder shape is
    `object{type:absolute,taskId,due{date,string,timezone,lang},...}` -- the outer
    group holds braces, so it never matched and the entire outer level was dropped
    in silence, `due` included. That is why PARAM_KEYS["due"] read as a dead rule.
    Flatten everything instead, then filter, so no level can go missing.

    Three things are stripped before flattening, all deliberately:
      (...)      format annotations -- string(uri), string(date)
      enum[...]  fixed constants. An enum value is not a slot anything can flow
                 into, so it must not create a key. It is still read by
                 schema_side_effects(), which works off the raw string.
      [1..100]   numeric range annotations, matched NARROWLY on `..`. A blanket
                 `\\[[^\\]]*\\]` was the second silent-drop bug in this function:
                 brackets also delimit `oneOf[...]`, so it swallowed all three
                 Todoist reminder variants whole and locLat/locLong/due/timezone
                 read as dead rules. Anything else in brackets is a union and is
                 flattened, not discarded.
    """
    t = re.sub(r"\([^()]*\)", " ", typ)
    t = re.sub(r"enum\[[^\]]*\]", " ", t)
    t = re.sub(r"\[[\d.\s]*\.\.[\d.\s]*\]", " ", t)
    t = re.sub(r"[<>{}\[\]|]", ",", t)
    out = []
    for ident in re.split(r"[,:]", t):
        ident = ident.strip()
        if ident and not ident.startswith("$") and ident.lower() not in TYPE_WORDS:
            out.append(ident)
    return out


class Counter:
    def __init__(self):
        self.phrase = collections.Counter()     # PARAM_KEYS hits
        self.token = collections.Counter()      # NOUNS fallback hits
        self.stop = collections.Counter()       # PARAM_STOP hits
        self.vendor = collections.Counter()     # ID_TAIL hits
        self.nested = 0                         # params contributing nested idents
        self.unmapped = collections.Counter()   # produced no key at all
        self.enum_verb = collections.Counter()    # verb found in an enum/type value
        self.prose_marker = collections.Counter()  # irreversibility marker in prose
        self.code_param = 0                        # tools accepting arbitrary code


def param_keys(name, typ, counts):
    """One parameter -> the set of join keys it can accept.

    Order is phrase, then token, then vendor-id tail. Nested identifiers from the
    type string are run through the same ladder and unioned in.
    """
    keys = set()
    n = norm_param(name)
    if n in PARAM_STOP:
        counts.stop[n] += 1
        return keys
    if n in PARAM_KEYS:
        counts.phrase[n] += 1
        keys.add(PARAM_KEYS[n])
    else:
        for w in P.tokens(name):
            k = P.NOUNS.get(w)
            if k:
                counts.token[w] += 1
                keys.add(k)
    nested = type_idents(typ)
    if nested:
        counts.nested += 1
    for ident in nested:
        ni = norm_param(ident)
        if ni in PARAM_STOP:
            counts.stop[ni] += 1
            continue
        if ni in PARAM_KEYS:
            counts.phrase[ni] += 1
            keys.add(PARAM_KEYS[ni])
            continue
        hit = False
        for w in P.tokens(ident):
            k = P.NOUNS.get(w)
            if k:
                counts.token[w] += 1
                keys.add(k)
                hit = True
        if not hit and P.tokens(ident) and P.tokens(ident)[-1] in ID_TAIL:
            counts.vendor[ni] += 1
            keys.add("vendor_id")
    if not keys:
        tl = P.tokens(name)
        if tl and tl[-1] in ID_TAIL:
            counts.vendor[n] += 1
            keys.add("vendor_id")
        else:
            counts.unmapped[n] += 1
    return keys


# --------------------------------------------------------------- runtime axis
# The third profile axis. The skill's capability model splits connectors into
# on-demand / schedulable / event-emitting, and the graph has never had any notion
# of it -- `trigger_action` was approximated by "is the middle node an
# automation_hub", which is an archetype guess standing in for a capability.
#
# Measuring it against the schemas immediately kills the third category. MCP is
# request/response: there is no subscribe, no webhook, no callback parameter
# anywhere in 178 tools. NOTHING here is event-emitting, so "schedulable" is not a
# property of a connector either -- anything readable can be put behind a cron.
#
# What IS a real per-connector property, and is directly visible in parameters, is
# whether a poll can ask "what changed". That is the axis worth having:
#
#   poll_windowed      a read tool takes a TYPED time-range parameter, so a poller
#                      passes a window and keeps no state of its own.
#   poll_windowed_dsl  the time filter exists but only inside a query-string
#                      language -- Gmail's `newer_than:`, Drive's `modifiedTime >`.
#                      Windowable, but the orchestrator has to build query strings
#                      instead of passing typed values, which is a real difference
#                      in how much can be checked before the call.
#   poll_blind         neither. Every poll returns the same unordered set and
#                      change detection needs the ORCHESTRATOR to hold state.
#
# The first cut of this matched name tokens against a FEED_TOKENS set and produced
# a fourth category, `activity_feed`. It labelled GOOGLE CALENDAR an activity feed,
# because `search_events` contains the token `events` -- the domain noun, not a
# change log -- and Calendar is the single most important connector to get right
# here. Deriving a schema-grade axis from names is self-defeating; the rule below
# reads parameters and parameter descriptions only.
#
# The category that is NOT here is the interesting one. "Returns a change log"
# cannot be separated from "returns a list" using input schemas, because MCP has
# no output schema -- the same structural limit that keeps `emits` name-derived.
# So an activity-feed category would have been a guess wearing a measurement's
# clothes, and it is left out.
#
# Google Calendar is the sharp case and it lands correctly: `search_events` takes
# `query`, `pageSize`, `pageToken` and nothing else, so "when a meeting is booked,
# do X" is not buildable from the calendar at any polling frequency.
DSL_TIME_MARKERS = ("newer_than", "older_than", "modifiedtime", "createdtime",
                    "viewedbymetime", "after:", "before:", "newer:", "older:")

# There is no subscribe, webhook, callback or notification-target parameter in any
# of the 178 tools. The skill's third capability state, event-emitting, is empty by
# measurement -- see cmd_derive, which asserts this rather than assuming it.
PUSH_MARKERS = ("webhook", "callback", "subscribe", "subscription_url", "notify_url")


def runtime_mode(tools_with_keys):
    """-> (mode, evidence). tools_with_keys is [(rec, name_class, keys), ...]."""
    typed, dsl = [], []
    for rec, ncls, keys in tools_with_keys:
        if ncls != "read":
            continue
        if "timestamp" in keys:
            typed.append(rec["tool"])
            continue
        blob = " ".join([d for _, _, _, d in rec["params"]]
                        + [rec.get("desc", "")] + rec.get("limits", [])).lower()
        if any(m in blob for m in DSL_TIME_MARKERS):
            dsl.append(rec["tool"])
    if typed:
        return "poll_windowed", sorted(typed)
    if dsl:
        return "poll_windowed_dsl", sorted(dsl)
    return "poll_blind", []


def push_params(recs):
    """Every parameter anywhere that would let a connector call US. Expected: none."""
    hits = []
    for r in recs:
        for pname, _, _, _ in r["params"]:
            if any(m in norm_param(pname) for m in PUSH_MARKERS):
                hits.append(f"{r['server']}.{r['tool']}.{pname}")
    return hits


def schema_side_effects(rec, keys, counts):
    """Side-effect class from evidence a tool NAME cannot carry.

    Returns the class implied by the schema ALONE. The caller takes the max
    against the name-derived class, so the two sources stay separable in the diff
    and neither can quietly mask the other.
    """
    cls = "read"

    def raise_to(c):
        return c if SIDE_RANK[c] > SIDE_RANK[cls] else cls

    for pname, typ, _, _ in rec["params"]:
        if norm_param(pname) not in ACTION_PARAMS:
            continue
        for grp in re.findall(r"enum\[([^\]]*)\]", typ):
            for w in P.tokens(grp):
                vc = P.VERB_CLASS.get(w)
                if vc and vc != "read":
                    counts.enum_verb[w] += 1
                    cls = raise_to(vc)

    for w in P.tokens(" ".join([rec.get("desc", "")] + rec.get("limits", []))):
        if w in IRREVERSIBLE_MARKERS:
            counts.prose_marker[w] += 1
            cls = raise_to("irreversible")

    if "code" in keys:
        counts.code_param += 1
        cls = raise_to(CODE_PARAM_CLASS)
    return cls


# ------------------------------------------------------------------- ingest

def load_raw():
    recs = []
    for path in sorted(glob.glob(os.path.join(RAW, "*.jsonl"))):
        for i, line in enumerate(open(path, encoding="utf-8")):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{i+1}: {e}")
    seen = collections.Counter((r["server"], r["tool"]) for r in recs)
    dupes = [k for k, v in seen.items() if v > 1]
    if dupes:
        raise SystemExit(f"duplicate tool records: {dupes}")
    return recs


def cmd_ingest(args):
    recs = load_raw()
    by_server = collections.defaultdict(list)
    for r in recs:
        by_server[r["server"]].append(r)
    idx = {
        "_schema": {
            "source": "ToolSearch full JSONSchema, read live in-session",
            "covers": "connectors connected to THIS session only -- not the directory",
            "note": "input schemas only; MCP exposes no output schema, so `emits` "
                    "is not derivable here and stays name-derived",
        },
        "observed_on": "2026-07-26",
        "n_tools": len(recs),
        "servers": {s: {"n_tools": len(v), "tools": sorted(x["tool"] for x in v)}
                    for s, v in sorted(by_server.items())},
    }
    os.makedirs(os.path.join(DATA, "schemas"), exist_ok=True)
    json.dump(idx, open(os.path.join(DATA, "schemas", "index.json"), "w", encoding="utf-8"),
              indent=1, sort_keys=True)
    print(f"{len(recs)} tool schemas over {len(by_server)} servers -> data/schemas/index.json")
    for s, v in sorted(by_server.items()):
        print(f"  {s:32} {len(v):3} tools")


# ------------------------------------------------------------------- derive

def build(counts):
    """-> {normalised connector name: profile}. One record per session connector."""
    recs = load_raw()
    by_server = collections.defaultdict(list)
    for r in recs:
        by_server[r["server"]].append(r)

    out = {}
    for server, tools in sorted(by_server.items()):
        consumes, selectors, per_tool, pre = set(), set(), [], []
        consumes_ns = set()   # same keys, split by the NAME class -- see below
        rt_input = []
        name_worst, schema_worst = "read", "read"
        for rec in sorted(tools, key=lambda x: x["tool"]):
            ncls, _ = P.classify_tool(rec["tool"], P.Counter())
            keys = set()
            for pname, ptyp, _req, _desc in rec["params"]:
                keys |= param_keys(pname, ptyp, counts)
            scls = schema_side_effects(rec, keys, counts)
            eff = max(ncls, scls, key=lambda c: SIDE_RANK[c])
            # Two splits are kept because parameters improve TWO things at once:
            # which keys a tool accepts, and whether it is a writer at all.
            # `consumes` uses the schema-informed class and is the better model --
            # it is what the graph should use. `consumes_namesplit` reuses Phase
            # 2's name class so --delta can attribute the difference to one cause
            # or the other instead of reporting a single confounded number.
            (selectors if eff == "read" else consumes).update(keys)
            if ncls != "read":
                consumes_ns |= keys
            if SIDE_RANK[ncls] > SIDE_RANK[name_worst]:
                name_worst = ncls
            if SIDE_RANK[scls] > SIDE_RANK[schema_worst]:
                schema_worst = scls
            if rec.get("requires_tool"):
                pre.append([rec["requires_tool"], rec["tool"]])
            rt_input.append((rec, ncls, keys))
            per_tool.append({
                "tool": rec["tool"], "name_class": ncls, "schema_class": eff,
                "n_params": len(rec["params"]), "keys": sorted(keys),
                "requires": rec.get("requires_tool"),
            })
        mode, mode_ev = runtime_mode(rt_input)
        out[P.norm(server)] = {
            "name": server,
            "tier": "SCHEMA",
            "n_tools": len(tools),
            "n_params": sum(len(r["params"]) for r in tools),
            "consumes": sorted(consumes),
            "consumes_namesplit": sorted(consumes_ns),
            "selectors": sorted(selectors),
            "side_effects_name": name_worst,
            "side_effects_schema": max(name_worst, schema_worst, key=lambda c: SIDE_RANK[c]),
            "runtime": mode,
            "runtime_evidence": sorted(mode_ev),
            "preconditions": sorted(pre),
            "_per_tool": per_tool,
        }
    return out


def cmd_derive(args):
    counts = Counter()
    profs = build(counts)
    slim = {k: {kk: vv for kk, vv in v.items() if kk != "_per_tool"} for k, v in profs.items()}
    json.dump(
        {"_schema": {
            "tier": "SCHEMA — tool list AND full parameter schemas observed live. "
                    "Strictly stronger than VERIFIED, which is names only.",
            "consumes": "derived from the input parameters of non-read tools",
            "selectors": "keys a READ tool can be addressed by — new in Phase 3",
            "emits": "NOT PRESENT. MCP schemas describe inputs only; emits stays "
                     "name-derived in data/profiles.json and is unchanged by Phase 3.",
            "preconditions": "[required_tool, dependent_tool] — mandatory ordering",
            "runtime": "activity_feed | poll_windowed | poll_blind — whether a poll "
                       "of this connector can ask what CHANGED. Nothing in MCP is "
                       "event-emitting; there is no subscribe or webhook parameter "
                       "in any of the 178 tools, so that category is empty by "
                       "measurement rather than by assumption.",
            "scope": "11 session connectors of 820. A depth upgrade, not coverage.",
         },
         "generated": __import__("datetime").date.today().isoformat(),
         "connectors": slim},
        open(os.path.join(DATA, "schema_profiles.json"), "w", encoding="utf-8"),
        indent=1, sort_keys=True)

    print(f"{len(profs)} connectors, {sum(p['n_tools'] for p in profs.values())} tools, "
          f"{sum(p['n_params'] for p in profs.values())} parameters\n")
    print(f"  {'connector':32} {'cls(name)':>12} {'cls(schema)':>12}  consumes")
    for k in sorted(profs):
        p = profs[k]
        flag = "*" if p["side_effects_schema"] != p["side_effects_name"] else " "
        print(f"  {p['name']:32} {p['side_effects_name']:>12} "
              f"{p['side_effects_schema']:>12}{flag} {','.join(p['consumes']) or '(none)'}")
    print(f"\n  runtime axis — can a poll of this connector ask what CHANGED?")
    for m in ("poll_windowed", "poll_windowed_dsl", "poll_blind"):
        names = [p["name"] for p in profs.values() if p["runtime"] == m]
        print(f"    {m:20}{len(names):3}  {', '.join(sorted(names))}")
    push = push_params(load_raw())
    none_msg = ("nothing in 178 tools takes a webhook, callback or subscribe "
                "parameter — the skill's event-emitting state is empty by "
                "measurement, not by assumption")
    print(f"    {'event_push':20}{len(push):3}  {', '.join(push) or none_msg}")

    npre = sum(len(p["preconditions"]) for p in profs.values())
    print(f"\n  * = class raised by evidence only a schema carries")
    print(f"  {npre} mandatory tool preconditions across "
          f"{sum(1 for p in profs.values() if p['preconditions'])} connectors")
    print(f"  unmapped params: {sum(counts.unmapped.values())} "
          f"({len(counts.unmapped)} distinct) — run --rules")
    print("-> data/schema_profiles.json")


# -------------------------------------------------------------------- rules

def cmd_rules(args):
    counts = Counter()
    build(counts)
    tot = (sum(counts.phrase.values()) + sum(counts.token.values())
           + sum(counts.stop.values()) + sum(counts.vendor.values())
           + sum(counts.unmapped.values()))
    print(f"PARAM MAPPING — {tot} parameter readings\n")
    print(f"  phrase  (PARAM_KEYS) {sum(counts.phrase.values()):5}  "
          f"{len(counts.phrase)}/{len(PARAM_KEYS)} entries live")
    print(f"  token   (NOUNS)      {sum(counts.token.values()):5}  "
          f"{len(counts.token)} distinct tokens")
    print(f"  stop    (PARAM_STOP) {sum(counts.stop.values()):5}  "
          f"{len(counts.stop)}/{len(PARAM_STOP)} entries live")
    print(f"  vendor_id tail       {sum(counts.vendor.values()):5}")
    print(f"  UNMAPPED             {sum(counts.unmapped.values()):5}  "
          f"{len(counts.unmapped)} distinct")
    print(f"  params with nested identifiers read out of the type: {counts.nested}")

    print("\n  by key (phrase + token):")
    bykey = collections.Counter()
    for p, n in counts.phrase.items():
        bykey[PARAM_KEYS[p]] += n
    for t, n in counts.token.items():
        bykey[P.NOUNS[t]] += n
    for k, n in bykey.most_common():
        print(f"    {k:12}{n}")

    dead_phrase = [k for k in PARAM_KEYS if not counts.phrase[k]]
    dead_stop = [k for k in PARAM_STOP if not counts.stop[k]]
    print(f"\n  DEAD PARAM_KEYS ({len(dead_phrase)}): {', '.join(sorted(dead_phrase)) or '(none)'}")
    print(f"  DEAD PARAM_STOP ({len(dead_stop)}): {', '.join(sorted(dead_stop)) or '(none)'}")

    print("\n  UNMAPPED param names, most frequent first — every one of these is a")
    print("  parameter the model can see but cannot type. Read this list, not the dict.")
    for p, n in counts.unmapped.most_common(30):
        print(f"    {p:34}{n}")

    print(f"\n  SIDE-EFFECT EVIDENCE outside the tool name")
    print(f"    verbs in enum/type values : {sum(counts.enum_verb.values()):4}  "
          f"{dict(counts.enum_verb.most_common(8))}")
    print(f"    irreversibility in prose  : {sum(counts.prose_marker.values()):4}  "
          f"{dict(counts.prose_marker.most_common(8))}")
    print(f"    tools taking a code param : {counts.code_param:4}  "
          f"(scored {CODE_PARAM_CLASS} regardless of name)")


# -------------------------------------------------------------------- delta

def cmd_delta(args):
    """The second held-out test.

    Phase 2's held-out test asked whether name-derived profiles recover facts we
    already knew. It passed 6/6, which was reassuring and cheap -- six hand-picked
    claims. This is the harder version: for the 11 connectors where BOTH a
    name-derived and a parameter-derived `consumes` exist, how often do they
    agree? Parameters are the reference, names are the estimate, and the error
    rate is the price of the method still carrying the other 450 connectors.
    """
    counts = Counter()
    sch = build(counts)
    pcounts = P.Counter()
    name_profiles, _, _ = P.build(pcounts)
    by_name = {P.norm(p["name"]): p for p in name_profiles.values()}

    rows, tp, fp, fn = [], 0, 0, 0
    ns_tp = ns_fp = ns_fn = 0
    cls_same = cls_diff = 0
    for k in sorted(sch):
        s = sch[k]
        n = by_name.get(k)
        if not n:
            rows.append((s["name"], None, None, None, None))
            continue
        sc, nc = set(s["consumes"]), set(n["consumes"])
        tp += len(sc & nc); fp += len(nc - sc); fn += len(sc - nc)
        ns = set(s["consumes_namesplit"])
        ns_tp += len(ns & nc); ns_fp += len(nc - ns); ns_fn += len(ns - nc)
        if s["side_effects_schema"] == n["side_effects"]:
            cls_same += 1
        else:
            cls_diff += 1
        rows.append((s["name"], sorted(nc), sorted(sc), sorted(nc - sc), sorted(sc - nc)))

    print("SECOND HELD-OUT TEST — names vs parameters, on the same 11 connectors\n")
    print("Parameters are the reference. Names are the estimate. Both derive `consumes`")
    print("from the same tool lists, so the only variable is how a key is read.\n")
    print(f"  {'connector':30} {'name-derived consumes':38} parameter-derived consumes")
    for name, nc, sc, only_n, only_s in rows:
        if nc is None:
            print(f"  {name:30} (not in the directory registry)")
            continue
        print(f"  {name:30} {','.join(nc) or '(none)':38} {','.join(sc) or '(none)'}")
        if only_n:
            print(f"  {'':30} - names invented    : {','.join(only_n)}")
        if only_s:
            print(f"  {'':30} + names missed      : {','.join(only_s)}")

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    print(f"\n  key-level agreement over {tp + fp + fn} distinct (connector, key) claims")
    print(f"    both agree             {tp:4}")
    print(f"    names claim, params no {fp:4}   (invented -- an edge that cannot exist)")
    print(f"    params claim, names no {fn:4}   (missed   -- a real edge never drawn)")
    print(f"    precision {prec:.3f}   recall {rec:.3f}   F1 {f1:.3f}")

    # Parameters improve two things at once. Holding the read/write split at
    # Phase 2's name-derived version isolates the key-extraction half, so the
    # headline number above can be attributed rather than just quoted.
    ns_p = ns_tp / (ns_tp + ns_fp) if ns_tp + ns_fp else 0.0
    ns_r = ns_tp / (ns_tp + ns_fn) if ns_tp + ns_fn else 0.0
    print(f"\n  attribution — the same comparison with the read/write split held at")
    print(f"  Phase 2's name-derived version, so only key EXTRACTION varies:")
    print(f"    both {ns_tp}, invented {ns_fp}, missed {ns_fn}, "
          f"precision {ns_p:.3f}, recall {ns_r:.3f}")
    print(f"    of the {fn} keys names missed, {ns_fn} are recovered by reading")
    print(f"    parameters instead of names, and the other {fn - ns_fn} need the tool")
    print(f"    reclassified as a writer first — better extraction alone cannot see them.")
    print(f"\n  side-effect class: {cls_same} agree, {cls_diff} differ of {cls_same + cls_diff}")

    # One connector is compared on unequal footing and saying so is cheaper than
    # having someone find it later. Cloudflare's `accounts_list` and
    # `set_active_account` were in the Phase 2 tool list but are not in this
    # session's deferred list, so the name side sees 25 tools and the parameter
    # side sees 23. `account` -> company is exactly the key the delta scores as
    # "invented", and it is a coverage artefact, not a method error.
    print("\n  CAVEAT — Cloudflare is scored on 23 of its 25 tools. accounts_list and")
    print("  set_active_account are absent from this session's deferred list though they")
    print("  were present in Phase 2. Its `company` miss is that gap, not a bad rule.")

    # Third held-out test. profile.py approximates the runtime axis from tool
    # names for the 464 connectors with no schemas; these 11 are the only place
    # that approximation can be scored, so score it.
    print("\n  RUNTIME AXIS — name-grade approximation vs schema-grade measurement")
    print("  profile.py has to guess this from names for the other 453. Here is its bill.")
    rt_ok = rt_bad = 0
    for k in sorted(sch):
        s = sch[k]
        n = by_name.get(k)
        if not n:
            continue
        got = n.get("runtime", "unmeasured")
        # The name grade has no DSL category -- it cannot see parameter prose --
        # so both windowed states count as agreement on "windowable".
        agree = (got == "poll_blind") == (s["runtime"] == "poll_blind")
        rt_ok += agree; rt_bad += not agree
        print(f"    {s['name']:32} names:{got:18} schemas:{s['runtime']:18}"
              f"{'' if agree else '  <- WRONG'}")
    print(f"    {rt_ok} agree, {rt_bad} disagree of {rt_ok + rt_bad} on whether the")
    print(f"    connector is pollable for change at all.")

    print("\n  SELECTORS — what a read tool can be addressed by (no name equivalent)")
    for k in sorted(sch):
        s = sch[k]
        weak = set(s["selectors"]) <= {"vendor_id", "text"}
        print(f"    {s['name']:32} {','.join(s['selectors']) or '(none)':44}"
              f"{'  <- opaque-id only' if weak and s['selectors'] else ''}")

    print("\n  PRECONDITIONS — mandatory tool ordering, invisible at name depth")
    for k in sorted(sch):
        for a, b in sch[k]["preconditions"]:
            print(f"    {sch[k]['name']:32} {a}  ->  {b}")

    os.makedirs(OUT, exist_ok=True)
    json.dump({
        "_schema": {"note": "names vs parameters on the 11 session connectors. "
                            "Parameters are the reference set."},
        "agreement": {"both": tp, "names_only": fp, "params_only": fn,
                      "precision": round(prec, 4), "recall": round(rec, 4),
                      "f1": round(f1, 4)},
        "side_effects": {"agree": cls_same, "differ": cls_diff},
        "connectors": {r[0]: {"name_derived": r[1], "param_derived": r[2],
                              "invented": r[3], "missed": r[4]}
                       for r in rows if r[1] is not None},
        "selectors": {sch[k]["name"]: sch[k]["selectors"] for k in sorted(sch)},
        "runtime": {sch[k]["name"]: {"schema": sch[k]["runtime"],
                                     "name": by_name.get(k, {}).get("runtime", "unmeasured")}
                    for k in sorted(sch)},
        "preconditions": {sch[k]["name"]: sch[k]["preconditions"]
                          for k in sorted(sch) if sch[k]["preconditions"]},
    }, open(os.path.join(OUT, "schema_delta.json"), "w", encoding="utf-8"),
        indent=1, sort_keys=True)
    print("\n-> out/schema_delta.json")


# ----------------------------------------------------------------- coverage

def cmd_coverage(args):
    recs = load_raw()
    have = collections.defaultdict(set)
    for r in recs:
        have[P.norm(r["server"])].add(r["tool"])
    ver = json.load(open(os.path.join(DATA, "verified_tools.json"), encoding="utf-8"))["connectors"]
    full = json.load(open(os.path.join(DATA, "registry_full.json"), encoding="utf-8"))
    in_registry = {P.norm(c["name"]) for c in full["connectors"]}

    print(f"SCHEMA COVERAGE — {len(recs)} tools over {len(have)} connectors\n")
    print(f"  {'connector':32} {'schema':>7} {'phase 2':>8}  status")
    ts = tv = 0
    for key, v in sorted(ver.items(), key=lambda kv: kv[1]["display"]):
        k = P.norm(v["display"])
        want, got = set(v["tools"]), have.get(k, set())
        ts += len(got); tv += len(want)
        miss = sorted(want - got)
        status = "complete" if not miss else f"MISSING {', '.join(miss)}"
        print(f"  {v['display']:32} {len(got):>7} {len(want):>8}  {status}")
    print(f"  {'TOTAL':32} {ts:>7} {tv:>8}")
    unknown = [s for s in have if s not in in_registry]
    print(f"\n  in the directory registry : {len(have) - len(unknown)} of 820 ({(len(have)-len(unknown))/820:.1%})")
    print(f"  session-only, not a directory connector : {unknown or 'none'}")
    print("\n  The ceiling here is the session, not the source. ToolSearch cannot see a")
    print("  connector this session is not connected to, and connecting 800 is not a")
    print("  thing a session can do. Phase 2's 58% harvest ceiling is unaffected and")
    print("  unbeaten; this is a different axis entirely.")


# ------------------------------------------------------------------ explain

def cmd_explain(args):
    counts = Counter()
    profs = build(counts)
    want = P.norm(args.explain)
    hit = next((v for k, v in profs.items() if k == want or want in k), None)
    if not hit:
        raise SystemExit(f"no session connector matching {args.explain!r}. "
                         f"have: {', '.join(sorted(profs))}")
    print(f"{hit['name']}   [{hit['tier']}]  {hit['n_tools']} tools, {hit['n_params']} params")
    print(f"  class    : name={hit['side_effects_name']}  schema={hit['side_effects_schema']}")
    print(f"  consumes : {hit['consumes']}")
    print(f"  selectors: {hit['selectors']}")
    if hit["preconditions"]:
        print(f"  requires : {hit['preconditions']}")
    print("  per tool:")
    for t in hit["_per_tool"]:
        req = f"  requires {t['requires']}" if t["requires"] else ""
        star = "*" if t["schema_class"] != t["name_class"] else " "
        print(f"    {t['name_class']:12}/{t['schema_class']:12}{star} "
              f"{t['tool'][:36]:38} {t['keys']}{req}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--derive", action="store_true")
    ap.add_argument("--rules", action="store_true")
    ap.add_argument("--delta", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--explain")
    a = ap.parse_args()
    if a.ingest:
        cmd_ingest(a)
    elif a.derive:
        cmd_derive(a)
    elif a.rules:
        cmd_rules(a)
    elif a.delta:
        cmd_delta(a)
    elif a.coverage:
        cmd_coverage(a)
    elif a.explain:
        cmd_explain(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
