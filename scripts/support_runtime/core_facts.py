"""Source-labelled core facts; never infer geography from a publisher or title."""
import re

PROVINCES={'서울','서울특별시','부산','부산광역시','대구','대구광역시','인천','인천광역시',
    '광주','광주광역시','대전','대전광역시','울산','울산광역시','세종','세종특별자치시',
    '경기','경기도','강원','강원도','강원특별자치도','충북','충청북도','충남','충청남도',
    '전북','전라북도','전북특별자치도','전남','전라남도','경북','경상북도','경남','경상남도',
    '제주','제주도','제주특별자치도'}


def region_scope(region):
    return 'province' if region in PROVINCES or region.endswith('도') else 'municipality'

LABELS={
 'target_description':['사업대상자','사업대상','지원대상','신청대상'],
 'support_description':['지원내용','사업내용','지원품목','자금 용도별 지원 조건'],
 'application_method':['신청방법','접수방법','신청장소','접수장소','접수처','신청접수처'],
 'implementing_institution':['시행기관','주관기관'],
 'application_period':['신청기간','접수기간','신청기한','모집기간','신청마감','접수마감','모집일시'],
 'required_documents':['제출서류','신청서류','구비서류'],
 'eligibility_description':['신청자격','지원자격','지원조건 및 의무사항','지원조건'],
 'exclusion_description':['제외대상','지원제외','신청제외'],
 'geographic_scope':['지원지역','사업지역','신청지역'],
 '_boundary':['사업명','사업기간','총사업비','사업비','재원비율','지원단가','지원한도','선정 우선순위','우선순위','문의처','협조사항','담당기관'],
}
ALIASES={re.sub(r'\s+','',label):key for key,labels in LABELS.items() for label in labels}
PATTERN='|'.join(r'\s*'.join(re.escape(c) for c in label) for label in sorted(ALIASES,key=len,reverse=True))
HEADER=re.compile(r'(?:'+r'(?P<colon>'+PATTERN+r')(?P<modifier>\s*(?:연장|변경\s*후|정정\s*후))?\s*[:：]'+
                  r'|(?:^|\s)(?:\d{1,2}|[가-하])[.．)]\s*(?P<number>'+PATTERN+r')(?=\s|[:：]|$))')


def sections(lines):
    # Join editor formatting first: e.g. "12." + "31." is one date, not two.
    text=' '.join(dict.fromkeys(' '.join(x.split()) for x in lines if x.strip()))
    matches=list(HEADER.finditer(text));result=[]
    for i,m in enumerate(matches):
        label=m.group('colon') or m.group('number');key=ALIASES[re.sub(r'\s+','',label)]
        if m.group('modifier'):label+=m.group('modifier')
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        value=text[m.end():end].strip(' :：')
        value=re.sub(r'\s+[가-하][.．)]\s*$','',value).strip()
        value=re.split(r'전체다운로드|첨부파일',value)[0].strip()
        if value:result.append((key,label,value,m.start()))
    return result


def section_lines(lines):
    return [label+' : '+value for key,label,value,_ in sections(lines) if key=='application_period']


def period_input(lines):
    repaired=section_lines(lines)
    if not repaired:return lines
    for line in lines:
        # Keep status, extension and cancellation signals outside date headings.
        if re.search(r'종료|조기\s*마감|마감되|현재|지금|상시|연중|연장|정정|변경',line):
            repaired.append(line)
        elif (re.search(r'(?:신청|접수|모집).*(?:마감|기한|기간|일시|[:：])',line)
              and not any(key=='application_period' for key,_,_,_ in sections([line]))):
            repaired.append(line)
    return list(dict.fromkeys(repaired))


def extract(lines,url):
    result={}
    def add(key,value,quote,location):
        if key not in result and value not in ('','unknown',None):
            result[key]={'value':value,'evidence':{'url':url,'quote':quote,'location':location}}
    for key,label,value,offset in sections(lines):
        if key.startswith('_') or key=='application_period':continue
        if key=='implementing_institution':continue
        if len(value)>900:continue  # No truncated qualification clause.
        if key=='geographic_scope':
            original=value
            if re.fullmatch(r'전국(?:\s*(?:대상|공통))?',value):
                value={'scope':'national','regions':['전국'],'basis':'unknown'}
            elif value in PROVINCES or re.fullmatch(r'[가-힣 ]{2,30}(?:시|군|구|도)',value):
                value={'scope':region_scope(value),'regions':[value],'basis':'unknown'}
            else:continue
        add(key,value,label+' : '+(original if key=='geographic_scope' else value),
            '공식 본문 항목 경계; 정규화 텍스트 위치 '+str(offset))
    for line in lines:
        m=re.fullmatch(r'(?:시행기관|주관기관)\s*[:：]\s*(.{2,70})',line)
        if m and re.fullmatch(r'[가-힣A-Za-z0-9 ()·]{2,70}(?:부|청|원|공사|센터|시|군|구|협회|재단|공단|조합|도)',m[1]):
            add('implementing_institution',m[1],line,'공식 본문의 시행·주관기관 항목')
    # The official bullet form distinguishes target and benefits without labels.
    for line in lines:
        for fragment in re.split(r'☞',line)[1:]:
            fragment=fragment.split('※')[0].strip()
            if not fragment or len(fragment)>700:continue
            if re.search(r'농업경영정보를\s*등록한\s*농업경영체',fragment):
                add('target_description',fragment,fragment,'공식 본문 대상 표시(☞)')
            elif re.search(r'종자|자재|구입비|컨설팅',fragment) and fragment.endswith('지원'):
                add('support_description',fragment,fragment,'공식 본문 지원 표시(☞)')
    text=' '.join(lines)
    method=re.search(r'농지소재지[^。]{0,100}?사업신청서\s*제출(?:\s*또는\s*온라인\s*신청)?',text)
    if method:add('application_method',method[0],method[0],'공식 본문 신청서 제출 문구')
    target=result.get('target_description',{});v=target.get('value','')
    # Preserve logical alternatives/exceptions as text; do not flatten them.
    if isinstance(v,str) and not re.search(r'또는|제외|다만|미등록|예비|창업계획',v):
        types=[]
        if re.match(r'^(?:다음\s*요건을\s*모두\s*충족하는\s*)?(?:관내\s*)?농업인\s*(?:및|·|,)\s*농업법인(?:\s|$)',v):
            types=['individual_farmer','agricultural_business']
        elif re.fullmatch(r'(?:관내\s*)?(?:농업인|농가)',v):types=['individual_farmer']
        elif re.fullmatch(r'(?:관내\s*)?농업법인',v):types=['agricultural_business']
        elif re.fullmatch(r'(?:관내\s*)?(?:농업인\s*)?단체',v):types=['institution_group']
        if types:result['applicant_types']={'value':types,'evidence':dict(target['evidence'])}
        locations=[]
        for kind,basis,pattern in [
            ('residence','residence',r'([가-힣]{2,10}(?:시|군|구|도))에\s*(?:거주하는|주소(?:지)?를\s*둔)'),
            ('business_location','farm_land',r'([가-힣]{2,10}(?:시|군|구|도))에\s*농지를\s*둔'),
            ('business_location','business_office',r'([가-힣]{2,10}(?:시|군|구|도))에\s*사업장을\s*둔')]:
            for m in re.finditer(pattern,v):locations.append((kind,basis,m[1]))
        if len(locations)==1:
            kind,basis,region=locations[0]
            result['location_requirement']={'value':{'kind':kind,'regions':[region],'location_basis':basis},'evidence':dict(target['evidence'])}
            result['geographic_scope']={'value':{'scope':region_scope(region),'regions':[region],'basis':basis},'evidence':dict(target['evidence'])}
    support=result.get('support_description',{})
    if isinstance(support.get('value'),str):
        value=support['value'];summary=value if len(value)<=350 else ''
        if not summary:
            labels=re.findall(r'\(\s*(시설\s*자금|리모델링\s*자금|운영\s*자금)\s*\)',value)
            summary='·'.join(dict.fromkeys(re.sub(r'\s+','',x) for x in labels))
        if summary:result['support_summary']={'value':summary,'evidence':dict(support['evidence']),
            'scope':'purpose_only_not_amount_or_eligibility'}
    return result
