"""격리 설치와 명시적 이전의 오프라인 계약 fixture."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

BUNDLE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BUNDLE/'assets'))
sys.path.insert(0,str(BUNDLE/'scripts'))
from rev import contracts as c
import install_rev as installer
import scaffold

HARDWARE=dict(os='Linux',machine='x86_64',cuda_driver_observed=True,
    total_ram_bytes=32*1024**3,available_ram_bytes=24*1024**3,
    nvidia=[dict(index=0,total_bytes=24*1024**3,free_bytes=24*1024**3)])

class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'한글 project';self.project.mkdir()
        shutil.copytree(BUNDLE/'assets/starter',self.project,dirs_exist_ok=True)
        self.runtime=self.root/'isolated'
        self.connection=dict(contract_version=1,runtime_version='0.4.0',runtime_id='fixture',
            endpoint='http://127.0.0.1:12345',token_env='REV_FIXTURE_TOKEN',
            lock_sha256=hashlib.sha256((BUNDLE/'contracts/upstream.lock.json').read_bytes()).hexdigest())
    def deploy(self,**kw):
        return installer.deploy(BUNDLE,self.project,self.runtime,self.connection,
            hardware=lambda:HARDWARE,ready=lambda x:None,**kw)
    def test_clean_setup_preserves_facts_and_settings(self):
        (self.project/'PROJECT.md').write_text('actual project facts',encoding='utf-8')
        before={p.relative_to(self.project):p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        result=self.deploy()
        self.assertEqual(result['status'],'connected');self.assertFalse(result['inference_measured'])
        installer.verify_bundle(self.runtime)
        for name,data in before.items():
            actual=(self.project/name).read_bytes()
            if str(name) in ('AGENTS.md','.gitignore'):self.assertTrue(actual.startswith(data))
            else:self.assertEqual(actual,data)
        self.assertIn(b'starter-rev:start',(self.project/'AGENTS.md').read_bytes())
        self.assertEqual(json.loads((self.project/'.ai/rev.json').read_text()),self.connection)
        with self.assertRaises(ValueError):self.deploy()
    def test_migration_is_explicit_and_shared_sev_never_deleted(self):
        old=self.project/'.ai/sev.json';old.write_text('{"deployment":"shared-fixture"}')
        before=old.read_bytes()
        with self.assertRaisesRegex(ValueError,'explicit --migrate'):self.deploy()
        self.assertFalse(self.runtime.exists());self.deploy(migrate=True)
        self.assertEqual(old.read_bytes(),before)
        report=installer.reference_report([self.project,self.root/'unknown'])
        self.assertEqual(report['legacy_references'],1);self.assertFalse(report['exhaustive']);self.assertFalse(report['deletion_allowed'])
    def test_existing_states_require_review_even_if_completed(self):
        for name in ('.ai/project-workflow/state.json','.ai/rev-workflow/state.json'):
            path=self.project/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('{"status":"completed","tasks":[{"id":"done"}]}')
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'archive'):self.deploy(migrate=True)
            self.assertEqual(path.read_bytes(),before);self.assertFalse(self.runtime.exists());path.unlink()
    def test_unsupported_host_stops_before_readiness_or_copy(self):
        with patch.object(installer,'diagnose',return_value=dict(os='Windows')), patch.object(installer.Client,'ready') as ready:
            with self.assertRaisesRegex(ValueError,'Rev 준비 필요:.*메모리 추정'):
                installer.deploy(BUNDLE,self.project,self.runtime,self.connection)
            ready.assert_not_called()
        self.assertFalse(self.runtime.exists())
    def test_authenticated_warmed_bounded_capacity_is_not_rejected_by_resident_estimate(self):
        lock=json.loads((BUNDLE/'contracts/upstream.lock.json').read_text())
        info=dict(runtime_id=self.connection['runtime_id'], lock_sha256=self.connection['lock_sha256'],
            runtime_version='0.4.0',ready=True,warmed=True,pid=123, model=lock['base']['repo'],
            revision=lock['base']['revision'],adapter_revision=lock['adapter']['revision'],
            checkpoint_sha256=lock['adapter']['artifacts']['checkpoint.pt'],temperature=1.96,
            max_row_tokens=16384,state_format='raw',device='cpu',dtype='bf16',
            offload_mode='block-private-mmap',derived_manifest_sha256='a'*64,
            inference_evidence='official-warmup-completed; authenticated-score-evidence-required',
            memory_plan=dict(mode='bounded-cpu',device='cpu',dtype='bf16',row_token_budget=512,
                estimated_process_bytes=2800000000,process_budget_bytes=3000000000,safety_margin_bytes=1400000000,
                observed_peak_rss_bytes=2000000000,observed_peak_private_bytes=2100000000))
        resources=dict(total_ram_bytes=16*1024**3,available_ram_bytes=3*1024**3,nvidia=[])
        installer.bounded_connection_capacity(info,self.connection,resources)
        for key,value in [('ready',False),('derived_manifest_sha256','bad'),('revision','wrong')]:
            with self.assertRaises((ValueError, RuntimeError)):
                installer.bounded_connection_capacity(dict(info,**{key:value}),self.connection,resources)
        result=installer.deploy(BUNDLE,self.project,self.runtime,self.connection,
            hardware=lambda:resources,ready=lambda _:info)
        self.assertEqual(result['status'],'connected')
        self.assertFalse(result['inference_measured'])  # mocked fixture remains a fixture
    def test_failed_publication_rolls_back_only_owned_files(self):
        original=Path.open
        def fail(path,*args,**kw):
            if path.name=='rev-install.json':raise OSError('fixture publication failure')
            return original(path,*args,**kw)
        with patch.object(Path,'open',fail):
            with self.assertRaises(OSError):self.deploy()
        self.assertFalse(self.runtime.exists());self.assertFalse((self.project/'.ai/rev.json').exists())
        self.assertTrue((self.project/'PROJECT.md').exists())
    def test_destination_overlap_and_existing_runtime_guard(self):
        for dest in (self.project,self.project/'runtime',BUNDLE/'runtime',self.root):
            self.runtime=dest
            with self.assertRaises(ValueError):self.deploy()
    def test_settings_are_rejected_without_conversion_or_overwrite(self):
        path=self.project/'.ai/models.yaml';path.write_text('models:\n  worker: custom-model\n')
        before=path.read_bytes()
        with self.assertRaises(ValueError):self.deploy()
        self.assertEqual(path.read_bytes(),before);self.assertFalse(self.runtime.exists())
    def test_connection_validation_and_identity(self):
        for endpoint in ('http://0.0.0.0:1234','http://remote:1234','http://user:pass@127.0.0.1:1234'):
            self.connection['endpoint']=endpoint
            with self.assertRaises(ValueError):self.deploy()
        self.connection['endpoint']='http://127.0.0.1:12345';self.connection['lock_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'identity'):self.deploy()
    def test_managed_guidance_replaces_only_known_legacy_block(self):
        path=self.project/'AGENTS.md'
        path.write_text('사용자 지침\n<!-- starter-sev:start -->old<!-- starter-sev:end -->\nproject facts',encoding='utf-8')
        self.deploy()
        text=path.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('사용자 지침\n'));self.assertTrue(text.endswith('\nproject facts'))
        self.assertNotIn('starter-sev:start',text);self.assertIn('starter-rev:start',text)
        self.assertEqual(installer.guidance_updates(self.project)[0][1],installer.guidance_updates(self.project)[0][2])
    def test_ambiguous_guidance_is_rejected_without_deployment(self):
        path=self.project/'AGENTS.md';path.write_text('<!-- starter-sev:start -->partial')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):self.deploy()
        self.assertFalse(self.runtime.exists());self.assertFalse((self.project/'.ai/rev.json').exists())
    def test_document_publication_failure_restores_originals(self):
        before=(self.project/'AGENTS.md').read_bytes();original=installer.replace_document
        def fail(path,old,new):
            if path.name=='.gitignore':raise OSError('fixture')
            return original(path,old,new)
        with patch.object(installer,'replace_document',side_effect=fail):
            with self.assertRaises(OSError):self.deploy()
        self.assertEqual((self.project/'AGENTS.md').read_bytes(),before)
        self.assertFalse(self.runtime.exists());self.assertFalse((self.project/'.ai/rev.json').exists())
    def test_bundle_integrity_and_extra_file_rejection(self):
        copy=self.root/'bundle';shutil.copytree(BUNDLE,copy,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        (copy/'unexpected.txt').write_text('extra')
        with self.assertRaises(ValueError):installer.verify_bundle(copy)
    def test_adoption_keeps_existing_project_facts_and_checks(self):
        path=self.project/'README.md';path.write_text('사용자 문서',encoding='utf-8')
        before={p.relative_to(self.project):p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        with patch.object(sys,'argv',['scaffold','--target',str(self.project),'--adopt','--files-only']):
            self.assertEqual(scaffold.main(),0)
        for name,data in before.items():self.assertEqual((self.project/name).read_bytes(),data)
    def test_template_has_unset_facts_and_checks(self):
        text=(BUNDLE/'assets/starter/PROJECT.md').read_text(encoding='utf-8')
        self.assertNotIn('Rush Hour',text);self.assertNotIn('Echo Garden',text)
        from runner.settings import config_from
        commands,_=config_from(BUNDLE/'assets/starter/.ai/verification.yaml')
        self.assertTrue(commands['commands']);self.assertTrue(all(v is None for v in commands['commands'].values()))

class SourceInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'project';self.project.mkdir()
    def install(self, snapshot='a'*40):
        with installer.source_locks(self.project):
            return installer.source_install(BUNDLE,self.project,snapshot)
    def test_fresh_client_install_never_probes_hardware_models_or_service(self):
        with patch.object(installer,'diagnose',side_effect=AssertionError('hardware probe')), patch.object(installer.Client,'ready',side_effect=AssertionError('service probe')):
            self.assertEqual(self.install()['source_status'],'installed')
            self.assertEqual(self.install()['source_status'],'current')
        installer.verify_bundle(self.project/'.ai/starter-source')
        self.assertFalse((self.project/'.ai/rev.json').exists())
        self.assertFalse((self.project/'.ai/rev-install.json').exists())
        self.assertEqual(self.install()['rev_status'],'preparation_needed')
    def test_sev_rev_adoption_and_source_update_preserve_custom_bytes_and_history(self):
        saved={'AGENTS.md':b'custom guidance','PROJECT.md':b'facts','README.md':b'user readme',
               '.ai/models.yaml':b'custom model','.ai/routing.yaml':b'custom routing',
               '.ai/verification.yaml':b'custom verification','.ai/config.yaml':b'user settings',
               '.ai/sev.json':b'{"version":"0.3.2","deployment":"old"}',
               '.ai/rev.json':b'{"runtime_id":"preserved"}',
               '.ai/rev-install.json':b'{"deployment":"preserved"}',
               '.ai/project-workflow/state.json':b'{"status":"completed","tasks":[{"id":"done"}]}',
               '.ai/reports/old.json':b'{"status":"completed","result":"keep"}', '.env':b'secret-fixture'}
        for name,data in saved.items():
            path=self.project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.install();receipt=self.project/installer.SOURCE_RECEIPT
        value=json.loads(receipt.read_text());value['version']='0.3.3'
        prior=self.project/'.ai/starter-source/release.json';release=json.loads(prior.read_text());release['version']='0.3.3'
        prior.write_text(json.dumps(release));value['sha256']['.ai/starter-source/release.json']=hashlib.sha256(prior.read_bytes()).hexdigest()
        receipt.write_text(json.dumps(value))
        self.assertTrue(self.install()['changed'])
        for name,data in saved.items():self.assertEqual((self.project/name).read_bytes(),data)
        value=json.loads(receipt.read_text());value['version']='9.0.0';receipt.write_text(json.dumps(value))
        self.assertEqual(self.install()['source_status'],'newer')
    def test_modified_unknown_and_unreceipted_source_stops(self):
        self.install();path=self.project/'.ai/starter-source/assets/runner/run.py'
        before=path.read_bytes();path.write_bytes(b'custom')
        with self.assertRaisesRegex(ValueError,'Modified'):self.install()
        path.write_bytes(before);extra=self.project/'.ai/starter-source/unknown.py';extra.write_bytes(b'custom')
        with self.assertRaisesRegex(ValueError,'Unknown'):self.install()
        extra.unlink();(self.project/installer.SOURCE_RECEIPT).unlink()
        with self.assertRaisesRegex(ValueError,'Unreceipted'):self.install()
    def test_active_unknown_and_missing_status_stop_before_copy(self):
        state=self.project/'.ai/rev-workflow/state.json';state.parent.mkdir(parents=True)
        for status in ('running','failed','unknown',None):
            state.write_text(json.dumps(dict(status=status)))
            with self.assertRaisesRegex(ValueError,'Active or uncertain'):self.install()
            self.assertFalse((self.project/'.ai/starter-source').exists())
    def test_failed_write_rolls_back_and_retry_completes(self):
        original=installer.replace_document
        def fail(path,before,after):
            if path.name=='source-install.json':raise OSError('injected interruption')
            return original(path,before,after)
        with patch.object(installer,'replace_document',side_effect=fail):
            with self.assertRaises(OSError):self.install()
        self.assertFalse((self.project/'.ai/source-transaction.json').exists())
        self.assertFalse((self.project/'AGENTS.md').exists())
        self.assertFalse((self.project/'.ai/starter-source').exists())
        self.assertTrue(self.install()['changed'])
    def test_recovery_preserves_concurrent_edit_and_ambiguous_journal(self):
        import base64
        path=self.project/'.ai/source-transaction.json';path.parent.mkdir(parents=True)
        entry=dict(name='AGENTS.md',before=None,after=base64.b64encode(b'owned').decode())
        path.write_text(json.dumps(dict(schema=1,entries=[entry])))
        (self.project/'AGENTS.md').write_bytes(b'concurrent user edit')
        with self.assertRaisesRegex(ValueError,'Concurrent'):self.install()
        self.assertTrue(path.exists());self.assertEqual((self.project/'AGENTS.md').read_bytes(),b'concurrent user edit')
        entry['name']='../outside';path.write_text(json.dumps(dict(schema=1,entries=[entry])))
        with self.assertRaisesRegex(ValueError,'Unsafe'):self.install()

if __name__=='__main__':unittest.main()
