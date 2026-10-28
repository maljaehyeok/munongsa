"""Private, version-bound eligibility evidence. No applicant matching or publication."""
import json
import math
import re
from datetime import date

import support_monitor as monitor

KINDS = ("applicant", "residence", "business_location", "age", "farming_experience",
         "independent_management", "farm_registration", "crop", "livestock", "scale",
         "facility", "other_required", "exclusion")
STATES = ("candidate", "verified", "ambiguous", "conflict")
PRESENCE = ("specified", "no_restriction", "unknown")
SCHEMA = """
CREATE TABLE IF NOT EXISTS eligibility_revisions (
 revision_id INTEGER PRIMARY KEY, notice_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 round_id TEXT, snapshot_json TEXT NOT NULL, payload_json TEXT NOT NULL,
 action TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL, reason TEXT NOT NULL
);
"""


def fail(message):
    raise monitor.MonitorError(message)


def snapshot(connection, notice_id):
    record = monitor.notice_record(connection, notice_id)
    body = None
    if monitor.has_table(connection, "body_versions"):
        row = connection.execute("SELECT body_version_id,content_hash FROM body_versions WHERE notice_id=? ORDER BY body_version_id DESC LIMIT 1",
                                 (notice_id,)).fetchone()
        body = dict(row) if row else None
    return {"source_id": record["source_id"], "original_id": record["original_id"],
            "round_id": record["round_id"], "rss_content_hash": record["content_hash"], "body": body}


def latest(connection, notice_id):
    monitor.notice_record(connection, notice_id)
    if not monitor.has_table(connection, "eligibility_revisions"):
        return None
    return connection.execute("SELECT * FROM eligibility_revisions WHERE notice_id=? ORDER BY revision_id DESC LIMIT 1",
                              (notice_id,)).fetchone()


def describe(connection, row):
    result = dict(row)
    result["snapshot"] = json.loads(result.pop("snapshot_json"))
    result["payload"] = json.loads(result.pop("payload_json"))
    result["needs_review"] = result["snapshot"] != snapshot(connection, row["notice_id"]) or row["action"] == "source_changed"
    for condition in result["payload"]["conditions"]:
        condition["effective_status"] = "candidate" if result["needs_review"] else condition["status"]
    result["publication_effect"] = "none; condition verification is not notice approval"
    return result


def show(connection, notice_id):
    row = latest(connection, notice_id)
    return describe(connection, row) if row else {"notice_id": notice_id, "conditions": [], "status": "not_collected"}


def history(connection, notice_id):
    latest(connection, notice_id)
    if not monitor.has_table(connection, "eligibility_revisions"):
        return []
    return [describe(connection, row) for row in connection.execute(
        "SELECT * FROM eligibility_revisions WHERE notice_id=? ORDER BY revision_id", (notice_id,))]


def write_revision(connection, notice_id, payload, actor, reason, action):
    current = snapshot(connection, notice_id)
    cursor = connection.execute("""INSERT INTO eligibility_revisions
        (notice_id,round_id,snapshot_json,payload_json,action,actor,recorded_at,reason) VALUES (?,?,?,?,?,?,?,?)""",
        (notice_id, current["round_id"], monitor.packed(current), monitor.packed(payload),
         action, actor.strip(), monitor.utc_now(), reason.strip()))
    return cursor.lastrowid


def invalidate(connection, notice_id, reason):
    """Called inside an existing successful source-change transaction; no schema creation."""
    row = latest(connection, notice_id)
    if row is None:
        return
    payload = json.loads(row["payload_json"])
    for condition in payload["conditions"]:
        condition.update(status="candidate", reviewer=None, reviewed_at=None)
    write_revision(connection, notice_id, payload, "source-version-monitor", reason, "source_changed")


def check_date(value):
    if value != "unknown" and (not isinstance(value, str) or date.fromisoformat(value).isoformat() != value):
        fail("reference date must be YYYY-MM-DD or unknown")


def check_range(value):
    for key in ("min", "max"):
        number = value.get(key)
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))
                                   or not math.isfinite(number) or number < 0):
            fail("range bounds must be finite nonnegative numbers or null (unspecified bound)")
    if value.get("min") is None and value.get("max") is None:
        fail("at least one explicit bound is required; otherwise use unknown/no_restriction")
    if value.get("min") is not None and value.get("max") is not None and value["min"] > value["max"]:
        fail("min cannot exceed max")
    for field in ("min_inclusive", "max_inclusive"):
        if type(value.get(field)) is not bool:
            fail("inclusive/exclusive bounds must be explicitly recorded")


def strings(value):
    return isinstance(value, list) and bool(value) and all(isinstance(s, str) and s.strip() for s in value)


def check_condition(condition, record, verified=False):
    if condition.get("kind") not in KINDS or condition.get("presence") not in PRESENCE:
        fail("invalid condition kind or presence")
    presence, value, kind = condition["presence"], condition.get("value"), condition["kind"]
    if presence != "specified":
        if value is not None:
            fail("unknown/no_restriction must have null value")
        if verified and presence == "unknown":
            fail("unknown information cannot be verified")
    else:
        if not isinstance(value, dict) or not value:
            fail("specified conditions require structured values")
        if kind == "applicant":
            if not strings(value.get("one_of")) or set(value["one_of"]) - {"individual_farmer", "agricultural_business", "institution_group"}:
                fail("invalid applicant types")
        elif kind in {"residence", "business_location"}:
            if not strings(value.get("regions")):
                fail("explicit regions are required; do not infer nationwide scope")
        elif kind in {"age", "farming_experience", "independent_management", "scale"}:
            check_range(value)
            if kind != "scale":
                check_date(value.get("basis_date", "unknown"))
                if verified and value.get("basis_date", "unknown") == "unknown":
                    fail("age/experience verification requires its reference date")
                if kind == "age":
                    if value.get("age_basis") not in ("international", "calendar", "other", "unknown"):
                        fail("record the age counting basis")
                    if any(v is not None and not isinstance(v, int) for v in (value.get("min"), value.get("max"))):
                        fail("age bounds must be whole years")
                    if verified and value["age_basis"] == "unknown":
                        fail("unknown age counting basis cannot be verified")
                elif value.get("unit") not in ("years", "months", "days"):
                    fail("experience unit is required")
            elif not isinstance(value.get("unit"), str) or not value["unit"].strip() or not value.get("metric"):
                fail("scale metric and unit are required")
        elif kind == "farm_registration":
            if type(value.get("registered")) is not bool:
                fail("registration condition must specify registered true/false")
        elif kind in {"crop", "livestock"}:
            if not strings(value.get("any_of")):
                fail("explicit crop/livestock names are required")
        elif kind == "facility":
            if not strings(value.get("required_features")):
                fail("facility requirements must be explicit")
        elif not isinstance(value.get("text"), str) or not value["text"].strip():
            fail("other/exclusion conditions require their text")
    evidence = condition.get("evidence", {})
    if not isinstance(evidence, dict) or set(evidence) - {"url", "location", "quote", "document_sha256"}:
        fail("invalid evidence fields")
    if any(not isinstance(value, str) for value in evidence.values()):
        fail("evidence values must be text")
    if evidence.get("url"):
        monitor.evidence_record(record, evidence["url"], evidence.get("location"))
        from support_source_registry import url
        url(evidence["url"])
    if evidence.get("document_sha256") and not re.fullmatch(r"[a-f0-9]{64}", evidence["document_sha256"]):
        fail("invalid attachment fingerprint")
    if verified:
        for field in ("url", "location", "quote"):
            if not isinstance(evidence.get(field), str) or evidence[field].strip() in {"", "unknown"}:
                fail("verification requires official URL, evidence location and original quotation")


def check_payload(payload, record):
    if not isinstance(payload, dict) or set(payload) != {"conditions", "logic"}:
        fail("provide conditions and logic only")
    conditions = payload["conditions"]
    if not isinstance(conditions, list) or not 1 <= len(conditions) <= 60:
        fail("provide 1..60 conditions")
    ids = set()
    for condition in conditions:
        if not isinstance(condition, dict) or set(condition) - {"condition_id", "kind", "presence", "value", "evidence"}:
            fail("registration accepts candidate condition fields only")
        identity = condition.get("condition_id", "")
        if not isinstance(identity, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", identity) or identity in ids:
            fail("condition IDs must be valid and unique")
        ids.add(identity)
        check_condition(condition, record)
    referenced = set()
    count = 0
    def walk(node, depth=0):
        nonlocal count
        count += 1
        if depth > 12 or count > 200 or not isinstance(node, dict):
            fail("invalid or overly complex logic")
        if set(node) == {"condition_id"}:
            if not isinstance(node["condition_id"], str) or node["condition_id"] not in ids:
                fail("logic refers to an unknown condition")
            referenced.add(node["condition_id"])
            return
        if set(node) - {"op", "children", "note"} or node.get("op") not in ("AND", "OR", "NOT", "UNKNOWN"):
            fail("logic must use AND/OR/NOT/UNKNOWN or a condition reference")
        children = node.get("children")
        if not isinstance(children, list) or not children or (node["op"] == "NOT" and len(children) != 1):
            fail("logic children missing or invalid NOT arity")
        for child in children:
            walk(child, depth + 1)
    walk(payload["logic"])
    if referenced != ids:
        fail("every condition, including exclusions, must be represented in the logic")


def register(connection, notice_id, payload, actor, reason):
    monitor.require_actor(actor, reason)
    record = monitor.notice_record(connection, notice_id)
    check_payload(payload, record)
    # Explicit writes only. Every registration is a new revision; old records are never replaced.
    connection.executescript(SCHEMA)
    payload = json.loads(monitor.packed(payload))
    for condition in payload["conditions"]:
        condition.update(status="candidate", reviewer=None, reviewed_at=None)
    with connection:
        write_revision(connection, notice_id, payload, actor, reason, "candidate_registered")
    return show(connection, notice_id)


def review(connection, notice_id, condition_id, status, actor, reason):
    monitor.require_actor(actor, reason)
    if status not in STATES:
        fail("invalid condition status")
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        row = latest(connection, notice_id)
        if row is None:
            fail("no candidate conditions registered")
        result = describe(connection, row)
        if result["needs_review"]:
            fail("notice version changed: re-register conditions against the current original first")
        payload = result["payload"]
        condition = next((c for c in payload["conditions"] if c["condition_id"] == condition_id), None)
        if condition is None:
            fail("unknown condition ID")
        for c in payload["conditions"]:
            c.pop("effective_status", None)
        check_condition(condition, monitor.notice_record(connection, notice_id), verified=status == "verified")
        condition.update(status=status, reviewer=actor.strip(), reviewed_at=monitor.utc_now())
        write_revision(connection, notice_id, payload, actor, reason, "condition_reviewed")
    return show(connection, notice_id)


def add_cli(sub):
    for name in ("eligibility-show", "eligibility-history"):
        command = sub.add_parser(name, help="read-only private eligibility evidence")
        command.add_argument("notice_id")
    command = sub.add_parser("eligibility-register", help="register candidate JSON; no approval or collection")
    command.add_argument("notice_id")
    command.add_argument("file", type=monitor.Path)
    review_command = sub.add_parser("eligibility-review", help="human condition evidence review, not notice approval")
    review_command.add_argument("notice_id")
    review_command.add_argument("condition_id")
    review_command.add_argument("status", choices=STATES)
    for command in (command, review_command):
        command.add_argument("--reviewer", required=True)
        command.add_argument("--reason", required=True)


def dispatch(connection, args):
    if args.command == "eligibility-show":
        return show(connection, args.notice_id)
    if args.command == "eligibility-history":
        return history(connection, args.notice_id)
    if args.command == "eligibility-register":
        return register(connection, args.notice_id, json.loads(args.file.read_text(encoding="utf-8-sig")),
                        args.reviewer, args.reason)
    return review(connection, args.notice_id, args.condition_id, args.status, args.reviewer, args.reason)
