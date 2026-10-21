"""Controller subprocess gates. Unknown relevance/tooling never grants cached success."""
import copy
import hashlib
import json
import os
import subprocess
import time

from rev import contracts as c
from .runtime_safety import redact


def fingerprint(workspace, configuration, tooling=None):
    return hashlib.sha256(json.dumps(dict(workspace=workspace, configuration=configuration, tooling=tooling),
                                    sort_keys=True, ensure_ascii=False, allow_nan=False,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def environment_identity():
    # Hash only: never store environment values, which may contain credentials.
    return hashlib.sha256(c.json_bytes(dict(sorted(os.environ.items())))).hexdigest()


def validate_relevance(proof, name, command, scope, stamp):
    """Only explicit controller/user-reviewed exclusions, never a model's claim.

    The caller owns review authorization and supplies this out of band; the CLI does
    not import exclusions from plans, model output or old state. Uncertainty => run.
    """
    c.obj(proof, ('name', 'command', 'scope', 'state_sha256', 'reason', 'review_id', 'source'))
    c.require(proof['source'] == 'explicit_user_review' and proof['name'] == name
              and proof['command'] == command and proof['scope'] == scope
              and proof['state_sha256'] == stamp, 'irrelevance requires current explicit review evidence')
    c.text(proof['reason']); c.text(proof['review_id'])
    return proof


def validate_results(checks, commands, scope, relevance=None):
    c.require(isinstance(checks, list) and len(checks) == len(commands), 'controller evidence must cover all configured checks')
    seen = set()
    for check in checks:
        c.validate_evidence(check)
        name = check['name']
        c.require(name in commands and name not in seen and check['command'] == commands[name]
                  and check['scope'] == scope and check['producer'] == 'controller_subprocess',
                  'mismatched controller evidence; model reports never satisfy required checks')
        c.require((check['status'] == 'unset') == (commands[name] is None), 'unset command mismatch')
        if check['status'] == 'irrelevant_skipped':
            proof = (relevance or {}).get(name)
            c.require(proof is not None, 'irrelevant skip has no explicit review evidence')
            validate_relevance(proof, name, commands[name], scope, check['state_sha256'])
            c.require(check['reason'] == 'irrelevant: ' + proof['review_id'] + ': ' + proof['reason'],
                      'irrelevance evidence mismatch')
        seen.add(name)
    return checks


def run_checks(project, commands, deadline, state_sha256, scope='task', relevance=None):
    """All configured commands run unless explicit current exclusion is supplied."""
    c.require(scope in ('task', 'milestone', 'final'), 'invalid check scope')
    checks = []
    for name, command in commands.items():
        evidence = dict(name=name, command=command, scope=scope,
                        status='unset' if command is None else 'required',
                        producer='controller_subprocess', state_sha256=state_sha256 if command else None,
                        executed=False, exit_code=None,
                        reason='command unset; not passed' if command is None else 'not executed')
        checks.append(evidence)
        proof = (relevance or {}).get(name)
        uncertain_relevance = False
        if command is not None and proof is not None:
            try:
                validate_relevance(proof, name, command, scope, state_sha256)
            except (ValueError, TypeError, KeyError):
                uncertain_relevance = True  # Retain the FULL configured suite.
            else:
                evidence.update(status='irrelevant_skipped', reason='irrelevant: ' + proof['review_id'] + ': ' + proof['reason'])
                continue
        if command is None or time.monotonic() >= deadline:
            if command is not None:
                evidence['reason'] = 'controller time budget exhausted; not executed'
            continue
        script = ("$ErrorActionPreference = 'Stop'\n$global:LASTEXITCODE = $null\n" + command +
                  '\n$revCheckSucceeded = $?\nif ($null -ne $global:LASTEXITCODE) { exit $global:LASTEXITCODE }\n'
                  'if (-not $revCheckSucceeded) { exit 1 }')
        args = (['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script]
                if os.name == 'nt' else ['/bin/sh', '-c', command])
        try:
            result = subprocess.run(args, cwd=project, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=max(.001, deadline-time.monotonic()), shell=False)
            evidence.update(executed=True, exit_code=result.returncode,
                            status='passed' if result.returncode == 0 else 'failed',
                            reason=redact(result.stdout + result.stderr) or '(no output)')
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
            partial = redact(decoded(error.stdout) + decoded(error.stderr))
            evidence.update(executed=True, status='failed',
                            reason='configured command timed out; exit code unknown; inspect possible partial edits: ' + partial)
        except OSError as error:
            # Launch failed: no subprocess was observed running.
            evidence.update(status='required', reason='configured command could not start; not executed: ' + redact(str(error)))
        if uncertain_relevance:
            evidence['reason'] = 'irrelevance uncertain; full check retained: ' + evidence['reason']
        c.validate_evidence(evidence)
    return checks


def satisfied(checks, current_sha256, relevance=None):
    if not checks:
        return False
    passed = False
    for check in checks:
        c.validate_evidence(check)
        if check['status'] == 'unset':
            continue
        if check['status'] == 'irrelevant_skipped':
            try:
                validate_results([check], {check['name']: check['command']}, check['scope'], relevance)
            except (ValueError, TypeError, KeyError):
                return False
            if check['state_sha256'] != current_sha256:
                return False
        elif not c.evidence_satisfies(check, current_sha256):
            return False
        else:
            passed = True
    # Empty/all-unset/all-skipped suites are not actual successful verification.
    return passed


class EvidenceCache:
    """In-memory, per-controller only. No toolchain attestation => no reuse.

    complete=True is an embedding controller's explicit attestation that identity
    covers ALL command tools, dependencies, external inputs and assumptions. The
    stock CLI cannot establish this for arbitrary shell commands and never opts in.
    Scope and command definitions are part of the key; task evidence cannot silently
    become final evidence. Environment changes invalidate even an attested identity.
    """
    def __init__(self):
        self.entries = {}

    def key(self, stamp, commands, scope, tooling):
        if not isinstance(tooling, dict) or tooling.get('complete') is not True:
            return None
        c.obj(tooling, ('complete', 'sha256'))
        c.digest(tooling['sha256'])
        return fingerprint(dict(state=stamp, environment=environment_identity()),
                           dict(commands=commands, scope=scope), tooling)

    def get(self, stamp, commands, scope, tooling):
        key = self.key(stamp, commands, scope, tooling)
        checks = self.entries.get(key) if key else None
        return copy.deepcopy(checks) if checks and satisfied(checks, stamp) else None

    def put(self, stamp, commands, scope, tooling, checks):
        validate_results(checks, commands, scope)
        key = self.key(stamp, commands, scope, tooling)
        if key and satisfied(checks, stamp):
            self.entries[key] = copy.deepcopy(checks)


def concise(checks):
    return [{k: x[k] for k in ('name', 'command', 'scope', 'status', 'producer', 'executed', 'exit_code')}
            for x in checks]
