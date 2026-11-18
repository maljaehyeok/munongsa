"""Offline integration of private review batches; never approves or publishes."""
import argparse,copy,json,re
from collections import Counter
from pathlib import Path
from collect_national_candidates import identity
import support_eligibility
from support_recommendation_readiness import classify
from support_runtime.ingestion import atomic

ROOT=Path(__file__).resolve().parents[1]


def integrate(batches,inventory):
    existing={identity(n['original_url']) for n in inventory['notices']}
    titles={re.sub(r'\s+','',n['title']) for n in inventory['notices']}
    items={};excluded=[];duplicates=[];conflicts=set()
    for batch in batches:
        for original in batch['candidates']:
            item=copy.deepcopy(original);key=identity(item['official_url'])
            if item.get('publication')!='private' or item.get('recommendation_eligible') is not False:
                raise ValueError('private unapproved candidates required')
            support_eligibility.check_payload(item['eligibility_candidate'],{'original_url':item['official_url']})
            if key in existing:excluded.append(item['original_id']);continue
            if key in items:
                duplicates.append(item['original_id'])
                old=items[key]
                if any(old.get(k)!=item.get(k) for k in ('title','facts','eligibility_candidate')):
                    conflicts.add(key)
                continue
            item['unknown_fields']=list(item.get('unknown_fields',[]))
            if re.sub(r'\s+','',item['title']) in titles:
                item['unknown_fields'].append('possible_duplicate_requires_review')
            if re.search(r'연장|변경|정정|재공고|취소',item['title']):
                item['unknown_fields'].append('amended_notice_requires_version_review')
            item['unknown_fields']=sorted(set(item['unknown_fields']))
            items[key]=item
    ready=0
    for key,item in items.items():
        blocked=(key in conflicts or item.get('related_versions') or any(k in item['unknown_fields']
            for k in ('possible_duplicate_requires_review','amended_notice_requires_version_review')))
        release=item.get('basic_release_review',{})
        if release.get('approved') is True:raise ValueError('unexpected actual approval')
        if blocked or release.get('status')!='candidate':
            item['basic_release_review']={'status':'hold','approved':False,'allowed_fields':[],
                'requires_operator_approval':True,'reason':'duplicate_version_or_release_evidence_review'}
        else:ready+=1
        item['recommendation_readiness']=classify({'public':{'publication':'private',
            'eligibility':item['eligibility_candidate']}},{},lambda _:False,{})
        if key in conflicts:item['unknown_fields'].append('conflicting_batch_evidence')
    rows=list(items.values())
    summary={'input_count':sum(len(b['candidates']) for b in batches),
        'distinct_official_notice_ids':len(rows),'within_batch_duplicates':len(duplicates),
        'operating_id_duplicates':len(excluded),'operating_db_count':len(inventory['notices']),
        'public_count':len(inventory['public_feed']['notices']),
        'cross_source_duplicate_suspects':sum('possible_duplicate_requires_review' in n['unknown_fields'] for n in rows),
        'changed_notice_review':sum('amended_notice_requires_version_review' in n['unknown_fields'] for n in rows),
        'conflicting_batches':len(conflicts),'basic_approval_candidates':ready,'held':len(rows)-ready,
        'condition_evidence_candidates':sum(any(c['presence']=='specified' for c in n['eligibility_candidate']['conditions']) for n in rows),
        'actual_recommendation_eligible':0,'actual_approved':0,'actual_published':0,
        'readiness_categories':dict(Counter(n['recommendation_readiness']['category'] for n in rows)),
        'distinct_program_count':'unconfirmed_cross_source_and_round_relationships'}
    return {'schema':'national-integration-review-v1','summary':summary,'candidates':rows,
        'excluded_existing_ids':excluded,'repeated_input_ids':duplicates}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,action='append',required=True)
    p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if ROOT/'work' not in args.output.resolve().parents:p.error('private work output required')
    result=integrate([json.loads(f.read_text('utf8')) for f in args.batch],json.loads(args.inventory.read_text('utf8')))
    atomic(args.output,result);print(json.dumps(result['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
