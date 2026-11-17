"""Bounded, hash-approved additions to seven existing descriptions. Default: read only."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from datetime import datetime, timezone
import review_support_details as review

SCHEMA='munongsa-support-detail-supplement-plan-v1'
TARGET_IDS=frozenset({
 'NOTICE-2951dab410e331f8df8dbb2b','NOTICE-026c7844e52e07f8aa3509db',
 'NOTICE-31197e7203679cc2a0fcb7c2','NOTICE-47e06379f45d716182ed51ce',
 'NOTICE-4e14955d4ebb5d240d9a90fc','NOTICE-b553093685243b84adc24bdd',
 'NOTICE-e0bf3cd8d40028f70d140b41'})

def encoded(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf8')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def version(value):return sha(encoded(value))
def content_version(doc):return version({k:v for k,v in doc.items() if k!='detail_supplement_history'})

def prepare(raw,plan,plan_sha):
    if plan.get('schema')!=SCHEMA or plan.get('replacements')!=[]:raise ValueError('supplement_only_no_replacement')
    rows=plan.get('records',[])
    if len(rows)!=7 or {r['basis']['id'] for r in rows}!=TARGET_IDS:raise ValueError('exact_seven_targets_required')
    review.validate({'schema':'munongsa-support-details-plan-v1','records':rows})
    doc=json.loads(raw)
    if doc.get('schema')!='munongsa-support-details-v1' or doc.get('preview') is not False:raise ValueError('approved_asset_required')
    existing=doc.get('records',[])
    if len(existing)!=19 or len({r['basis']['id'] for r in existing})!=19:raise ValueError('nineteen_unique_existing_records_required')
    if any(r.get('approval',{}).get('state')!='approved' for r in existing):raise ValueError('existing_approval_missing')
    expected=plan.get('base_record_versions',{})
    if set(expected)!={r['basis']['id'] for r in existing} or any(expected[r['basis']['id']]!=version(r) for r in existing):
        raise ValueError('existing_record_version_changed')
    applied=[x for x in doc.get('detail_supplement_history',[]) if x.get('plan_sha256')==plan_sha]
    if applied:
        if len(applied)!=1 or applied[0].get('result_content_sha256')!=content_version(doc):raise ValueError('applied_state_changed')
        supplements=[s for s in doc.get('detail_supplements',[]) if s.get('plan_sha256')==plan_sha]
        if len(supplements)!=7 or {s['basis']['id'] for s in supplements}!=TARGET_IDS:raise ValueError('applied_supplements_missing')
        return doc,[],True
    if sha(raw)!=plan.get('base_asset_sha256'):raise ValueError('original_file_hash_mismatch')
    occupied={s['basis']['id'] for s in doc.get('detail_supplements',[])}
    if occupied&TARGET_IDS:raise ValueError('supplement_already_exists_other_plan')
    by_id={r['basis']['id']:r for r in existing};changes=[]
    for row in rows:
        old=by_id[row['basis']['id']]
        if row['basis']!=old['basis']:raise ValueError('notice_basis_changed')
        if row['rights'].get('display_scope')!=review.FACT_SCOPE:raise ValueError('field_scope_required')
        if set(row['fields'])&set(old['fields']):raise ValueError('existing_field_replacement_forbidden')
        changes.append({'id':row['basis']['id'],'preserved_fields':sorted(old['fields']),'added_fields':sorted(row['fields'])})
    return doc,changes,False

def apply_file(asset,plan_raw,approved_sha,reviewer,reference,backup_dir):
    """Called only after a real approval; tests use independent synthetic files."""
    digest=sha(plan_raw)
    if approved_sha!=digest or not reviewer.strip() or not reference.strip():raise ValueError('explicit_exact_approval_required')
    if asset.is_symlink():raise ValueError('symlink_asset_forbidden')
    raw=asset.read_bytes();plan=json.loads(plan_raw);doc,changes,done=prepare(raw,plan,digest)
    if done:return {'status':'already_applied','plan_sha256':digest,'changed':False}
    original_stat=asset.stat();by_id={r['basis']['id']:r for r in doc['records']}
    addition=review.build({'schema':'munongsa-support-details-plan-v1','records':plan['records']},reviewer,reference,approved=True)
    result=copy.deepcopy(doc)
    supplements=copy.deepcopy(result.get('detail_supplements',[]))
    for row in addition['records']:
        row['base_record']=copy.deepcopy(by_id[row['basis']['id']])
        row['base_record_sha256']=version(row['base_record'])
        row['plan_sha256']=digest
        supplements.append(row)
    result['detail_supplements']=supplements
    event={'plan_sha256':digest,'reviewer':reviewer,'reference':reference,
           'checked_at':datetime.now(timezone.utc).isoformat(),'before_file_sha256':sha(raw),
           'changes':changes,'result_content_sha256':content_version(result)}
    result['detail_supplement_history']=copy.deepcopy(doc.get('detail_supplement_history',[]))+[event]
    output=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    backup_dir.mkdir(parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix='supplement-'+digest[:12]+'-',dir=backup_dir))
    os.chmod(backup,0o700)
    (backup/'original.json').write_bytes(raw)
    if sha((backup/'original.json').read_bytes())!=sha(raw):raise ValueError('backup_verification_failed')
    (backup/'audit.json').write_text(json.dumps({**event,'after_file_sha256':sha(output)},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=asset.parent,prefix='.detail-supplement-',delete=False) as f:
            temp=Path(f.name);f.write(output);f.flush();os.fsync(f.fileno())
        os.chmod(temp,stat.S_IMODE(original_stat.st_mode))
        if hasattr(os,'chown'):os.chown(temp,original_stat.st_uid,original_stat.st_gid)
        if sha(asset.read_bytes())!=sha(raw):raise ValueError('asset_changed_before_replace')
        os.replace(temp,asset);temp=None
    finally:
        if temp is not None:temp.unlink(missing_ok=True)
    return {'status':'applied','plan_sha256':digest,'changed':True,'added_fields':sum(len(c['added_fields']) for c in changes),
            'before_sha256':sha(raw),'after_sha256':sha(output),'backup':str(backup)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--asset',type=Path,required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--approved-plan-sha256')
    p.add_argument('--reviewer');p.add_argument('--approval-reference');p.add_argument('--backup-dir',type=Path)
    a=p.parse_args();raw=a.plan.read_bytes();digest=sha(raw)
    if a.apply:
        if not (a.approved_plan_sha256 and a.reviewer and a.approval_reference and a.backup_dir):p.error('explicit approval and private backup directory required')
        result=apply_file(a.asset,raw,a.approved_plan_sha256,a.reviewer,a.approval_reference,a.backup_dir)
    else:
        _,changes,done=prepare(a.asset.read_bytes(),json.loads(raw),digest)
        result={'status':'already_applied' if done else 'review_only','plan_sha256':digest,'changes':changes,'changed':False}
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
