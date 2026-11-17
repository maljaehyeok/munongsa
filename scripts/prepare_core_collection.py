"""Private national collection review using authenticated results already fetched.

No API credentials, DB writes, approval, GPT calls or public export. Optional
detail requests use the existing robots/rate/size/host constrained transport.
"""
import argparse,copy,json
from pathlib import Path
from collections import Counter
import support_official_apis as api
from collect_national_candidates import prepare
from support_runtime import boards,discovery,ingestion,periods,bizinfo_detail,source_quality

ROOT=Path(__file__).resolve().parents[1]


def portal_release_review(result,portal_rows,details):
    """Operator review candidates under the EXISTING portal metadata policy only.

    Never licenses transformed summaries/qualifications or produces approvals.
    """
    import support_guidance as guidance
    origins={}
    conflicting=set()
    for row in portal_rows:
        key=source_quality.notice_key(row['original_url'])
        if key in origins and origins[key]!=row:conflicting.add(key)
        origins[key]=row
    checked={e['metadata']['original_id'] for e in details if e.get('detail_fetched')
        and e.get('status')!='failed' and not e.get('fact_conflicts')}
    count=0
    for item in result['candidates']:
        key=source_quality.notice_key(item['official_url']);origin=origins.get(key)
        ready=(result['summary']['operating_private_db_compared'] and key not in conflicting
            and origin and origin['title']==item['title'] and item['original_id'] in checked
            and not item.get('related_versions')
            and not any(k in item['unknown_fields'] for k in (
                'possible_duplicate_requires_review','amended_notice_requires_version_review')))
        if ready:
            guidance.canonical(origin['original_url']);guidance.safe_title(origin['title'])
            item['basic_release_review']={'status':'candidate','approved':False,
                'requires_operator_approval':True,'allowed_fields':list(guidance.POLICY['fields']),
                'source_policy':dict(guidance.POLICY),'reason':'unchanged_portal_metadata_only',
                'excludes':['summary','eligibility','amount','attachments','full_text']}
            count+=1
    result['summary'].update(basic_approval_candidates=count,release_held=len(result['candidates'])-count)
    return result


def read_rows(document):
    if 'analyses' in document:
        return [dict(e['metadata'],description=e.get('facts',{}).get('support_description',{}).get('value',''))
            for e in document['analyses']]
    if 'rows' in document:return document['rows']
    result=[]
    for region,group in document.items():
        if region in api.REGION_TAGS:
            result.extend(dict(r,list_region=region,region_basis='official_api_discovery_tag_only')
                for r in group.get('rows',[]))
    return result


def build(documents,inventory,previous=(),limit=12,detail_fetcher=None,now=None):
    now=now or periods.as_of();raw=[r for d in documents for r in read_rows(d)]
    merged,duplicates,conflicts=api.merge(raw)
    selected=[r for r in merged if r['original_id'] not in conflicts and api.agricultural(r)
        and boards.classify(r)!='excluded']
    entries=[api.entry(r) for r in selected]
    plan=source_quality.detail_plan(entries,[r['original_url'] for r in inventory['notices']],previous,limit)
    group={'kind':'bizinfo','analyses':[],'errors':[],'list_count':len(merged),
        'candidate_count':len(entries),'state':'로컬 검토 자료'}
    for entry in plan['entries']:
        if detail_fetcher:
            try:entry=bizinfo_detail.enrich(entry,detail_fetcher(entry['metadata']['original_url']),now)
            except Exception as error:
                entry=copy.deepcopy(entry);entry['detail_error']=boards.error_name(error)
                entry.setdefault('unknown_fields',[]).append('공식 상세 접근 미확인')
                group['errors'].append({'id':entry['metadata']['original_id'],'error':boards.error_name(error)})
        group['analyses'].append(entry)
    result=prepare([group],inventory['public_feed'],inventory)
    for item in result['candidates']:
        item['collection_quality']=source_quality.quality({'metadata':{'original_url':item['official_url']},'facts':item['facts']})
        item['basic_release_review']={'approved':False,'status':'hold',
            'reason':'source_display_rights_and_operator_approval_required',
            'allowed_fields':[],'requires_operator_approval':True}
    result['acquisition']={'raw_records':len(raw),'unique_api_records':len(merged),
        'repeated_api_records':len(duplicates),'conflicting_api_ids':conflicts,
        'agricultural_candidates':len(entries),'selection':{k:v for k,v in plan.items() if k!='entries'},
        'quality':source_quality.source_report(group),'actual_approved':0,'actual_published':0}
    return result,group


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,action='append',required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--previous',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--detail-limit',type=int,default=12)
    parser.add_argument('--fetch-details',action='store_true')
    parser.add_argument('--portal-result',type=Path,help='Actual authorized portal response for metadata policy review')
    parser.add_argument('--reuse-details',type=Path,help='Previous private detail group from this pipeline; offline only')
    parser.add_argument('--cached-detail',type=Path,help='One previous sanitized article fixture; no repeat request')
    parser.add_argument('--cached-detail-url',help='Exact official URL belonging to the cached article')
    args=parser.parse_args();output=args.output.resolve()
    if ROOT/'work' not in output.parents:parser.error('output must stay in private work/')
    if bool(args.cached_detail)!=bool(args.cached_detail_url):parser.error('cached detail requires its exact URL')
    inventory=json.loads(args.inventory.read_text('utf8'))
    previous=[r['official_url'] for r in json.loads(args.previous.read_text('utf8'))['candidates']] if args.previous else []
    documents=[json.loads(p.read_text('utf8')) for p in args.input]
    if args.reuse_details and args.fetch_details:parser.error('reuse existing details without network requests')
    transport=None;fetcher=None
    if args.fetch_details:
        source=next(s for s in json.loads((ROOT/'config/collector_sources.json').read_text('utf8'))['sources'] if s['kind']=='bizinfo')
        transport=discovery.Transport(dict(source,official_hosts=['www.bizinfo.go.kr']))
        transport.get('https://www.bizinfo.go.kr/robots.txt',True)
        cached=args.cached_detail.read_bytes() if args.cached_detail else None
        def fetcher(url):
            if cached and source_quality.notice_key(url)==source_quality.notice_key(args.cached_detail_url):return cached
            return transport.get(url)
    result,group=build(documents,inventory,previous,args.detail_limit,fetcher)
    if args.reuse_details:
        acquisition=result['acquisition']
        group=json.loads(args.reuse_details.read_text('utf8'))
        result=prepare([group],inventory['public_feed'],inventory)
        for item in result['candidates']:
            item['collection_quality']=source_quality.quality({'metadata':{'original_url':item['official_url']},'facts':item['facts']})
            item['basic_release_review']={'approved':False,'status':'hold','allowed_fields':[],
                'requires_operator_approval':True,'reason':'licensed_metadata_or_version_review_required'}
        result['acquisition']=dict(acquisition,reused_detail_count=len(group['analyses']),
            quality=source_quality.source_report(group))
    if args.portal_result:
        portal=json.loads(args.portal_result.read_text('utf8'))
        portal_release_review(result,portal.get('rows',[]),group['analyses'])
    result['acquisition']['public_detail_requests']=transport.count if transport else 0
    ingestion.atomic(output,result);ingestion.atomic(output.with_name(output.stem+'-group.json'),group)
    print(json.dumps({'summary':result['summary'],'acquisition':result['acquisition']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
