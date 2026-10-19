# 0.3.2 project workflow repair

2026-10-19. Original files, 0.3.1 source, model mappings and SEV weights are preserved.

- Planning returns a typed plan object, separate from human summary. Recursive,
  idempotent credential masking preserves JSON and saved/resumed task structure.
- Execution context retains the goal, facts and current task. Direct dependencies
  supply bounded result summaries, changed paths and check statuses; completed task
  instructions no longer accumulate. Detailed evidence remains in private state.
- SHA256 workspace fingerprints detect edits/deletions after completed work.
  Resume stops until explicit --reverify passes configured real checks, without
  replaying completed model calls. Explicit retry accepts stopped-task partial edits.
- Windows permission helper captures command bytes, avoiding locale decode failures.
- Planning and every implementation task still invoke local SEV independently.
  Explicit model overrides retain the existing bypass. No app chat model switching.

State schema is now 3. Old states are readable, but cannot resume automatically;
inspect edits and archive the workflow directory before starting a new goal.
Source edits do not update existing installed runtimes: rebuild/reinstall explicitly.

Validation: 32 repository tests plus 64 bundle tests (96 total), bundle hashes,
reproducible ZIP and Windows PowerShell parser checks. Model and SEV calls are
fixtures; configured workflow checks run as real subprocesses. Actual paid model
execution, learned routing accuracy, production installation and cost savings have
not been measured. Context regression compares characters, not billed tokens.

Limits: excluded files/external link targets and concurrent edits are not covered
by workspace fingerprints. Immediate-child timeout and hard-crash recovery remain
limitations. See assets/runner/PROJECT-WORKFLOW.md for operation and exclusions.
