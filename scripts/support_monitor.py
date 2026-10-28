"""Private RSS discovery queue; never writes the site's public JSON files.

Python 3.10+ standard library only. Run --help for the local administrator CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/monitor_sources.json"
DEFAULT_STATE = ROOT / "work/support-monitor"
USER_AGENT = "MunongsaNoticeMonitor/0.1 (+daily official RSS; private review)"
MAX_BYTES = 2 * 1024 * 1024
KST = timezone(timedelta(hours=9))


class MonitorError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def plain(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def safe_error(error):
    # Do not log URLs, credentials, server response bodies, or arbitrary AI output.
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTPError: status={error.code}"
    if isinstance(error, MonitorError):
        return f"MonitorError: {error}"
    return f"{type(error).__name__}: request/parse/storage failed; inspect locally"


def canonical_url(value, hosts):
    url = urllib.parse.urlsplit(value.strip())
    if url.scheme not in {"http", "https"} or url.hostname not in hosts:
        raise MonitorError("item URL is outside the registered official hosts")
    if url.username or url.password or url.port not in (None, 80, 443):
        raise MonitorError("unexpected item URL credentials or port")
    # Strip tracking/layout parameters, preserve identifying and meaningful parameters.
    query = sorted((k, v) for k, v in urllib.parse.parse_qsl(url.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in {"layout", "fbclid"})
    return urllib.parse.urlunsplit(("https", url.hostname, url.path,
                                    urllib.parse.urlencode(query), ""))


def published_iso(value):
    from email.utils import parsedate_to_datetime
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    # MAFRA's RSS emits local timestamps with fractional seconds and no timezone.
    return result.replace(tzinfo=result.tzinfo or KST).isoformat()


def parse_rss(body, source):
    if len(body) > MAX_BYTES:
        raise MonitorError("RSS response exceeds size limit")
    # Reject custom entities/DTDs before parsing; no external entity resolution.
    probe = body.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
        raise MonitorError("DTD/entities are not accepted")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise MonitorError("response is not valid RSS XML") from error
    if root.tag != "rss" or root.find("channel") is None:
        raise MonitorError("expected RSS channel, not HTML/another schema")
    nodes = root.findall("./channel/item")
    if not nodes:
        raise MonitorError("empty RSS requires review; not recorded as no new notices")
    if len(nodes) > source.get("max_items", 50):
        raise MonitorError("RSS item count exceeds configured limit")
    result = []
    for node in nodes:
        def value(tag):
            found = node.find(tag)
            return "" if found is None else "".join(found.itertext()).strip()
        title, link = plain(value("title")), value("link")
        if not title or not link:
            raise MonitorError("RSS item is missing title/link; raw response preserved")
        link = canonical_url(link, source["allowed_hosts"])
        path = urllib.parse.urlsplit(link).path
        number = re.search(r"/bbs/[^/]+/(\d+)/(\d+)/artclView\.do$", path)
        identity = f"{number[1]}:{number[2]}" if number else (value("guid") or link)
        # Author/contact names stay only in the private raw response, not review metadata.
        item = {"original_id": identity, "title": title, "original_url": link,
                "published_at_raw": value("pubDate"),
                "published_at": published_iso(value("pubDate")),
                "description": value("description"), "category_as_recorded": value("category")}
        result.append(item)
    return result


def review_region_hint(item):
    """Queue priority only; mentions never establish residence or eligibility."""
    text = plain(item.get("title", "") + " " + item.get("description", ""))
    names = ("전북특별자치도", "전라북도", "전북", "전주", "군산", "익산", "정읍", "남원",
             "김제", "완주", "진안", "무주", "장수", "임실", "순창", "고창", "부안")
    matches = [name for name in names if re.search(
        r"(?<![가-힣])" + re.escape(name) + r"(?:시|군)?(?=$|[^가-힣]|지역|거주|소재|농업|에서|의)", text)]
    return {"region": "jeonbuk", "relevance": "explicit_mention" if matches else "unknown",
            "matched_terms": matches, "verification_status": "unverified",
            "meaning": "지역명 언급에 따른 검토 우선순위이며 신청 자격 또는 적용 지역 확인이 아님"}


def prioritize_review_queue(connection, rows):
    """Read latest preserved RSS metadata, including legacy records, without writes."""
    for row in rows:
        version = connection.execute(
            "SELECT raw_item_json FROM notice_versions WHERE notice_id=? ORDER BY version_id DESC LIMIT 1",
            (row["notice_id"],)).fetchone()
        item = {"title": row["title"]}
        if version:
            try:
                raw = json.loads(version[0])
                if isinstance(raw, dict):
                    item["description"] = raw.get("description", "")
            except (ValueError, TypeError):
                pass
        row["review_priority"] = review_region_hint(item)
    return sorted(rows, key=lambda row: row["review_priority"]["relevance"] != "explicit_mention")


def extract_hints(item):
    """Conservative, unverified hints. Missing RSS body is never fabricated."""
    title = item["title"]
    text = plain(item.get("description", ""))
    classification = "unknown"
    for label, words in (
        ("institution_call", ("지자체 대상", "수행기관 모집", "사업자 선정 입찰", "용역 입찰")),
        ("business_support", ("중소기업", "농업법인", "예비사회적기업")),
        ("direct_farmer_support", ("농업인 대상", "청년농업인 모집", "귀농인 모집")),
        ("policy_reference", ("시행지침", "시행계획", "정책자료")),
    ):
        if any(word in title for word in words):
            classification = label
            break
    hints = {"application_period": "unknown", "target": "unknown", "region": "unknown",
             "support": "unknown", "classification": classification,
             "classification_status": "unverified", "application_status": "unknown",
             "conditions_verified": False, "application_period_verified": False,
             "extraction_status": "partial_hints", "evidence": {},
             "review_priority": review_region_hint(item)}
    # Only explicitly labelled lines in the RSS description are considered. Publication
    # dates and title years must not be mistaken for application dates/eligibility.
    for field, label in (("target", "지원 대상"), ("region", "대상 지역"), ("support", "지원 내용")):
        match = re.search(re.escape(label) + r"\s*[:：]\s*([^;\n]{1,250})", text)
        if match:
            hints[field] = match[1].strip()
            hints["evidence"][field] = "RSS description labelled text (unverified)"
    period = re.search(r"신청\s*기간\s*[:：]\s*(\d{4}[-.]\d{1,2}[-.]\d{1,2})\s*[~～]\s*(\d{4}[-.]\d{1,2}[-.]\d{1,2})", text)
    if period:
        try:
            dates = [datetime.strptime(v.replace(".", "-"), "%Y-%m-%d").date().isoformat()
                     for v in period.groups()]
            if dates[0] <= dates[1]:
                hints["application_period"] = {"start": dates[0], "end": dates[1],
                                               "timezone": "Asia/Seoul", "end_time": "unknown"}
                hints["evidence"]["application_period"] = "RSS description (unverified)"
        except ValueError:
            pass
    return hints


def recommendation_allowed(record, now=None):
    """Defense for any future adapter; this monitor does not publish/export anything."""
    now = now or datetime.now(timezone.utc)
    period = record.get("verified_application_period") or {}
    try:
        start = datetime.fromisoformat(period["start"])
        end = datetime.fromisoformat(period["end"])
        if start.tzinfo is None or end.tzinfo is None:
            return False
        in_period = start <= now <= end
    except (KeyError, TypeError, ValueError):
        return False
    return bool(record.get("publication") == "approved"
                and record.get("verification_status") == "verified"
                and record.get("freshness") == "current"
                and record.get("conditions_verified") is True
                and record.get("application_period_verified") is True
                and record.get("application_status") == "open"
                and record.get("approved_by") and record.get("approved_at")
                and in_period)


SCHEMA = """
CREATE TABLE IF NOT EXISTS monitor_sources (
 source_id TEXT PRIMARY KEY, institution TEXT NOT NULL, board_url TEXT NOT NULL,
 method TEXT NOT NULL, enabled INTEGER NOT NULL, config_json TEXT NOT NULL,
 last_success_at TEXT, last_attempt_at TEXT, last_error TEXT
);
CREATE TABLE IF NOT EXISTS crawl_runs (
 run_id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES monitor_sources(source_id),
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 collected_count INTEGER NOT NULL DEFAULT 0, new_count INTEGER NOT NULL DEFAULT 0,
 modified_count INTEGER NOT NULL DEFAULT 0, unchanged_count INTEGER NOT NULL DEFAULT 0,
 extraction_error_count INTEGER NOT NULL DEFAULT 0, error TEXT, http_status INTEGER,
 content_type TEXT, response_hash TEXT, raw_response BLOB
);
CREATE TABLE IF NOT EXISTS programs (
 program_id TEXT PRIMARY KEY, title TEXT NOT NULL, origin TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_rounds (
 round_id TEXT PRIMARY KEY, program_id TEXT NOT NULL REFERENCES programs(program_id),
 label TEXT NOT NULL, application_status TEXT NOT NULL DEFAULT 'unknown',
 verification_status TEXT NOT NULL DEFAULT 'unverified'
);
CREATE TABLE IF NOT EXISTS discovered_notices (
 notice_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES monitor_sources(source_id),
 original_id TEXT NOT NULL, title TEXT NOT NULL, published_at TEXT, original_url TEXT NOT NULL,
 first_collected_at TEXT NOT NULL, last_collected_at TEXT NOT NULL, content_hash TEXT NOT NULL,
 classification TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending',
 verification_status TEXT NOT NULL DEFAULT 'unverified', freshness TEXT NOT NULL DEFAULT 'unknown',
 publication TEXT NOT NULL DEFAULT 'review', application_status TEXT NOT NULL DEFAULT 'unknown',
 hints_json TEXT NOT NULL, program_id TEXT REFERENCES programs(program_id),
 round_id TEXT REFERENCES application_rounds(round_id),
 UNIQUE(source_id, original_id)
);
CREATE TABLE IF NOT EXISTS notice_versions (
 version_id INTEGER PRIMARY KEY, notice_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 run_id INTEGER NOT NULL REFERENCES crawl_runs(run_id), content_hash TEXT NOT NULL,
 collected_at TEXT NOT NULL, change_type TEXT NOT NULL, raw_item_json TEXT NOT NULL,
 hints_json TEXT NOT NULL, extraction_error TEXT
);
CREATE TABLE IF NOT EXISTS duplicate_candidates (
 left_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 right_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
 PRIMARY KEY(left_id, right_id)
);
CREATE TABLE IF NOT EXISTS notice_links (
 link_id INTEGER PRIMARY KEY, notice_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 program_id TEXT NOT NULL REFERENCES programs(program_id),
 round_id TEXT NOT NULL REFERENCES application_rounds(round_id),
 reviewer TEXT NOT NULL, linked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notice_reviews (
 notice_id TEXT PRIMARY KEY REFERENCES discovered_notices(notice_id),
 content_hash TEXT NOT NULL, review_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_events (
 event_id INTEGER PRIMARY KEY, notice_id TEXT NOT NULL REFERENCES discovered_notices(notice_id),
 action TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL, reason TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL
);
"""


def connect(state_dir=DEFAULT_STATE, readonly=False, require_existing=False):
    folder = Path(state_dir).resolve()
    database = folder / "monitor.sqlite3"
    for public_dir in (ROOT / "data", ROOT / "assets"):
        if folder == public_dir or public_dir in folder.parents:
            raise MonitorError("review state cannot be stored inside public data/assets")
    if readonly or require_existing:
        if not database.is_file():
            raise MonitorError("DB가 없습니다. 먼저 run 명령으로 수집 DB를 생성하세요.")
        mode = "ro" if readonly else "rw"
        connection = sqlite3.connect(database.as_uri() + "?mode=" + mode, uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        if readonly:
            connection.execute("PRAGMA query_only = ON")
            return connection
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        return connection
    folder.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(folder / "monitor.sqlite3", timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


VERIFICATION = ("unverified", "partially_verified", "verified", "conflict")
FRESHNESS = ("current", "unknown", "due")
APPLICATION = ("open", "upcoming", "closed", "unknown")
PUBLICATION = ("review", "approved_reference", "approved", "held", "archived")


def has_table(connection, name):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def notice_record(connection, notice_id):
    row = connection.execute("SELECT * FROM discovered_notices WHERE notice_id=?", (notice_id,)).fetchone()
    if row is None:
        raise MonitorError("공고 ID를 찾을 수 없습니다.")
    result = dict(row)
    review = {"target": "unknown", "region": "unknown", "support": "unknown",
              "verified_application_period": {}, "conditions_verified": False,
              "application_period_verified": False, "field_evidence": {},
              "reviewer": None, "reviewed_at": None, "approved_by": None, "approved_at": None}
    if has_table(connection, "notice_reviews"):
        saved = connection.execute("SELECT * FROM notice_reviews WHERE notice_id=?", (notice_id,)).fetchone()
        # Human evidence is bound to a specific RSS revision, never carried to changed content.
        if saved and saved["content_hash"] == row["content_hash"]:
            review.update(json.loads(saved["review_json"]))
    result.update(review)
    return result


def record_event(connection, notice_id, action, actor, reason, before, after):
    connection.execute("""INSERT INTO review_events
      (notice_id,action,actor,recorded_at,reason,before_json,after_json) VALUES (?,?,?,?,?,?,?)""",
      (notice_id, action, actor, utc_now(), reason, packed(before), packed(after)))
    if action in {"source_changed", "body_changed"}:
        from support_eligibility import invalidate
        invalidate(connection, notice_id, reason)


def save_review(connection, before, after, action, actor, reason):
    columns = ("verification_status", "freshness", "application_status", "publication", "review_status")
    connection.execute("UPDATE discovered_notices SET " + ",".join(k + "=?" for k in columns) + " WHERE notice_id=?",
                       (*[after[k] for k in columns], after["notice_id"]))
    fields = ("target", "region", "support", "verified_application_period", "conditions_verified",
              "application_period_verified", "field_evidence", "reviewer", "reviewed_at", "approved_by", "approved_at")
    connection.execute("""INSERT INTO notice_reviews VALUES (?,?,?) ON CONFLICT(notice_id)
      DO UPDATE SET content_hash=excluded.content_hash,review_json=excluded.review_json""",
      (after["notice_id"], after["content_hash"], packed({k: after[k] for k in fields})))
    record_event(connection, after["notice_id"], action, actor, reason, before, after)


def require_actor(actor, reason):
    if not actor or not actor.strip() or not reason or not reason.strip():
        raise MonitorError("검토자와 변경 사유는 필수입니다.")


def evidence_record(record, url=None, location=None):
    if not (url and url.strip()) and not (location and location.strip()):
        return None
    url = url or record["original_url"]
    parts = urllib.parse.urlsplit(url)
    original_host = urllib.parse.urlsplit(record["original_url"]).hostname
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.port not in (None, 443)
            or not (parts.hostname == original_host or parts.hostname.endswith(".go.kr"))):
        raise MonitorError("근거 URL은 원문 기관 또는 정부기관의 HTTPS 주소여야 합니다.")
    return {"url": url, "location": (location or "").strip()}


def checked_period(period):
    try:
        start, end = (datetime.fromisoformat(period[k]) for k in ("start", "end"))
        if start.tzinfo is None or end.tzinfo is None or start > end:
            raise ValueError()
        return start, end
    except (KeyError, TypeError, ValueError):
        raise MonitorError("신청기간은 시간대가 포함된 시작·종료 시각이며 시작 <= 종료여야 합니다.")


def review_notice(connection, notice_id, actor, reason, *, verification_status=None, freshness=None,
                  application_status=None, target=None, region=None, support=None,
                  period_start=None, period_end=None, clear_period=False, conditions_verified=None,
                  application_period_verified=None, evidence_url=None, evidence_location=None,
                  notice_basics_verified=False, now=None):
    require_actor(actor, reason)
    now = now or datetime.now(timezone.utc)
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        before = notice_record(connection, notice_id)
        after = json.loads(packed(before))
        proof = evidence_record(before, evidence_url, evidence_location)
        if notice_basics_verified:
            source = connection.execute('SELECT institution FROM monitor_sources WHERE source_id=?', (before['source_id'],)).fetchone()
            if (verification_status != 'verified' or not proof or not proof.get('location')
                    or not before['title'].strip() or before['title'].strip().lower() == 'unknown'
                    or not source or not source['institution'].strip() or source['institution'].strip().lower() == 'unknown'):
                raise MonitorError('기본 공고 확인에는 기관·사업명·공식 근거 위치와 명시적인 검증 결과가 필요합니다.')
            after['field_evidence']['notice'] = proof
        for field, value, allowed in (("verification_status", verification_status, VERIFICATION),
                                      ("freshness", freshness, FRESHNESS),
                                      ("application_status", application_status, APPLICATION)):
            if value is not None:
                if value not in allowed:
                    raise MonitorError("허용되지 않은 상태값입니다.")
                after[field] = value
        for field, value in (("target", target), ("region", region), ("support", support)):
            if value is not None:
                if not value.strip():
                    raise MonitorError("빈 값 대신 unknown을 입력하세요.")
                after[field] = value.strip()
                after["field_evidence"].pop(field, None)
                if value.strip() != "unknown" and proof:
                    after["field_evidence"][field] = proof
                if field in {"target", "region"}:
                    after["conditions_verified"] = False
        if clear_period and (period_start is not None or period_end is not None):
            raise MonitorError("기간 입력과 기간 삭제를 함께 사용할 수 없습니다.")
        if clear_period or period_start is not None or period_end is not None:
            period = {} if clear_period else {"start": period_start, "end": period_end}
            if period:
                checked_period(period)
            after["verified_application_period"] = period
            after["application_period_verified"] = False
            after["field_evidence"].pop("application_period", None)
            if period and proof:
                after["field_evidence"]["application_period"] = proof
            if application_status is None:
                after["application_status"] = "unknown"
        for field, value in (("conditions_verified", conditions_verified),
                             ("application_period_verified", application_period_verified)):
            if value is not None:
                if not isinstance(value, bool):
                    raise MonitorError("검증 플래그는 true/false여야 합니다.")
                after[field] = value
        known = [k for k in ("target", "region", "support") if after[k] != "unknown"]
        if after["verified_application_period"]:
            known.append("application_period")
        if after["verification_status"] == "verified" and (
                (not known and not after['field_evidence'].get('notice')) or any(not after["field_evidence"].get(k) for k in known)):
            raise MonitorError("검증 완료에는 확인한 필드와 해당 공식 근거가 필요합니다.")
        if after["conditions_verified"] and any(after[k] == "unknown" or not after["field_evidence"].get(k)
                                                for k in ("target", "region")):
            raise MonitorError("자격조건 검증에는 지원 대상·지역과 각각의 근거가 필요합니다.")
        if after["application_period_verified"]:
            checked_period(after["verified_application_period"])
            if not after["field_evidence"].get("application_period"):
                raise MonitorError("신청기간 검증에는 공식 근거가 필요합니다.")
        if after["application_status"] != "unknown":
            if not after["application_period_verified"]:
                raise MonitorError("신청 상태 판단에는 검증된 신청기간이 필요합니다.")
            start, end = checked_period(after["verified_application_period"])
            expected = "upcoming" if now < start else "closed" if now > end else "open"
            if after["application_status"] != expected:
                raise MonitorError("신청 상태가 검증된 기간과 현재 시각에 맞지 않습니다.")
        # Any human revision revokes the previous publication approval.
        after.update(publication="review", review_status="reviewed", approved_by=None, approved_at=None,
                     reviewer=actor.strip(), reviewed_at=utc_now())
        save_review(connection, before, after, "review", actor.strip(), reason.strip())
    return after


def publish_notice(connection, notice_id, publication, actor, reason, now=None):
    require_actor(actor, reason)
    if publication not in PUBLICATION:
        raise MonitorError("허용되지 않은 공개 상태입니다.")
    now = now or datetime.now(timezone.utc)
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        before = notice_record(connection, notice_id)
        after = json.loads(packed(before))
        after.update(publication=publication, approved_by=None, approved_at=None)
        if publication in {"approved_reference", "approved"}:
            if (after["verification_status"] != "verified" or after["freshness"] != "current"
                    or not after["field_evidence"] or not after["reviewer"]):
                raise MonitorError("공개 승인에는 최신 검증 결과와 공식 근거·검토 기록이 필요합니다.")
            after.update(approved_by=actor.strip(), approved_at=utc_now())
            if publication == "approved" and (after["support"] == "unknown"
                    or not after["field_evidence"].get("support") or not recommendation_allowed(after, now)):
                raise MonitorError("추천 승인 조건 미충족: 자격·지원 내용·신청기간·현재 모집 상태를 확인하세요.")
        after["review_status"] = "pending" if publication == "review" else "reviewed"
        save_review(connection, before, after, "publication", actor.strip(), reason.strip())
    return after


def register_sources(connection, sources):
    ids = [source["source_id"] for source in sources]
    if len(set(ids)) != len(ids):
        raise MonitorError("duplicate source IDs in registry")
    for source in sources:
        connection.execute("""INSERT INTO monitor_sources
          (source_id,institution,board_url,method,enabled,config_json) VALUES (?,?,?,?,?,?)
          ON CONFLICT(source_id) DO UPDATE SET institution=excluded.institution,
          board_url=excluded.board_url,method=excluded.method,enabled=excluded.enabled,
          config_json=excluded.config_json""",
          (source["source_id"], source["institution"], source["board_url"], source["method"],
           int(source["enabled"]), packed(source)))
    connection.commit()


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https" or urllib.parse.urlsplit(newurl).hostname not in self.hosts:
            raise MonitorError("redirect outside registered HTTPS hosts blocked")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def request_bytes(url, source):
    if source.get("method") in {"html", "html_pending", "other"}:
        raise MonitorError("HTML/other source collection is not enabled; policy review and adapter required")
    if urllib.parse.urlsplit(url).scheme != "https" or urllib.parse.urlsplit(url).hostname not in source["allowed_hosts"]:
        raise MonitorError("request is outside registered HTTPS hosts")
    opener = urllib.request.build_opener(OfficialRedirects(source["allowed_hosts"]))
    timeout = min(max(float(source.get("timeout_seconds", 15)), 1), 30)
    attempts = min(max(int(source.get("max_attempts", 2)), 1), 3)
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, text/xml, text/plain;q=0.8"})
            with opener.open(request, timeout=timeout) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise MonitorError("response exceeds size limit")
                return data, response.status, response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            # Do not hammer a denied/rate-limited service (including 429).
            if error.code < 500 or attempt + 1 == attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 == attempts:
                raise
        time.sleep(1 + attempt)


def fetch_rss(source):
    if source["method"] != "rss":
        raise MonitorError("source adapter is not implemented")
    url = source["discovery_url"]
    parts = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    try:
        body, _, kind = request_bytes(robots_url, source)
        if "html" in kind.lower():
            raise MonitorError("robots returned HTML; access policy needs review")
        policy = urllib.robotparser.RobotFileParser()
        policy.parse(body.decode("utf-8-sig").splitlines())
        if not policy.can_fetch(USER_AGENT, url):
            raise MonitorError("robots policy disallows this RSS")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    return request_bytes(url, source)


def duplicate_key(title):
    # Only a candidate: exact normalized title AND an explicit year. No merging.
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", title)).strip().casefold()
    return normalized if re.search(r"\b20\d{2}\s*년", normalized) else None


def find_duplicate_candidates(connection, notice_id, source_id, title):
    key = duplicate_key(title)
    if not key:
        return
    for row in connection.execute("SELECT notice_id,title FROM discovered_notices WHERE source_id<>?", (source_id,)):
        if duplicate_key(row["title"]) == key:
            left, right = sorted((notice_id, row["notice_id"]))
            connection.execute("INSERT OR IGNORE INTO duplicate_candidates VALUES (?,?,?,?,?)",
                               (left, right, "same normalized title/year; round identity needs human review", "pending", utc_now()))


def collect_source(connection, source, fetcher=fetch_rss, extractor=extract_hints, force=False, parser=parse_rss):
    """Network/parse failures are persisted as failed runs, never as an empty success."""
    source_id = source["source_id"]
    started = utc_now()
    result = {"source_id": source_id, "status": "failed", "collected": 0,
              "new": 0, "modified": 0, "unchanged": 0, "extraction_errors": 0}
    # SQLite writer lock protects the interval check and upserts against overlapping jobs.
    connection.execute("BEGIN IMMEDIATE")
    try:
        old = connection.execute("SELECT * FROM monitor_sources WHERE source_id=?", (source_id,)).fetchone()
        if old is None:
            raise MonitorError("source must be registered before collection")
        if not source["enabled"] or source["method"] not in {"rss", "bizinfo_api"}:
            result["status"] = "skipped_disabled_or_unimplemented"
            connection.commit()
            return result
        if old["last_attempt_at"] and not force:
            hours = max(float(source.get("minimum_interval_hours", 24)), 24)
            if datetime.now(timezone.utc) - datetime.fromisoformat(old["last_attempt_at"]) < timedelta(hours=hours):
                result["status"] = "skipped_interval"
                connection.commit()
                return result
        cursor = connection.execute("INSERT INTO crawl_runs(source_id,started_at,status) VALUES (?,?,'running')", (source_id, started))
        run_id = cursor.lastrowid
        result['run_id'] = run_id
        connection.execute("UPDATE monitor_sources SET last_attempt_at=? WHERE source_id=?", (started, source_id))
        body, status, kind = fetcher(source)
        connection.execute("UPDATE crawl_runs SET raw_response=?,response_hash=?,http_status=?,content_type=? WHERE run_id=?",
                           (body, digest(body), status, kind, run_id))
        items = parser(body, source)
        connection.execute("SAVEPOINT notice_batch")
        try:
            seen = {}
            for item in items:
                content_hash = digest(packed(item))
                if item["original_id"] in seen:
                    if seen[item["original_id"]] != content_hash:
                        raise MonitorError("conflicting duplicate IDs within a feed")
                    continue
                seen[item["original_id"]] = content_hash
                notice_id = "NOTICE-" + digest(source_id + "\n" + item["original_id"])[:24]
                existing = connection.execute("SELECT * FROM discovered_notices WHERE notice_id=?", (notice_id,)).fetchone()
                result["collected"] += 1
                if existing and existing["content_hash"] == content_hash:
                    connection.execute("UPDATE discovered_notices SET last_collected_at=? WHERE notice_id=?", (started, notice_id))
                    result["unchanged"] += 1
                    continue
                extraction_error = None
                try:
                    hints = extractor(item)
                    if not isinstance(hints, dict):
                        raise ValueError("extractor must return a dictionary")
                except Exception as error:
                    # Original item and full RSS remain preserved even when enrichment fails.
                    extraction_error = safe_error(error)
                    hints = {"application_period": "unknown", "target": "unknown", "region": "unknown",
                             "support": "unknown", "classification": "unknown", "application_status": "unknown",
                             "extraction_status": "failed", "conditions_verified": False,
                             "application_period_verified": False}
                    result["extraction_errors"] += 1
                classification = hints.get("classification", "unknown")
                change = "modified" if existing else "new"
                previous_review = notice_record(connection, notice_id) if existing else None
                connection.execute("""INSERT INTO discovered_notices
                  (notice_id,source_id,original_id,title,published_at,original_url,first_collected_at,
                  last_collected_at,content_hash,classification,hints_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(notice_id) DO UPDATE SET title=excluded.title,published_at=excluded.published_at,
                  original_url=excluded.original_url,last_collected_at=excluded.last_collected_at,
                  content_hash=excluded.content_hash,classification=excluded.classification,hints_json=excluded.hints_json,
                  review_status='pending',verification_status='unverified',freshness='unknown',
                  publication='review',application_status='unknown'""",
                  (notice_id, source_id, item["original_id"], item["title"], item["published_at"],
                   item["original_url"], started, started, content_hash, classification, packed(hints)))
                if previous_review:
                    connection.execute("DELETE FROM notice_reviews WHERE notice_id=?", (notice_id,))
                    record_event(connection, notice_id, "source_changed", "rss-collector",
                                 "RSS revision changed; human verification and approval invalidated",
                                 previous_review, notice_record(connection, notice_id))
                connection.execute("""INSERT INTO notice_versions
                  (notice_id,run_id,content_hash,collected_at,change_type,raw_item_json,hints_json,extraction_error)
                  VALUES (?,?,?,?,?,?,?,?)""", (notice_id, run_id, content_hash, started, change,
                                                packed(item), packed(hints), extraction_error))
                find_duplicate_candidates(connection, notice_id, source_id, item["title"])
                result[change] += 1
            connection.execute("RELEASE notice_batch")
        except Exception:
            connection.execute("ROLLBACK TO notice_batch")
            connection.execute("RELEASE notice_batch")
            result.update(collected=0, new=0, modified=0, unchanged=0, extraction_errors=0)
            raise
        result["status"] = "partial" if result["extraction_errors"] else "success"
        connection.execute("""UPDATE crawl_runs SET finished_at=?,status=?,collected_count=?,new_count=?,
          modified_count=?,unchanged_count=?,extraction_error_count=? WHERE run_id=?""",
          (utc_now(), result["status"], result["collected"], result["new"], result["modified"],
           result["unchanged"], result["extraction_errors"], run_id))
        connection.execute("UPDATE monitor_sources SET last_success_at=?,last_error=NULL WHERE source_id=?", (started, source_id))
    except Exception as error:
        message = safe_error(error)
        result["status"] = "failed"
        if "run_id" not in locals():
            connection.rollback()
            raise
        connection.execute("UPDATE crawl_runs SET finished_at=?,status='failed',error=? WHERE run_id=?", (utc_now(), message, run_id))
        connection.execute("UPDATE monitor_sources SET last_error=? WHERE source_id=?", (message, source_id))
        result["error"] = message
    connection.commit()
    return result


def link_round(connection, notice_id, program_id, round_id, label, reviewer):
    notice = connection.execute("SELECT * FROM discovered_notices WHERE notice_id=?", (notice_id,)).fetchone()
    if not notice or not reviewer.strip() or not label.strip():
        raise MonitorError("existing notice, reviewer and round label are required")
    if not connection.execute("SELECT 1 FROM programs WHERE program_id=?", (program_id,)).fetchone():
        raise MonitorError("program ID must exist in the preserved catalog")
    with connection:
        connection.execute("INSERT OR IGNORE INTO application_rounds(round_id,program_id,label) VALUES (?,?,?)", (round_id, program_id, label))
        row = connection.execute("SELECT * FROM application_rounds WHERE round_id=?", (round_id,)).fetchone()
        if row["program_id"] != program_id or row["label"] != label:
            raise MonitorError("round ID already belongs to a different program/label")
        connection.execute("UPDATE discovered_notices SET program_id=?,round_id=? WHERE notice_id=?", (program_id, round_id, notice_id))
        connection.execute("INSERT INTO notice_links(notice_id,program_id,round_id,reviewer,linked_at) VALUES (?,?,?,?,?)", (notice_id, program_id, round_id, reviewer, utc_now()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="collect due enabled RSS sources")
    run.add_argument("--source")
    run.add_argument("--force", action="store_true", help="manual troubleshooting only: bypass 24h guard")
    sub.add_parser("bizinfo-check", help="check environment only; never calls an API or opens a DB")
    probe = sub.add_parser("bizinfo-probe", help="explicit one-request API check; no DB writes or collection")
    probe.add_argument("--confirm-live", action="store_true", help="permit a single real API request")
    probe.add_argument("--diagnose-structure", action="store_true", help="show redacted response shape only")
    manual = sub.add_parser("bizinfo-collect", help="explicit small manual collection; trial DB by default")
    manual.add_argument("--confirm-live", action="store_true")
    manual.add_argument("--confirm-db-write", action="store_true", help="allow writing the existing review DB after backup")
    manual.add_argument("--limit", type=int, choices=range(1, 21), default=10)
    trial = sub.add_parser("bizinfo-jeonbuk-trial", help="one Jeonbuk request into a private trial DB with offline dedup check")
    trial.add_argument("--confirm-live", action="store_true")
    trial.add_argument("--limit", type=int, choices=range(1, 21), default=20)
    sub.add_parser("sources")
    queue = sub.add_parser("list", help="private review queue, metadata only")
    queue.add_argument("--priority-region", choices=["jeonbuk"], help="prioritize regional mentions, not eligibility")
    show = sub.add_parser("show")
    show.add_argument("notice_id")
    sub.add_parser("runs")
    sub.add_parser("duplicates")
    pending = sub.add_parser("pending", help="read-only queue awaiting review/publication")
    pending.add_argument("--priority-region", choices=["jeonbuk"], help="prioritize regional mentions, not eligibility")
    bodies = sub.add_parser("fetch-bodies", help="private MAFRA 13-notice HTML pilot; no attachments")
    bodies.add_argument("--notice-id", help="optional single ID within the fixed pilot")
    history = sub.add_parser("history", help="read-only verification, approval and link history")
    history.add_argument("notice_id")
    review = sub.add_parser("review", help="record a human verification; revokes publication approval")
    review.add_argument("notice_id")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--verification-status", choices=VERIFICATION)
    review.add_argument("--freshness", choices=FRESHNESS)
    review.add_argument("--application-status", choices=APPLICATION)
    for field in ("target", "region", "support", "period-start", "period-end", "evidence-url", "evidence-location"):
        review.add_argument("--" + field)
    review.add_argument("--clear-period", action="store_true")
    review.add_argument("--notice-basics-verified", action="store_true", help="human verification of institution/title/official notice only; not eligibility")
    review.add_argument("--conditions-verified", action=argparse.BooleanOptionalAction, default=None)
    review.add_argument("--application-period-verified", action=argparse.BooleanOptionalAction, default=None)
    publish = sub.add_parser("publish", help="human publication decision; never exports to the website")
    publish.add_argument("notice_id")
    publish.add_argument("publication", choices=PUBLICATION)
    publish.add_argument("--reviewer", required=True)
    publish.add_argument("--reason", required=True)
    link = sub.add_parser("link", help="human mapping only; does not approve/publish")
    for name in ("notice_id", "program_id", "round_id", "label", "reviewer"):
        link.add_argument(name)
    from support_source_registry import add_cli, dispatch as source_dispatch
    add_cli(sub)
    from support_eligibility import add_cli as add_eligibility_cli, dispatch as eligibility_dispatch
    add_eligibility_cli(sub)
    args = parser.parse_args(argv)
    try:
        if args.command in {"bizinfo-check", "bizinfo-probe", "bizinfo-collect", "bizinfo-jeonbuk-trial"}:
            from support_bizinfo import check_configuration, probe_connection, manual_collect
            registry = json.loads(args.config.read_text(encoding="utf-8"))["sources"]
            source = next(s for s in registry if s["source_id"] == "bizinfo-support-api")
            if args.command == "bizinfo-jeonbuk-trial":
                from support_bizinfo import jeonbuk_trial
                result = jeonbuk_trial(source, state_dir=args.state_dir, confirm_live=args.confirm_live, limit=args.limit)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return int(result["status"] != "success")
            if args.command == "bizinfo-collect":
                result = manual_collect(source, state_dir=args.state_dir, confirm_live=args.confirm_live,
                                        confirm_db_write=args.confirm_db_write, limit=args.limit)
                print(packed(result))
                return int(result['status'] not in {'success', 'skipped_interval'})
            if args.command == "bizinfo-probe":
                result = probe_connection(source, confirm=args.confirm_live, diagnose=args.diagnose_structure)
                print(packed(result))
                return int(result['status'] != 'success')
            print(packed(check_configuration(source)))
            return 0
        readonly = args.command in {"sources", "list", "show", "runs", "duplicates", "pending", "history",
                                    "source-list", "source-show", "source-policy", "source-history",
                                    "eligibility-show", "eligibility-history"}
        connection = connect(args.state_dir, readonly=readonly,
                             require_existing=args.command in {"review", "publish", "link", "fetch-bodies",
                                                               "eligibility-register", "eligibility-review"})
        try:
            if args.command.startswith("eligibility-"):
                result = eligibility_dispatch(connection, args)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            if args.command.startswith("source-"):
                result = source_dispatch(connection, args)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            if args.command in {"run", "link"}:
                registry = json.loads(args.config.read_text(encoding="utf-8"))["sources"]
                register_sources(connection, registry)
                catalog = json.loads((ROOT / "data/smart-agriculture-catalog.json").read_text(encoding="utf-8"))
                with connection:
                    for program in catalog.get("supportPrograms", []):
                        connection.execute("INSERT OR IGNORE INTO programs VALUES (?,?,?)", (program["id"], program["title"], "existing_catalog_read_only"))
            if args.command == "run":
                selected = [s for s in registry if (args.source == s["source_id"] if args.source else s["enabled"])]
                if not selected:
                    raise MonitorError("no matching registered source")
                results = []
                for source in selected:
                    if source["method"] == "bizinfo_api":
                        from support_bizinfo import collect_bizinfo
                        results.append(collect_bizinfo(connection, source, force=args.force))
                    else:
                        results.append(collect_source(connection, source, force=args.force))
                print(packed(results))
                return int(any(r["status"] in {"failed", "partial"} for r in results))
            if args.command == "fetch-bodies":
                from support_notice_body import collect_bodies
                registry = json.loads(args.config.read_text(encoding="utf-8"))["sources"]
                source = next(s for s in registry if s["source_id"] == "mafra-notices-rss")
                results = collect_bodies(connection, source, args.notice_id)
                print(json.dumps(results, ensure_ascii=False, indent=2))
                return int(any(r["status"] in {"access_failed", "extraction_failed"} for r in results))
            if args.command == "show":
                result = notice_record(connection, args.notice_id)
                result["hints"] = json.loads(result.pop("hints_json"))
                result["versions"] = [dict(r) for r in connection.execute("SELECT version_id,collected_at,change_type,content_hash,extraction_error FROM notice_versions WHERE notice_id=? ORDER BY version_id", (args.notice_id,))]
                from support_notice_body import latest_body
                result["body_candidate"] = latest_body(connection, args.notice_id)
            elif args.command == "link":
                link_round(connection, args.notice_id, args.program_id, args.round_id, args.label, args.reviewer)
                result = {"linked": args.notice_id, "publication": "unchanged; no approval performed"}
            elif args.command == "review":
                fields = ("verification_status", "freshness", "application_status", "target", "region", "support",
                          "period_start", "period_end", "clear_period", "conditions_verified",
                          "application_period_verified", "evidence_url", "evidence_location", "notice_basics_verified")
                result = review_notice(connection, args.notice_id, args.reviewer, args.reason,
                                       **{k: getattr(args, k) for k in fields})
            elif args.command == "publish":
                result = publish_notice(connection, args.notice_id, args.publication, args.reviewer, args.reason)
            elif args.command == "history":
                notice_record(connection, args.notice_id)  # reject unknown IDs, including legacy DBs
                events = [dict(r) for r in connection.execute(
                    "SELECT * FROM review_events WHERE notice_id=? ORDER BY event_id", (args.notice_id,))] if has_table(connection, "review_events") else []
                for event in events:
                    event["before"] = json.loads(event.pop("before_json"))
                    event["after"] = json.loads(event.pop("after_json"))
                result = {"events": events, "links": [dict(r) for r in connection.execute(
                    "SELECT * FROM notice_links WHERE notice_id=? ORDER BY link_id", (args.notice_id,))]}
                result["body_fetches"] = [dict(r) for r in connection.execute(
                    "SELECT fetch_id,original_url,collected_at,status,change_type,http_status,error FROM body_fetches WHERE notice_id=? ORDER BY fetch_id", (args.notice_id,))] if has_table(connection, "body_fetches") else []
                result["body_versions"] = [dict(r) for r in connection.execute(
                    "SELECT body_version_id,collected_at,content_hash FROM body_versions WHERE notice_id=? ORDER BY body_version_id", (args.notice_id,))] if has_table(connection, "body_versions") else []
            else:
                queries = {
                    "sources": "SELECT source_id,institution,method,enabled,last_success_at,last_attempt_at,last_error FROM monitor_sources",
                    "list": "SELECT notice_id,source_id,title,published_at,original_url,classification,review_status,verification_status,freshness,publication,application_status,program_id,round_id FROM discovered_notices ORDER BY first_collected_at DESC,notice_id",
                    "pending": "SELECT notice_id,title,review_status,verification_status,freshness,publication,application_status FROM discovered_notices WHERE publication='review' ORDER BY first_collected_at,notice_id",
                    "runs": "SELECT run_id,source_id,started_at,finished_at,status,collected_count,new_count,modified_count,unchanged_count,extraction_error_count,error,response_hash FROM crawl_runs ORDER BY run_id DESC LIMIT 30",
                    "duplicates": "SELECT * FROM duplicate_candidates ORDER BY created_at DESC",
                }
                result = [dict(row) for row in connection.execute(queries[args.command])]
                if getattr(args, "priority_region", None):
                    result = prioritize_review_queue(connection, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        finally:
            connection.close()
    except (MonitorError, OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(safe_error(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Lazy body adapter imports must share this module's exceptions and helpers.
    sys.modules.setdefault("support_monitor", sys.modules[__name__])
    # Keep Korean review metadata readable in PowerShell pipes and scheduler logs.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
