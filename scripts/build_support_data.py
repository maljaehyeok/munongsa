"""Build review-only support reference/detail JSON from the preserved source CSVs.

Run from the project root: python scripts/build_support_data.py
The source CSVs and catalog are read-only inputs; only the two generated JSON files
are written. This dataset is not an application-eligibility decision.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCE_DIR = DATA / "source"
CATALOG = DATA / "smart-agriculture-catalog.json"
OUT = DATA / "support-programs.json"
AUDIT = DATA / "support-integration-audit.json"


def read_csv(filename: str) -> list[dict[str, str]]:
    with (SOURCE_DIR / filename).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_json(path: Path):
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    source_rows = read_csv("munongsa_official_sources_batch1_support.csv")
    detail_rows = read_csv("munongsa_program_detail_youth_farmer_2026_round2.csv")
    catalog = load_json(CATALOG)
    existing = {p["id"]: p for p in catalog.get("supportPrograms", [])}

    relations = {
        "SUP-2026-001": ("guideline", "youth", "2026 최초 시행지침"),
        "SUP-2026-002": ("guideline", None, "후계농업경영인 시행지침; 우수후계농과 별도"),
        "SUP-2026-003": ("policy_reference", None, "농림축산식품사업 공통 지침; 개별 사업 아님"),
        "SUP-2026-004": ("policy_plan", None, "스마트농업 정책 계획; 개별 사업 공고 아님"),
        "SUP-2026-005": ("call", "district", "지자체·사업계획 공모; 개인 농가 신청사업 아님"),
        "SUP-2026-006": ("selection_result", "district", "선정 결과; 개별 농가 신청사업 아님"),
    }
    reference_documents = []
    for row in source_rows:
        record_type, related, note = relations.get(row["record_id"], ("reference", None, "유형 추가 검토"))
        reference_documents.append({
            **row,
            "recordType": record_type,
            "relatedProgramIds": [related] if related else [],
            "applicationStatus": "not_an_individual_application" if record_type in {"policy_reference", "policy_plan", "selection_result"} else "unknown",
            "factVerificationStatus": "partially_verified",
            "publicationStatus": "review",
            "reviewNote": note + ". CSV에 기록된 출처 확인을 독립 원문 대조와 게시 승인으로 간주하지 않음.",
        })

    detail_records = []
    for row in detail_rows:
        linked = "youth" if row["record_id"] == "SUP-DETAIL-2026-001" and "youth" in existing else None
        detail_records.append({
            **row,
            "relatedProgramId": linked,
            "recordType": "program_round_detail",
            "roundApplicationStatus": "closed",
            "futureRecruitmentStatus": "unknown",
            "factVerificationStatus": "partially_verified",
            "fieldVerification": {
                "eligibility_age": {"status": "source_checked", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 3–4"},
                "eligibility_farming_experience": {"status": "source_checked", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 3–4"},
                "eligibility_military": {"status": "source_checked", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 4"},
                "eligibility_residence": {"status": "source_checked", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 4"},
                "other_exclusions": {"status": "partially_verified", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 4–6; 전체 예외·세부조건 확인 필요"},
                "support_amount": {"status": "source_checked", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 4–5"},
                "application_period_2026_round2": {"status": "source_checked", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 20; 고창군 2차 모집 공고"},
                "application_method": {"status": "source_checked", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 20"},
                "required_documents_confirmed": {"status": "partially_verified", "evidence": "농식품부 2차 시행지침 PDF 인쇄면 20, 32; CSV의 간략 목록 외 상세 증빙 및 예외 대조 필요"},
                "contact": {"status": "unverified", "evidence": "CSV 기록만 있음; 노출하지 않음"},
                "futureRecruitmentStatus": {"status": "unverified", "evidence": "지침은 별도 추가모집 일정을 허용; 이후 전국·지역별 공고 전수 확인 미완료"},
            },
            "publicationStatus": "pending_review",
            "publicationNote": "기존 사업 카드의 상세 패널에서 검토 중인 2차 기록으로 구분해 표시. 현재 신청 가능 사업으로 추천하지 않음.",
        })

    output = {
        "schemaVersion": 1,
        "generatedFrom": [
            "data/source/munongsa_official_sources_batch1_support.csv",
            "data/source/munongsa_program_detail_youth_farmer_2026_round2.csv",
        ],
        "generatedAt": "2026-10-24",
        "referenceDocuments": reference_documents,
        "programDetails": detail_records,
        "notice": "참고·검토용 데이터입니다. 원문 확인 또는 자료 수록만으로 자격·신청 가능성·게시 승인이 확정되지 않습니다.",
    }

    workbook_mapping = {
        "workbook": "outputs/무농사_시범사업데이터.xlsx",
        "purpose": "reference_only_duplicate_check",
        "recordsCompared": 4,
        "matchedExistingProgramIds": ["youth", "direct", "insurance", "district"],
        "newProgramCardsAdded": 0,
        "note": "사업목록 4건은 기존 카탈로그의 네 지원사업 카드와 대응. 원본 통합·덮어쓰기 입력으로 사용하지 않음.",
    }
    audit = {
        "schemaVersion": 1,
        "generatedAt": "2026-10-24",
        "existingCatalogProgramIds": list(existing),
        "sourceCsvRecordIds": [r["record_id"] for r in source_rows],
        "detailRecordIds": [r["record_id"] for r in detail_rows],
        "referenceDocumentCount": len(reference_documents),
        "programDetailCount": len(detail_records),
        "newSupportProgramCards": 0,
        "duplicatePolicy": "기존 사업 카드는 복제하지 않고 관련 ID로 연결; 지침·공모·선정결과는 참고문서 유형으로 분리.",
        "workbookComparison": workbook_mapping,
        "checks": {
            "sourceRecordIdsUnique": len({r["record_id"] for r in source_rows}) == len(source_rows),
            "detailRecordIdsUnique": len({r["record_id"] for r in detail_rows}) == len(detail_rows),
            "allRelatedProgramsExist": all(not r["relatedProgramIds"] or all(x in existing for x in r["relatedProgramIds"]) for r in reference_documents) and all(not r["relatedProgramId"] or r["relatedProgramId"] in existing for r in detail_records),
            "roundTwoClosed": all(r["roundApplicationStatus"] == "closed" for r in detail_records),
            "futureRecruitmentNotAssertedOpen": all(r["futureRecruitmentStatus"] == "unknown" for r in detail_records),
        },
    }
    write_json(OUT, output)
    write_json(AUDIT, audit)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(reference_documents)} references, {len(detail_records)} details)")
    print(f"Wrote {AUDIT.relative_to(ROOT)}; existing cards added: 0")


if __name__ == "__main__":
    main()
