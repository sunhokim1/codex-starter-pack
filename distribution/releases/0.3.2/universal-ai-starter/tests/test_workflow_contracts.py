"""Structured planning, minimal dependency context and workspace resume contracts."""
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/runner'))
import run as runner
import project
import runtime_safety as safety
from workspace import changes, snapshot


class WorkflowContracts(unittest.TestCase):
    def test_redaction_is_idempotent_and_preserves_nested_json_quotes(self):
        examples=['token=EXAMPLE', 'password="dummy-value"', "api_key='dummy-value'",
                  'token="a \\" quoted value"', '한글 token=EXAMPLE 값']
        for example in examples:
            text=example
            for depth in range(3):
                with self.subTest(example=example,depth=depth):
                    filtered=safety.redact(text)
                    self.assertEqual(filtered,safety.redact(filtered))
                    self.assertNotIn('EXAMPLE',filtered)
                    self.assertNotIn('dummy-value',filtered)
                    if depth: self.assertIsInstance(json.loads(filtered),dict)
                text=json.dumps({'instructions':text},ensure_ascii=False)

    def test_structured_plan_schema_and_validation_are_separate_from_summary(self):
        schema=runner.outcome_schema({'test':None},planning=True)
        self.assertIn('plan',schema['required'])
        self.assertEqual(schema['properties']['plan']['properties']['tasks']['items']['type'],'object')
        outcome={'outcome':'completed','summary':'A short human summary, not JSON.',
                 'verification':[],'escalation':None,'plan':{'tasks':[]}}
        runner.validate_outcome(outcome,planning=True)
        with self.assertRaises(ValueError):project.validate_plan(outcome['plan'],True)
        outcome['plan']=None
        with self.assertRaises(ValueError):runner.validate_outcome(outcome,planning=True)

    def test_dependency_context_omits_unrelated_completed_instructions_and_limits_excerpts(self):
        task=lambda name: {'id':name,'title':name,'instructions':'do '+name,'depends_on':[],
            'approval_required':False,'selection_context':{'facts':[],'risks':[],'dependencies':[]},'status':'completed',
            'result':{'summary':'result '*1000,'changed_paths':['file'+str(i) for i in range(100)],'verification':{}}}
        unrelated=task('unrelated');unrelated['instructions']='MUST_NOT_RETRANSMIT'
        dependency=task('dependency');current=task('current');current['depends_on']=['dependency']
        state={'goal':'Keep all security constraints.','tasks':[unrelated,dependency,current],'approved':[]}
        request=project.execution_request(state,current,None)
        self.assertNotIn('MUST_NOT_RETRANSMIT',request)
        self.assertNotIn('do dependency',request)
        self.assertIn('Keep all security constraints.',request)
        self.assertIn('file19',request);self.assertNotIn('file20',request)
        self.assertIn('state.json',request)
        self.assertLess(len(request),3500)

    def test_snapshot_detects_add_modify_delete_and_ignores_private_runtime(self):
        root=ROOT.parent/('.workspace-contract-'+uuid.uuid4().hex);root.mkdir()
        try:
            (root/'source.py').write_text('one')
            before=snapshot(root)
            (root/'source.py').write_text('two');(root/'new.txt').write_text('new')
            (root/'.ai/project-workflow').mkdir(parents=True)
            (root/'.ai/project-workflow/state.json').write_text('private state')
            (root/'.env').write_text('not-a-real-credential')
            after=snapshot(root)
            self.assertEqual(changes(before,after),['new.txt','source.py'])
            (root/'source.py').unlink()
            self.assertEqual(changes(after,snapshot(root)),['source.py'])
        finally:
            if not root.resolve().is_relative_to(ROOT.parent.resolve()):raise ValueError('unsafe cleanup')
            shutil.rmtree(root)


if __name__=='__main__':unittest.main(verbosity=2)
