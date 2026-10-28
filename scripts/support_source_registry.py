"""Private source candidates and append-only policy history. No network operations."""
import json
import re
from datetime import date
from urllib.parse import urlsplit

import support_monitor as monitor

POLICIES = ("unknown", "allowed", "restricted", "prohibited", "needs_review")
ACCESS = ("unknown", "accessible", "inaccessible")
METHODS = ("rss", "api", "bizinfo_api", "html", "other")
TARGETS = ("individual_farmer", "business", "institution", "mixed", "unknown")
SCOPES = ("national", "province", "municipality")
FIELDS = {"source_id", "institution", "region_scope", "region_name", "homepage_url",
          "board_url", "method", "target", "access_status", "automation_policy",
          "reuse_policy", "policy_url", "rights_url", "policy_checked_at", "notes"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS source_management (
 source_id TEXT PRIMARY KEY REFERENCES monitor_sources(source_id), metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_policy_events (
 event_id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES monitor_sources(source_id),
 actor TEXT NOT NULL, reason TEXT NOT NULL, recorded_at TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL
);
"""


def fail(message):
    raise monitor.MonitorError(message)


def url(value):
    if not isinstance(value, str):
        fail("URL must be a string")
    parts = urlsplit(value)
    # Administrative metadata must never become a credential storage channel.
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.port not in (None, 443) or parts.fragment
            or re.search(r"(?:key|token|secret|password|auth|crtfc|session)", parts.query, re.I)):
        fail("use a public HTTPS URL without credentials, secrets or session parameters")
    return value


def validate(data):
    if not isinstance(data, dict) or set(data) - FIELDS:
        fail("unknown source fields; activation and credentials cannot be supplied")
    for name in ("source_id", "institution", "region_name", "homepage_url", "board_url"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            fail("required source field missing: " + name)
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,79}", data["source_id"]):
        fail("invalid source ID")
    for field, options in (("method", METHODS), ("region_scope", SCOPES), ("target", TARGETS),
                           ("access_status", ACCESS), ("automation_policy", POLICIES),
                           ("reuse_policy", POLICIES)):
        if data.get(field) not in options:
            fail("invalid source field: " + field)
    for field in ("homepage_url", "board_url", "policy_url", "rights_url"):
        if data.get(field):
            url(data[field])
    checked = data.get("policy_checked_at")
    if checked:
        if not isinstance(checked, str) or date.fromisoformat(checked).isoformat() != checked:
            fail("policy date must be YYYY-MM-DD")
        if date.fromisoformat(checked) > monitor.datetime.now(monitor.KST).date():
            fail("policy check date cannot be in the future")
    for field, evidence in (("automation_policy", "policy_url"), ("reuse_policy", "rights_url")):
        if data[field] != "unknown" and (not data.get(evidence) or not checked):
            fail("policy decisions require their evidence URL and check date")
    if not isinstance(data.get("notes", ""), str):
        fail("notes must be text")
    return data


def present(connection, row):
    result = {k: row[k] for k in ("source_id", "institution", "board_url", "method", "enabled",
                                 "last_success_at", "last_attempt_at", "last_error")}
    metadata = None
    if monitor.has_table(connection, "source_management"):
        saved = connection.execute("SELECT metadata_json FROM source_management WHERE source_id=?",
                                   (row["source_id"],)).fetchone()
        if saved:
            metadata = json.loads(saved[0])
    result["managed_candidate"] = metadata is not None
    result["metadata"] = metadata or {
        "region_scope": "unknown", "region_name": "unknown", "homepage_url": None,
        "target": "unknown", "access_status": "unknown", "automation_policy": "unknown",
        "reuse_policy": "unknown", "policy_url": None, "rights_url": None,
        "policy_checked_at": None, "notes": "기존 수집 설정은 유지. 새 정책 체계로 재판정하지 않음."
    }
    reasons = []
    if not row["enabled"]:
        reasons.append("collection_disabled")
    if metadata:
        if metadata["automation_policy"] != "allowed":
            reasons.append("automation_policy_not_allowed")
        if metadata["reuse_policy"] != "allowed":
            reasons.append("reuse_policy_not_allowed")
        reasons.append("candidate_activation_not_implemented")
    if row["method"] not in {"rss", "bizinfo_api"}:
        reasons.append("collector_adapter_not_implemented")
    result["block_reasons"] = reasons
    return result


def get(connection, source_id):
    row = connection.execute("SELECT * FROM monitor_sources WHERE source_id=?", (source_id,)).fetchone()
    if not row:
        fail("unknown source ID")
    return present(connection, row)


def listing(connection):
    return [present(connection, row) for row in connection.execute(
        "SELECT * FROM monitor_sources ORDER BY source_id")]


def history(connection, source_id):
    get(connection, source_id)
    if not monitor.has_table(connection, "source_policy_events"):
        return []
    rows = connection.execute("SELECT * FROM source_policy_events WHERE source_id=? ORDER BY event_id",
                              (source_id,))
    return [{**{k: row[k] for k in ("event_id", "actor", "reason", "recorded_at")},
             "before": json.loads(row["before_json"]), "after": json.loads(row["after_json"])}
            for row in rows]


def write(connection, records, actor, reason, update=False):
    monitor.require_actor(actor, reason)
    if not isinstance(records, list) or not records:
        fail("provide a nonempty list of source candidates")
    # Validate the entire batch before any schema or record mutation.
    ids = set()
    for data in records:
        validate(data)
        if data["source_id"] in ids:
            fail("duplicate source ID in batch")
        ids.add(data["source_id"])
        existing = connection.execute("SELECT 1 FROM monitor_sources WHERE source_id=?",
                                      (data["source_id"],)).fetchone()
        managed = monitor.has_table(connection, "source_management") and connection.execute(
            "SELECT 1 FROM source_management WHERE source_id=?", (data["source_id"],)).fetchone()
        if update and not managed:
            fail("only existing managed candidates can be updated; legacy collectors are protected")
        if not update and existing:
            fail("source ID already exists")
    connection.executescript(SCHEMA)
    with connection:
        for data in records:
            before = get(connection, data["source_id"]) if update else None
            if update and before["metadata"]["method"] != data["method"]:
                fail("candidate method is immutable; register a distinct source instead")
            # Reuse source identity, operational status and timestamps in monitor_sources.
            config = {"source_id": data["source_id"], "institution": data["institution"],
                      "board_url": data["board_url"], "method": data["method"],
                      "enabled": False, "discovery_url": None}
            connection.execute("""INSERT INTO monitor_sources
                (source_id,institution,board_url,method,enabled,config_json) VALUES (?,?,?,?,0,?)
                ON CONFLICT(source_id) DO UPDATE SET institution=excluded.institution,
                board_url=excluded.board_url,enabled=0,config_json=excluded.config_json""",
                (data["source_id"], data["institution"], data["board_url"], data["method"], monitor.packed(config)))
            connection.execute("""INSERT INTO source_management VALUES (?,?) ON CONFLICT(source_id)
                DO UPDATE SET metadata_json=excluded.metadata_json""",
                (data["source_id"], monitor.packed(data)))
            connection.execute("""INSERT INTO source_policy_events
                (source_id,actor,reason,recorded_at,before_json,after_json) VALUES (?,?,?,?,?,?)""",
                (data["source_id"], actor.strip(), reason.strip(), monitor.utc_now(),
                 monitor.packed(before), monitor.packed(get(connection, data["source_id"]))))
    return {"registered" if not update else "updated": len(records), "enabled": False}


def add_cli(sub):
    sub.add_parser("source-list", help="read-only source metadata and block reasons")
    for name in ("source-show", "source-policy", "source-history"):
        command = sub.add_parser(name, help="read-only source detail/policy/history")
        command.add_argument("source_id")
    for name in ("source-register", "source-update"):
        command = sub.add_parser(name, help="explicit private DB write; never enables or fetches")
        command.add_argument("file", type=monitor.Path)
        command.add_argument("--reviewer", required=True)
        command.add_argument("--reason", required=True)


def dispatch(connection, args):
    if args.command in {"source-register", "source-update"}:
        data = json.loads(args.file.read_text(encoding="utf-8-sig"))
        return write(connection, data if isinstance(data, list) else [data],
                     args.reviewer, args.reason, update=args.command == "source-update")
    if args.command == "source-list":
        return listing(connection)
    if args.command == "source-history":
        return history(connection, args.source_id)
    result = get(connection, args.source_id)
    if args.command == "source-policy":
        return {"source_id": result["source_id"], "enabled": result["enabled"],
                "metadata": result["metadata"], "block_reasons": result["block_reasons"]}
    return result
