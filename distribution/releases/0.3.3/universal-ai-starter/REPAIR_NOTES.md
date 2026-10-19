# 0.3.3 Windows permission preflight release

0.3.3 adds an automatic native managed Windows sandbox probe immediately after
creating the selected venv, before dependency/model preparation, service startup,
project connections, skill promotion or optional startup registration. It checks
stdlib reads, a child Python process and temporary workspace reads/writes.
Failure stops installation with diagnostics; no ACL grants, authentication changes,
sandbox bypass or alternative implementation is attempted. Non-Windows returns
`not_applicable`.

The canonical source is a separate 0.3.3 bundle. Older releases, model mappings
and NPZ weights are preserved. The root distribution mapping, compatibility entry
points, version fixtures and ZIP target 0.3.3. Package generation uses an explicit
source list; integrity verification rejects extra/missing files and changed hashes.

Offline checks mock installation, subprocesses and permissions. They do not prove
an actual install, model inference, startup registration or access on another PC.
A native managed `:workspace` probe passed in the parent environment; this does
not guarantee that future policy/runtime changes will remain accessible.

## Historical 0.3.2 repair notes and evidence

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
