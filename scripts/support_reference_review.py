"""Private review queue and explicit human approval of official notice guidance.

Never collects, approves recommendations, publishes a web feed or changes scheduling.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
from contextlib import closing

import support_monitor as monitor
import support_eligibility as eligibility
import export_support_public as public
from support_runtime import periods,ingestion

SCHEMA='munongsa-reference-decision-v1'


def review_fingerprint(record):
    keys=('notice_id','content_hash','title','original_url','published_at','institution','publication',
          'verification_status','reviewed_at','structured_conditions')
    return monitor.digest(monitor.packed({k:record.get(k) for k in keys}))


def db_record(db,notice_id):
    record=monitor.notice_record(db,notice_id)
    record['institution']=db.execute('SELECT institution FROM monitor_sources WHERE source_id=?',(record['source_id'],)).fetchone()[0]
    record['structured_conditions']=eligibility.show(db,notice_id)
    return record


def classify(record):
    title=record['title']
    if re.search(r'자문단|연구 참여자|효과검증|선정결과|축제|박람회',title):category='general_notice'
    elif re.search(r'교육|연수|수강',title):category='training'
    elif re.search(r'지원사업|시범사업|지원\s*사업|육성자금|임대농장|정착금|대출|기술창업|면세유|산업기능요원',title):category='support_candidate'
    else:category='needs_review'
    facts=record.get('facts',{})
    period=record.get('period_assessment',{}).get('status','unknown')
    return {'notice_id':record['notice_id'],'title':title,'institution':record['institution'],
            'url':record['original_url'],'published_at':record.get('published_at'),'category':category,
            'period':period,'fact_fields':sorted(facts),'publication':record.get('publication','review'),
            'remaining_checks':['official basic facts and support-notice type',
                                'permitted public-use scope and evidence',
                                'explicit human reference approval'],
            'basis':'title and stored extraction only; official verification/public rights still required',
            'review_priority':'archive' if period=='closed' else 'candidate' if category=='support_candidate' and facts else 'check'}


def draft(record):
    public.checked_url(record['original_url'])
    dates={}
    for field,key in (('application_start','start'),('application_deadline','end')):
        part=record.get('facts',{}).get(field,{})
        if isinstance(part.get('value'),dict) and part['value'].get('date'):
            dates[key]={'date':part['value']['date'],'evidence':copy.deepcopy(part.get('evidence',{}))}
            if part['value'].get('time') not in (None,'unknown'):
                dates[key].update(time=part['value']['time'],timezone=part['value'].get('timezone'))
    return {'schema_version':SCHEMA,'notice_id':record['notice_id'],'expected_fingerprint':review_fingerprint(record),
            'title':record['title'],'url':record['original_url'],
            'basics_confirmed':False,'support_notice_confirmed':False,'public_use_confirmed':False,
            'notice_evidence':{'url':record['original_url'],'location':''},
            'confirmed_fields':{},'reference_dates_confirmed':False,'reference_dates':dates,
            'release_verified_conditions':False,
            'rights':{'public_display':'unconfirmed','evidence_url':'','checked_at':'','scope_note':''},
            'extracted_candidates':copy.deepcopy(record.get('facts',{})),
            'warning':'Draft only. Extracted fields and date suggestions are unverified. No publication or recommendation approval.'}


def prepare(db,plan,rights,reviewer,reason,now=None):
    now=periods.as_of(now)
    monitor.require_actor(reviewer,reason)
    if plan.get('schema_version')!=SCHEMA or any(plan.get(k) is not True for k in
            ('basics_confirmed','support_notice_confirmed','public_use_confirmed')):
        raise monitor.MonitorError('Basic facts, support notice and public use must each be explicitly confirmed.')
    before=db_record(db,plan['notice_id'])
    if before['publication'] in ('approved','approved_reference'):
        raise monitor.MonitorError('Already approved; use the existing review/history commands for revisions.')
    if review_fingerprint(before)!=plan.get('expected_fingerprint'):
        raise monitor.MonitorError('Notice or review/condition version changed; prepare a new decision.')
    evidence=plan.get('notice_evidence',{})
    public.checked_url(evidence.get('url',''))
    if not evidence.get('location','').strip():raise monitor.MonitorError('Checked official evidence location required.')
    fields=plan.get('confirmed_fields',{})
    if set(fields)-{'target','region','support'}:raise monitor.MonitorError('Unsupported confirmed field.')
    grant=copy.deepcopy(plan.get('rights',{}))
    if not grant.get('scope_note','').strip() or public.rights_for({before['notice_id']:grant},before['notice_id'],now) is None:
        raise monitor.MonitorError('Checked public-use evidence, date and permitted scope required.')
    grant['notice_content_hash']=before['content_hash']
    if plan.get('reference_dates_confirmed') is True:
        grant.update(reference_dates_verified=True,reference_dates=copy.deepcopy(plan.get('reference_dates',{})))
        if not public.reference_dates(grant,before):raise monitor.MonitorError('Confirmed dates are empty.')
    else:
        grant.pop('reference_dates_verified',None);grant.pop('reference_dates',None)
    if plan.get('release_verified_conditions') is True:
        revision=before['structured_conditions']
        if 'payload' not in revision or revision.get('needs_review'):raise monitor.MonitorError('Current condition revision required.')
        grant['eligibility_revision_id']=revision['revision_id']
    else:grant.pop('eligibility_revision_id',None)
    updated=copy.deepcopy(rights);updated[before['notice_id']]=grant
    # Reuse the existing rule enforcement on an isolated DB before any real write.
    memory=sqlite3.connect(':memory:');memory.row_factory=sqlite3.Row
    try:
        db.backup(memory)
        reviewed=monitor.review_notice(memory,before['notice_id'],reviewer,reason,verification_status='verified',
            freshness='current',notice_basics_verified=True,application_status='unknown',conditions_verified=False,
            evidence_url=evidence['url'],evidence_location=evidence['location'],now=now,**fields)
        approved=monitor.publish_notice(memory,before['notice_id'],'approved_reference',reviewer,reason,now=now)
        feed,stats=public.export(memory,updated,now)
        item=next((n for n in feed['notices'] if n['id']==before['notice_id']),None)
        if item is None or item['recommendation_eligible']:raise monitor.MonitorError('Reference export validation failed.')
        return before,reviewed,approved,updated,feed,stats
    finally:memory.close()


def apply(state,plan,rights_path,reviewer,reason,confirmed=False,now=None):
    if confirmed is not True:raise monitor.MonitorError('Explicit human reference approval required.')
    state=Path(state).resolve();rights_path=Path(rights_path).resolve()
    if rights_path!=state/'publication-rights.json':raise monitor.MonitorError('Use publication-rights.json in the private state directory.')
    with ingestion.lock(state/'run.lock'):
        rights=json.loads(rights_path.read_text('utf-8-sig')) if rights_path.exists() else {}
        with closing(monitor.connect(state,readonly=True)) as ro:
            before,reviewed,approved,updated,feed,stats=prepare(ro,plan,rights,reviewer,reason,now)
            backup=state/'backups'/('reference-approval-'+uuid.uuid4().hex+'.sqlite3');backup.parent.mkdir(exist_ok=True)
            with closing(sqlite3.connect(backup)) as copy_db:
                ro.backup(copy_db)
                if copy_db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise monitor.MonitorError('Backup integrity check failed.')
            backup.chmod(0o600)
        if rights_path.exists():
            ingestion.atomic(state/'backups'/('rights-before-'+uuid.uuid4().hex+'.json'),rights)
        with closing(monitor.connect(state,require_existing=True)) as db:
            with db:
                db.execute('BEGIN IMMEDIATE')
                if review_fingerprint(db_record(db,plan['notice_id']))!=review_fingerprint(before):
                    raise monitor.MonitorError('Notice changed during review; no approval applied.')
                monitor.save_review(db,before,reviewed,'review',reviewer,reason)
                monitor.save_review(db,reviewed,approved,'publication',reviewer,reason)
                # A manifest alone never grants publication; DB rollback still fails closed.
                ingestion.atomic(rights_path,updated)
        return {'notice_id':plan['notice_id'],'publication':'approved_reference','public_feed_written':False,
                'recommendation_eligible':False,'backup':str(backup)}


def private_output(path,data):
    path=Path(path).resolve();root=(monitor.ROOT/'work').resolve()
    if root not in path.parents or path.suffix!='.json' or path.exists():raise monitor.MonitorError('Use a new .json path under work/.')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:json.dump(data,stream,ensure_ascii=False,indent=2)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('queue','draft'):
        p=sub.add_parser(name);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
        if name=='draft':p.add_argument('--notice-id',required=True)
    for name in ('preview','approve-reference'):
        p=sub.add_parser(name);p.add_argument('--state-dir',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
        p.add_argument('--rights-file',type=Path,required=True);p.add_argument('--reviewer',required=True);p.add_argument('--reason',required=True)
        if name=='preview':p.add_argument('--output',type=Path,required=True)
        else:p.add_argument('--confirm-human-approval',action='store_true')
    args=parser.parse_args()
    try:
        if args.command in ('queue','draft'):
            snapshot=json.loads(args.snapshot.read_text('utf-8-sig'));records=snapshot['notices']
            data={'candidates':[classify(n) for n in records]} if args.command=='queue' else draft(next(n for n in records if n['notice_id']==args.notice_id))
            private_output(args.output,data);result={'saved':str(args.output),'db_changed':False}
        else:
            plan=json.loads(args.plan.read_text('utf-8-sig'))
            if args.command=='preview':
                rights=json.loads(args.rights_file.read_text('utf-8-sig')) if args.rights_file.exists() else {}
                with closing(monitor.connect(args.state_dir,readonly=True)) as db:
                    before,reviewed,approved,updated,feed,stats=prepare(db,plan,rights,args.reviewer,args.reason)
                private_output(args.output,feed);result={**stats,'db_changed':False,'public_feed_written':False}
            else:result=apply(args.state_dir,plan,args.rights_file,args.reviewer,args.reason,args.confirm_human_approval)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,TypeError,KeyError,StopIteration,OSError,monitor.MonitorError):
        print(json.dumps({'status':'rejected','reason':'Check explicit confirmations, evidence, rights, notice version and private paths. No website publication performed.'}));return 1

if __name__=='__main__':raise SystemExit(main())
