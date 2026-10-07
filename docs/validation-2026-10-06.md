# Native worker code validation — 2026-10-06

> Historical experiment record. Native worker delegation and parallel-agent orchestration were removed from the active starter in v0.2.6. This report does not define the current workflow.

Validation used isolated Python utility projects scaffolded from the registered skill.
The original starter remains uninitialized; its PROJECT.md, model mapping, history and ZIP were unchanged.
No framework, dependency or external API was installed or connected.

| Scenario | Explicit model selection | Result |
| --- | --- | --- |
| One small implementation: ASCII HH:MM:SS parser | worker: gpt-6-luna, low | 3 unittest methods passed |
| Two independent implementations: label normalization and integer-cent totals | two workers: gpt-6-luna, low | 2 label + 3 pricing + 1 integration methods passed |
| Controlled regression detected, then handed off for repair | main: gpt-6.1-sol, medium | expected failure detected; 3 methods passed after repair |

Tests were written before implementation and checked for modifications afterward. None changed.
Workers had disjoint write ownership (labels.py versus pricing.py). The coordinator reviewed the implementations
and independently ran `python -m unittest discover -s tests -v` for each completed project.
Cases included whitespace/Unicode normalization, malformed duration strings, integer validation excluding bool,
negative values, empty inputs and a receipt combining both parallel modules.

The escalation case deliberately injected an incorrect result (3720 instead of 3723 seconds) into a previously
passing worker implementation. Tests caught it; main removed the defect without altering tests.
This demonstrates native handoff and verification after a controlled failure, not a natural worker failure.

## Conclusions and limits

Single-worker implementation, two-worker parallel ownership, integration verification and main handoff worked
in this environment. No starter-policy correction was needed from this run.
Dispatch was performed by the coordinating agent following AGENTS.md/routing.yaml; no deterministic automatic
router or standalone model runner was added. This is a small smoke test, not evidence of production quality,
cost savings, speed improvements, automatic failure classification or Astra escalation reliability.
The same model/tool availability is required on other computers. Runtime model aliases were explicitly
requested; this test does not establish provider-internal model versions beyond those exposed aliases.

Fixtures and exact command outputs were retained in the local temporary experiment directory:
`C:/Users/kccistc/AppData/Local/Temp/starter-code-validation-y_ue7p3t/`.
This report is repository evidence, not an extra mandatory document in the distributed starter.
