"""Build finance review data from the team's workbook without editing the source.

Run from the project root with Python 3: python scripts/build_finance_data.py
Only standard-library ZIP/XML/JSON modules are used. Source workbook/catalog are read-only.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "data/source/moonongsa_agricultural_finance_with_criteria.xlsx"
CATALOG = ROOT / "data/smart-agriculture-catalog.json"
OUT = ROOT / "data/finance-products.json"
AUDIT = ROOT / "data/finance-integration-audit.json"
NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def excel_column_index(address: str) -> int:
    letters = re.match(r"[A-Z]+", address).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def number(value):
    if value is None or value == "":
        return None
    try:
        n = float(value)
        return int(n) if n.is_integer() else n
    except (TypeError, ValueError):
        return value


def read_xlsx_sheets(path: Path) -> list[tuple[str, list[list[object]]]]:
    """Read displayed cell values and formulas with Python's standard library."""
    with zipfile.ZipFile(path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rels = {r.attrib["Id"]: r.attrib["Target"] for r in rels_root.findall("rel:Relationship", NS)}
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            strings = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in item.findall(".//a:t", NS)) for item in strings.findall("a:si", NS)]
        result = []
        for sheet in workbook.findall("a:sheets/a:sheet", NS):
            target = rels[sheet.attrib[f"{{{NS['r']}}}id"]].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            xml = ET.fromstring(zf.read(target))
            rows = []
            for row in xml.findall("a:sheetData/a:row", NS):
                values = []
                for cell in row.findall("a:c", NS):
                    idx = excel_column_index(cell.attrib["r"])
                    while len(values) <= idx:
                        values.append(None)
                    typ = cell.attrib.get("t")
                    v = cell.find("a:v", NS)
                    formula = cell.find("a:f", NS)
                    if typ == "s" and v is not None and v.text:
                        value = shared[int(v.text)]
                    elif typ == "inlineStr":
                        value = "".join(t.text or "" for t in cell.findall(".//a:t", NS))
                    elif typ == "b" and v is not None:
                        value = v.text == "1"
                    elif v is not None:
                        value = number(v.text)
                    else:
                        value = None
                    # Formula cells with no cached result remain explicit; we never recalculate them here.
                    if formula is not None:
                        value = {"formula": formula.text or "", "cachedValue": value}
                    values[idx] = value
                rows.append(values)
            result.append((sheet.attrib["name"], rows))
        return result


def records_for(sheet: tuple[str, list[list[object]]], id_prefix: str) -> tuple[list[str], list[dict]]:
    name, rows = sheet
    header_idx = next((i for i, row in enumerate(rows) if row and isinstance(row[0], str) and row[0].strip()), None)
    # These workbooks use title/subtitle rows; row 4 is the table header.
    header_idx = next((i for i, row in enumerate(rows) if row and isinstance(row[0], str) and any(x in row[0] for x in ["상품ID", "카테고리ID", "특수금융ID", "기종코드", "설비코드", "구입/도입"])), 3)
    headers = [str(v or "").strip() for v in rows[header_idx]]
    records = []
    for row_number, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if not row or row[0] in (None, ""):
            continue
        cells = list(row) + [None] * max(0, len(headers) - len(row))
        raw = dict(zip(headers, cells))
        records.append({"sourceRow": row_number, "raw": raw})
    return headers, records


def get(rec: dict, col: int):
    vals = list(rec["raw"].values())
    return vals[col] if col < len(vals) else None


def make_product(rec: dict) -> dict:
    r = rec["raw"]
    values = list(r.values())
    product_id = values[0]
    category = values[1]
    fund_type = str(values[6] or "")
    title = str(values[5] or "")
    text = f"{category} {title} {fund_type}"
    if product_id.startswith("LP-EQP") or "농기계" in text:
        purpose_category, product_type = "machinery", "machinery_finance"
    elif "주택" in title:
        purpose_category, product_type = "housing", "land_housing_finance"
    elif any(t in text for t in ["농지", "경영회생", "환매"]):
        purpose_category, product_type = "land_or_farmland_welfare", "land_housing_finance"
    elif "농지연금" in text or "농업인행복" in text:
        purpose_category, product_type = "retirement_or_commercial", "private_finance" if "은행 자체" in fund_type else "public_finance"
    elif product_id.startswith("LP-ADD") or product_id.startswith("LP-FAC"):
        purpose_category, product_type = "facility", "facility_finance"
    elif any(t in text for t in ["축산", "가축", "사료"]):
        purpose_category, product_type = "livestock", "policy_loan"
    elif any(t in text for t in ["6차산업", "가공", "원료구매"]):
        purpose_category, product_type = "processing_and_distribution", "policy_loan"
    elif any(t in text for t in ["태양광", "신재생"]):
        purpose_category, product_type = "renewable_energy", "policy_loan"
    elif "재해" in text:
        purpose_category, product_type = "emergency_recovery", "emergency_policy_loan"
    elif any(t in text for t in ["영농운전", "운전", "경영자금"]):
        purpose_category, product_type = "operating_cost", "policy_loan"
    elif "상업금융" in text or "은행 자체" in fund_type:
        purpose_category, product_type = "commercial_credit", "private_finance"
    else:
        purpose_category, product_type = "startup_and_settlement", "policy_loan"
    financing_nature = "private_finance" if "민간" in fund_type or "은행 자체" in fund_type else "public_institution_finance" if "공공기관" in fund_type or "공공 연금" in fund_type else "policy_finance"

    source_ids = []
    if product_id == "LP-FAC-001":
        source_ids = ["S-MAFRA-2026-PLAN"]
    elif product_id in {"LP-NAT-003", "LP-NAT-004"}:
        source_ids = ["S-GREENDAERO-2026-STARTUP-LOAN"]
    elif product_id == "LP-6TH-002":
        source_ids = ["SRC-AT-2026-POLICY-FUNDS"]
    at_partially_verified = product_id == "LP-6TH-002"
    green_daero_reviewed = product_id in {"LP-NAT-003", "LP-NAT-004"}
    field_verification = {
        "title": "unverified",
        "target": "unverified",
        "limit": "unverified",
        "interest": "conflict" if green_daero_reviewed else "unverified",
        "repayment": "partially_verified" if green_daero_reviewed else "unverified",
        "eligibility": "unverified",
        "applicationStatus": "unverified",
    }
    return {
        "id": product_id,
        "recordType": "finance_candidate",
        "title": values[5],
        "category": category,
        "subCategory": values[2],
        "productType": product_type,
        "purposeCategory": purpose_category,
        "financingNature": financing_nature,
        "institutionId": values[3],
        "institution": values[4],
        "fundType": values[6],
        "maxLimitAsRecordedWon": values[7],
        "interestAsRecorded": {"type": values[8], "referenceRate": values[9]},
        "graceYearsAsRecorded": values[10],
        "repaymentYearsAsRecorded": values[11],
        "repaymentMethodAsRecorded": values[12],
        "guaranteeAsRecorded": values[13],
        "allowedUsesAsRecorded": values[14],
        "subsidyLinkAsRecorded": values[15],
        "applicationStatusAsRecordedInWorkbook": values[16],
        "verificationStatusAsRecordedInWorkbook": values[17],
        "approvalFactorsAsRecorded": values[18] if len(values) > 18 else None,
        "currentApplicationStatus": "unknown",
        "factVerificationStatus": "partially_verified" if at_partially_verified or green_daero_reviewed else "unverified",
        "fieldVerification": field_verification,
        "officialComparisons": ([
            {
                "field": "interest",
                "status": "conflict",
                "workbookValue": values[8],
                "officialValue": "고정 연 2.0% 또는 변동금리 선택; 변동금리는 금융기관 고시금리를 적용하고 6개월마다 변동. 고정 2.0%는 2025년 사업 선정자부터 적용.",
                "evidenceLocation": "2026 사업안내 > 대출금리, 게시 페이지 안내 141–148행",
            },
            {
                "field": "repayment",
                "status": "partially_verified",
                "workbookValue": f"{values[10]}년 거치 · {values[11]}년 원금균등 상환",
                "officialValue": "5년 거치 · 10년 원금균등 분할상환",
                "evidenceLocation": "2026 사업안내 > 상환 기간, 153–157행",
            },
        ] if green_daero_reviewed else []),
        "publicationStatus": "review",
        "sourceIds": source_ids,
        "relatedCatalogRecordIds": [],
        "sourceWorkbookRow": rec["sourceRow"],
        "notice": "팀 엑셀 기록을 보존한 검토 후보입니다. 귀농 창업·주택 자금은 공식 안내와 금리 기록이 달라 충돌 검토 중입니다. 한도·자격·현재 신청 상태는 확정하지 않았습니다.",
        "raw": r,
    }


def main() -> None:
    sheets = read_xlsx_sheets(XLSX)
    if len(sheets) != 6:
        raise ValueError(f"Expected six workbook sheets, found {len(sheets)}")
    extracted = [records_for(sheet, str(i)) for i, sheet in enumerate(sheets)]
    loan_headers, loan_records = extracted[0]
    taxonomy_headers, taxonomy_records = extracted[1]
    special_headers, special_records = extracted[2]
    machinery_headers, machinery_records = extracted[3]
    facility_headers, facility_records = extracted[4]
    simulator_headers, simulator_records = extracted[5]
    products = [make_product(rec) for rec in loan_records]

    catalog = json.loads(CATALOG.read_text(encoding="utf-8-sig"))
    catalog_sources = {s["id"]: s for s in catalog.get("sources", [])}
    catalog_finance = [r for r in catalog.get("sampleRecords", []) if r.get("category") == "은행·정책금융"]
    catalog_ids = {r["id"] for r in catalog_finance}
    relation_map = {
        "LP-FAC-001": ["SMARTFARM-LOAN-2026"],
        "LP-NAT-003": ["NEW-FARMER-STARTUP-LOAN-2026"],
        "LP-NAT-004": ["NEW-FARMER-STARTUP-LOAN-2026"],
    }
    for product in products:
        product["relatedCatalogRecordIds"] = [i for i in relation_map.get(product["id"], []) if i in catalog_ids]
        if product["id"] in {"LP-FAC-001", "LP-NAT-003", "LP-NAT-004"}:
            product["duplicateHandling"] = "existing_catalog_record_linked; do not create a second card"
        else:
            product["duplicateHandling"] = "no matching finance card found in current catalog"

    special_relations = {
        "SP-6TH-01": "LP-6TH-001", "SP-AT-01": "LP-6TH-002", "SP-HOU-01": "LP-HOU-001",
        "SP-REH-01": "LP-REH-001", "SP-PEN-01": "LP-PEN-001", "SP-LIV-01": "LP-LIV-003",
    }
    special = []
    for rec in special_records:
        v = list(rec["raw"].values())
        special.append({"id": v[0], "title": v[2], "category": v[1], "institution": v[3], "targetAsRecorded": v[4], "termsAsRecorded": {"limit": v[5], "interestAndRepayment": v[6]}, "notesAsRecorded": v[7], "relatedProductId": special_relations.get(v[0]), "factVerificationStatus": "unverified", "publicationStatus": "review", "sourceWorkbookRow": rec["sourceRow"], "raw": rec["raw"]})
    machinery = []
    for rec in machinery_records:
        v = list(rec["raw"].values())
        machinery.append({"id": v[0], "equipmentType": v[1], "specificationAsRecorded": v[2], "modelsAsRecorded": v[3], "estimatedPriceAsRecordedWon": v[4], "loanLimitAsRecordedWon": v[5], "ratioAsRecorded": v[6], "termsAsRecorded": v[7], "teamNote": v[8], "recordType": "team_machinery_finance_example", "factVerificationStatus": "unverified", "publicationStatus": "review", "priceBasisDate": None, "officialSourceUrl": None, "sourceWorkbookRow": rec["sourceRow"], "raw": rec["raw"]})
    facility_links = {"FAC-ENG-01":"LP-ADD-001","FAC-ENG-02":"LP-ADD-001","FAC-ENG-03":"LP-ADD-001","FAC-ICT-01":"LP-ADD-002","FAC-ICT-02":"LP-ADD-002","FAC-ICT-03":"LP-ADD-002","FAC-PST-01":"LP-ADD-003","FAC-PST-02":"LP-ADD-003","FAC-WTR-01":"LP-ADD-004","FAC-WTR-02":"LP-ADD-004","FAC-LIV-01":"LP-LIV-001","FAC-LIV-02":"LP-LIV-002","FAC-ENG-04":"LP-ENG-001"}
    facilities = []
    for rec in facility_records:
        v = list(rec["raw"].values())
        facilities.append({"id": v[0], "category": v[1], "item": v[2], "purposeAsRecorded": v[3], "installationCostAsRecorded": v[4], "subsidyRateAsRecorded": v[5], "financeTermsAsRecorded": v[6], "programAndInstitutionAsRecorded": v[7], "relatedProductId": facility_links.get(v[0]), "factVerificationStatus": "unverified", "publicationStatus": "review", "sourceWorkbookRow": rec["sourceRow"], "raw": rec["raw"]})
    taxonomy = []
    for rec in taxonomy_records:
        v = list(rec["raw"].values())
        taxonomy.append({"id": v[0], "category": v[1], "subCategory": v[2], "personaAsRecorded": v[3], "ageAndExperienceAsRecorded": v[4], "purposeAsRecorded": v[5], "collateralAsRecorded": v[6], "mandatoryCriteriaAsRecorded": v[7], "benefitAsRecorded": v[8], "formulaOrProductCountAsRecorded": v[9], "teamMatchingLogic": v[10], "recordType": "team_taxonomy_draft", "factVerificationStatus": "unverified", "publicationStatus": "review", "raw": rec["raw"]})
    taxonomy_by_category = {row["category"]: row for row in taxonomy}
    for product in products:
        draft = taxonomy_by_category.get(product["category"])
        product["teamClassificationDraft"] = ({"persona": draft["personaAsRecorded"], "ageAndExperience": draft["ageAndExperienceAsRecorded"], "mandatoryCriteria": draft["mandatoryCriteriaAsRecorded"], "teamMatchingLogic": draft["teamMatchingLogic"], "status": "팀 분류 초안 · 미검증"} if draft else None)
    scenarios = []
    formula_samples = {}
    for rec in simulator_records:
        v = list(rec["raw"].values())
        scenarios.append({"labelAsRecorded": v[0], "principalWonAsRecorded": v[1], "annualRateAsRecorded": v[2], "graceYearsAsRecorded": v[3], "repaymentYearsAsRecorded": v[4], "recordType": "workbook_calculator_scenario_not_site_calculator", "factVerificationStatus": "unverified", "publicationStatus": "review", "raw": rec["raw"]})
        for col_name, cell in rec["raw"].items():
            if isinstance(cell, dict) and cell.get("formula"):
                formula_samples[col_name] = cell["formula"]

    at_source = {
        "id": "SRC-AT-2026-POLICY-FUNDS",
        "title": "2026년 정책자금 종합안내",
        "publisher": "한국농수산식품유통공사(aT)",
        "url": "https://www.at.or.kr/contents/apko331100/view.action",
        "publicationDate": "2026",
        "evidenceLocation": "2026년 정책자금 종합안내 표; 식품가공원료매입자금 항목",
        "verificationScope": "사업명·용도·대상 범주의 공식 페이지 존재 확인. 개별 금리·한도·신청 기간·현재 접수 상태는 추가 원문 대조 필요.",
        "lastCheckedAt": "2026-10-24",
    }
    green_daero_source = {
        "id": "S-GREENDAERO-2026-STARTUP-LOAN",
        "title": "2026년 귀농 농업창업 및 주택구입 지원사업 안내",
        "publisher": "그린대로 귀농귀촌 종합 플랫폼",
        "url": "https://www.greendaero.go.kr/svc/rfph/cpif/front/frtHome.do",
        "publicationDate": "2026 사업 안내",
        "evidenceLocation": "사업대상자·지원대상 및 제출서류; 대출금리(141–148행); 상환기간(153–157행); 접수처·금융기관 사전 신용·담보 조회(165–173행)",
        "verificationScope": "LP-NAT-003·004에 대해 금리와 상환구조만 공식 페이지에서 일부 대조했습니다. 금리는 팀 엑셀의 1.5% 기록과 공식 페이지의 고정 연 2.0% 안내가 충돌합니다. 한도, 개별 자격 충족, 시군 접수 여부 및 현재 신청 가능 상태는 확인하지 않았습니다.",
        "lastCheckedAt": "2026-10-24",
    }
    source_lookup = {**catalog_sources, at_source["id"]: at_source, green_daero_source["id"]: green_daero_source}
    for product in products:
        product["sources"] = [source_lookup[sid] for sid in product["sourceIds"] if sid in source_lookup]

    out = {
        "schemaVersion": 1,
        "generatedAt": "2026-10-24",
        "sourceWorkbook": "data/source/moonongsa_agricultural_finance_with_criteria.xlsx",
        "sourceWorkbookModified": False,
        "notice": "팀 워크북의 기록값과 공식 검증 사실을 구분합니다. 현재 신청 가능 여부는 모든 항목에서 미확인입니다. 대출 승인은 취급기관 심사에 따릅니다.",
        "officialSources": [at_source, green_daero_source],
        "masterProducts": products,
        "teamTaxonomyDrafts": taxonomy,
        "specialtyProductDetails": special,
        "machineryFinanceExamples": machinery,
        "facilityFinanceDetails": facilities,
        "calculatorScenarios": scenarios,
    }
    formula_count = sum(1 for row in sheets[5][1] for cell in row if isinstance(cell, dict) and cell.get("formula"))
    audit = {
        "schemaVersion": 1,
        "generatedAt": "2026-10-24",
        "sourceSheetCounts": {
            "masterProducts": len(products), "teamTaxonomyDrafts": len(taxonomy),
            "specialtyProductDetails": len(special), "machineryFinanceExamples": len(machinery),
            "facilityFinanceDetails": len(facilities), "calculatorScenarios": len(scenarios),
        },
        "catalogFinanceRecordIds": sorted(catalog_ids),
        "linkedDuplicateCandidates": {p["id"]: p["relatedCatalogRecordIds"] for p in products if p["relatedCatalogRecordIds"]},
        "catalogConflictCandidates": [
            {"productId": "LP-FAC-001", "catalogRecordId": "SMARTFARM-LOAN-2026", "workbookClaim": "3억원 한도 기록, 고정 1.0~2.0% 또는 변동, 5년 거치·15년 상환", "catalogClaim": "최대 50억원, 고정 연리 1.0%, 5년 거치·20년 균분상환", "conflictingFields": ["한도", "금리 체계", "상환 기간", "기준 자료"], "resolution": "두 기록을 병합하지 않고 원문 연도·자금유형 대조 필요"},
            {"productId": "LP-NAT-003", "catalogRecordId": "NEW-FARMER-STARTUP-LOAN-2026", "workbookClaim": "창업자금 최대 3억원, 고정 1.5% 또는 변동, 5년 거치·10년 원금균등 기록", "catalogClaim": "2026 안내 기준 고정 연 2.0% 또는 변동, 5년 거치·10년 원금균등", "conflictingFields": ["금리"], "resolution": "그린대로 2026 사업안내에서 고정 연 2.0% 또는 변동 및 5년 거치·10년 원금균등을 확인. 워크북의 1.5%는 공식 안내와 충돌하므로 원자료 기록은 보존하고 금리를 검토 상태로 표시. 한도와 현재 접수 상태는 미확인."},
            {"productId": "LP-NAT-004", "catalogRecordId": "NEW-FARMER-STARTUP-LOAN-2026", "workbookClaim": "주택자금 최대 7천5백만원, 고정 1.5% 또는 변동, 5년 거치·10년 원금균등", "catalogClaim": "카탈로그 카드는 창업·주택 사업을 묶어 2.0% 및 5년 거치·10년 상환 안내", "conflictingFields": ["상품 범위", "금리", "상환 조건 연결"], "resolution": "그린대로 2026 사업안내는 2.0% 고정 또는 변동, 5년 거치·10년 원금균등을 안내. 워크북 금리와 충돌하며, 별도 주택자금 한도·세부 자격·현재 접수는 추가 확인 필요."},
        ],
        "crossSheetDuplicateLinks": special_relations,
        "facilityDetailLinks": facility_links,
        "officialSourceCoverage": {
            "fullyVerifiedProductTerms": 0,
            "partiallyVerifiedProductPresenceOrPurpose": ["LP-6TH-002"],
            "partiallyVerifiedFieldRecords": {"LP-NAT-003": ["repayment"], "LP-NAT-004": ["repayment"]},
            "conflictingFieldRecords": ["LP-NAT-003.interest", "LP-NAT-004.interest"],
            "unverifiedProductTerms": len(products),
            "currentApplicationStatusKnown": 0,
            "rowsWithOriginalSourceUrl": 0,
        },
        "calculatorReview": {
            "scenarioCount": len(scenarios),
            "formulaCount": formula_count,
            "cachedFormulaResults": 0,
            "formulas": formula_samples,
            "assessment": "계산 시트에 수식 42개가 있으나 저장된 계산 결과는 없습니다. F는 거치기간 월 이자를 단리로 계산하고, G는 월 원금균등액에 최초 원금 기준 월 이자를 더합니다. H는 거치이자와 연 단위 원금균등 상환을 가정한 단순 총이자식입니다. 월별 잔액 감소 및 실제 금융기관의 납입 스케줄과 일치한다고 확인되지 않아 서비스 계산기로 이식하지 않았습니다.",
            "siteCalculatorImplemented": False,
        },
        "checks": {
            "masterIdsUnique": len({p["id"] for p in products}) == len(products),
            "allMasterRowsHaveReviewStatus": all(p["publicationStatus"] == "review" for p in products),
            "noWorkbookOpenStatusTreatedAsCurrentlyOpen": all(p["currentApplicationStatus"] == "unknown" for p in products),
            "duplicateCatalogRowsLinkedInsteadOfDuplicated": all(p["duplicateHandling"].startswith("existing_catalog") for p in products if p["relatedCatalogRecordIds"]),
        },
        "limitations": [
            "마스터 및 세부 시트에 상품별 공식 원문 URL·근거 위치가 거의 없어, source_checked 표기만으로 독립 검증하지 않았습니다.",
            "엑셀 카테고리의 추천 매칭 문구는 팀 초안으로만 보존하고 사용자 추천 로직에 사용하지 않습니다.",
            "스마트팜·귀농 융자 후보는 기존 카탈로그 카드와 연결했으며, 엑셀 조건은 충돌 가능성이 있어 미검증 표시합니다.",
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {OUT.relative_to(ROOT)}: {len(products)} master products, {len(machinery)} machinery examples")
    print(f"Generated {AUDIT.relative_to(ROOT)}: {formula_count} formulas recorded, site calculator not deployed")


if __name__ == "__main__":
    main()
