---
name: single-model-runner
description: Execute development requests through local SEV and one selected Codex model when enabled by project instructions or requested explicitly. General questions stay in the app chat.
---

# Single model runner

Read the project's `.ai/sev.json` for the installed Python, runner, service and state
paths. Do not invent machine paths. Pass the unchanged request via a UTF-8 task file
and only already available facts via an optional context file. No exploration to classify.

Run the configured Python with the configured runner and:
`--project <project> --models <project>/.ai/models.yaml --task-file <file>
--report <report.json> --selector sev --local-python <python> --local-script <service>
--sev-state <state>`. Add `--context-file` when needed. User model choices override
SEV via `--model worker|main`. Use `--write` only for authorized modifications.

First use starts SEV if absent; later calls reuse it. Manage with configured Python:
`<service> start|status|stop --state <state>`. Windows installation starts it at sign-in.
Local socket access can require the tool's normal permission approval; do not bypass it.
On installation/runtime/selection failure report and stop; do not use paid classification.

The one selected Codex CLI execution owns exploration, implementation and verification.
No subagents, parallel execution or coordinator review. Do not redo its completed work
or call this runner recursively. Preserve the project's model mapping and permission rules.
The app conversation keeps its model. CLI requested_model is not backend-confirmed
actual_model unless events expose that information. Report actual outcome and checks.

SEV classification has no OpenAI tokens/API calls. App invocation and coding still use
tokens according to authentication. Do not change authentication or silently use an API key.
