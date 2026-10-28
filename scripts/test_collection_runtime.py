"""Production boundary tests, isolated files and recorded/mocked responses only."""
import copy
import hashlib
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import run_support_collection as runtime
import support_monitor as monitor
from support_runtime import ingestion, periods
from test_support_public import PublicTests

NOW = periods.as_of('2026-10-28T16:00:00+09:00')


def item():
    link = 'https://www.buan.go.kr/board/view.buan?boardId=TEST&dataSid=999999'
    proof = {'url': link, 'quote': '모의 신청기간 2026.10.01.~2026.10.30.', 'location': '모의 p1'}
    return {'kind': 'buan', 'metadata': {'original_id': 'TEST-1', 'title': '모의 농업 지원사업 · 시험 전용',
        'published_at': '2026-10-28', 'original_url': link}, 'facts': {
        'application_start': {'value': {'date': '2026-10-01', 'time': 'unknown', 'timezone': 'Asia/Seoul'}, 'evidence': proof},
        'application_deadline': {'value': {'date': '2026-10-30', 'time': 'unknown', 'timezone': 'Asia/Seoul'}, 'evidence': proof}},
        'status': 'partial', 'checked_at': NOW.isoformat(), 'detail_fetched': True}


class RuntimeTests(unittest.TestCase):
    def test_robots_denial_never_sends_a_detail_request(self):
        from support_runtime import boards
        from types import SimpleNamespace
        transport=boards.Transport({'official_hosts':['www.gimje.go.kr']})
        transport.robot=SimpleNamespace(can_fetch=lambda agent,link:False)
        with patch.object(boards.http,'build_opener') as opener,self.assertRaises(boards.Blocked):
            transport.get('https://www.gimje.go.kr/board/list.gimje')
        opener.assert_not_called();self.assertEqual(transport.count,0)

    def test_common_board_detail_extracts_without_missing_html_import(self):
        from support_runtime import boards
        body='<div class="basicView"><div class="conText"><p>신청기간: 2026.10.01.~2026.10.30.</p><p>지원내용: 시설 &amp; 장비 지원</p></div></div>'.encode('utf-8')
        result=boards.extract(body,'https://www.jinan.go.kr/board/view.jinan?boardId=TEST&dataSid=1')
        self.assertEqual(result['content_selector'],'.basicView .conText')
        self.assertIsInstance(result['facts'],dict)

    def test_detail_analysis_does_not_mislabel_html_import_error_as_extraction_failure(self):
        from support_runtime import discovery
        from types import SimpleNamespace
        body='<div class="basicView"><div class="conText"><p>신청기간: 2026.10.01.~2026.10.30.</p></div></div>'.encode('utf-8')
        entry=item()
        result=discovery.analyse(entry,SimpleNamespace(get=lambda link:body),NOW)
        self.assertNotEqual(result['status'],'failed')
        self.assertNotEqual(result.get('error'),'NameError')

    def test_central_rss_uses_imported_monitor_without_local_shadowing(self):
        source={'enabled':True}
        with patch.object(ingestion.m,'fetch_rss',return_value=(b'<rss/>',200,'application/rss+xml')) as fetch,patch.object(ingestion.m,'parse_rss',return_value=[]):
            result=ingestion.central(source,'mafra')
        fetch.assert_called_once()
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['list_count'],0)

    def test_central_rss_failure_is_isolated_and_sanitized(self):
        with patch.object(ingestion.m,'fetch_rss',side_effect=RuntimeError('PRIVATE_URL_DO_NOT_LOG')):
            result=ingestion.central({'enabled':True},'mafra')
        self.assertEqual(result['errors'][0]['error'],'RuntimeError')
        self.assertNotIn('PRIVATE_URL',json.dumps(result))

    def test_disabled_central_source_never_fetches(self):
        with patch.object(ingestion.m,'fetch_rss') as fetch:
            result=ingestion.central({'enabled':False},'mafra')
        fetch.assert_not_called();self.assertTrue(result['skipped'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / 'private'
        self.output = Path(self.temp.name) / 'public'
        self.registry = runtime.sources()
        self.network = patch('socket.socket.connect', side_effect=AssertionError('network forbidden'))
        self.network.start()
        ingestion.SOURCES.clear()
        ingestion.SOURCES.update({s['kind']: s for s in self.registry})

    def tearDown(self):
        self.network.stop()
        self.temp.cleanup()

    def run_groups(self, items=None, errors=None):
        group = {'kind': 'buan', 'analyses': items if items is not None else [item()], 'errors': errors or [], 'list_count': 1}
        return runtime.execute(self.state, self.output, self.state / 'publication-rights.json', self.registry, [group], now=NOW)

    def db(self):
        return monitor.connect(self.state, readonly=True)

    def test_registry_preserves_14_cities_and_disabled_api(self):
        self.assertEqual(len([s for s in self.registry if s['kind'] not in ('mafra', 'bizinfo', 'jbares')]), 14)
        self.assertFalse(next(s for s in self.registry if s['kind'] == 'bizinfo')['enabled'])

    def test_blocked_sources_remain_disabled(self):
        self.assertTrue(all(not s['enabled'] for s in self.registry if s['kind'] in ('iksan', 'namwon', 'wanju')))

    def test_private_public_paths_cannot_overlap(self):
        with self.assertRaises(ValueError): runtime.paths(self.state, self.state / 'public')

    def test_checkout_public_path_rejected(self):
        with self.assertRaises(ValueError): runtime.paths(self.state, runtime.ROOT / 'data')

    def test_trial_db_cannot_be_silently_imported(self):
        self.state.mkdir(); (self.state / 'monitor.sqlite3').write_bytes(b'trial')
        with self.assertRaises(ValueError): runtime.prepare_state(self.state)

    def test_initialized_missing_db_cannot_be_silently_recreated(self):
        runtime.prepare_state(self.state)
        with self.assertRaises(ValueError): runtime.prepare_state(self.state)

    def test_missing_rights_manifest_cannot_erase_existing_public_feed(self):
        self.run_groups()
        feed=self.output/'support-public.json';feed.write_text('{"notices":[{"id":"test-only-last-approved"}]}',encoding='utf8')
        before=feed.read_bytes()
        with self.assertRaises(ValueError):runtime.export_public(self.state,self.output,self.state/'publication-rights.json',NOW)
        self.assertEqual(feed.read_bytes(),before)

    def test_fresh_state_never_imports_72_records(self):
        runtime.prepare_state(self.state)
        with closing(monitor.connect(self.state)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM discovered_notices').fetchone()[0], 0)

    def test_new_rows_private_review_only(self):
        r = self.run_groups(); self.assertEqual(r['counts']['new'], 1)
        with closing(self.db()) as c:
            row = c.execute('SELECT publication,verification_status FROM discovered_notices').fetchone()
            self.assertEqual(tuple(row), ('review', 'unverified'))
        self.assertEqual(json.loads((self.output / 'support-public.json').read_text('utf8'))['notices'], [])

    def test_same_response_no_new_change_or_versions(self):
        self.run_groups()
        with closing(self.db()) as c: before = c.execute('SELECT COUNT(*) FROM notice_versions').fetchone()[0]
        r = self.run_groups(); self.assertEqual(r['counts']['same'], 1); self.assertEqual(r['counts']['changed'], 0)
        with closing(self.db()) as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM notice_versions').fetchone()[0], before)

    def test_deadline_extension_reopens_review_preserves_history(self):
        self.run_groups()
        with closing(monitor.connect(self.state)) as c:
            nid = c.execute('SELECT notice_id FROM discovered_notices').fetchone()[0]
            monitor.review_notice(c, nid, 'fixture', 'test only', verification_status='verified', freshness='current', target='모의 농업인', evidence_url=item()['metadata']['original_url'], evidence_location='모의 p1')
            monitor.publish_notice(c, nid, 'approved_reference', 'fixture', 'test only')
        changed = item(); changed['facts']['application_deadline']['value']['date'] = '2026-11-10'
        self.assertEqual(self.run_groups([changed])['counts']['changed'], 1)
        with closing(self.db()) as c:
            self.assertEqual(monitor.notice_record(c, nid)['publication'], 'review')
            event = c.execute("SELECT before_json FROM review_events WHERE action='source_changed'").fetchone()
            self.assertEqual(json.loads(event[0])['publication'], 'approved_reference')

    def test_fetch_failure_preserves_previous_facts(self):
        self.run_groups(); failed = item(); failed.update(status='failed', facts={})
        self.assertEqual(self.run_groups([failed])['exit_code'], 1)
        with closing(self.db()) as c:
            h = json.loads(c.execute('SELECT hints_json FROM discovered_notices').fetchone()[0])
            self.assertIn('application_deadline', h['objective_facts'])

    def test_source_failure_does_not_prevent_other_save(self):
        r = runtime.execute(self.state, self.output, self.state / 'publication-rights.json', self.registry,
            [{'kind': 'muju', 'analyses': [], 'errors': [{'error': 'HTTP 404'}]}, {'kind': 'buan', 'analyses': [item()], 'errors': []}], now=NOW)
        self.assertEqual(r['exit_code'], 1); self.assertEqual(r['counts']['new'], 1)

    def test_unknown_period_not_open(self):
        self.assertEqual(periods.assess({}, now=NOW)['status'], 'unknown')

    def test_date_window_does_not_assert_official_open(self):
        self.assertEqual(periods.assess(item()['facts'], now=NOW)['status'], 'date_window_open')

    def test_backup_integrity_and_database_outside_public(self):
        self.run_groups()
        files = list((self.state / 'backups').glob('*.sqlite3')); self.assertEqual(len(files), 1)
        import sqlite3
        with closing(sqlite3.connect(files[0])) as c: self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual([p.name for p in self.output.iterdir()], ['support-public.json'])

    def test_lock_prevents_parallel_writer(self):
        runtime.prepare_state(self.state)
        with closing(monitor.connect(self.state)):pass
        with ingestion.lock(self.state / 'run.lock'):
            with self.assertRaises(RuntimeError): self.run_groups()

    def test_publication_does_not_modify_db(self):
        self.run_groups(); db = self.state / 'monitor.sqlite3'; before = hashlib.sha256(db.read_bytes()).hexdigest()
        runtime.export_public(self.state, self.output, self.state / 'publication-rights.json', NOW)
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)

    def test_rights_manifest_cannot_be_served(self):
        self.run_groups()
        with self.assertRaises(ValueError): runtime.export_public(self.state, self.output, self.output / 'rights.json', NOW)

    def test_unknown_file_in_public_mount_rejected(self):
        self.run_groups(); (self.output / 'private.sqlite3').write_bytes(b'private')
        with self.assertRaises(ValueError): runtime.export_public(self.state, self.output, self.state / 'rights.json', NOW)

    def test_timer_is_0700_korea_and_not_enabled_by_script(self):
        timer = (runtime.ROOT / 'deploy/collector/munongsa-collector.timer').read_text()
        self.assertIn('07:00:00 Asia/Seoul', timer)
        script = (runtime.ROOT / 'deploy/collector/prepare-release.sh').read_text()
        self.assertNotIn('systemctl enable', script)
        self.assertNotIn('systemctl start', script)

    def test_condition_failure_retains_private_notice_and_counts_it(self):
        with patch('support_runtime.ingestion.eligibility.register', side_effect=monitor.MonitorError('fixture')):
            result = self.run_groups()
        self.assertEqual(result['counts']['new'], 1)
        self.assertEqual(result['exit_code'], 1)
        with closing(self.db()) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM discovered_notices').fetchone()[0], 1)

    def test_search_controls_preserve_official_document_identity(self):
        source = item(); original = source['metadata']['original_url'] + '&keyword=test&page=2'
        source['metadata']['original_url'] = original
        self.run_groups([source])
        with closing(self.db()) as c:
            row = c.execute('SELECT original_url,hints_json FROM discovered_notices').fetchone()
            self.assertIn('dataSid=999999', row['original_url'])
            self.assertNotIn('keyword=', row['original_url'])
            self.assertEqual(json.loads(row['hints_json'])['observed_original_url'], original)

    def test_backup_can_be_opened_as_independent_restored_copy(self):
        self.run_groups(); self.run_groups()
        import sqlite3, shutil
        files = sorted((self.state / 'backups').glob('*.sqlite3'), key=lambda p: p.stat().st_mtime_ns)
        restored = Path(self.temp.name) / 'restore.sqlite3'; shutil.copyfile(files[-1], restored)
        with closing(sqlite3.connect(restored.as_uri() + '?mode=ro', uri=True)) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM discovered_notices').fetchone()[0], 1)

    def checker(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('collector_check',runtime.ROOT/'deploy/collector/check_server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_checker_avoids_ssh_configuration_and_hostkey_writes(self):
        import io,subprocess
        from contextlib import redirect_stdout
        module=self.checker();responses=[subprocess.CompletedProcess([],0,'a'*40+' refs/heads/main',''),subprocess.CompletedProcess([],0,'{"status":"checked"}','')]
        with patch('sys.argv',['check_server.py','--ssh']),patch.object(module.subprocess,'run',side_effect=responses) as run,redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(),0)
        args=run.call_args_list[1].args[0]
        self.assertEqual(run.call_args_list[1].kwargs['input'],module.REMOTE)
        for option in ['StrictHostKeyChecking=yes','UpdateHostKeys=no','ControlMaster=no','ControlPath=none','AddKeysToAgent=no']:
            self.assertIn(option,args)

    def test_checker_never_prints_ssh_error_or_credential_text(self):
        import io,subprocess
        from contextlib import redirect_stdout
        module=self.checker();responses=[subprocess.CompletedProcess([],128,'','DO_NOT_PRINT'),subprocess.CompletedProcess([],255,'','DO_NOT_PRINT')]
        output=io.StringIO()
        with patch('sys.argv',['check_server.py','--ssh']),patch.object(module.subprocess,'run',side_effect=responses),redirect_stdout(output):
            self.assertEqual(module.main(),1)
        self.assertNotIn('DO_NOT_PRINT',output.getvalue())

    def test_remote_inventory_only_calls_read_commands(self):
        text=self.checker().REMOTE
        import ast
        tree=ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute):
                self.assertNotIn(node.attr,('write_text','write_bytes','mkdir','chmod','unlink','rename','replace','rmdir'))
        self.assertIn("GIT_OPTIONAL_LOCKS='0'",text)
        # Inspect command arguments, not JSON labels such as "restart" policy.
        forbidden={'stop','restart','build','fetch','pull','checkout','enable'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and node.args and isinstance(node.args[0],ast.List):
                values={x.value for x in node.args[0].elts if isinstance(x,ast.Constant) and isinstance(x.value,str)}
                self.assertFalse(values & forbidden)

    def test_notice_basics_flag_is_exposed_by_existing_cli(self):
        import subprocess,sys
        p=subprocess.run([sys.executable,'-B',str(runtime.ROOT/'scripts/support_monitor.py'),'review','--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0);self.assertIn('--notice-basics-verified',p.stdout)

    def test_isolated_preflight_requires_explicit_option(self):
        import io,subprocess
        from contextlib import redirect_stdout
        module=self.checker();responses=[subprocess.CompletedProcess([],0,'9349a3d5be057cf0e634aa9586f1dfdab69cb980 refs/heads/main',''),subprocess.CompletedProcess([],0,'{"status":"checked","preflight":{"status":"passed"}}','')]
        with patch('sys.argv',['check_server.py','--ssh','--preflight']),patch.object(module,'preflight_source',return_value='ISOLATED_TEST_ONLY') as bundle,patch.object(module.subprocess,'run',side_effect=responses) as run,redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(),0)
        bundle.assert_called_once();self.assertEqual(run.call_args_list[1].kwargs['input'],'ISOLATED_TEST_ONLY')

    def test_preflight_bundle_contains_only_selected_release_files(self):
        import ast,base64,io,zipfile
        module=self.checker();source=module.preflight_source();tree=ast.parse(source)
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='preflight')
        encoded=ast.literal_eval(call.args[1])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as archive:
            expected=(runtime.ROOT/'deploy/collector/release-files.txt').read_text().splitlines()
            self.assertEqual(sorted(archive.namelist()),sorted(expected))
            self.assertFalse(any(n.startswith(('work/','outputs/')) or n.endswith(('.sqlite3','.log','.pem')) for n in archive.namelist()))
        self.assertLess(len(source),1024*1024)

    def venv_guard(self):
        namespace={};exec(self.checker().PYTHON_PREPARATION,namespace)
        return namespace['validate_venv_plan']

    def test_venv_plan_accepts_only_new_matching_packages(self):
        plan='Inst python3.12-venv (3.12.3-1 Ubuntu:24.04/noble [amd64])\nInst python3-pip-whl (24.0-1 Ubuntu:24.04/noble [all])\n0 upgraded, 2 newly installed, 0 to remove and 4 not upgraded.'
        self.assertEqual(self.venv_guard()(plan,{'python3.12':'3.12.3-1'},'python3.12-venv'),
                         [('python3.12-venv','3.12.3-1'),('python3-pip-whl','24.0-1')])

    def test_venv_plan_rejects_upgrades_and_removals(self):
        for plan in ['1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.',
                     '0 upgraded, 1 newly installed, 1 to remove and 0 not upgraded.',
                     'Remv nginx [1.0]\n0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.',
                     'Inst python3.12-venv [3.12.1] (3.12.3 Ubuntu [amd64])\n0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.']:
            with self.subTest(plan=plan),self.assertRaises(ValueError):
                self.venv_guard()(plan,{},'python3.12-venv')

    def test_venv_plan_rejects_unexpected_dependencies_and_python_versions(self):
        for package in ['nginx','python3.11-venv','python3.12','libpython3.12']:
            plan='Inst '+package+' (1.0 Ubuntu [amd64])\n0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.'
            with self.subTest(package=package),self.assertRaises(ValueError):
                self.venv_guard()(plan,{},'python3.12-venv')

    def test_venv_plan_rejects_existing_package_reinstallation(self):
        plan='Inst python3-pip-whl (24.0 Ubuntu [all])\n0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.'
        with self.assertRaises(ValueError):self.venv_guard()(plan,{'python3-pip-whl':'24.0'},'python3.12-venv')

    def test_venv_plan_rejects_missing_or_inconsistent_simulation(self):
        for plan in ['', '0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.',
                     'Inst python3.12-venv (1.0 Ubuntu [amd64])\n0 upgraded, 2 newly installed, 0 to remove and 0 not upgraded.']:
            with self.subTest(plan=plan),self.assertRaises(ValueError):self.venv_guard()(plan,{},'python3.12-venv')

    def test_venv_plan_accepts_already_installed_without_changes(self):
        self.assertEqual(self.venv_guard()('0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.',
                                          {'python3.12-venv':'1.0'},'python3.12-venv'),[])

    def test_venv_setup_cannot_run_without_explicit_preflight(self):
        import io
        from contextlib import redirect_stderr
        module=self.checker()
        with patch('sys.argv',['check_server.py','--ssh','--prepare-python-approved']),patch.object(module.subprocess,'run') as run,redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            module.main()
        run.assert_not_called()

    def test_venv_setup_is_not_in_default_preflight(self):
        import ast
        module=self.checker()
        self.assertNotIn('def approved_python_preparation',module.preflight_source())
        source=module.preflight_source(prepare_python=True);ast.parse(source)
        self.assertIn('_setup=approved_python_preparation()',source)
        self.assertIn('NEEDRESTART_MODE=l',source)
        self.assertIn('post_install_package_changes_require_review',source)

    def run_mock_venv_setup(self,low_disk=False,unsafe=False):
        import subprocess,sys
        from types import SimpleNamespace
        namespace={};exec(self.checker().PYTHON_PREPARATION,namespace)
        target='python%d.%d-venv'%sys.version_info[:2]
        plan='Inst '+target+' (1.0 Ubuntu [amd64])\n0 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.'
        calls=[];installed=False
        def fake_run(args,**kwargs):
            nonlocal installed
            calls.append(args)
            if args[0]=='dpkg-query':out='python3\t1.0\tinstalled\n'+(target+'\t1.0\tinstalled\n' if installed else '')
            elif args[0]=='apt-cache':out='Size: 1024\nInstalled-Size: 32\n'
            elif '-s' in args:out='1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.' if unsafe else plan
            elif '-y' in args:installed=True;out=''
            else:raise AssertionError(args)
            return subprocess.CompletedProcess(args,0,out,'')
        def text(path,*args,**kwargs):
            if str(path).replace('\\','/')=='/etc/os-release':return 'ID=ubuntu\nVERSION_ID="24.04"\n'
            if str(path).replace('\\','/')=='/proc/meminfo':return 'MemAvailable: 512000 kB\n'
            raise AssertionError(path)
        with patch('subprocess.run',side_effect=fake_run),patch.object(Path,'read_text',text),patch('shutil.disk_usage',return_value=SimpleNamespace(free=(100 if low_disk else 4096)*1048576)):
            result=namespace['approved_python_preparation']()
        return result,calls

    def test_venv_setup_safe_plan_installs_exact_versions_only(self):
        result,calls=self.run_mock_venv_setup()
        self.assertEqual(result['status'],'installed')
        installs=[args for args in calls if '-y' in args]
        self.assertEqual(len(installs),1)
        self.assertIn('--no-remove',installs[0]);self.assertIn('--no-upgrade',installs[0])
        self.assertIn('NEEDRESTART_MODE=l',installs[0])
        self.assertTrue(any(arg.endswith('-venv=1.0') for arg in installs[0]))

    def test_venv_setup_low_disk_never_installs(self):
        result,calls=self.run_mock_venv_setup(low_disk=True)
        self.assertEqual(result['error'],'insufficient_resources')
        self.assertFalse(any('-y' in args for args in calls))

    def test_venv_setup_unsafe_simulation_never_installs(self):
        result,calls=self.run_mock_venv_setup(unsafe=True)
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(any('-y' in args for args in calls))


if __name__ == '__main__':
    unittest.main()
