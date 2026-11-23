# 재배기술 연결 기준 — 2026-11-23

- 농사로 기존 12개 검증 작물 코드를 보존한다. 고추·오이·벼·딸기에서 공식 페이지의 생산기술 `sectionCrop02`, 농작업일정 `sectionCrop05`, 병해충 방제 `sectionCrop06` 영역을 확인했다. 농작업일정은 물·비료 또는 수확·저장만 모은 상세 문서가 아니므로 해당 작형·항목을 확인하도록 표시한다. 나머지 작물은 확인되지 않은 주제 매개변수를 생성하지 않는다.
- NCPMS 공식 식량·채소·과수·화훼·특용작물 도감의 공개 작물명과 코드 목록을 대조하여 기존 67종 중 이름이 정확히 일치하는 48종을 연결한다. `kncrCode`는 해당 도감의 실제 검색 필드이며 농사로 코드에서 추정하지 않는다. 벼 등 불일치·미확인 명칭은 재선택 안내를 유지한다.
- 농약안전정보시스템의 실제 작물명 검색 필드 `sAgCropsNm1`, `sAgCropsYn1=Y`를 사용한다. 고추·오이의 새 URL에서 검색값 유지와 실제 작물별 결과를 확인했다. 67종에 같은 검색 규약을 사용하지만 등록농약 존재·효능·처방을 보장하지 않는다.
- 흙토람 비료·물 처방은 필지·토양검정·재배조건 등 추가 입력을 유지한다. 외부 폼 자동 입력·세션 주입·로그인 우회는 하지 않는다.
- 기존 7개 주제를 6개로 정리한다. 재배 시작과 재배환경을 합치고 모든 기존 출처의 주제 대응을 보존한다. 기존 작물별 농작업일정·배추 동영상과 상담·처방 링크를 삭제하지 않는다.

공식 근거: [농사로 고추](https://www.nongsaro.go.kr/portal/farmTechMain.ps?menuId=PS65291&stdPrdlstCode=VC011205), [NCPMS 오이](https://ncpms.rda.go.kr/npms/VegitablesPhotoListR.np?kncrCode=VC010901), [농약안전정보 작물명 검색](https://psis.rda.go.kr/psis/agc/res/agchmRegistStusLst.ps?menuId=PS00263&pageUnit=20&sAgCropsNm1=%EA%B3%A0%EC%B6%94&sAgCropsYn1=Y), [흙토람](https://soil.rda.go.kr/sibi/sibiPrescript.do).
