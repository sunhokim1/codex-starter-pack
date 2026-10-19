---
name: project-workflow
description: Automatically plan and carry out large software project goals through the installed local SEV/Codex runner, with resumable sequential tasks and real verification. Keep small questions and contained edits on the quick path.
---

# Project workflow

Use this skill automatically when the user gives a project-sized software goal that
requires multiple implementation steps, milestones, or cross-subsystem changes. The
user should only need to state the goal; do not require them to invoke this skill by
name or manually issue each task. For general questions, small edits, or one contained
change with a clear check, use the ordinary single-model runner instead.

Choose the mode using only the current request and already known project facts. Do not
call a classifier, create subagents, or explore broadly just to decide. Preserve an
explicit user model choice for every run. This controller is sequential and does not
change the app conversation model.

Read `.ai/sev.json` for the configured Python and `project_runner` paths. If the project
runner is missing, explain that the starter installation must be updated; do not emulate
the controller by issuing many quick-runner calls. Pass the user's goal and known facts
through UTF-8 files; use secret references rather than literal credentials (known
credential formats are filtered). For an authorized implementation request, start with:

```powershell
$sev = Get-Content .ai/sev.json -Raw | ConvertFrom-Json
& $sev.python $sev.project_runner start --project . --goal-file <goal-file> --context-file <context-file> --write
```

Omit `--context-file` when there are no additional known facts. Preserve user model
choices using `--model worker|main`. Defaults are at most 20 model invocations and
3600 active seconds; don't increase them without explicit authorization. The controller
creates a persisted task plan, then runs one dependency-ready task at a time through
the configured quick runner. It executes every configured verification command after
each implementation step and saves the actual subprocess results.

Use `status --project .` to inspect an existing workflow and `resume --project . --write`
to continue the same goal. Read `PROJECT-WORKFLOW.md` next to the installed runner
before using approval, retry, or budget options. Never retry interrupted edits
automatically, approve a task, or extend a budget without explicit authorization.
Report stop reasons, actual configured checks, and any checks that were unset or not
executed. Do not create per-task LLM eval reports; deterministic project verification
is the completion gate.

The workflow supports one active goal per project. It is deliberately sequential, has
no background daemon or automatic replanning, and does not promise unattended deployment.

The planner must provide task-specific selection_context (facts, risks, dependencies),
carrying applicable goal constraints and uncertainty without unrelated history or risk
suppression. The controller classifies complete current instructions with this scope;
execution receives the full original goal and known facts, the current task, approval
and a bounded previous-attempt diagnostic. Only direct dependencies contribute result
summaries (up to 1,200 characters), changed paths (up to 20) and check statuses.
Completed task instructions and unrelated results are not repeatedly appended.
Detailed evidence remains in private state; read relevant files or private state for
omitted details, but do not print private state. Review saved selection_scope/selection_input
for routing evidence; a worker/main classification is not proof of coding success or cost
savings.

New workflows use state schema 3. Schemas 1 and 2 remain readable via `status`, but
cannot resume under the schema 3 contract. Explicitly reconcile pending edits and
archive the old workflow directory before a new schema 3 start. Never automatically
migrate or replay old completed tasks, or rewrite completed history to resume it.
