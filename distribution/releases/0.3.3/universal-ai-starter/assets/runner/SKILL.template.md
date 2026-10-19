---
name: single-model-runner
description: Execute development requests through local SEV and one selected Codex model when enabled by project instructions or requested explicitly. General questions stay in the app chat.
---

# Single model runner

Read the project's `.ai/sev.json` for the installed Python, runner, service and state
paths. Do not invent machine paths. Pass the request via a UTF-8 task file
and only already available facts via an optional context file. No exploration to classify.

Run the configured Python with the configured runner and:
`--project <project> --models <project>/.ai/models.yaml --task-file <file>
--report <report.json> --selector sev --local-python <python> --local-script <service>
--sev-state <state>`. Add `--context-file` when needed. User model choices override
SEV via `--model worker|main`. Use `--write` only for authorized modifications.
Use `.ai/reports/` for private reports. Never embed credentials in requests; use
environment references. Known credential formats are filtered before execution and
in saved diagnostics. Console output is a compact status, not the complete report.

First use starts SEV if absent; later calls reuse it. Manage with configured Python:
`<service> start|status|stop --state <state>`. Windows installation starts it at sign-in.
Local socket access can require the tool's normal permission approval; do not bypass it.
On installation/runtime/selection failure report and stop; do not use paid classification.

The selected Codex CLI model owns exploration, implementation and verification.
No subagents, parallel execution or coordinator review. Do not redo its completed work
or call this runner recursively. Preserve the project's model mapping and permission rules.
The app conversation keeps its model. CLI requested_model is not backend-confirmed
actual_model unless events expose that information. Report actual outcome and checks.

SEV classification has no OpenAI tokens/API calls. App invocation and coding still use
tokens according to authentication. Do not change authentication or silently use an API key.

The runner reads project routing/verification settings and applies role reasoning.
Do not equate CLI turn completion with task success: report the structured outcome
and check states. Check evidence is selected-model reporting, not independent runner
observation. Missing/unset commands are not passed. Current-model backend and user
overrides retain the model. Only an explicitly requested sequential CLI workflow
may set execution.backend to codex_cli and pass --allow-escalation; never add that
flag implicitly. Only diagnosed capability problems beyond the model qualify;
environment/service/transient failures do not. Previous execution stops before the
next configured role starts. Existing installed copies require reinstall to update.
Quick completion requires all configured checks to pass and at least one configured
check. An explicit controller-owned call returns awaiting_verification, never completed;
only its controller can perform the final completion gate. Installation creates a new
runtime/runner deployment and preserves existing user skill documents.

## Automatic project workflow selection

Apply the separate `project-workflow` skill automatically when the user's goal is a
project-sized deliverable that needs multiple independently verifiable implementation
steps, milestones, or cross-subsystem changes. The user gives the goal once; do not ask
them to say “project workflow” or issue each subtask. Keep general questions, small
contained edits, and tasks with one clear implementation/check on the existing quick
single-run SEV path. Use only the request and already known project facts to choose;
don't launch a classifier or explore broadly just to classify. An explicit user model
choice is passed through the project workflow for every invocation.

The separate skill reads `project_runner` from `.ai/sev.json`; if absent, report that
the project installation needs updating and do not silently fall back to repeated
quick-runner calls. The controller plans once, persists the dependency-aware task list,
then sequentially invokes the quick runner and executes configured checks. It is an
outer controller exception; never invoke it recursively from a selected planning or
implementation task. Use `status`/`resume` for the same goal. Honor failure, approval,
and budget stops. Inspect concrete saved tasks before user approval. Never automatically
add `--approve`/`--retry` or increase budgets. No subagents, parallel execution, paid
API keys or frameworks. Report exact configured names/commands only in verification;
supplemental checks go in summary, never under an invented runner key.

Project-controller calls separate selection scope from execution context using optional
--selection-task-file and --selection-context-file. Ordinary calls keep their unchanged
task/context selection behavior. Do not manufacture a reduced scope for a quick call
merely to influence routing; retain relevant risks, dependencies and uncertainty.
