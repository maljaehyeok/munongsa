"""Read-only HTTP projection of a prefiltered approval artifact, bound to live feed."""
import json,os
from pathlib import Path
import rag_catalogue,rag_search

def payload(kind):
    if kind not in ('details','review'):raise ValueError('projection_kind')
    root=Path(__file__).resolve().parents[1]
    feed_path=Path('/run/munongsa-rag-public/support-public.json') if os.environ.get('MUNONGSA_RAG_SYNC_DIR') else root/'data/support-public.json'
    feed=json.loads(feed_path.read_text('utf8'))
    notices={n['id']:n for n in rag_catalogue.records(feed)}
    if kind=='review':
        # Approval-filtered metadata only; internal source data is never read here.
        source=json.loads((root/'data/support-review-public.json').read_text('utf8'))
        return source
    source=json.loads((root/'data/support-details-public.json').read_text('utf8'))
    def permitted(r):
        n=notices.get(r.get('basis',{}).get('id'))
        if not n or r['basis']!=rag_search.basis(n):return False
        return n.get('publication') in ('approved','approved_reference') and n.get('verification_status')=='verified' or n.get('publication')=='official_guidance' and n.get('verification_status')=='basics_only' and n.get('recommendation_eligible') is False and n.get('eligibility_complete') is False and r.get('rights',{}).get('display_scope')=='reviewed_facts_v1'
    records=[r for r in source['records'] if permitted(r)]
    links=[r for r in source.get('link_reviews',[]) if r['basis'].get('id') in notices and r['basis']=={k:notices[r['basis']['id']].get(k) for k in ('id','title','url','source_id')}]
    return {'schema':'munongsa-support-details-v1','preview':False,'records':records,'link_reviews':links,'withheld_ids':[i for i in source.get('withheld_ids',[]) if i in notices]}
