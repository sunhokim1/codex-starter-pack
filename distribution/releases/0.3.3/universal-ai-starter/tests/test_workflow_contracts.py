"""Structured planning, minimal dependency context and workspace resume contracts."""
import json
from pathlib import Path
import re
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


def guidance_contract_errors(text):
    """Check schema/context promises, allowing layout and surrounding prose to vary."""
    text=' '.join(text.replace('`','').split())
    requirements={
        'new schema': r'New workflows use (?:state )?schema 3',
        'legacy status': r'Schemas 1 and 2 remain readable (?:via|with) status',
        'legacy resume stop': r'cannot resume under (?:the schema 3|the new .*?) contract',
        'explicit reconciliation': r'Explicitly reconcile pending edits and archive the old workflow directory before a new schema 3 start',
        'no replay': r'Never automatically migrate or replay old completed tasks',
        'original context': r'execution (?:receives|gets) the full original goal and (?:known )?facts, the current task',
        'bounded dependencies': r'Only direct dependencies contribute result summaries \(up to 1,200 characters\), changed paths \(up to 20\) and check statuses',
        'no accumulated history': r'Completed task instructions and unrelated results are not repeatedly appended',
        'private evidence': r'Detailed evidence remains in private state',
        'private read without disclosure': r'read relevant files or private state for omitted details, but do not print private state',
    }
    errors={name for name,pattern in requirements.items() if not re.search(pattern,text,re.I)}
    if re.search(r'full project context|new schema [12] start',text,re.I):
        errors.add('stale promises')
    return errors


class WorkflowContracts(unittest.TestCase):
    def test_released_workflow_guidance_matches_schema_and_execution_contract(self):
        guidance=(ROOT/'assets/project-workflow/SKILL.template.md').read_text(encoding='utf-8')
        self.assertEqual(guidance_contract_errors(guidance),set())

    def test_guidance_regression_rejects_original_schema_and_context_promises(self):
        guidance=' '.join((ROOT/'assets/project-workflow/SKILL.template.md').read_text(encoding='utf-8').split())
        # Exact original released tail: an offline negative fixture, never installed.
        original='''execution retains the full project context. Review saved selection_scope/selection_input
for routing evidence; a worker/main classification is not proof of coding success or cost
savings. Schema 1 audits remain readable via status but require explicit reconciliation
and archival before a new schema 2 start; never rewrite completed history to resume it.'''
        prefix=guidance.split('execution receives',1)[0]
        errors=guidance_contract_errors(prefix+original)
        self.assertTrue({'new schema','legacy status','legacy resume stop',
                         'original context','bounded dependencies','private evidence',
                         'stale promises'}.issubset(errors))
        # Independent mutations ensure either stale promise fails on its own.
        mutations={
            'new schema': ('New workflows use state schema 3.', 'New workflows use state schema 2.'),
            'legacy status': ('Schemas 1 and 2 remain readable', 'Schema 1 remains readable'),
            'legacy resume stop': ('cannot resume under', 'can resume under'),
            'explicit reconciliation': ('Explicitly reconcile pending edits', 'Ignore pending edits'),
            'no replay': ('Never automatically migrate or replay', 'Automatically migrate or replay'),
            'original context': ('full original goal and known facts', 'full project context'),
            'bounded dependencies': ('Only direct dependencies', 'All completed tasks'),
            'no accumulated history': ('are not repeatedly appended', 'are repeatedly appended'),
            'private evidence': ('Detailed evidence remains in private state', 'Detailed evidence is discarded'),
            'private read without disclosure': ('do not print private state', 'print private state'),
        }
        for contract,(before,after) in mutations.items():
            with self.subTest(contract=contract):
                self.assertIn(before,guidance)
                self.assertIn(contract,guidance_contract_errors(guidance.replace(before,after)))

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
