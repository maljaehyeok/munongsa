"""Build equipment review data from the current catalog and finance import.

Run after build_finance_data.py:
    python scripts/build_equipment_data.py

Inputs are read only. No item is presented as a verified commercial product
unless a product/model and an official manufacturer source are both present.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/smart-agriculture-catalog.json"
FINANCE = ROOT / "data/finance-products.json"
OUT = ROOT / "data/equipment-catalog.json"
AUDIT = ROOT / "data/equipment-integration-audit.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    catalog = read_json(CATALOG)
    finance = read_json(FINANCE)
    sources = {item["id"]: item for item in catalog.get("sources", [])}

    guidelines = []
    for item in catalog.get("verifiedGuidelineItems", []):
        source = sources.get(item.get("sourceId"), {})
        guidelines.append({
            **item,
            "recordType": "official_guideline_category",
            "factVerificationStatus": "partially_verified",
            "publicationStatus": "reference_only",
            "source": {
                "id": source.get("id", item.get("sourceId")),
                "publisher": source.get("publisher"),
                "title": source.get("title"),
                "url": source.get("url"),
            },
        })

    ideas = []
    for item in catalog.get("candidateExamples", []):
        source = sources.get(item.get("sourceId"), {})
        group = (
            "센싱·관측" if "SENSOR" in item["id"] or "WEATHER" in item["id"]
            else "관수·제어" if "DRIP" in item["id"] or "VALVE" in item["id"]
            else "농기계·작업"
        )
        ideas.append({
            **item,
            "group": group,
            "recordType": "team_equipment_idea",
            "factVerificationStatus": "unverified",
            "publicationStatus": "review",
            "source": {
                "id": source.get("id", item.get("sourceId")),
                "publisher": source.get("publisher", "무농사 팀"),
                "title": source.get("title", "팀 검토 아이디어"),
                "url": source.get("url"),
            },
        })

    product_candidates = []
    for row in finance.get("machineryFinanceExamples", []):
        product_candidates.append({
            "id": row["id"],
            "title": row.get("equipmentType", "장비 유형 미기록"),
            "group": "농기계·작업",
            "recordType": "team_workbook_product_candidate",
            "specificationAsRecorded": row.get("specificationAsRecorded"),
            "modelsAsRecorded": row.get("modelsAsRecorded"),
            "priceAsRecordedWon": row.get("estimatedPriceAsRecordedWon"),
            "financeLimitAsRecordedWon": row.get("loanLimitAsRecordedWon"),
            "financingRatioAsRecorded": row.get("ratioAsRecorded"),
            "termsAsRecorded": row.get("termsAsRecorded"),
            "cultivationModes": [],
            "factVerificationStatus": "unverified",
            "productIdentityVerificationStatus": "unverified",
            "priceVerificationStatus": "unverified",
            "performanceVerificationStatus": "unverified",
            "salesStatus": "unknown",
            "publicationStatus": "review",
            "source": {
                "publisher": "팀 제공 금융 엑셀",
                "title": "농기계 세부융자표",
                "url": row.get("officialSourceUrl"),
                "evidenceLocation": row.get("sourceWorkbookRow"),
            },
            "notice": "기종·모델·가격·융자 조건은 워크북 기록이며 제조사 원문과 대조되지 않았습니다. 실제 판매 제품으로 확인되지 않았습니다.",
        })

    facility_candidates = []
    for row in finance.get("facilityFinanceDetails", []):
        facility_candidates.append({
            "id": row["id"],
            "title": row.get("item", "시설 장비 미기록"),
            "group": row.get("category", "시설 설비"),
            "recordType": "team_workbook_facility_candidate",
            "purposeAsRecorded": row.get("purposeAsRecorded"),
            "installationCostAsRecorded": row.get("installationCostAsRecorded"),
            "subsidyRateAsRecorded": row.get("subsidyRateAsRecorded"),
            "financeTermsAsRecorded": row.get("financeTermsAsRecorded"),
            "programAndInstitutionAsRecorded": row.get("programAndInstitutionAsRecorded"),
            "cultivationModes": [],
            "factVerificationStatus": "unverified",
            "productIdentityVerificationStatus": "unverified",
            "priceVerificationStatus": "unverified",
            "performanceVerificationStatus": "unverified",
            "salesStatus": "unknown",
            "publicationStatus": "review",
            "source": {
                "publisher": "팀 제공 금융 엑셀",
                "title": "추가설비 상세명세",
                "url": None,
                "evidenceLocation": row.get("sourceWorkbookRow"),
            },
            "notice": "품목·설치비·보조율·융자 조건은 워크북 기록이며 공식 제품·사업 원문과 대조되지 않았습니다.",
        })

    # Similarity is a review lead, not a declaration that records are identical.
    possible_links = [
        {"leftId": "EX-AGRI-DRONE", "rightId": "MC-DR-001", "reason": "농업용 드론이라는 주제 유사성만 확인; 동일 제품 아님"},
        {"leftId": "EX-AUTONOMOUS-TRACTOR", "rightId": "MC-TR-001", "reason": "트랙터 범주 유사성만 확인; 자율주행 패키지와 일반 트랙터는 동일 항목으로 판정하지 않음"},
        {"leftId": "EX-AUTONOMOUS-TRACTOR", "rightId": "MC-TR-002", "reason": "트랙터 범주 유사성만 확인; 자율주행 패키지와 일반 트랙터는 동일 항목으로 판정하지 않음"},
        {"leftId": "EX-VALVE-NUTRIENT", "rightId": "FAC-ICT-02", "reason": "양액 공급·제어 범주 유사성만 확인; 제품·구성이 일치하는지 미확인"},
    ]

    payload = {
        "schemaVersion": 1,
        "generatedAt": date.today().isoformat(),
        "generatedFrom": [
            "data/smart-agriculture-catalog.json",
            "data/finance-products.json (생성 순서: build_finance_data.py 먼저 실행)",
        ],
        "notice": "공식 지침상 범주, 팀 아이디어, 팀 워크북의 기종·설비 후보를 분리합니다. 실제 제조사 제품으로 확인된 항목은 현재 0건입니다.",
        "officialGuidelineCategories": guidelines,
        "teamIdeas": ideas,
        "productCandidates": product_candidates,
        "facilityCandidates": facility_candidates,
        "verifiedProducts": [],
    }
    audit = {
        "schemaVersion": 1,
        "generatedAt": payload["generatedAt"],
        "counts": {key: len(payload[key]) for key in ["officialGuidelineCategories", "teamIdeas", "productCandidates", "facilityCandidates", "verifiedProducts"]},
        "productSourceCoverage": {
            "verifiedManufacturerProductPages": 0,
            "officialGuidelineCategoriesWithDirectUrl": sum(bool(x["source"].get("url")) for x in guidelines),
            "officialGuidelineCategoriesMissingDirectUrl": sum(not bool(x["source"].get("url")) for x in guidelines),
            "productCandidateRowsMissingManufacturerVerification": len(product_candidates),
            "facilityCandidateRowsWithoutProductIdentity": len(facility_candidates),
        },
        "possibleDuplicateLinks": possible_links,
        "checks": {
            "allTeamIdeasMarkedReview": all(x["publicationStatus"] == "review" for x in ideas),
            "allWorkbookCandidatesUnverified": all(x["factVerificationStatus"] == "unverified" for x in product_candidates + facility_candidates),
            "noWorkbookCandidateMarkedForSale": all(x["salesStatus"] == "unknown" for x in product_candidates + facility_candidates),
            "verifiedProductsRequireOfficialManufacturerUrl": all(bool(x.get("manufacturerSourceUrl") and x.get("model")) for x in payload["verifiedProducts"]),
        },
        "limitations": [
            "금융 엑셀의 농기계·설비 기록은 제품 및 정부 지원 대상 확인의 근거로 단독 사용하지 않음",
            "팀 아이디어와 워크북 기종 후보의 유사성은 중복 확정이 아님",
            "공식 제품 페이지와 모델이 연결된 검증 제품은 현재 없음",
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "audit": str(AUDIT.relative_to(ROOT)), "counts": audit["counts"], "possibleDuplicateLinks": len(possible_links)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
