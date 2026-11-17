"""Offline re-extraction of fixed private candidates, never collection or approval."""
import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
import support_eligibility
from support_runtime import core_facts,conditions,periods,enrichment
from support_recommendation_readiness import classify

ROOT=Path(__file__).resolve().parents[1]


def valid(fact):
    return isinstance(fact,dict) and fact.get('value') not in (None,'','unknown',[],{})


def counts(items):
    result={k:sum(valid(n.get('facts',{}).get(k)) for n in items) for k in (
        'geographic_scope','implementing_institution','target_description','support_description','application_method')}
    result['application_period']=sum(isinstance(n.get('facts',{}).get('application_deadline',{}).get('value'),dict)
        and bool(n['facts']['application_deadline']['value'].get('date')) for n in items)
    result['condition_evidence_notices']=sum(any(c['presence']=='specified' for c in n['eligibility_candidate']['conditions']) for n in items)
    return result


def reprocess(baseline,cache_dir):
    if any(n.get('publication')!='private' or n.get('recommendation_eligible') is not False for n in baseline['candidates']):
        raise ValueError('private unapproved candidates only')
    result=copy.deepcopy(baseline);failures=[]
    for n in result['candidates']:
        url=n['official_url'];path=cache_dir/(hashlib.sha256(url.encode()).hexdigest()[:16]+'-lines.json')
        if path.exists():
            cache=json.loads(path.read_text('utf8'))
            if cache['official_url']!=url:raise ValueError('cache identity mismatch')
            lines=cache['lines'];source='normalized_official_body'
        else:
            lines=list(dict.fromkeys(f['evidence']['quote'] for f in n['facts'].values()
                if isinstance(f,dict) and f.get('evidence',{}).get('url')==url and f['evidence'].get('quote')))
            source='previous_evidence_fragments' if lines else 'listing_only' if n.get('listing_facts') else 'no_reusable_detail_evidence'
        n['extraction_input']=source
        if not lines:continue
        additions=enrichment.extra_facts(lines,url)
        n['reference_fact_history']={k:copy.deepcopy(n['facts'][k]) for k in (
            'application_start','application_deadline') if k in n['facts']}
        n['facts'].update(additions)
        n['implementing_institution']=n['facts'].get('implementing_institution')
        n['unknown_fields']=[k for k in n.get('unknown_fields',[]) if not valid(n['facts'].get(k))]
        date_lines=core_facts.period_input(lines)
        if date_lines and path.exists():
            parsed=periods.extract(date_lines,url)
            if parsed.get('period'):
                pairs=[('application_start','start'),('application_deadline','end')]
                conflicts=[]
                for key,part in pairs:
                    old=n['reference_fact_history'].get(key,{}).get('value');new=parsed['period'].get(part)
                    if isinstance(old,dict) and old.get('date') and new and old['date']!=new.get('date'):conflicts.append(key)
                if conflicts and not parsed['period'].get('extension'):
                    n['new_application_period_candidate']=parsed['period']
                    n['recruitment']={'status':'unknown','reason':'기존 신청기간과 새 근거가 달라 재검토 필요'}
                else:
                    for key,part in pairs:
                        if parsed['period'].get(part):n['facts'][key]={'value':parsed['period'][part],'evidence':parsed['period']['evidence']}
                    n['recruitment']=periods.assess(n['facts'],parsed,checked_at=cache['checked_at'])
            elif parsed.get('warnings'):
                n['recruitment']={'status':'unknown','reason':'새 근거의 신청기간 충돌·형식 재검토 필요'}
            n['source_cache_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        payload=conditions.payload_for(n['facts'],{})
        for c in payload['conditions']:c.pop('status',None)
        try:support_eligibility.check_payload(payload,{'original_url':url})
        except Exception:
            failures.append(n['original_id']);n['condition_schema_valid']=False;continue
        n['condition_schema_valid']=True
        n['eligibility_candidate']=payload
    for n in result['candidates']:
        document={'public':{'publication':n['publication'],'eligibility':n['eligibility_candidate']},'record':{'fields':{}}}
        n['recommendation_readiness']=classify(document,{},lambda _:False,{})
        n['condition_review_ready']=n.get('condition_schema_valid',False) and any(c['presence']=='specified' for c in n['eligibility_candidate']['conditions'])
        n['recommendation_eligible']=False
    result['core_extraction_summary']={'before':counts(baseline['candidates']),'after':counts(result['candidates']),
        'input_types':dict(Counter(n['extraction_input'] for n in result['candidates'])),
        'schema_failures':failures,'actual_recommendation_available':0,
        'requires_condition_review':sum(n['condition_review_ready'] for n in result['candidates']),
        'actual_categories':dict(Counter(n['recommendation_readiness']['category'] for n in result['candidates'])),
        'approved':0,'published':0}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--cache-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if ROOT/'work' not in args.output.resolve().parents:p.error('private work/ output required')
    data=json.loads(args.baseline.read_text('utf8'));result=reprocess(data,args.cache_dir)
    from support_runtime.ingestion import atomic
    atomic(args.output,result);print(json.dumps(result['core_extraction_summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
