"""Project workflow regression coverage.
Model/SEV are mocked; configured verification commands run as real subprocesses.
Tests named observation document existing limitations, not desired regressions.
"""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

HERE=Path(__file__).resolve().parents[1]
SOURCE=HERE
sys.dont_write_bytecode=True
sys.path.insert(0,str(SOURCE/'assets/runner'))
import project
import run as runner
import runtime_safety as safety


@contextmanager
def scratch_temp(*args,**kwargs):
    root=HERE.parent/'.workflow-test-scratch';root.mkdir(exist_ok=True)
    path=root/uuid.uuid4().hex;path.mkdir()
    try: yield str(path)
    finally:
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('unsafe cleanup')
        shutil.rmtree(path)


class ProjectModeAudit(unittest.TestCase):
    def setUp(self):
        self.temp=scratch_temp();self.base=Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__,None,None,None)
        self.target=self.base/'project';shutil.copytree(SOURCE/'assets/starter',self.target)
        self.state_path=self.target/'.ai/project-workflow/state.json'
        self.goal=self.base/'goal.txt';self.goal.write_text('Create two verified sequential fixture artifacts.',encoding='utf-8')
        self.events=[];self.behavior={};self.approval_second=False
        self.model_override='main';self.requested_models=[];self.prompt_sizes=[]
        self.planning_instruction='Create a fixture artifact.'
        check=self.target/'check.py'
        check.write_text("from pathlib import Path\nimport sys\np=Path('checks.log')\np.write_text((p.read_text() if p.exists() else '')+'check\\n')\nsys.exit(9 if Path('fail-check').exists() or not Path('artifact.txt').exists() else 0)\n")
        quote=lambda text: "'"+str(text).replace("'","''")+"'"
        command=('& '+quote(sys.executable)+' '+quote(check)) if os.name=='nt' else quote(sys.executable)+' '+quote(check)
        (self.target/'.ai/verification.yaml').write_text('commands:\n  test: '+json.dumps(command)+'\n',encoding='utf-8')
        (self.target/'.ai/sev.json').write_text(json.dumps({'python':sys.executable,'runner':str(Path(runner.__file__).resolve()),
             'service':'mock-service','state':'mock-service-state'}),encoding='utf-8')
        for item in (patch.object(tempfile,'TemporaryDirectory',scratch_temp),
                     patch.object(safety,'private_permissions'),
                     patch.object(runner,'invoke',side_effect=self.invoke)):
            item.start();self.addCleanup(item.stop)

    def plan(self):
        scope={'facts':[],'risks':[],'dependencies':[]}
        return {'tasks':[
            {'id':'one','title':'First fixture','instructions':self.planning_instruction,'depends_on':[],
             'approval_required':False,'selection_context':scope},
            {'id':'two','title':'Second fixture','instructions':'Append a second fixture.','depends_on':['one'],
             'approval_required':self.approval_second,'selection_context':scope}]}

    def invoke(self,codex,model,cwd,prompt,timeout,**kwargs):
        self.requested_models.append(model)
        self.prompt_sizes.append({'write':kwargs['write'],'characters':len(prompt)})
        if not kwargs['write']:
            self.events.append(('plan',False))
            summary='Structured fixture plan'
            outcome='completed'
        else:
            task=json.JSONDecoder().raw_decode(prompt.split('\nCurrent task:\n',1)[1])[0]
            name=task['id'];self.events.append((name,True))
            behavior=self.behavior.get(name)
            if behavior=='interrupt':
                (self.target/'partial.txt').write_text('partial fixture')
                raise KeyboardInterrupt()
            if behavior=='blocked':
                outcome='blocked'
            else:
                artifact=self.target/'artifact.txt'
                artifact.write_text((artifact.read_text() if artifact.exists() else '')+name+'\n')
                outcome='completed'
                if behavior=='config-change':
                    with (self.target/'.ai/routing.yaml').open('a',encoding='utf-8') as stream:stream.write('\n# changed in model fixture\n')
            summary='fixture outcome'
        result={'outcome':outcome,'summary':summary,'verification':[
            {'name':'test','command':runner.config_from(self.target/'.ai/verification.yaml')[0]['commands']['test'] or '',
             'executed':False,'exit_code':None,'evidence':'controller executes configured check'}],'escalation':None}
        if not kwargs['write']: result['plan']=self.plan()
        return {'response':json.dumps(result),'usage':{'input_tokens':1,'output_tokens':1}}

    def call(self,action,*extra):
        args=[action,'--project',str(self.target)]
        if action=='start':
            args+=['--goal-file',str(self.goal),'--codex',sys.executable]
            if self.model_override:args+=['--model',self.model_override]
        args+=list(extra)
        out=io.StringIO()
        with redirect_stdout(out),redirect_stderr(out):code=project.main(args)
        self.last_output=out.getvalue()
        state=json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else None
        return code,state

    def checks(self):
        path=self.target/'checks.log'
        return len(path.read_text().splitlines()) if path.exists() else 0

    def test_full_plan_two_tasks_and_real_subprocess_checks(self):
        code,state=self.call('start','--write')
        self.assertEqual(code,0,self.last_output)
        self.assertEqual(state['status'],'completed')
        self.assertEqual(self.events,[('plan',False),('one',True),('two',True)])
        self.assertEqual(self.checks(),2)
        self.assertEqual((self.target/'artifact.txt').read_text(),'one\ntwo\n')
        self.assertEqual(state['attempts'][-1]['verification']['test']['evidence_source'],'workflow_subprocess')

    def test_readonly_plan_then_resume_without_replanning(self):
        code,state=self.call('start')
        self.assertEqual(code,1);self.assertEqual(state['status'],'approval_required')
        self.assertEqual(self.events,[('plan',False)]);self.assertEqual(self.checks(),0)
        code,state=self.call('resume','--write')
        self.assertEqual(code,0,self.last_output)
        self.assertEqual(self.events,[('plan',False),('one',True),('two',True)])

    def test_duplicate_start_preserves_saved_state(self):
        self.call('start');saved=self.state_path.read_bytes()
        code,_=self.call('start','--write')
        self.assertEqual(code,1);self.assertEqual(saved,self.state_path.read_bytes())

    def test_approval_blocks_then_executes_only_remaining_task(self):
        self.approval_second=True
        _,state=self.call('start','--write')
        self.assertEqual(state['status'],'approval_required');self.assertEqual(self.checks(),1)
        before=list(self.events)
        self.call('resume','--write')
        self.assertEqual(self.events,before)
        code,state=self.call('resume','--write','--approve','two')
        self.assertEqual(code,0,self.last_output)
        self.assertEqual(self.events.count(('one',True)),1)
        self.assertEqual(self.events.count(('two',True)),1)

    def test_failed_check_stops_dependencies_and_requires_retry(self):
        (self.target/'fail-check').touch()
        _,state=self.call('start','--write')
        self.assertEqual(state['tasks'][0]['status'],'failed')
        self.assertEqual(state['tasks'][1]['status'],'pending')
        self.assertNotIn(('two',True),self.events)
        before=list(self.events);self.call('resume','--write');self.assertEqual(self.events,before)
        (self.target/'fail-check').unlink()
        code,_=self.call('resume','--write','--retry','one')
        self.assertEqual(code,0,self.last_output)

    def test_blocked_task_requires_both_approval_and_retry(self):
        self.behavior['one']='blocked'
        _,state=self.call('start','--write')
        self.assertEqual(state['tasks'][0]['status'],'blocked')
        self.behavior.clear();before=list(self.events)
        self.call('resume','--write','--approve','one');self.assertEqual(self.events,before)
        code,_=self.call('resume','--write','--approve','one','--retry','one')
        self.assertEqual(code,0,self.last_output)

    def test_interruption_keeps_partial_edits_and_never_silently_replays(self):
        self.behavior['one']='interrupt'
        _,state=self.call('start','--write')
        self.assertEqual(state['tasks'][0]['status'],'running')
        self.assertTrue((self.target/'partial.txt').exists())
        before=list(self.events);self.call('resume','--write');self.assertEqual(self.events,before)
        self.behavior.clear();code,_=self.call('resume','--write','--retry','one')
        self.assertEqual(code,0,self.last_output)
        self.assertTrue((self.target/'partial.txt').exists())

    def test_run_budget_stops_after_plan_and_requires_explicit_extension(self):
        _,state=self.call('start','--write','--max-runs','1')
        self.assertEqual(state['status'],'budget_exhausted');self.assertEqual(state['runs'],1)
        self.assertEqual(self.events,[('plan',False)])
        code,_=self.call('resume','--write','--max-runs','3')
        self.assertEqual(code,0,self.last_output)

    def test_configuration_change_blocks_resume(self):
        self.call('start')
        with (self.target/'.ai/routing.yaml').open('a') as stream:stream.write('\n# fixture change\n')
        before=list(self.events);code,_=self.call('resume','--write')
        self.assertEqual(code,1);self.assertEqual(before,self.events)
        self.assertIn('configuration changed',self.last_output)

    def test_midtask_configuration_change_blocks_verification_and_dependencies(self):
        self.behavior['one']='config-change'
        _,state=self.call('start','--write')
        self.assertEqual(state['status'],'stopped');self.assertEqual(self.checks(),0)
        self.assertNotIn(('two',True),self.events)

    def test_all_unset_checks_never_complete(self):
        (self.target/'.ai/verification.yaml').write_text('commands:\n  test: null\n')
        _,state=self.call('start','--write')
        self.assertEqual(state['tasks'][0]['status'],'unresolved')
        self.assertNotEqual(state['status'],'completed')

    def test_status_does_not_invoke_models(self):
        self.call('start');before=list(self.events)
        code,_=self.call('status')
        self.assertEqual(code,0);self.assertEqual(before,self.events)
        self.assertNotIn('Create two verified',self.last_output)

    def test_credential_example_plan_survives_masking_save_and_resume(self):
        self.planning_instruction='Create a dummy config with token=EXAMPLE value.'
        code,state=self.call('start')
        self.assertEqual(code,1)
        self.assertEqual(state['plan_status'],'completed')
        self.assertNotIn('EXAMPLE',state['tasks'][0]['instructions'])
        self.assertIn('[REDACTED]',state['tasks'][0]['instructions'])
        self.assertIsInstance(state['attempts'][0]['report']['attempts'][0]['outcome']['plan'],dict)
        code,state=self.call('resume','--write')
        self.assertEqual(code,0,self.last_output)

    def test_completed_artifact_changes_require_reverification_without_model_replay(self):
        self.call('start','--write');before=list(self.events)
        (self.target/'artifact.txt').unlink()
        code,state=self.call('resume','--write')
        self.assertEqual(code,1)
        self.assertEqual(state['status'],'workspace_changed')
        self.assertEqual(self.events,before)
        code,state=self.call('resume','--write','--reverify')
        self.assertEqual(code,1)
        self.assertEqual(state['status'],'workspace_changed')
        (self.target/'artifact.txt').write_text('one\ntwo\n')
        code,state=self.call('resume','--write','--reverify')
        self.assertEqual(code,0,self.last_output)
        self.assertEqual(self.events,before)
        self.assertEqual(state['status'],'completed')

    def test_observation_status_omits_pending_task_details(self):
        self.approval_second=True;self.call('start','--write')
        self.call('status');printed=json.loads(self.last_output)
        self.assertNotIn('tasks',printed)
        self.assertNotIn('approved',printed)
        self.assertEqual(printed['status'],'approval_required')

    def test_sev_is_called_for_plan_and_each_task_and_selected_models_are_used(self):
        self.model_override=None
        selections=[];real_run=project.subprocess.run
        roles=iter(['main','worker','main'])
        def service_or_check(command,*args,**kwargs):
            if isinstance(command,list) and 'mock-service' in command:
                task=Path(command[command.index('--task-file')+1]).read_text(encoding='utf-8')
                facts=Path(command[command.index('--context-file')+1]).read_text(encoding='utf-8')
                selections.append((task,facts))
                return __import__('types').SimpleNamespace(returncode=0,stderr='',stdout=json.dumps(
                    {'ok':True,'pid':42,'requests':len(selections),
                     'selection':{'role':next(roles),'backend':'local','api_calls':0}}))
            return real_run(command,*args,**kwargs)
        with patch.object(project.subprocess,'run',side_effect=service_or_check):
            code,state=self.call('start','--write')
        self.assertEqual(code,0,self.last_output)
        self.assertEqual(len(selections),3)
        self.assertIn('Plan this explicitly requested',selections[0][0])
        self.assertEqual(selections[1][0],'First fixture\nCreate a fixture artifact.')
        self.assertEqual(selections[2][0],'Second fixture\nAppend a second fixture.')
        self.assertEqual(json.loads(selections[2][1])['depends_on'],['one'])
        models=runner.models_from(self.target/'.ai/models.yaml')
        self.assertEqual(self.requested_models,[models['main'],models['worker'],models['main']])
        self.assertEqual(self.checks(),2)

    def test_explicit_override_skips_sev_for_entire_project(self):
        calls=[];real_run=project.subprocess.run
        def service_or_check(command,*args,**kwargs):
            if isinstance(command,list) and 'mock-service' in command:
                calls.append(command);raise AssertionError('override must bypass SEV')
            return real_run(command,*args,**kwargs)
        with patch.object(project.subprocess,'run',side_effect=service_or_check):
            code,_=self.call('start','--write')
        self.assertEqual(code,0,self.last_output)
        self.assertEqual(calls,[])
        self.assertEqual(self.requested_models,[runner.models_from(self.target/'.ai/models.yaml')['main']]*3)

    def test_external_changes_during_approval_require_checks_without_replaying(self):
        self.approval_second=True
        self.call('start','--write')
        (self.target/'artifact.txt').write_text('externally edited\n')
        before=list(self.events)
        code,state=self.call('resume','--write','--approve','two')
        self.assertEqual(code,1)
        self.assertEqual(state['status'],'workspace_changed')
        self.assertEqual(self.events,before)
        code,state=self.call('resume','--write','--approve','two','--reverify')
        self.assertEqual(code,0,self.last_output)
        self.assertEqual(self.events,before+[('two',True)])
        self.assertEqual(self.checks(),3)

    def test_old_state_is_readable_but_not_resumed_or_rewritten(self):
        self.call('start')
        state=json.loads(self.state_path.read_text(encoding='utf-8'))
        state['version']=2
        self.state_path.write_text(json.dumps(state),encoding='utf-8')
        saved=self.state_path.read_bytes();before=list(self.events)
        code,_=self.call('status')
        self.assertEqual(code,0)
        code,_=self.call('resume','--write')
        self.assertEqual(code,1)
        self.assertEqual(self.events,before)
        self.assertEqual(self.state_path.read_bytes(),saved)

    def test_completed_task_definitions_do_not_accumulate_in_later_prompts(self):
        scope={'facts':[],'risks':[],'dependencies':[]}
        tasks=[{'id':'step'+str(i),'title':'Fixture step '+str(i),
                'instructions':'Write a fixture artifact. '*15,'depends_on':[] if i==0 else ['step'+str(i-1)],
                'approval_required':False,'selection_context':scope} for i in range(10)]
        self.plan=lambda:{'tasks':tasks}
        with patch.object(project,'real_checks',return_value={'test':{'status':'passed'}}):
            code,_=self.call('start','--write')
        self.assertEqual(code,0,self.last_output)
        sizes=[item['characters'] for item in self.prompt_sizes if item['write']]
        self.assertEqual(len(sizes),10)
        self.assertLess(sizes[-1],sizes[0]+1600)



if __name__=='__main__':unittest.main(verbosity=2)
