"""Five fictional programs, temporary SQLite only; never official qualification checks."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import support_monitor as monitor
import support_eligibility as eligibility
from test_support_monitor import SOURCE, feed


def leaf(identity, kind, value, presence="specified", evidence=True):
    result = {"condition_id": identity, "kind": kind, "presence": presence, "value": value,
              "evidence": {"url": "https://www.mafra.go.kr/bbs/home/791/501/artclView.do",
                           "location": "모의 첨부 p.2 신청자격", "quote": "실제 공고가 아닌 격리 시험용 조건 원문"} if evidence else {}}
    return result


def payload(conditions, op="AND"):
    return {"conditions": conditions, "logic": {"op": op, "children": [
        {"condition_id": c["condition_id"]} for c in conditions]}}


def samples():
    age = {"min": 18, "max": 39, "min_inclusive": True, "max_inclusive": True,
           "basis_date": "2026-01-01", "age_basis": "international"}
    years = {"min": 0, "max": 3, "min_inclusive": True, "max_inclusive": True,
             "basis_date": "2026-01-01", "unit": "years"}
    return [
        payload([leaf("age", "age", age), leaf("region", "residence", {"regions": ["전북특별자치도 김제시"]}),
                 leaf("experience", "independent_management", years)]),
        payload([leaf("person", "applicant", {"one_of": ["individual_farmer"]}),
                 leaf("business", "applicant", {"one_of": ["agricultural_business"]})], "OR"),
        payload([leaf("crop", "crop", {"any_of": ["마늘"]})]),
        payload([leaf("uncollected", "farm_registration", None, "unknown", False)], "UNKNOWN"),
        payload([leaf("registration", "farm_registration", {"registered": True})]),
    ]


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = monitor.connect(self.temp.name)
        monitor.register_sources(self.db, [SOURCE])
        self.transport = patch("socket.socket.connect", side_effect=AssertionError("network forbidden"))
        self.transport.start()
        self.ids = []
        for i in range(5):
            self.collect(i)
            self.ids.append(self.db.execute("SELECT notice_id FROM discovered_notices WHERE original_id=?",
                                           ("791:" + str(501 + i),)).fetchone()[0])

    def tearDown(self):
        self.transport.stop()
        self.db.close()
        self.temp.cleanup()

    def collect(self, i, description=""):
        body = feed(title=f"2026년 모의 사업 {i} (시험 전용)", number=str(501 + i), description=description)
        return monitor.collect_source(self.db, SOURCE, fetcher=lambda _: (body, 200, "text/xml"), force=True)

    def register(self, i=0, data=None):
        return eligibility.register(self.db, self.ids[i], data or samples()[i], "fixture-reviewer", "격리 모의 시험")

    def review(self, identity, status="verified", i=0):
        return eligibility.review(self.db, self.ids[i], identity, status, "fixture-reviewer", "모의 근거 검토")

    def test_five_programs_and_and_or_crop_unknown(self):
        for i in range(5):
            result = self.register(i)
            self.assertEqual(result["payload"]["logic"], samples()[i]["logic"])
            self.assertTrue(all(c["status"] == "candidate" for c in result["payload"]["conditions"]))
        self.assertEqual(self.db.execute("SELECT count(*) FROM discovered_notices").fetchone()[0], 5)

    def test_and_age_region_experience_independently_verified(self):
        self.register()
        for identity in ("age", "region", "experience"):
            result = self.review(identity)
        self.assertTrue(all(c["status"] == "verified" and c["reviewer"] and c["reviewed_at"]
                            for c in result["payload"]["conditions"]))
        self.assertEqual(result["payload"]["logic"]["op"], "AND")

    def test_or_not_and_structure_preserved(self):
        data = samples()[1]
        data["conditions"].append(leaf("excluded", "exclusion", {"text": "모의 중복수혜 제외 조건"}))
        original_or = copy.deepcopy(data["logic"])
        data["logic"] = {"op": "AND", "children": [original_or,
            {"op": "NOT", "children": [{"condition_id": "excluded"}]}]}
        result = self.register(1, data)
        self.assertEqual(result["payload"]["logic"], data["logic"])

    def test_unknown_distinct_from_no_restriction(self):
        self.register(3)
        with self.assertRaises(monitor.MonitorError):
            self.review("uncollected", i=3)
        data = payload([leaf("unlimited", "age", None, "no_restriction")])
        self.register(3, data)
        result = self.review("unlimited", i=3)
        self.assertEqual(result["payload"]["conditions"][0]["presence"], "no_restriction")

    def test_missing_evidence_cannot_be_verified(self):
        for field in ("url", "location", "quote"):
            data = samples()[2]
            del data["conditions"][0]["evidence"][field]
            self.register(2, data)
            with self.assertRaises(monitor.MonitorError):
                self.review("crop", i=2)

    def test_age_basis_missing_blocks_verification(self):
        data = samples()[0]
        data["conditions"][0]["value"]["basis_date"] = "unknown"
        self.register(data=data)
        with self.assertRaises(monitor.MonitorError):
            self.review("age")

    def test_ambiguous_conflict_and_review_history(self):
        self.register(3)
        self.review("uncollected", "ambiguous", 3)
        self.review("uncollected", "conflict", 3)
        rows = eligibility.history(self.db, self.ids[3])
        self.assertEqual([r["payload"]["conditions"][0]["status"] for r in rows],
                         ["candidate", "ambiguous", "conflict"])

    def test_condition_verification_does_not_approve_notice(self):
        self.register(2)
        self.review("crop", i=2)
        record = monitor.notice_record(self.db, self.ids[2])
        self.assertEqual((record["verification_status"], record["publication"], record["application_status"]),
                         ("unverified", "review", "unknown"))
        self.assertFalse(record["conditions_verified"])
        with self.assertRaises(monitor.MonitorError):
            monitor.publish_notice(self.db, self.ids[2], "approved", "tester", "must refuse")
        self.assertFalse(monitor.recommendation_allowed(record))

    def test_source_revision_invalidates_and_preserves_history(self):
        self.register(4)
        self.review("registration", i=4)
        self.collect(4, "모의 공고 조건 변경")
        result = eligibility.show(self.db, self.ids[4])
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["payload"]["conditions"][0]["effective_status"], "candidate")
        rows = eligibility.history(self.db, self.ids[4])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["payload"]["conditions"][0]["status"], "verified")
        self.assertEqual(rows[2]["action"], "source_changed")
        with self.assertRaises(monitor.MonitorError):
            self.review("registration", i=4)
        self.register(4)
        self.assertFalse(self.review("registration", i=4)["needs_review"])

    def test_failed_collection_does_not_invalidate(self):
        self.register(2)
        self.review("crop", i=2)
        with patch.object(monitor, "fetch_rss", side_effect=TimeoutError):
            def failed(_):
                raise TimeoutError()
            monitor.collect_source(self.db, SOURCE, fetcher=failed, force=True)
        self.assertFalse(eligibility.show(self.db, self.ids[2])["needs_review"])
        self.assertEqual(len(eligibility.history(self.db, self.ids[2])), 2)

    def test_unchanged_collection_keeps_verification(self):
        self.register(2)
        self.review("crop", i=2)
        self.collect(2)
        self.assertEqual(eligibility.show(self.db, self.ids[2])["payload"]["conditions"][0]["effective_status"], "verified")

    def test_round_change_is_detected_without_query_writes(self):
        self.register(2)
        self.db.execute("INSERT INTO programs VALUES ('fixture','시험','fixture')")
        self.db.execute("INSERT INTO application_rounds (round_id,program_id,label) VALUES ('round1','fixture','모의 회차')")
        self.db.execute("UPDATE discovered_notices SET round_id='round1' WHERE notice_id=?", (self.ids[2],))
        self.db.commit()
        self.assertTrue(eligibility.show(self.db, self.ids[2])["needs_review"])
        result = self.register(2)
        self.assertEqual(result["round_id"], "round1")
        self.assertEqual(result["snapshot"]["original_id"], "791:503")

    def test_body_revision_invalidates(self):
        self.register(2)
        self.review("crop", i=2)
        self.db.execute("CREATE TABLE body_versions (body_version_id INTEGER PRIMARY KEY,notice_id TEXT,content_hash TEXT)")
        self.db.execute("INSERT INTO body_versions VALUES (1,?,?)", (self.ids[2], "fixture-body-hash"))
        before = monitor.notice_record(self.db, self.ids[2])
        monitor.record_event(self.db, self.ids[2], "body_changed", "tester", "모의 본문 변경", before, before)
        self.db.commit()
        result = eligibility.show(self.db, self.ids[2])
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["snapshot"]["body"]["body_version_id"], 1)

    def test_malformed_logic_or_hidden_conditions_rejected(self):
        cases = []
        data = samples()[0]; data["logic"] = {"condition_id": "missing"}; cases.append(data)
        data = samples()[0]; data["logic"] = {"condition_id": "age"}; cases.append(data)
        data = samples()[0]; data["logic"]["op"] = "NOT"; cases.append(data)
        data = samples()[0]; data["conditions"][1]["condition_id"] = "age"; cases.append(data)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(monitor.MonitorError):
                self.register(data=data)
        self.assertFalse(monitor.has_table(self.db, "eligibility_revisions"))

    def test_invalid_numeric_ranges_rejected(self):
        for low, high in ((-1, 39), (40, 18), (True, 39), (float("nan"), 39)):
            data = samples()[0]
            data["conditions"][0]["value"].update(min=low, max=high)
            with self.subTest(low=low), self.assertRaises(monitor.MonitorError):
                self.register(data=data)

    def test_unknown_ids_and_status_rejected(self):
        self.register()
        for notice, condition, status in (("missing", "age", "verified"), (self.ids[0], "missing", "verified"),
                                          (self.ids[0], "age", "approved")):
            with self.assertRaises(monitor.MonitorError):
                eligibility.review(self.db, notice, condition, status, "tester", "reason")

    def test_wrong_json_types_rejected_safely(self):
        data = samples()[2]
        data["conditions"][0]["evidence"]["url"] = 123
        with self.assertRaises(monitor.MonitorError):
            self.register(2, data)
        data = samples()[2]
        data["logic"] = {"condition_id": []}
        with self.assertRaises(monitor.MonitorError):
            self.register(2, data)

    def test_read_only_commands_preserve_bytes(self):
        self.register()
        path = Path(self.temp.name) / "monitor.sqlite3"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        for command in ("eligibility-show", "eligibility-history"):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(monitor.main(["--state-dir", self.temp.name, command, self.ids[0]]), 0)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_legacy_reads_no_schema_and_missing_db_no_creation(self):
        self.assertEqual(eligibility.show(self.db, self.ids[0])["status"], "not_collected")
        self.assertFalse(monitor.has_table(self.db, "eligibility_revisions"))
        path = Path(self.temp.name) / "absent"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(monitor.main(["--state-dir", str(path), "eligibility-show", "missing"]), 1)
        self.assertFalse(path.exists())

    def test_cli_register_review_history(self):
        path = Path(self.temp.name) / "conditions.json"
        path.write_text(json.dumps(samples()[2]), encoding="utf-8")
        for command in (["eligibility-register", self.ids[2], str(path), "--reviewer", "tester", "--reason", "fixture"],
                        ["eligibility-review", self.ids[2], "crop", "verified", "--reviewer", "tester", "--reason", "fixture"]):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(monitor.main(["--state-dir", self.temp.name, *command]), 0)
        self.assertEqual(len(eligibility.history(self.db, self.ids[2])), 2)


if __name__ == "__main__":
    unittest.main()
