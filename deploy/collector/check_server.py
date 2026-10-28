"""Read-only inventory; explicit options permit isolated preflight/minimal venv setup."""
import argparse
import json
import subprocess
from pathlib import Path


def failure_kind(stderr):
    text=stderr.lower()
    for fragments, code in (
        (('identity file', 'permission denied'), 'key_file_access_denied'),
        (('unprotected private key',), 'key_permissions_rejected'),
        (('host key verification failed',), 'host_verification_failed'),
        (('permission denied (publickey',), 'ssh_authentication_failed'),
        (('connection timed out',), 'network_timeout'),
        (('could not read username',), 'github_authentication_unavailable'),
        (('terminal prompts disabled',), 'github_authentication_unavailable')):
        if all(part in text for part in fragments):return code
    return 'unclassified_failure'


REMOTE = r'''
import json, shutil, subprocess, urllib.request, os, stat
from pathlib import Path
root=Path('/home/ubuntu/munongsa')
def run(args):
    return subprocess.check_output(args,cwd=root,stderr=subprocess.PIPE,text=True,env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')).strip()
def inspect(kind,name):
    return json.loads(run(['sudo','-n','docker',kind,'inspect',name]))[0]
try:
    c=inspect('container','munongsa');i=inspect('image',c['Image'])
    def env(obj):return dict(v.split('=',1) for v in obj['Config'].get('Env',[]) or [])
    old=[]
    for name in run(['sudo','-n','docker','ps','-a','--format','{{.Names}}']).splitlines():
        if name.startswith(('munongsa-before-','munongsa-rollback-','munongsa-backup')):
            obj=inspect('container',name)
            try:inspect('image',obj['Image']);available=True
            except Exception:available=False
            old.append({'name':name,'state':obj['State']['Status'],'image_available':available})
    mem={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1/',timeout=8) as response:status=response.status
    def unit_state(command):
        p=subprocess.run(['systemctl',command,'munongsa-collector.timer'],capture_output=True,text=True)
        return p.stdout.strip() or 'not-installed'
    files=[]
    for name in ('index.html','Dockerfile','data/support-public.json','data/support-review.json'):
        p=root/name
        files.append({'name':name,'exists':p.is_file(),'mode':oct(stat.S_IMODE(p.stat().st_mode)) if p.exists() else None})
    backup_root=Path('/home/ubuntu/munongsa-deploy-backups')
    backups=[]
    if backup_root.is_dir():
        for p in sorted(backup_root.iterdir())[-10:]:
            if p.is_dir():backups.append({'name':p.name,'mode':oct(stat.S_IMODE(p.stat().st_mode))})
    print(json.dumps({'status':'checked','git_head':run(['git','rev-parse','HEAD']),
      'branch':run(['git','branch','--show-current']),'working_tree_clean':not run(['git','status','--porcelain']),
      'container':{'name':'munongsa','id':c['Id'],'image':c['Image'],'state':c['State']['Status'],
        'ports':c['HostConfig']['PortBindings'],'restart':c['HostConfig']['RestartPolicy']['Name'],
        'mount_count':len(c['Mounts']),'environment_matches_image_defaults':env(c)==env(i)},
      'rollback_containers':old,'public_files':files,'backup_root_exists':backup_root.is_dir(),'backup_directories':backups,
      'http_status':status,'disk_free_mb':shutil.disk_usage('/').free//1048576,
      'memory_available_mb':mem.get('MemAvailable',0)//1024,
      'private_state_exists':Path('/var/lib/munongsa/monitor.sqlite3').exists(),
      'timer_enabled':unit_state('is-enabled'),'timer_active':unit_state('is-active')},indent=2))
except Exception as error:
    print(json.dumps({'status':'check_failed','error':type(error).__name__}));raise SystemExit(1)
'''

# Explicit isolated validation only. The default --ssh inventory stays read-only.
PREFLIGHT = r'''
import base64, hashlib, io, os, re, sqlite3, tarfile, tempfile, time, uuid, zipfile
from contextlib import closing

class PreflightError(Exception):
    def __init__(self,code):self.code=code

def preflight(snapshot, encoded):
    stage='initial_state';cid=None;original=None;homepage=None;token=uuid.uuid4().hex
    result={'status':'failed','operating_service_unchanged':None,'timer_enabled_by_check':False}
    def command(args, timeout=90):
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,
                         env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PIP_NO_CACHE_DIR='1'))
        if p.returncode:
            text=(p.stdout+p.stderr).decode('utf8','replace').lower()
            code='isolated_command_failed'
            for word,label in [('ensurepip','python3_venv_package_required'),('no space left','disk_full'),
                               ('cannot allocate memory','insufficient_memory'),('not allowed to execute','sudo_permission_required'),
                               ('could not fetch url','dependency_index_unavailable')]:
                if word in text:code=label;break
            raise PreflightError(code)
        return p.stdout
    def get_container(name):return json.loads(command(['sudo','-n','docker','container','inspect',name]))[0]
    def http(path,port=80):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:'+str(port)+path,timeout=5) as r:
            assert r.status==200
            data=r.read(4*1024*1024+1);assert len(data)<=4*1024*1024
            return data
    try:
        assert snapshot['status']=='checked' and snapshot['working_tree_clean'] and snapshot['branch']=='main'
        assert snapshot['git_head']=='9349a3d5be057cf0e634aa9586f1dfdab69cb980'
        assert snapshot['disk_free_mb']>=700 and snapshot['memory_available_mb']>=180
        assert not snapshot['private_state_exists'], 'Initial rollout requires separate review of any existing DB'
        assert snapshot['timer_active']!='active'
        command(['sudo','-n','true'])
        for name in ('/var/lib/munongsa','/var/lib/munongsa-public'):
            path=Path(name);assert not path.is_symlink()
            if path.exists():
                assert path.is_dir() and path.stat().st_uid==os.getuid()
                if name=='/var/lib/munongsa':assert not list(path.iterdir())
        result['persistent_paths']='initial empty state; ownership/modes will be installed only after approval'
        original=get_container('munongsa');assert original['State']['Running']
        assert not original['Mounts'] and snapshot['container']['environment_matches_image_defaults']
        homepage=http('/');existing_feed=json.loads(http('/data/support-public.json'))
        assert existing_feed['schema_version']=='munongsa-support-public-v1'
        assert isinstance(existing_feed['notices'],list) and not existing_feed['notices'], 'Existing public approvals require migration review'
        result['existing_public_notices']=len(existing_feed['notices'])
        with tempfile.TemporaryDirectory(prefix='munongsa-preflight-') as temporary:
            work=Path(temporary);os.chmod(work,0o700);release=work/'release';release.mkdir()
            stage='release_bundle'
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as archive:
                for entry in archive.infolist():
                    target=(release/entry.filename).resolve()
                    assert target.is_relative_to(release) and not entry.is_dir() and entry.file_size<2*1024*1024
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(entry))
            manifest={p.relative_to(release).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in release.rglob('*') if p.is_file()}
            assert len(manifest)==34
            result['release_file_count']=len(manifest)
            result['release_digest']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
            stage='python_venv'
            command(['python3','-m','venv',str(work/'venv')])
            python=str(work/'venv/bin/python')
            stage='python_dependencies'
            command([python,'-m','pip','install','--no-input','--only-binary=:all:','--retries','0','--timeout','15',
                     '--no-cache-dir','--disable-pip-version-check','-r',str(release/'deploy/collector/requirements.txt')])
            version=json.loads(command([python,'-B','-c','import json,sys,bs4;print(json.dumps({"python":sys.version.split()[0],"beautifulsoup4":bs4.__version__}))']))
            result['python']=version
            stage='isolated_sqlite'
            state=work/'private';public=work/'public'
            args=[python,'-B',str(release/'scripts/run_support_collection.py'),'--state-dir',str(state),'--public-dir',str(public),'--export-only']
            first=json.loads(command(args));assert first['exit_code']==0 and first['publication']['exported']==0
            second=json.loads(command(args));assert second['exit_code']==0
            database=state/'monitor.sqlite3';backups=list((state/'backups').glob('*.sqlite3'));assert backups
            restored=work/'restored.sqlite3';shutil.copyfile(backups[-1],restored)
            with closing(sqlite3.connect(restored.as_uri()+'?mode=ro',uri=True)) as db:
                assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                assert db.execute('SELECT COUNT(*) FROM discovered_notices').fetchone()[0]==0
            result['sqlite']={'initial_records':0,'restart_preserved':database.is_file(),'backup_restore':'ok',
                'private_mode':oct(stat.S_IMODE(state.stat().st_mode)),
                'database_mode':oct(stat.S_IMODE(database.stat().st_mode)),
                'same_filesystem_as_var_lib':database.stat().st_dev==Path('/var/lib').stat().st_dev}
            assert result['sqlite']['private_mode']=='0o700' and result['sqlite']['database_mode']=='0o600'
            stage='systemd_configuration'
            units=work/'units';units.mkdir()
            service=(release/'deploy/collector/munongsa-collector.service').read_text()
            service=service.replace('/home/ubuntu/munongsa/.venv-collector/bin/python',python).replace('/home/ubuntu/munongsa',str(release))
            service=service.replace('/var/lib/munongsa-public',str(public)).replace('/var/lib/munongsa',str(state))
            (units/'munongsa-collector.service').write_text(service)
            shutil.copyfile(release/'deploy/collector/munongsa-collector.timer',units/'munongsa-collector.timer')
            command(['systemd-analyze','verify',str(units/'munongsa-collector.service'),str(units/'munongsa-collector.timer')])
            command(['systemd-analyze','calendar','--iterations=1','*-*-* 07:00:00 Asia/Seoul'])
            result['systemd']='syntax and calendar checked; not installed or enabled'
            stage='website_backup_restore'
            raw=command(['sudo','-n','docker','cp','munongsa:/usr/share/nginx/html/.','-'])
            assert len(raw)<=16*1024*1024
            backup=work/'website-backup.tar';backup.write_bytes(raw);website=work/'website-restored';website.mkdir(mode=0o755)
            with tarfile.open(fileobj=io.BytesIO(backup.read_bytes())) as archive:
                for entry in archive.getmembers():
                    target=(website/entry.name).resolve();assert target.is_relative_to(website)
                    if entry.isdir():target.mkdir(parents=True,exist_ok=True,mode=0o755)
                    else:
                        assert entry.isfile() and entry.size<4*1024*1024
                        target.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
                        target.write_bytes(archive.extractfile(entry).read());target.chmod(0o644)
            assert (website/'index.html').read_bytes()==homepage
            cid=command(['sudo','-n','docker','run','--pull=never','-d','--name','munongsa-preflight-'+token,
                '--label','munongsa.preflight='+token,'--memory=128m','--memory-swap=128m','--cpus=0.25','--pids-limit=64',
                '-p','127.0.0.1::80','--mount','type=bind,src='+str(website)+',dst=/usr/share/nginx/html,readonly',
                '--mount','type=bind,src='+str(public)+',dst=/srv/munongsa-public,readonly',
                '--mount','type=bind,src='+str(release/'deploy/collector/nginx.conf')+',dst=/etc/nginx/conf.d/default.conf,readonly',
                original['Image']]).decode().strip()
            assert re.fullmatch('[0-9a-f]{64}',cid)
            test=get_container(cid);port=int(test['NetworkSettings']['Ports']['80/tcp'][0]['HostPort'])
            command(['sudo','-n','docker','exec',cid,'nginx','-t'])
            for attempt in range(12):
                try:
                    assert http('/',port)==homepage;break
                except (OSError,AssertionError):
                    if attempt==11:raise
                    time.sleep(.5)
            names=('smart-agriculture-catalog','crop-cultivation-records','support-programs','support-review','finance-products','equipment-catalog')
            for name in names:
                path='/data/'+name+'.json';data=http(path,port);json.loads(data)
                assert data==(website/path.lstrip('/')).read_bytes()
            assert json.loads(http('/data/support-public.json',port))['notices']==[]
            # Serve the proposed index from the same isolated restored snapshot.
            candidate=(release/'index.html').read_bytes();(website/'index.html').write_bytes(candidate)
            assert http('/',port)==candidate
            result['website']={'backup_restore':'ok','candidate_index':'ok','public_json_files_checked':7,'temporary_port_loopback_only':True}
            stage='operating_service_unchanged'
            current=get_container('munongsa')
            assert current['Id']==original['Id'] and current['State']['Running'] and http('/')==homepage
            assert not Path('/var/lib/munongsa/monitor.sqlite3').exists()
            result.update(status='passed',operating_service_unchanged=True)
            assert get_container(cid)['Config'].get('Labels',{}).get('munongsa.preflight')==token
            command(['sudo','-n','docker','rm','-f',cid]);cid=None
            result['isolated_container_removed']=True
    except Exception as error:
        result.update(status='failed',failed_stage=stage,error=type(error).__name__)
        if isinstance(error,PreflightError):result['detail_code']=error.code
    finally:
        if cid:
            try:
                obj=get_container(cid)
                assert obj['Config'].get('Labels',{}).get('munongsa.preflight')==token
                command(['sudo','-n','docker','rm','-f',cid])
                result['isolated_container_removed']=True
            except Exception as error:result.update(status='failed',cleanup_error=type(error).__name__)
        if original is not None and homepage is not None:
            try:
                current=get_container('munongsa')
                result['operating_service_unchanged']=(current['Id']==original['Id'] and current['State']['Running'] and http('/')==homepage)
                if not result['operating_service_unchanged']:result['status']='failed'
            except Exception:result.update(status='failed',operating_service_unchanged=None)
    return result
'''


PYTHON_PREPARATION = r'''
def approved_python_preparation():
    import os,re,shutil,subprocess,sys
    from pathlib import Path
    result={'status':'blocked','packages_installed':False}
    def run(args,timeout=60):
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,
                         env=dict(os.environ,LC_ALL='C',DEBIAN_FRONTEND='noninteractive',NEEDRESTART_MODE='l'))
        if p.returncode:
            detail=(p.stdout+'\n'+p.stderr).lower()
            for fragments,code in ((('could not get lock',),'package_manager_locked'),
                                   (('unable to locate package',),'matching_venv_package_unavailable'),
                                   (('unmet dependencies',),'dependency_changes_require_review'),
                                   (('failed to fetch',),'package_download_failed'),
                                   (('password is required',),'sudo_permission_required')):
                if all(part in detail for part in fragments):raise ValueError(code)
            raise ValueError('package_command_failed')
        return p.stdout
    try:
        release=dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        result['ubuntu']=release.get('VERSION_ID','').strip('"')
        result['python']='.'.join(map(str,sys.version_info[:3]))
        if release.get('ID','').strip('"')!='ubuntu' or result['ubuntu']!='24.04':
            raise ValueError('unexpected_os_review_required')
        target='python%d.%d-venv'%sys.version_info[:2]
        installed={}
        for line in run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${db:Status-Status}\n']).splitlines():
            fields=line.split('\t')
            if len(fields)==3 and fields[2]=='installed':installed[fields[0].split(':')[0]]=fields[1]
        result['venv_packages']={p:installed.get(p) for p in ('python3-venv',target)}
        args=['apt-get','--no-install-recommends','--no-remove','--no-upgrade','install',target]
        simulation=run(['sudo','-n',*args[:1],'-s',*args[1:]])
        # Only package identifiers are reported when an unsafe proposal is rejected.
        result['proposed_package_names']=sorted(set(re.findall(r'^(?:Inst|Remv|Purg) ([a-z0-9.+:-]+)',simulation,re.M)))
        plan=validate_venv_plan(simulation,installed,target)
        result['simulation']={'new_packages':[{'name':p,'version':v} for p,v in plan],
                              'upgraded':0,'removed':0,'existing_packages_changed':0}
        if not plan:
            result['status']='already_installed';return result
        # Bound disk using both package archives and uncompressed installed sizes.
        required=0
        for name,version in plan:
            metadata=run(['apt-cache','show',name+'='+version])
            sizes=re.findall(r'^Size: (\d+)$',metadata,re.M)
            installed_sizes=re.findall(r'^Installed-Size: (\d+)$',metadata,re.M)
            if not sizes or not installed_sizes:raise ValueError('package_size_unknown')
            required+=max(map(int,sizes))+1024*max(map(int,installed_sizes))
        free=min(shutil.disk_usage('/').free,shutil.disk_usage('/var/cache/apt/archives').free)
        memory=re.search(r'^MemAvailable:\s+(\d+) kB',Path('/proc/meminfo').read_text(),re.M)
        result['resources']={'package_space_upper_bound_mb':(required+1048575)//1048576,
                             'disk_free_mb':free//1048576,
                             'memory_available_mb':int(memory[1])//1024 if memory else None}
        if free<required+800*1048576 or not memory or int(memory[1])<180*1024:
            raise ValueError('insufficient_resources')
        # Exact versions + restricted preferences prevent any unplanned dependency selection.
        # No apt update, upgrade, autoremove, service restart or reboot is performed.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='munongsa-venv-apt-') as temp:
            preferences=Path(temp)/'preferences'
            preferences.write_text('Package: *\nPin: version *\nPin-Priority: -1\n\n'+''.join(
                'Package: '+name+'\nPin: version '+version+'\nPin-Priority: 1001\n\n'
                for name,version in plan))
            pinned=['sudo','-n','apt-get','-o','Dir::Etc::preferences='+str(preferences),
                    '-o','Dir::Etc::preferencesparts=-','--no-install-recommends','--no-remove','--no-upgrade',
                    'install',*[name+'='+version for name,version in plan]]
            checked=validate_venv_plan(run(pinned[:3]+['-s']+pinned[3:]),installed,target)
            if sorted(checked)!=sorted(plan):raise ValueError('pinned_plan_changed')
            result['installation_attempted']=True
            run(['sudo','-n','env','DEBIAN_FRONTEND=noninteractive','NEEDRESTART_MODE=l',
                 *pinned[2:3],'-y',*pinned[3:]],timeout=240)
        after={}
        for line in run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${db:Status-Status}\n']).splitlines():
            fields=line.split('\t')
            if len(fields)==3 and fields[2]=='installed':after[fields[0].split(':')[0]]=fields[1]
        if any(after.get(p)!=v for p,v in installed.items()) or {p for p in after if p not in installed}!={p for p,v in plan}:
            raise ValueError('post_install_package_changes_require_review')
        if any(after.get(p)!=v for p,v in plan):raise ValueError('post_install_version_mismatch')
        result.update(status='installed',packages_installed=True)
    except (ValueError,OSError,subprocess.TimeoutExpired) as error:
        # Never echo apt output, environment values or repository URLs.
        result['error']=str(error) if isinstance(error,ValueError) else type(error).__name__
    return result

def validate_venv_plan(text,installed,target):
    import re
    allowed={target,'python3-pip-whl','python3-setuptools-whl'}
    summary=re.findall(r'^(\d+) upgraded, (\d+) newly installed, (\d+) to remove and (\d+) not upgraded\.',text,re.M)
    if len(summary)!=1 or int(summary[0][0]) or int(summary[0][2]):
        raise ValueError('existing_package_changes_or_unrecognized_plan')
    plan=[]
    for line in text.splitlines():
        if line.startswith(('Remv ','Purg ')):raise ValueError('package_removal_rejected')
        if not line.startswith('Inst '):continue
        match=re.fullmatch(r'Inst ([a-z0-9.+-]+)(?::[a-z0-9]+)? \(([^\s()]+) [^\r\n]+\)',line)
        if not match:raise ValueError('package_upgrade_or_unrecognized_plan')
        name,version=match.groups()
        if name in installed or name not in allowed:raise ValueError('unexpected_package_change')
        if not re.fullmatch(r'[a-zA-Z0-9.+:~_-]+',version):raise ValueError('invalid_package_version')
        plan.append((name,version))
    if len(plan)!=int(summary[0][1]) or len({p for p,v in plan})!=len(plan):
        raise ValueError('incomplete_package_plan')
    if target not in installed and target not in {p for p,v in plan}:raise ValueError('venv_package_missing_from_plan')
    return plan
'''


def preflight_source(prepare_python=False):
    """Send only the reviewed source allowlist, never work/, logs or credentials."""
    import base64,io,zipfile
    root=Path(__file__).resolve().parents[2]
    names=(root/'deploy/collector/release-files.txt').read_text('utf8').splitlines()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            path=(root/name).resolve()
            if (not path.is_relative_to(root) or path.is_symlink() or name.startswith(('work/','outputs/'))
                    or path.suffix in ('.log','.pem','.key','.sqlite3') or path.name.startswith('.env') or not path.is_file()):
                raise ValueError('invalid release allowlist')
            archive.writestr(name,path.read_bytes())
    encoded=base64.b64encode(buffer.getvalue()).decode('ascii')
    preparation=(PYTHON_PREPARATION+'\n_setup=approved_python_preparation()\n'
                 +'_snapshot["python_preparation"]=_setup\n'
                 +'if _setup["status"] not in ("installed","already_installed"):\n print(json.dumps(_snapshot));raise SystemExit(1)\n') if prepare_python else ''
    return ('import io,contextlib,json\n_buffer=io.StringIO()\ntry:\n with contextlib.redirect_stdout(_buffer):\n  exec('+repr(REMOTE)+')\n'
            +'except SystemExit:\n print(_buffer.getvalue());raise\n_snapshot=json.loads(_buffer.getvalue())\n'
            +preparation+PREFLIGHT+'\n_result=preflight(_snapshot,'+repr(encoded)+')\n'
            +'print(json.dumps({**_snapshot,"preflight":_result}))\nraise SystemExit(0 if _result["status"]=="passed" else 1)\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh', action='store_true', required=True)
    parser.add_argument('--preflight', action='store_true', help='explicit temporary venv/SQLite/container validation; never replaces the site or enables scheduling')
    parser.add_argument('--prepare-python-approved', action='store_true', help='conditionally install only new matching venv/wheel packages after a safe simulation; requires --preflight')
    parser.add_argument('--identity', type=Path, default=Path.home() / '.ssh/munongsa-keypair.pem')
    args = parser.parse_args()
    if args.prepare_python_approved and not args.preflight:
        parser.error('--prepare-python-approved requires --preflight')
    try:
        # Preserve the user's existing VS Code/PowerShell authentication path.
        # No credential-helper installation, login, credential output or config writes.
        import os
        repo=Path(__file__).resolve().parents[2]
        github={'remote_checked':False}
        try:
            git=subprocess.run(['git','--no-optional-locks','-c','safe.directory='+repo.as_posix(),'-c','credential.helper=',
                                'ls-remote','origin','refs/heads/main'],cwd=repo,capture_output=True,text=True,
                               env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never'),timeout=25)
            github['remote_checked']=git.returncode==0
            if git.returncode:github['error']=failure_kind(git.stderr)
            if git.returncode==0 and git.stdout.split():github['remote_main']=git.stdout.split()[0]
        except (OSError,subprocess.TimeoutExpired) as error:
            github['error']=type(error).__name__
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                                 '-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no',
                                 '-o','ControlMaster=no','-o','ControlPath=none','-o','AddKeysToAgent=no','-i', str(args.identity),
                                 'ubuntu@43.201.72.109', 'python3 -B -'],
                                input=(preflight_source(prepare_python=True) if args.prepare_python_approved else preflight_source()) if args.preflight else REMOTE,
                                capture_output=True, text=True, encoding='utf8', timeout=720 if args.prepare_python_approved else 360 if args.preflight else 40)
        try:
            structured=json.loads(result.stdout)
        except ValueError:
            structured=None
        if result.returncode and not isinstance(structured,dict):
            print(json.dumps({'status': 'connection_or_remote_check_failed', 'exit_code': result.returncode,
                              'error':failure_kind(result.stderr),'github':github}))
        else:
            # Print only the structured inventory, never SSH stderr or credentials.
            print(json.dumps({**structured,'github':github}, ensure_ascii=False, indent=2))
        return int(result.returncode != 0 or (args.preflight and (not github.get('remote_checked')
                   or github.get('remote_main')!='9349a3d5be057cf0e634aa9586f1dfdab69cb980')))
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        print(json.dumps({'status': 'check_failed', 'error': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
