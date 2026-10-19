# Optional project workflow

Automatically use this workflow when a user gives a project-sized goal that needs
multiple implementation steps, milestones or cross-subsystem work. The user should only
state the goal; don't require a special phrase or individual subtask prompts. Ordinary
questions and small contained edits keep the existing single-run SEV path. This mode
is a deterministic outer controller, not a team of agents. It never enables routing
orchestration flags, paid classification, automatic escalation or per-task LLM evaluation.
Each planning/implementation invocation uses the configured quick runner and persistent
SEV, or the user's worker/main override. The app conversation model does not change.

Rebuild the Starter package and reinstall SEV to install `scripts/project.py` next to
`scripts/run.py`. `.ai/sev.json` then contains `project_runner`. Existing personal
installations are not updated by editing source. The command examples below use
PowerShell variables read from that file, without hardcoded machine paths:

```powershell
$sev = Get-Content .ai/sev.json -Raw | ConvertFrom-Json
# Write your goal to goal.txt; context.txt is optional, already known project facts.
& $sev.python $sev.project_runner start --project . --goal-file goal.txt --context-file context.txt --write --max-runs 20 --max-seconds 3600
& $sev.python $sev.project_runner status --project .
& $sev.python $sev.project_runner resume --project . --write
```

The controller makes one read-only planning call. Its structured outcome has a dedicated typed `plan` object, separate from the human
`summary`, containing a validated task list (id, title, instructions/acceptance criteria,
depends_on, approval_required, selection_context). Unknown dependencies, cycles, duplicate ids and
invalid fields stop execution. It saves the plan before implementation and executes
one ready task at a time, in stable plan order. It does not automatically replan.
Starting without `--write` creates a reviewable plan and stops before implementation.
`--model worker|main` on start is retained for the entire workflow; otherwise each
invocation uses local SEV. No invocation recursively launches this controller.


Model selection and execution have separate inputs. Planning is classified using the
full goal and known facts, since design/decomposition is its actual scope. The planner
must give every implementation task a `selection_context` object with three lists of
nonempty strings: `facts`, `risks`, `dependencies` (empty lists allowed when nothing
applies). It must carry applicable overall constraints, security/architecture/impact
risks, uncertain interfaces and dependency assumptions into that task, without copying
unrelated history or suppressing risks to obtain worker. Selection uses the complete
current title/instructions plus this context, dependency ids and approval flag. Retry
also includes previous outcomes, errors and verification evidence. There is no keyword
stripping, risk-summary classifier, threshold change, worker quota or guarantee of
worker selection. Planner omissions remain a model-judgment limitation; review the plan
when important risks are involved.

Execution gets the full original goal and facts, the current task, approval and a
bounded previous-attempt diagnostic. Only direct dependencies contribute result
summaries (up to 1,200 characters), changed paths (up to 20) and check statuses.
Completed task instructions and unrelated results are not repeatedly appended.
Detailed evidence remains in private state. This reduces repeated context; it is
not a measured token, price or model-quality guarantee. `run.py` accepts optional
`--selection-task-file` and `--selection-context-file`; without them the quick path is
unchanged. Selection context requires a selection task file; a separate task without
context intentionally selects on that task alone. Overrides skip selection. Exact
selection input fingerprints (hash and length) are saved in runner reports; controller
attempts persist the redacted scope needed for resume. Raw prompts are not retained
in quick-runner reports. Never embed credentials; use environment references.

New workflows use state schema 3. Schemas 1 and 2 remain readable with `status`,
but cannot resume under the new plan/context/fingerprint contract. Inspect pending
edits and archive the old workflow directory before starting again. Old completed
tasks are never automatically migrated or replayed. Schema 3 plans are validated
again on resume. Existing budgets, approvals, explicit retries and overrides remain.
Credential masking preserves JSON structure and is safe to apply repeatedly.
Never put real credentials in goals, plans or context.

After every successful implementation call, the controller runs **all non-null
configured commands** from `.ai/verification.yaml`, in mapping order, in the project
directory. Choose checks suitable for the whole project before starting. Windows
commands run through `powershell.exe -NoProfile -NonInteractive -Command`; other
platforms use `/bin/sh -c`. Check keys and strings are preserved exactly, including
`test`. Output, execution flags and exit codes are saved as `workflow_subprocess`
evidence, separately from the selected model's report. There are no invented `runner`
checks. Supplemental checks in model responses belong in summary. Unset checks are
unset; no configured checks means unresolved rather than verified completion. The
model is instructed to leave controller checks unexecuted in its report to avoid
running the same checks twice. The quick runner receives verification_owner=controller
and returns awaiting_verification. This is a candidate result; the controller runs
real checks before final completion. Quick model-owned calls require configured checks
to pass; not_executed, missing and all-null checks cannot claim completion.

State and attempt reports live in `.ai/project-workflow/state.json` (ignored by the
bundled .gitignore). Known credentials are redacted; inputs should use secret references.
Private writes set current-user permissions before writing and replace atomically.
Console status shows only a summary. Inspect private state locally when needed.
Writes are atomic and an OS lock prevents overlapping controller processes. Completed
tasks are never replayed on resume. The goal, facts, model override, budgets, approval
decisions, attempts and configuration hashes persist. A changed project location or
models/routing/verification/SEV configuration blocks resume; reconcile the workspace
and archive the workflow directory before a new start. To start another goal, archive
that directory after the previous process has stopped. No automatic deletion occurs.

After each attempt the controller records a SHA256 workspace fingerprint. On resume,
external additions, modifications or deletions after completed work stop with
`workspace_changed`. Inspect edits, then use `resume --project . --write --reverify`.
This reruns configured checks and updates the baseline only when all pass; it does
not replay completed model calls. Failed checks preserve the stop and edits.
An explicit `--retry TASK_ID` accepts partial edits for that stopped task and still
requires checks after the retry. Reverification consumes the active-time budget.
Before any task has completed, edits can update the baseline without attesting completion.

Fingerprints ignore version control, dependencies, virtual environments, caches,
SEV runtime, private workflow/reports, installation locks and secret `.env` files.
Example env files remain included. Links/reparse points are recorded without
following them; external link targets are not monitored. This detects ordinary
workspace changes, not concurrent editing or changes to excluded/external resources.
Keep verification checks deterministic and relevant to the project.

Stops are explicit:

- Failed model/SEV calls, malformed plans, unresolved/blocked results or failed checks
  stop dependent work. There is no paid fallback or automatic retry.
- Approval tasks stop before invocation. After reviewing the saved task, approve only
  that task with `resume --project . --write --approve TASK_ID`. The plan asks the model
  to mark publishing/deployment/destructive/external actions; this is model judgment,
  not a deterministic security sandbox. Newly discovered approval needs must return
  blocked; inspect the report before explicitly approving/retrying the task.
- Interrupted work remains running/uncertain. Inspect edits and ensure any child
  processes have stopped, then use `resume --project . --write --retry TASK_ID` (or
  `--retry plan`). Retry explicitly authorizes another invocation against the current
  workspace; it does not roll back edits. A blocked task needing approval also needs
  `--approve TASK_ID`; the controller records that approval and passes it to the model.
- `max-runs` counts every planning/implementation attempt, including failures and
  interrupted calls. `max-seconds` limits active controller time and sets subprocess
  deadlines. After a hard crash, unaccounted elapsed time, including downtime, is
  conservatively charged on resume. Extend budgets only explicitly with
  `resume --project . --write --max-runs 30 --max-seconds 7200`. These are invocation/time
  limits, not hard token/spend limits. Subprocess timeout terminates the immediate
  child; grandchildren may require manual reconciliation before retry. CLI token
  usage, when exposed, is preserved inside attempt reports.

`status` returns zero for a readable state; start/resume return zero only for verified
completion, one for a stop. State retains the concrete stop reason and task/check
evidence. This smallest workflow has one active goal per project, no background daemon,
no automatic recovery/replanning and no guarantee of unattended deployment safety.

Source verification (no paid calls):

```text
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/package_starter.py --check
```

These are supplemental tooling checks, not a configured verification key named runner.
