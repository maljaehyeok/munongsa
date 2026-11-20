"""Official notice names and direct links only; not a licence for source content."""
import re
from urllib.parse import urlsplit,parse_qs

POLICY_ID='official-notice-name-link-v1'
TITLE_BASIS='https://www.mcst.go.kr/site/s_policy/copyright/netizen/netizen02.jsp'
LINK_BASIS='https://www.copyright.or.kr/customer-center/faq/list.do?categorycode1=&counselfaqno=41686&pageIndex=12&portalcode=&searchkeyword='
# Reviewed existing official boards. New hosts/boards need separate review.
SOURCES={
 'rda-young-official':('www.rda.go.kr',r'/young/custom/policy/view\.do','https://www.rda.go.kr/datacprprot.do'),
 'jeonbuk-buan-official':('www.buan.go.kr',r'/(?:jbares/)?board/view\.buan','https://www.buan.go.kr/index.buan?menuCd=DOM_000000108006000000'),
 'jeonbuk-gochang-official':('www.gochang.go.kr',r'/board/view\.gochang',None),
 'jeonbuk-jinan-official':('www.jinan.go.kr',r'/board/view\.jinan',None),
 'jeonbuk-imsil-official':('www.imsil.go.kr',r'/agri/board/view\.imsil','https://www.imsil.go.kr/index.imsil?menuCd=DOM_000000107009000000'),
 'jeonbuk-sunchang-official':('www.sunchang.go.kr',r'/farm/board/post/view\.do','https://www.sunchang.go.kr/index.do?menuUid=ff8080819a2f0e3b019ac98510df4fb2'),
 'jeonbuk-province-notices':('www.jeonbuk.go.kr',r'/board/view\.jeonbuk','https://www.jeonbuk.go.kr/index.jeonbuk?menuCd=DOM_000000107006000000'),
 'jeonbuk-agriculture-guidelines':('www.jeonbuk.go.kr',r'/board/view\.jeonbuk','https://www.jeonbuk.go.kr/index.jeonbuk?menuCd=DOM_000000107006000000'),
 'jeonbuk-academy-official':('agriacademy.jeonbuk.go.kr',r'/bbs/board\.php',None),
 'at-export-official':('global.at.or.kr',r'/front/bizReq/brView\.do',None),
 'mafra-notices-rss':('www.mafra.go.kr',r'/bbs/home/\d+/\d+/artclView\.do',None),
 'koat-business-official':('www.koat.or.kr',r'/board/business/\d+/view\.do',None),
 'jeonbuk-gimje-official':('www.gimje.go.kr',r'/board/view\.gimje',None),
}

def allowed(row,check):
    spec=SOURCES.get(row['source_id']);u=urlsplit(row['original_url'])
    if not spec or u.scheme!='https' or u.hostname!=spec[0] or not re.fullmatch(spec[1],u.path):return None
    if (not check or check.get('status')!='checked' or check.get('url')!=row['original_url']
        or not check.get('title_match') or check.get('metadata_title_confirmed') is not True
        or check.get('metadata_link_restricted') is True):return None
    if row['source_id']=='at-export-official' and check.get('at_identity_verified') is not True:return None
    # A paragraph pasted into a title is not treated as an unprotected name.
    title=check.get('display_title') or row['title']
    if len(title)>180 or re.search(r'\b\d{2,3}-\d{3,4}-\d{4}\b|@|[<>\x00-\x1f]',title):return None
    return {'id':POLICY_ID,'type':'name_link','scope':'title_institution_link_only',
            'evidence_url':TITLE_BASIS,'link_basis_url':LINK_BASIS,'source_policy_url':spec[2],
            'body_redistribution':False,'attachment_redistribution':False,'eligibility_approval':False}

def title_check(soup,title,normalizer):
    wanted=normalizer(title)
    # Do not accept a title just because it appears in menus or related notices.
    candidates=soup.select('h4.title, .viewArea h4, .view_tit, .bbs_view h4, .border_view h4, .view-con h4, h4, .bbs-subject, .bo_v_title, .artclTitle, .artclViewTitle, .view-title, .view_top > dl > dt')
    return bool(wanted) and any(normalizer(n.get_text(' ',strip=True))==wanted for n in candidates)

def at_title_evidence(soup,stored,url,normalizer):
    """Official URL identity + matching hidden IDs + unique business-name cell."""
    u=urlsplit(url);q=parse_qs(u.query,keep_blank_values=True)
    if u.scheme!='https' or u.netloc!='global.at.or.kr' or u.path!='/front/bizReq/brView.do':return None
    identity={}
    for key in ('proj_id','proj_detail_id'):
        values=q.get(key,[]);nodes=soup.select('input[name="'+key+'"]')
        if len(values)!=1 or not re.fullmatch(r'\d{1,9}',values[0]) or len(nodes)!=1 or nodes[0].get('value')!=values[0]:return None
        identity[key]=values[0]
    names=[]
    for th in soup.select('article.contentGroup th'):
        if normalizer(th.get_text(' ',strip=True)) not in ('사업명','사업명필수'):continue
        td=th.find_next_sibling('td');name=td.get_text(' ',strip=True) if td else ''
        if not 5<=len(name)<=180 or re.search(r'@|[<>\x00-\x1f]|\d{2,3}-\d{3,4}-\d{4}',name):return None
        names.append(name)
    if len(set(names))!=1:return None
    name=names[0];truncated=bool(re.search(r'(?:\.\.\.|…)\s*$',stored))
    wanted=normalizer(re.sub(r'(?:\.\.\.|…)\s*$','',stored) if truncated else stored)
    if not wanted or (truncated and len(wanted)<8):return None
    matches=normalizer(name).startswith(wanted) if truncated else normalizer(name)==wanted
    if not matches:return None
    return {'identity':identity,'title':name,'location':'공식 사업명 항목 및 proj_id/proj_detail_id 대조','truncated':truncated}


def recovered_title(soup,stored,url,normalizer):
    """Only a truncated aT name can be completed from its labelled business-name cell."""
    result=at_title_evidence(soup,stored,url,normalizer)
    return result['title'] if result and result['truncated'] else None

def restricted(text):
    return bool(re.search(r'(?:직접\s*링크|제목.{0,12}재게시|자동.{0,8}수집)\s*(?:를|을)?\s*금지',text))
