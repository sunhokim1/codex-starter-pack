"""Offline regressions. External installs, Codex, sockets and Windows ACL calls are mocked."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import ast
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
for relative in ('assets/runner', 'assets/sev', 'scripts'):
    sys.path.insert(0, str(ROOT/relative))
import runtime_safety as safety
import run as runner
import project
import sev_service as service
import install_sev as installer
import scaffold
import package_starter as package
REAL_PERMISSIONS = safety.private_permissions


@contextmanager
def workspace_temp(*args, **kwargs):
    # Inherit workspace ACLs (some Windows sandboxes reject mode=0700 temp dirs).
    scratch = ROOT.parent/'.starter-test-scratch'
    scratch.mkdir(exist_ok=True)
    path = scratch/uuid.uuid4().hex
    path.mkdir()
    try:
        yield str(path)
    finally:
        if not path.resolve().is_relative_to(scratch.resolve()):
            raise RuntimeError('cleanup escaped test workspace')
        shutil.rmtree(path)


class Regressions(unittest.TestCase):
    def setUp(self):
        self.tmp = workspace_temp()
        self.base = Path(self.tmp.__enter__())
        self.addCleanup(self.tmp.__exit__, None, None, None)
        self.patches = [patch.object(tempfile, 'TemporaryDirectory', workspace_temp),
                        patch.object(safety, 'private_permissions')]
        for item in self.patches:
            item.start(); self.addCleanup(item.stop)

    def copy_bundle(self):
        bundle = self.base/'bundle'
        shutil.copytree(ROOT, bundle, ignore=shutil.ignore_patterns('.scratch', '__pycache__', '*.pyc'))
        (bundle/'release.json').write_text(json.dumps(package.manifest(bundle)), encoding='utf-8')
        return bundle

    def target(self):
        target = self.base/'project'
        shutil.copytree(ROOT/'assets/starter', target)
        return target

    def quick(self, records, commands=None, owner='model', outcome='completed', task='ordinary test request'):
        target = self.target()
        commands = {'test': 'audit-test', 'lint': None} if commands is None else commands
        (target/'.ai/verification.yaml').write_text('commands:\n'+''.join(
            '  '+key+': '+('null' if value is None else value)+'\n' for key, value in commands.items()))
        taskfile = self.base/'task.txt'; taskfile.write_text(task, encoding='utf-8')
        result = {'outcome': outcome, 'summary': 'fixture result', 'verification': records, 'escalation': None}
        args = SimpleNamespace(codex='mock', project=str(target), task_file=taskfile, context_file=None,
            models=target/'.ai/models.yaml', model='main', write=False, verification_owner=owner)
        with patch.object(runner.shutil,'which',return_value='mock'), patch.object(runner,'invoke',
                return_value={'response':json.dumps(result),'usage':{}}) as invoke:
            report = runner.run(args)
        return report, invoke.call_args

    def record(self, executed=True, code=0, name='test', command='audit-test'):
        return {'name':name,'command':command,'executed':executed,'exit_code':code,'evidence':'fixture evidence'}

    def test_python_syntax(self):
        for path in ROOT.rglob('*.py'):
            if '.scratch' not in path.parts:
                ast.parse(path.read_text(encoding='utf-8'))

    def test_neutral_template_and_unset_checks(self):
        for name in ('AGENTS.md', 'PROJECT.md', 'README.md'):
            text=(ROOT/'assets/starter'/name).read_text(encoding='utf-8')
            for stale in ('Rush Hour', 'Echo Garden', 'web/engine.js', 'experiments/', 'evaluation/'):
                self.assertNotIn(stale,text)
        settings,_=runner.config_from(ROOT/'assets/starter/.ai/verification.yaml')
        self.assertTrue(settings['commands'])
        self.assertTrue(all(value is None for value in settings['commands'].values()))

    def test_dry_run_writes_nothing(self):
        target=self.base/'new'
        with patch.object(sys,'argv',['scaffold','--target',str(target),'--dry-run']), \
             patch.object(scaffold.subprocess,'call') as install, redirect_stdout(io.StringIO()):
            self.assertEqual(scaffold.main(),0)
        self.assertFalse(target.exists()); install.assert_not_called()

    def test_files_only_creates_all_template_files_without_install(self):
        target=self.base/'new'
        with patch.object(sys,'argv',['scaffold','--target',str(target),'--files-only']), \
             patch.object(scaffold.subprocess,'call') as install, redirect_stdout(io.StringIO()):
            self.assertEqual(scaffold.main(),0)
        for source in (ROOT/'assets/starter').rglob('*'):
            if source.is_file(): self.assertEqual(source.read_bytes(),(target/source.relative_to(ROOT/'assets/starter')).read_bytes())
        install.assert_not_called()

    def test_adopt_preserves_user_facts_models_commands_and_ignore(self):
        target=self.target()
        names=('PROJECT.md','AGENTS.md','.ai/models.yaml','.ai/verification.yaml','.gitignore')
        for name in names: (target/name).write_text('user data '+name,encoding='utf-8')
        before={name:(target/name).read_bytes() for name in names}
        with patch.object(sys,'argv',['scaffold','--target',str(target),'--adopt','--files-only']), redirect_stdout(io.StringIO()):
            self.assertEqual(scaffold.main(),0)
        self.assertEqual(before,{name:(target/name).read_bytes() for name in names})

    def test_conflict_is_all_or_nothing(self):
        target=self.base/'project'; target.mkdir(); (target/'PROJECT.md').write_text('existing')
        with patch.object(sys,'argv',['scaffold','--target',str(target),'--files-only']), redirect_stderr(io.StringIO()):
            self.assertEqual(scaffold.main(),2)
        self.assertEqual([p.name for p in target.iterdir()],['PROJECT.md'])

    def test_quick_unexecuted_cannot_complete(self):
        self.assertEqual(self.quick([self.record(False,None)])[0]['status'],'unresolved')

    def test_quick_missing_record_cannot_complete(self):
        self.assertEqual(self.quick([])[0]['status'],'unresolved')

    def test_quick_no_checks_cannot_complete(self):
        self.assertEqual(self.quick([],{'test':None})[0]['status'],'unresolved')

    def test_quick_failed_check_cannot_complete(self):
        self.assertEqual(self.quick([self.record(True,7)])[0]['status'],'verification_failed')

    def test_quick_pass_can_complete_and_does_not_retain_raw_response(self):
        report,_=self.quick([self.record()])
        self.assertEqual(report['status'],'completed')
        self.assertNotIn('response',report['execution'])
        self.assertNotIn('ordinary test request',json.dumps(report))

    def test_controller_candidate_is_never_final_completion(self):
        report,_=self.quick([self.record(False,None)],owner='controller')
        self.assertEqual(report['status'],'awaiting_verification')

    def test_blocked_outcome_stays_blocked(self):
        self.assertEqual(self.quick([],outcome='blocked')[0]['status'],'blocked')

    def test_mismatched_verification_rejected(self):
        self.assertEqual(self.quick([self.record(command='wrong')])[0]['status'],'failed')

    def test_credentials_not_sent_or_reported(self):
        secret='sk-'+'a'*40
        report,call=self.quick([self.record()],task='Use api_key="'+secret+'" for the fixture')
        self.assertNotIn(secret,json.dumps(report))
        self.assertNotIn(secret,call.args[3])

    def test_redaction_handles_assignments_headers_private_keys_and_nested_data(self):
        value={'error':'password="sensitive-value" Bearer ABCDEFGHIJKLMNOPQ',
               'token':'opaque-value','items':['-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----']}
        text=json.dumps(safety.redact(value))
        for secret in ('sensitive-value','ABCDEFGHIJKLMNOPQ','opaque-value','\nsecret\n'):
            self.assertNotIn(secret,text)

    def test_private_write_is_atomic_and_does_not_change_old_file_on_permission_failure(self):
        path=self.base/'private.json'; path.write_text('old')
        with patch.object(safety,'private_permissions',side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError): safety.private_write(path,'new')
        self.assertEqual(path.read_text(),'old')
        self.assertEqual(list(self.base.iterdir()),[path])

    def test_console_summary_omits_raw_inputs_and_outputs(self):
        value={'status':'failed','goal':'private goal','facts':'private facts','attempts':[{'report':'private report'}]}
        self.assertEqual(safety.summary(value),{'status':'failed'})

    def test_message_schema_nonobject_and_bad_json(self):
        for payload in (b'[]\n',b'null\n',b'3\n',b'"abc"\n',b'{bad}\n',b'\xff\n'):
            with self.subTest(payload=payload), self.assertRaises(ValueError): service.read_message(io.BytesIO(payload))

    def test_request_schema_types_auth_fields_and_capacity(self):
        valid={'op':'select','token':'fixture','request':'hello','facts':''}
        self.assertEqual(service.validate_request(valid,'fixture'),'select')
        for changed in ({'token':2},{'token':'wrong'},{'request':[]},{'facts':{}},
                        {'op':[]},{'extra':'x'},{'request':'x'*(service.TEXT_LIMIT+1)}):
            with self.subTest(changed=changed), self.assertRaises((ValueError,TypeError)):
                service.validate_request(dict(valid,**changed),'fixture')

    def test_service_survives_malformed_and_unauthenticated_requests(self):
        selector=SimpleNamespace(select=lambda task,facts:{'role':'main'})
        modules={'sev_keyword_selector':SimpleNamespace(KeywordSelector=lambda:selector),
                 'sev_long_candidate':SimpleNamespace(LongCandidate=lambda:SimpleNamespace(load=lambda p:None)),
                 'selector':SimpleNamespace(HERE=self.base)}
        listener=MagicMock(); listener.__enter__.return_value=listener
        listener.getsockname.return_value=('127.0.0.1',12345)
        payloads=[b'[]\n',b'{"op":"status","token":"wrong"}\n',
                  b'{"op":"select","token":"fixture","request":[]}\n',
                  b'{"op":"status","token":"fixture"}\n', b'{"op":"stop","token":"fixture"}\n']
        connections=[]
        for payload in payloads:
            conn=MagicMock(); conn.__enter__.return_value=conn; conn.makefile.return_value=io.BytesIO(payload)
            connections.append(conn)
        listener.accept.side_effect=[(conn,None) for conn in connections]
        with patch.dict(sys.modules,modules), patch.object(service.socket,'socket',return_value=listener), \
             patch.object(service.secrets,'token_hex',return_value='fixture'):
            service.serve(self.base/'service.json')
        outcomes=[json.loads(conn.sendall.call_args.args[0])['ok'] for conn in connections]
        self.assertEqual(outcomes,[False,False,False,True,True])
        self.assertFalse((self.base/'service.json').exists())

    def test_oversize_message_rejected(self):
        with self.assertRaises(ValueError): service.read_message(io.BytesIO(b'x'*(service.LIMIT+1)))

    def test_guidance_markers_preserve_unmanaged_text_and_are_idempotent(self):
        text='before\n'+installer.BEGIN+'\nold\n'+installer.END+'\nafter'
        merged=installer.merge_guidance(text)
        self.assertTrue(merged.startswith('before\n')); self.assertTrue(merged.endswith('\nafter'))
        self.assertEqual(merged,installer.merge_guidance(merged))

    def test_guidance_rejects_orphan_duplicate_and_reversed_markers(self):
        for text in (installer.END,installer.BEGIN,installer.END+installer.BEGIN,
                     installer.BEGIN*2+installer.END,installer.BEGIN+installer.END*2):
            with self.subTest(text=text), self.assertRaises(ValueError): installer.merge_guidance(text)

    def test_ignore_merge_preserves_existing_rules_and_ignores_private_paths(self):
        merged=installer.merge_ignore('custom-rule\n')
        self.assertIn('custom-rule',merged)
        for rule in installer.IGNORE_RULES: self.assertIn(rule,merged)
        self.assertEqual(merged,installer.merge_ignore(merged))

    def test_manifest_rejects_extra_missing_and_tampered_file(self):
        bundle=self.copy_bundle()
        extra=bundle/'assets/sev/unlisted.py'; extra.write_text('# fixture')
        with self.assertRaises(ValueError): installer.verify_bundle(bundle)
        extra.unlink()
        path=bundle/'assets/sev/requirements.txt'; original=path.read_bytes(); path.write_text('changed')
        with self.assertRaises(ValueError): installer.verify_bundle(bundle)
        path.write_bytes(original)
        self.assertEqual(installer.verify_bundle(bundle),'0.3.2')
        path.unlink()
        with self.assertRaises(OSError): installer.verify_bundle(bundle)

    def setup_install(self):
        target=self.target(); runtime=self.base/'runtime'; runtime.mkdir()
        (runtime/'sev_service.py').write_text('old runtime')
        skills=self.base/'skills'; existing=skills/'single-model-runner/SKILL.md'
        existing.parent.mkdir(parents=True); existing.write_text('custom user skill')
        return target,runtime,skills,existing

    def test_pip_failure_leaves_old_runtime_and_project_untouched(self):
        target,runtime,skills,existing=self.setup_install()
        before={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
        calls=[]
        def checked(command):
            calls.append([str(x) for x in command])
            if 'pip' in command: raise RuntimeError('fixture failure')
        with patch.object(installer,'checked',side_effect=checked), self.assertRaises(RuntimeError):
            installer.install(target,runtime,skills,ROOT,autostart=False)
        self.assertEqual((runtime/'sev_service.py').read_text(),'old runtime')
        self.assertEqual(existing.read_text(),'custom user skill')
        self.assertFalse(any('stop' in call for call in calls))
        for name,data in before.items(): self.assertEqual((target/name).read_bytes(),data)
        self.assertFalse((target/'.ai/sev.json').exists())

    def test_success_uses_versioned_runner_preserves_old_runtime_and_custom_skill(self):
        target,runtime,skills,existing=self.setup_install()
        with patch.object(installer,'checked') as checked, redirect_stdout(io.StringIO()):
            config=installer.install(target,runtime,skills,ROOT,autostart=False)
        self.assertTrue(Path(config['runner']).is_file())
        self.assertTrue(Path(config['runner']).is_relative_to(runtime/'releases'))
        self.assertEqual((runtime/'sev_service.py').read_text(),'old runtime')
        self.assertEqual(existing.read_text(),'custom user skill')
        self.assertIn('.ai/project-workflow/',(target/'.gitignore').read_text())
        self.assertEqual(config,json.loads((target/'.ai/sev.json').read_text()))
        calls=[[str(x) for x in call.args[0]] for call in checked.call_args_list]
        self.assertTrue(any('status' in call for call in calls))
        self.assertFalse(any('stop' in call for call in calls))

    def test_start_failure_restores_project_and_stops_only_new_service(self):
        target,runtime,skills,existing=self.setup_install()
        calls=[]
        def checked(command):
            calls.append([str(x) for x in command])
            if 'start' in command: raise RuntimeError('fixture failure')
        with patch.object(installer,'checked',side_effect=checked), self.assertRaises(RuntimeError):
            installer.install(target,runtime,skills,ROOT,autostart=False)
        stops=[call for call in calls if 'stop' in call]
        self.assertEqual(len(stops),1)
        self.assertIn(str(runtime/'releases'),stops[0][1])
        self.assertFalse((target/'.ai/sev.json').exists())

    def test_final_write_failure_restores_existing_project_files(self):
        target,runtime,skills,existing=self.setup_install()
        config=target/'.ai/sev.json'; config.write_text('{"old":"configuration"}')
        before={name:(target/name).read_bytes() for name in ('AGENTS.md','.gitignore','.ai/sev.json')}
        real_write=installer.private_write; failed=False
        def write(path,data):
            nonlocal failed
            if Path(path)==config and not failed:
                failed=True; raise OSError('fixture write failure')
            return real_write(path,data)
        with patch.object(installer,'checked'), patch.object(installer,'private_write',side_effect=write), self.assertRaises(RuntimeError):
            installer.install(target,runtime,skills,ROOT,autostart=False)
        for name,data in before.items(): self.assertEqual((target/name).read_bytes(),data)
        self.assertEqual(existing.read_text(),'custom user skill')

    def test_startup_failure_rolls_back_project_and_new_skills(self):
        target,runtime,skills,existing=self.setup_install()
        startup=self.base/'fixture.lnk'
        def create(*args):
            startup.write_text('partial fixture'); raise OSError('fixture startup failure')
        before=(target/'AGENTS.md').read_bytes()
        with patch.object(installer,'checked'), patch.object(installer,'startup_path',return_value=startup), \
             patch.object(installer,'create_startup',side_effect=create), self.assertRaises(RuntimeError):
            installer.install(target,runtime,skills,ROOT,autostart=True)
        self.assertEqual((target/'AGENTS.md').read_bytes(),before)
        self.assertFalse((target/'.ai/sev.json').exists())
        self.assertFalse(startup.exists())
        self.assertFalse((skills/'project-workflow/SKILL.md').exists())

    def test_private_path_link_rejected_before_write(self):
        with patch.object(Path,'is_symlink',return_value=True), self.assertRaises(ValueError):
            safety.private_write(self.base/'file','fixture')

    def test_plan_unknown_and_cyclic_dependencies_rejected(self):
        task={'id':'a','title':'fixture','instructions':'fixture','approval_required':False,
              'depends_on':['a'],'selection_context':{'facts':[],'risks':[],'dependencies':[]}}
        for deps in (['a'],['missing']):
            task['depends_on']=deps
            with self.assertRaises(ValueError): project.validate_plan({'tasks':[task]},True)

    def test_controller_real_check_success_failure_and_redacted_output(self):
        with patch.object(project.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='password="fixture-secret"',stderr='')):
            checks=project.real_checks(self.base,{'test':'fixture'},project.time.monotonic()+10)
        self.assertEqual(checks['test']['status'],'passed')
        self.assertNotIn('fixture-secret',checks['test']['evidence'])
        with patch.object(project.subprocess,'run',return_value=SimpleNamespace(returncode=8,stdout='',stderr='failure')):
            checks=project.real_checks(self.base,{'test':'fixture'},project.time.monotonic()+10)
        self.assertEqual(checks['test']['status'],'failed')

    def test_controller_advances_candidate_only_after_real_checks(self):
        task={'id':'fix','title':'fixture','instructions':'fixture','depends_on':[],
              'approval_required':False,'selection_context':{'facts':[],'risks':[],'dependencies':[]},'status':'pending'}
        state={'max_seconds':60,'elapsed_seconds':0,'max_runs':3,'runs':0,'plan_status':'completed',
               'tasks':[task],'approved':[],'attempts':[],'goal':'fixture','configuration':{'fixture':'hash'}}
        report={'status':'awaiting_verification','attempts':[]}
        passed={'test':{'status':'passed','configured':True}}
        with patch.object(project,'model_call',return_value=report), \
             patch.object(project,'configuration',return_value=({'fixture':'hash'},None,None)), \
             patch.object(project,'real_checks',return_value=passed) as checks:
            result=project.advance(self.base,self.base/'state.json',state,{'test':'fixture'},None,True)
        self.assertEqual(result['status'],'completed'); checks.assert_called_once()

    def test_controller_no_checks_is_unresolved(self):
        task={'id':'fix','title':'fixture','instructions':'fixture','depends_on':[],
              'approval_required':False,'selection_context':{'facts':[],'risks':[],'dependencies':[]},'status':'pending'}
        state={'max_seconds':60,'elapsed_seconds':0,'max_runs':3,'runs':0,'plan_status':'completed',
               'tasks':[task],'approved':[],'attempts':[],'goal':'fixture','configuration':{}}
        with patch.object(project,'model_call',return_value={'status':'awaiting_verification'}), \
             patch.object(project,'configuration',return_value=({},None,None)):
            result=project.advance(self.base,self.base/'state.json',state,{},None,True)
        self.assertEqual(result['tasks'][0]['status'],'unresolved')
        self.assertNotEqual(result['status'],'completed')

    def test_model_call_explicitly_sets_controller_owner(self):
        state={'max_seconds':60,'elapsed_seconds':0,'facts':'fixture','model':None,
               'codex':'mock','attempts':[]}
        sev={'python':'mock-python','service':'mock-service','state':'mock-state'}
        with patch.object(project.runner,'run',return_value={'status':'awaiting_verification'}) as call:
            project.model_call(self.base,state,sev,'fixture task',True)
        self.assertEqual(call.call_args.args[0].verification_owner,'controller')

    def test_controller_timeout_is_failed(self):
        with patch.object(project.subprocess,'run',side_effect=subprocess.TimeoutExpired('fixture',1)):
            checks=project.real_checks(self.base,{'test':'fixture'},project.time.monotonic()+10)
        self.assertEqual(checks['test']['status'],'failed')
        self.assertIsNone(checks['test']['exit_code'])

    def test_local_selector_receives_only_filtered_private_input(self):
        target=self.target()
        secret='sk-'+'q'*40
        taskfile=self.base/'task.txt'; taskfile.write_text('api_key="'+secret+'"',encoding='utf-8')
        args=SimpleNamespace(codex='mock',project=str(target),task_file=taskfile,context_file=None,
             models=target/'.ai/models.yaml',model=None,write=False,selector='sev',local_python='mock-python',
             local_script='mock-service',sev_state='mock-state',selection_timeout=90)
        selection={'ok':True,'pid':1,'requests':1,'selection':{'role':'main','backend':'local','api_calls':0,
                    'matches':[{'category':'security','clause':'private request excerpt'}]}}
        def selected(command,**kwargs):
            safe=Path(command[command.index('--task-file')+1])
            self.assertNotEqual(safe,taskfile)
            self.assertNotIn(secret,safe.read_text())
            return SimpleNamespace(returncode=0,stdout=json.dumps(selection),stderr='')
        outcome={'outcome':'completed','summary':'fixture','verification':[],'escalation':None}
        with patch.object(runner.shutil,'which',return_value='mock'), \
             patch.object(runner.subprocess,'run',side_effect=selected), \
             patch.object(runner,'invoke',return_value={'response':json.dumps(outcome)}):
            report=runner.run(args)
        self.assertNotIn('private request excerpt',json.dumps(report))
        self.assertNotIn(secret,json.dumps(report))
        self.assertEqual(report['status'],'unresolved')

    def test_windows_acl_commands_are_hidden_and_use_validated_sid(self):
        # Exercise the real permission function with fake Windows commands, even on POSIX.
        permission_function=REAL_PERMISSIONS
        responses=[SimpleNamespace(stdout='"fixture-user","S-1-5-21-123"\n'),SimpleNamespace(stdout='')]
        with patch.object(safety.os,'name','nt'), \
             patch.object(safety.subprocess,'CREATE_NO_WINDOW',0x08000000,create=True), \
             patch.object(safety.subprocess,'run',side_effect=responses) as call:
            permission_function(self.base/'private.json')
        self.assertEqual(call.call_args_list[1].args[0][-1],'*S-1-5-21-123:F')
        self.assertEqual(call.call_args_list[1].kwargs['creationflags'],0x08000000)


if __name__ == '__main__':
    unittest.main(verbosity=2)
