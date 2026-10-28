"""Offline tests. No official requests, public JSON writes, or persistent test DB."""
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from unittest.mock import Mock, patch
import urllib.error

import support_monitor as monitor


SOURCE = {"source_id": "fixture-mafra", "institution": "fixture only", "board_url": "https://www.mafra.go.kr/",
          "discovery_url": "https://www.mafra.go.kr/feed", "method": "rss", "enabled": True,
          "allowed_hosts": ["www.mafra.go.kr", "mafra.go.kr"], "max_items": 50,
          "minimum_interval_hours": 24}


def feed(title="2026년 청년농업인 모집 2차 공고", description="", number="123", author=""):
    return (f'<rss version="2.0"><channel><title>Fixture</title><item><title>{escape(title)}</title>'
            f'<link>http://www.mafra.go.kr/bbs/home/791/{number}/artclView.do</link>'
            f'<pubDate>2026-10-23 09:07:27.53</pubDate><description>{escape(description)}</description>'
            f'<author>{escape(author)}</author></item></channel></rss>').encode()


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = monitor.connect(self.temp.name)
        monitor.register_sources(self.db, [SOURCE])

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def collect(self, body=None, **kwargs):
        body = feed() if body is None else body
        return monitor.collect_source(self.db, SOURCE, fetcher=lambda _: (body, 200, "text/xml"), force=True, **kwargs)

    def notice(self):
        return self.db.execute("SELECT * FROM discovered_notices").fetchone()

    def test_first_run_creates_private_unverified_notice(self):
        result = self.collect()
        self.assertEqual((result["status"], result["new"], result["collected"]), ("success", 1, 1))
        row = self.notice()
        self.assertEqual((row["publication"], row["verification_status"], row["freshness"], row["application_status"]),
                         ("review", "unverified", "unknown", "unknown"))
        self.assertEqual(row["original_id"], "791:123")
        self.assertTrue(row["published_at"].endswith("+09:00"))

    def test_repeat_run_does_not_duplicate_notice_or_version(self):
        self.collect()
        result = self.collect()
        self.assertEqual((result["new"], result["modified"], result["unchanged"]), (0, 0, 1))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM discovered_notices").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notice_versions").fetchone()[0], 1)

    def test_modified_notice_preserves_previous_version_and_resets_review(self):
        self.collect()
        self.db.execute("UPDATE discovered_notices SET publication='approved_reference',verification_status='verified',review_status='done'")
        self.db.commit()
        result = self.collect(feed(description="신청 기간: 2026-10-01 ~ 2026-11-01"))
        self.assertEqual(result["modified"], 1)
        self.assertEqual(self.notice()["publication"], "review")
        self.assertEqual(self.notice()["verification_status"], "unverified")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notice_versions").fetchone()[0], 2)

    def test_network_failure_logged_and_existing_data_preserved(self):
        self.collect()
        def failed(_):
            raise TimeoutError("do not expose credentials in exception")
        result = monitor.collect_source(self.db, SOURCE, fetcher=failed, force=True)
        self.assertEqual(result["status"], "failed")
        run = self.db.execute("SELECT * FROM crawl_runs ORDER BY run_id DESC").fetchone()
        self.assertEqual(run["status"], "failed")
        self.assertNotIn("credentials", run["error"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM discovered_notices").fetchone()[0], 1)
        self.assertEqual(self.notice()["application_status"], "unknown")

    def test_missing_period_never_open(self):
        self.collect()
        hints = json.loads(self.notice()["hints_json"])
        self.assertEqual(hints["application_period"], "unknown")
        self.assertEqual(self.notice()["application_status"], "unknown")
        self.assertFalse(monitor.recommendation_allowed(dict(self.notice())))

    def test_cross_source_same_title_is_candidate_not_merge(self):
        self.collect()
        other = dict(SOURCE, source_id="fixture-other-official-source")
        monitor.register_sources(self.db, [other])
        monitor.collect_source(self.db, other, fetcher=lambda _: (feed(number="456"), 200, "text/xml"), force=True)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM discovered_notices").fetchone()[0], 2)
        row = self.db.execute("SELECT * FROM duplicate_candidates").fetchone()
        self.assertEqual(row["status"], "pending")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM application_rounds").fetchone()[0], 0)

    def test_different_round_titles_not_auto_duplicates(self):
        self.collect()
        other = dict(SOURCE, source_id="fixture-other")
        monitor.register_sources(self.db, [other])
        monitor.collect_source(self.db, other, fetcher=lambda _: (feed(title="2026년 청년농업인 모집 3차 공고"), 200, "text/xml"), force=True)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM duplicate_candidates").fetchone()[0], 0)

    def test_review_and_reference_cannot_enter_recommendation_gate(self):
        self.collect()
        public_files = [monitor.ROOT / "index.html", monitor.ROOT / "assets/profile-matching.js", *sorted((monitor.ROOT / "data").glob("*.json"))]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in public_files}
        self.collect(feed(description="내용 수정"))
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in public_files})
        for status in ["review", "approved_reference", "held", "archived"]:
            self.assertFalse(monitor.recommendation_allowed({**dict(self.notice()), "publication": status}))

    def test_future_gate_requires_human_conditions_and_actual_period(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        record = {"publication": "approved", "verification_status": "verified", "freshness": "current",
                  "conditions_verified": True, "application_period_verified": True,
                  "application_status": "open", "approved_by": "fixture-reviewer", "approved_at": "2026-10-24",
                  "verified_application_period": {"start": "2026-10-01T00:00:00+09:00", "end": "2026-10-31T18:00:00+09:00"}}
        self.assertTrue(monitor.recommendation_allowed(record, now))
        for key in ["approved_by", "approved_at", "conditions_verified", "application_period_verified"]:
            self.assertFalse(monitor.recommendation_allowed({**record, key: None}, now))
        self.assertFalse(monitor.recommendation_allowed({**record, "verified_application_period": {}}, now))
        self.assertFalse(monitor.recommendation_allowed(record, datetime(2026, 11, 1, tzinfo=timezone.utc)))

    def test_extractor_failure_keeps_original_and_marks_partial(self):
        def failed(_):
            raise ValueError("AI provider failure")
        result = self.collect(extractor=failed)
        self.assertEqual((result["status"], result["extraction_errors"]), ("partial", 1))
        version = self.db.execute("SELECT * FROM notice_versions").fetchone()
        self.assertIn("청년농업인", version["raw_item_json"])
        self.assertIsNotNone(version["extraction_error"])
        self.assertEqual(json.loads(version["hints_json"])["application_period"], "unknown")

    def test_html_schema_error_keeps_response_not_empty_success(self):
        result = self.collect(b"<html><body>Maintenance</body></html>")
        self.assertEqual(result["status"], "failed")
        self.assertIn(b"Maintenance", self.db.execute("SELECT raw_response FROM crawl_runs").fetchone()[0])
        self.assertIsNone(self.db.execute("SELECT last_success_at FROM monitor_sources").fetchone()[0])

    def test_empty_feed_requires_review(self):
        self.assertEqual(self.collect(b"<rss><channel/></rss>")["status"], "failed")

    def test_bad_item_does_not_partially_commit_batch(self):
        body = feed().replace(b"</channel>", b"<item><title>missing link</title></item></channel>")
        self.assertEqual(self.collect(body)["status"], "failed")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM discovered_notices").fetchone()[0], 0)

    def test_daily_guard_prevents_request_even_after_failure(self):
        self.collect(b"not xml")
        def forbidden(_):
            self.fail("daily guard must stop the network request")
        result = monitor.collect_source(self.db, SOURCE, fetcher=forbidden)
        self.assertEqual(result["status"], "skipped_interval")

    def test_disabled_source_not_fetched(self):
        disabled = dict(SOURCE, enabled=False)
        result = monitor.collect_source(self.db, disabled, fetcher=lambda _: self.fail("disabled source fetched"))
        self.assertEqual(result["status"], "skipped_disabled_or_unimplemented")

    def test_entity_and_external_links_rejected(self):
        for body in [b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel/></rss>',
                     feed().replace(b"www.mafra.go.kr", b"attacker.example")]:
            with self.assertRaises(monitor.MonitorError):
                monitor.parse_rss(body, SOURCE)

    def test_http_https_and_tracking_variants_same_identity(self):
        a = monitor.parse_rss(feed(), SOURCE)[0]
        b = monitor.parse_rss(feed().replace(b"http://", b"https://").replace(b"artclView.do<", b"artclView.do?utm_source=fixture<"), SOURCE)[0]
        self.assertEqual(a, b)

    def test_publication_date_not_misread_as_application_period(self):
        hints = monitor.extract_hints(monitor.parse_rss(feed(description="게시일: 2026-10-01 ~ 2026-11-01"), SOURCE)[0])
        self.assertEqual(hints["application_period"], "unknown")

    def test_explicit_period_is_hint_only_and_never_open(self):
        self.collect(feed(description="신청 기간: 2026-10-01 ~ 2026-11-01"))
        hints = json.loads(self.notice()["hints_json"])
        self.assertEqual(hints["application_period"]["start"], "2026-10-01")
        self.assertFalse(hints["application_period_verified"])
        self.assertEqual(self.notice()["application_status"], "unknown")

    def test_reversion_preserves_full_revision_history(self):
        self.collect()
        self.collect(feed(description="changed"))
        self.collect()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notice_versions").fetchone()[0], 3)

    def test_human_round_link_keeps_review_and_checks_program(self):
        self.collect()
        self.db.execute("INSERT INTO programs VALUES ('youth','fixture title','catalog')")
        self.db.commit()
        notice_id = self.notice()["notice_id"]
        monitor.link_round(self.db, notice_id, "youth", "fixture-round", "fixture round label", "reviewer")
        self.assertEqual(self.notice()["round_id"], "fixture-round")
        self.assertEqual(self.notice()["publication"], "review")
        with self.assertRaises(monitor.MonitorError):
            monitor.link_round(self.db, notice_id, "nonexistent", "other-round", "other", "reviewer")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notice_links").fetchone()[0], 1)

    def test_authors_only_in_private_raw_response(self):
        self.collect(feed(author="fixture-person"))
        version = self.db.execute("SELECT raw_item_json FROM notice_versions").fetchone()[0]
        self.assertNotIn("fixture-person", version)
        self.assertIn(b"fixture-person", self.db.execute("SELECT raw_response FROM crawl_runs").fetchone()[0])

    def test_public_state_directories_rejected(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.connect(monitor.ROOT / "data/private-monitor")

    def test_robots_denial_blocks_feed_request(self):
        with patch.object(monitor, "request_bytes", return_value=(b"User-agent: *\nDisallow: /feed\n", 200, "text/plain")) as request:
            with self.assertRaises(monitor.MonitorError):
                monitor.fetch_rss(SOURCE)
            self.assertEqual(request.call_count, 1)

    def test_robots_failure_does_not_bypass_policy(self):
        with patch.object(monitor, "request_bytes", side_effect=TimeoutError()) as request:
            with self.assertRaises(TimeoutError):
                monitor.fetch_rss(SOURCE)
            self.assertEqual(request.call_count, 1)

    def test_retry_5xx_is_bounded(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://www.mafra.go.kr/feed", 503, "unavailable", {}, None)
        with patch.object(monitor.urllib.request, "build_opener", return_value=opener), patch.object(monitor.time, "sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                monitor.request_bytes(SOURCE["discovery_url"], dict(SOURCE, max_attempts=2))
            self.assertEqual(opener.open.call_count, 2)

    def test_rate_limit_is_not_retried(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://www.mafra.go.kr/feed", 429, "rate limit", {}, None)
        with patch.object(monitor.urllib.request, "build_opener", return_value=opener), patch.object(monitor.time, "sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                monitor.request_bytes(SOURCE["discovery_url"], SOURCE)
            self.assertEqual(opener.open.call_count, 1)

    def test_redirect_to_external_host_is_rejected(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.OfficialRedirects(SOURCE["allowed_hosts"]).redirect_request(None, None, 302, "", {}, "https://attacker.example/")

    def test_last_success_is_not_replaced_by_failed_attempt(self):
        self.collect()
        previous = self.db.execute("SELECT last_success_at FROM monitor_sources").fetchone()[0]
        self.collect(b"invalid XML")
        row = self.db.execute("SELECT last_success_at,last_error FROM monitor_sources").fetchone()
        self.assertEqual(row["last_success_at"], previous)
        self.assertIsNotNone(row["last_error"])


class AdminTests(unittest.TestCase):
    setUp = MonitorTests.setUp
    tearDown = MonitorTests.tearDown
    collect = MonitorTests.collect
    notice = MonitorTests.notice

    def fixture(self):
        self.collect()
        return self.notice()["notice_id"]

    def reviewed(self, notice_id=None, **overrides):
        notice_id = notice_id or self.fixture()
        now = datetime.now(timezone.utc)
        values = dict(verification_status="verified", freshness="current", application_status="open",
                      target="fixture farmers", region="fixture region", support="fixture support",
                      period_start=(now - timedelta(days=1)).isoformat(),
                      period_end=(now + timedelta(days=1)).isoformat(),
                      conditions_verified=True, application_period_verified=True,
                      evidence_url="https://www.mafra.go.kr/fixture", evidence_location="fixture page 1")
        values.update(overrides)
        return monitor.review_notice(self.db, notice_id, "fixture-reviewer", "fixture evidence checked", **values)

    def cli(self, *args):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = monitor.main(["--state-dir", self.temp.name, *args])
        return code, out.getvalue(), err.getvalue()

    def test_all_queries_preserve_database_bytes_and_rows(self):
        notice_id = self.fixture()
        dbfile = Path(self.temp.name) / "monitor.sqlite3"
        before = dbfile.read_bytes()
        snapshot = list(self.db.iterdump())
        for args in [("sources",), ("list",), ("show", notice_id), ("runs",),
                     ("duplicates",), ("pending",), ("history", notice_id)]:
            with self.subTest(command=args[0]):
                code, _, _ = self.cli(*args)
                self.assertEqual(code, 0)
                self.assertEqual(dbfile.read_bytes(), before)
                self.assertEqual(list(self.db.iterdump()), snapshot)

    def test_query_does_not_load_registry_or_catalog(self):
        self.fixture()
        with patch.object(monitor.Path, "read_text", side_effect=AssertionError("query read config/catalog")):
            self.assertEqual(self.cli("list")[0], 0)

    def test_missing_database_queries_do_not_create_folder(self):
        missing = Path(self.temp.name) / "absent"
        for command in ["sources", "list", "show", "runs", "duplicates", "pending", "history"]:
            args = [command, "NOTICE-missing"] if command in {"show", "history"} else [command]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
                self.assertEqual(monitor.main(["--state-dir", str(missing), *args]), 1)
            self.assertIn("DB가 없습니다", err.getvalue())
            self.assertFalse(missing.exists())

    def test_readonly_connection_rejects_write(self):
        self.fixture()
        db = monitor.connect(self.temp.name, readonly=True)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM discovered_notices")
        finally:
            db.close()

    def test_legacy_queries_do_not_migrate(self):
        notice_id = self.fixture()
        self.db.executescript("DROP TABLE review_events; DROP TABLE notice_reviews;")
        before = (Path(self.temp.name) / "monitor.sqlite3").read_bytes()
        self.assertEqual(self.cli("show", notice_id)[0], 0)
        self.assertEqual(self.cli("history", notice_id)[0], 0)
        self.assertEqual((Path(self.temp.name) / "monitor.sqlite3").read_bytes(), before)
        self.assertFalse(monitor.has_table(self.db, "notice_reviews"))

    def test_additive_migration_preserves_existing_records(self):
        self.fixture()
        self.db.executescript("DROP TABLE review_events; DROP TABLE notice_reviews;")
        before = [tuple(r) for r in self.db.execute("SELECT * FROM discovered_notices")]
        db = monitor.connect(self.temp.name, require_existing=True)
        db.close()
        self.assertEqual(before, [tuple(r) for r in self.db.execute("SELECT * FROM discovered_notices")])
        self.assertTrue(monitor.has_table(self.db, "review_events"))

    def test_review_stores_provenance_and_history_not_rss_hints(self):
        notice_id = self.fixture()
        hints = self.notice()["hints_json"]
        row = self.reviewed(notice_id)
        self.assertEqual(row["verification_status"], "verified")
        self.assertEqual(row["publication"], "review")
        self.assertEqual(self.notice()["hints_json"], hints)
        self.assertEqual(row["reviewer"], "fixture-reviewer")
        self.assertTrue(row["reviewed_at"])
        event = self.db.execute("SELECT * FROM review_events").fetchone()
        self.assertEqual(json.loads(event["before_json"])["verification_status"], "unverified")
        self.assertEqual(json.loads(event["after_json"])["target"], "fixture farmers")
        self.assertEqual(row["field_evidence"]["target"]["location"], "fixture page 1")

    def test_verified_without_evidence_rejected_atomically(self):
        notice_id = self.fixture()
        before = dict(self.notice())
        with self.assertRaises(monitor.MonitorError):
            monitor.review_notice(self.db, notice_id, "reviewer", "reason", target="fixture", verification_status="verified")
        self.assertEqual(dict(self.notice()), before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM review_events").fetchone()[0], 0)

    def test_verified_empty_scope_rejected(self):
        with self.assertRaises(monitor.MonitorError):
            monitor.review_notice(self.db, self.fixture(), "reviewer", "reason", verification_status="verified", evidence_location="page 1")

    def test_partial_unknown_fields_preserved(self):
        notice_id = self.fixture()
        row = monitor.review_notice(self.db, notice_id, "reviewer", "reason", verification_status="partially_verified", support="known", evidence_location="page 2")
        self.assertEqual((row["target"], row["region"], row["application_status"]), ("unknown", "unknown", "unknown"))
        self.assertFalse(monitor.recommendation_allowed(row))

    def test_all_verification_and_freshness_states_recorded(self):
        row = self.reviewed()
        for state in monitor.VERIFICATION:
            for freshness in monitor.FRESHNESS:
                result = monitor.review_notice(self.db, row["notice_id"], "reviewer", "reason", verification_status=state, freshness=freshness)
                self.assertEqual((result["verification_status"], result["freshness"]), (state, freshness))
        self.assertEqual(self.db.execute("SELECT count(*) FROM review_events").fetchone()[0], 13)

    def test_approval_missing_conditions_rejected(self):
        notice_id = self.fixture()
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, notice_id, "approved", "reviewer", "reason")
        self.assertEqual(self.notice()["publication"], "review")

    def test_reference_verified_scope_not_recommendation(self):
        notice_id = self.fixture()
        monitor.review_notice(self.db, notice_id, "reviewer", "scope verified", support="reference information",
                              verification_status="verified", freshness="current", evidence_location="page 1")
        row = monitor.publish_notice(self.db, notice_id, "approved_reference", "approver", "reference only")
        self.assertEqual(row["approved_by"], "approver")
        self.assertFalse(monitor.recommendation_allowed(row))
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, notice_id, "approved", "approver", "missing conditions")

    def test_reference_unverified_or_due_rejected(self):
        notice_id = self.fixture()
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, notice_id, "approved_reference", "approver", "reason")
        self.reviewed(notice_id, freshness="due")
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, notice_id, "approved_reference", "approver", "reason")

    def test_valid_recommendation_approval_and_history(self):
        reviewed = self.reviewed()
        row = monitor.publish_notice(self.db, reviewed["notice_id"], "approved", "approver", "criteria confirmed")
        self.assertTrue(monitor.recommendation_allowed(row))
        self.assertEqual(monitor.notice_record(self.db, row["notice_id"]), row)
        code, out, _ = self.cli("history", row["notice_id"])
        self.assertEqual(code, 0)
        events = json.loads(out)["events"]
        self.assertEqual([e["action"] for e in events], ["review", "publication"])
        self.assertEqual(events[1]["actor"], "approver")

    def test_closed_and_upcoming_not_approved(self):
        now = datetime.now(timezone.utc)
        notice_id = self.fixture()
        for state, start, end in [("closed", now-timedelta(days=2), now-timedelta(days=1)),
                                  ("upcoming", now+timedelta(days=1), now+timedelta(days=2))]:
            self.reviewed(notice_id, application_status=state, period_start=start.isoformat(), period_end=end.isoformat())
            with self.assertRaises(monitor.MonitorError):
                monitor.publish_notice(self.db, notice_id, "approved", "approver", "reason")

    def test_expired_open_approval_rejected_at_current_time(self):
        now = datetime.now(timezone.utc)
        row = self.reviewed(period_end=(now+timedelta(seconds=30)).isoformat())
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, row["notice_id"], "approved", "approver", "reason", now=now+timedelta(days=1))

    def test_naive_reversed_incomplete_period_rejected(self):
        notice_id = self.fixture()
        for start, end in [("2026-01-01", "2026-12-01"), ("2026-12-01T00:00:00+09:00", "2026-01-01T00:00:00+09:00"),
                           ("2026-01-01T00:00:00+09:00", None)]:
            with self.assertRaises(monitor.MonitorError):
                monitor.review_notice(self.db, notice_id, "reviewer", "reason", period_start=start, period_end=end)

    def test_timezone_boundary_matches_gate(self):
        now = datetime(2026, 10, 25, 0, tzinfo=timezone.utc)
        row = self.reviewed(application_status="unknown", period_start="2026-10-25T09:00:00+09:00", period_end="2026-10-25T10:00:00+09:00")
        row = monitor.review_notice(self.db, row["notice_id"], "reviewer", "boundary", application_status="open", now=now)
        approved = monitor.publish_notice(self.db, row["notice_id"], "approved", "approver", "boundary", now=now)
        self.assertTrue(monitor.recommendation_allowed(approved, now))

    def test_invalid_ids_states_and_blank_actor_reason_rejected(self):
        notice_id = self.fixture()
        for args in [("missing", "reviewer", "reason"), (notice_id, "", "reason"), (notice_id, "reviewer", " ")]:
            with self.assertRaises(monitor.MonitorError):
                monitor.review_notice(self.db, *args)
        for field in ["verification_status", "freshness", "application_status"]:
            with self.assertRaises(monitor.MonitorError):
                monitor.review_notice(self.db, notice_id, "reviewer", "reason", **{field:"invalid"})
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, notice_id, "invalid", "reviewer", "reason")

    def test_untrusted_evidence_url_rejected(self):
        notice_id = self.fixture()
        for url in ["https://attacker.example/proof", "https://user:secret@www.mafra.go.kr/proof", "http://www.mafra.go.kr/proof"]:
            with self.assertRaises(monitor.MonitorError):
                monitor.review_notice(self.db, notice_id, "reviewer", "reason", support="fixture", evidence_url=url)

    def test_each_changed_field_needs_fresh_evidence(self):
        row = self.reviewed()
        with self.assertRaises(monitor.MonitorError):
            monitor.review_notice(self.db, row["notice_id"], "reviewer", "changed support", support="changed")
        self.assertEqual(monitor.notice_record(self.db, row["notice_id"])["support"], "fixture support")

    def test_human_revision_revokes_approval_keeps_history(self):
        row = self.reviewed()
        monitor.publish_notice(self.db, row["notice_id"], "approved", "approver", "reason")
        changed = monitor.review_notice(self.db, row["notice_id"], "reviewer", "recheck", freshness="due")
        self.assertEqual(changed["publication"], "review")
        self.assertIsNone(changed["approved_by"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM review_events").fetchone()[0], 3)

    def test_source_change_and_reversion_do_not_restore_human_approval(self):
        row = self.reviewed()
        monitor.publish_notice(self.db, row["notice_id"], "approved", "approver", "reason")
        self.collect(feed(description="changed RSS"))
        self.collect()
        current = monitor.notice_record(self.db, row["notice_id"])
        self.assertEqual((current["publication"], current["verification_status"]), ("review", "unverified"))
        self.assertEqual(current["target"], "unknown")
        self.assertIsNone(current["approved_by"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM review_events WHERE action='source_changed'").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM notice_versions").fetchone()[0], 3)

    def test_unchanged_rss_preserves_human_review(self):
        row = self.reviewed()
        monitor.publish_notice(self.db, row["notice_id"], "approved_reference", "approver", "reason")
        self.collect()
        self.assertEqual(monitor.notice_record(self.db, row["notice_id"])["publication"], "approved_reference")

    def test_hold_archive_and_reopen_record_all_decisions(self):
        notice_id = self.fixture()
        for state in ["held", "archived", "review"]:
            row = monitor.publish_notice(self.db, notice_id, state, "reviewer", "decision")
            self.assertEqual(row["publication"], state)
            self.assertFalse(monitor.recommendation_allowed(row))
        self.assertEqual(self.db.execute("SELECT count(*) FROM review_events").fetchone()[0], 3)

    def test_cli_review_publish_history_pending(self):
        notice_id = self.fixture()
        self.assertEqual(self.cli("review", notice_id, "--reviewer", "tester", "--reason", "checked",
                                  "--support", "reference", "--verification-status", "verified", "--freshness", "current", "--evidence-location", "page 1")[0], 0)
        self.assertEqual(self.cli("publish", notice_id, "approved_reference", "--reviewer", "tester", "--reason", "reference only")[0], 0)
        self.assertEqual(json.loads(self.cli("pending")[1]), [])
        self.assertEqual(len(json.loads(self.cli("history", notice_id)[1])["events"]), 2)

    def test_period_clear_removes_verification_and_open_status(self):
        row = self.reviewed()
        row = monitor.review_notice(self.db, row["notice_id"], "reviewer", "period unknown", clear_period=True)
        self.assertEqual(row["verified_application_period"], {})
        self.assertFalse(row["application_period_verified"])
        self.assertEqual(row["application_status"], "unknown")

    def test_status_conflicting_with_period_and_unknown_period_rejected(self):
        notice_id = self.fixture()
        with self.assertRaises(monitor.MonitorError):
            monitor.review_notice(self.db, notice_id, "reviewer", "reason", application_status="open")
        now = datetime.now(timezone.utc)
        with self.assertRaises(monitor.MonitorError):
            self.reviewed(notice_id, application_status="open", period_start=(now-timedelta(days=3)).isoformat(),
                          period_end=(now-timedelta(days=2)).isoformat())

    def test_cli_invalid_status_rejected_without_data_change(self):
        notice_id = self.fixture()
        before = (Path(self.temp.name) / "monitor.sqlite3").read_bytes()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            monitor.main(["--state-dir", self.temp.name, "publish", notice_id, "invalid", "--reviewer", "tester", "--reason", "reason"])
        self.assertEqual(result.exception.code, 2)
        self.assertEqual((Path(self.temp.name) / "monitor.sqlite3").read_bytes(), before)

    def test_link_does_not_verify_or_approve_notice(self):
        notice_id = self.fixture()
        self.db.execute("INSERT INTO programs VALUES ('youth','fixture','fixture')")
        self.db.commit()
        monitor.link_round(self.db, notice_id, "youth", "fixture-round", "fixture round", "reviewer")
        row = monitor.notice_record(self.db, notice_id)
        self.assertEqual((row["verification_status"], row["publication"], row["application_status"]),
                         ("unverified", "review", "unknown"))
        self.assertEqual(len(json.loads(self.cli("history", notice_id)[1])["links"]), 1)

    def test_fifty_pending_records_unchanged_by_queries(self):
        for number in range(50):
            self.collect(feed(number=str(1000 + number)))
        before = [tuple(r) for r in self.db.execute("SELECT * FROM discovered_notices ORDER BY notice_id")]
        self.assertEqual(len(json.loads(self.cli("pending")[1])), 50)
        self.assertEqual(len(json.loads(self.cli("list")[1])), 50)
        self.assertEqual(before, [tuple(r) for r in self.db.execute("SELECT * FROM discovered_notices ORDER BY notice_id")])
        self.assertEqual(self.db.execute("SELECT count(*) FROM discovered_notices WHERE verification_status='unverified' AND publication='review'").fetchone()[0], 50)


if __name__ == "__main__":
    unittest.main()
