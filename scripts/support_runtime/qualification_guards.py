"""Conservative candidate interpretation; never approves or publishes a fact."""
import re


def personal_only(text):
    # A farmer appearing among exporters/packers/entities is not an exclusive
    # individual-farmer requirement. Unsupported enterprise kinds stay unknown.
    return bool(re.search(r'농업인|농가', text)) and not re.search(
        r'법인|기업|업체|제조자|농협|조합|기관|단체|생산자조직', text)


def review_requirements(text):
    """Keep requirements not expressible as an independent scalar visible."""
    checks = [
        (r'여성|남성|출생|짝수|홀수', '성별·출생연도 및 연령 기준 확인 필요'),
        (r'본인.{0,30}등록된\s*농지|등록된\s*관내\s*농지', '등록된 농지·생산 및 소재지 요건 확인 필요'),
        (r'추가|변경\s*신청|신청하지\s*못한', '추가·변경 신청 해당 여부 확인 필요'),
        (r'관내|도내', '관내·도내의 실제 적용 지역과 기준 확인 필요'),
        (r'업체|법인|단체|기관', '신청 주체별 적용 범위와 예외 확인 필요'),
        (r'또는|다만|예외|예정|정착을\s*희망', '대안·예외·이전 조건을 함께 확인해야 함'),
    ]
    return [note for pattern, note in checks if re.search(pattern, text)]


def explicit_locations(text):
    """Named geography in the eligibility sentence, not in publisher metadata.

    Branches and relocations require human review. Never expand 관내/도내.
    """
    if re.search(r'또는|다만|예외|관외|타시군|이전\s*완료|선정된\s*후', text):
        return []
    places=[]
    joint=re.search(r'([가-힣]{2,10}(?:시|군|구|도))에\s*주소(?:지)?\s*(?:및|와)\s*농지를\s*둔',text)
    if joint:
        return [{'kind':kind,'regions':[joint[1]],'location_basis':basis} for kind,basis in
                [('residence','residence'),('business_location','farm_land')]]
    for kind,basis,pattern in [
        ('residence','residence',r'([가-힣]{2,10}(?:시|군|구|도))(?:에\s*|\s*관내\s*)(?:거주(?:하는|하면서)|주소(?:지)?를?\s*둔)'),
        ('business_location','farm_land',r'([가-힣]{2,10}(?:시|군|구|도))에\s*농지를\s*둔'),
        ('business_location','business_office',r'([가-힣]{2,10}(?:시|군|구|도))에\s*사업장을\s*둔'),
    ]:
        for match in re.finditer(pattern,text):
            item={'kind':kind,'regions':[match[1]],'location_basis':basis}
            if item not in places:places.append(item)
    return places
