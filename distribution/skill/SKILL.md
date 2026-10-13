---
name: universal-ai-starter
description: Apply the user's framework-neutral Universal AI Starter to a new project or adopt it into an existing project while preserving project facts. Use when asked to apply this reusable starter, not for ordinary development in an initialized project.
---

# Universal AI Starter

Strong models, thin harness. Use the bundled seven core files in `assets/starter/`.
User requirements and existing project instructions take precedence over template defaults.

## Apply

Use the requested target directory or current project. Read applicable AGENTS.md instructions.
Run `python <skill-dir>/scripts/scaffold.py --target <project-dir> --dry-run`, then run
without `--dry-run` if the preflight passes. The script never overwrites existing files.
Use Python 3.11+; on Windows, if unavailable run the bundled `scripts/bootstrap.ps1`
with `-Target <project>` to install Python and apply the starter. Honor tool permissions.
The non-dry-run scaffold also installs shared local SEV, dependencies, pinned public
model weights, the single-model-runner skill and Windows sign-in startup. Installation
requires internet once, disk space and local socket access; no classification API is used.
If an existing project's core files conflict, preserve/merge them first, then run
`python <skill-dir>/scripts/install_sev.py --target <project>` to finish the same setup.
Do not stop after copying core files or silently skip failed SEV installation.
After installation `.ai/sev.json` contains machine-specific paths and managed AGENTS
guidance enables development requests through SEV. Verify service status using those
paths and report installation separately from coding verification. No framework is installed.

Read the resulting AGENTS.md and PROJECT.md. Initialize confirmed project facts as described below;
leave empty projects uninitialized. Record supplied requirements in PROJECT.md. Check template
completeness and report results. Add project-specific documents only when actual architecture needs them.

## Initialize project facts

After copying or merging, inspect the target's top-level folders and relevant manifests/build
configuration. Follow existing nested AGENTS.md where applicable; inspect enough code to confirm
major subsystem boundaries and entry points without inventorying every file.

- Fill unset PROJECT.md fields with confirmed stack, runtime and supplied goals/constraints.
  Leave unsupported facts unset; preserve existing project facts and user choices.
- Populate the root AGENTS.md map with confirmed major subsystem paths, entry points, tests,
  docs/schema and existing nested AGENTS.md. Preserve existing rows; correct stale paths only
  with evidence. Use relative paths and leave absent areas uninitialized. Do not list every file
  or create nested instructions merely to fill the table.
- Fill unset verification.yaml commands only from actual project scripts/configuration or
  documented commands corroborated by the project. For example, use the package manager
  established by the project with scripts that exist in package.json. Do not invent commands
  from a framework name, replace configured commands, install dependencies or run builds/tests
  merely to initialize facts. Leave ambiguous commands unset and explain the gap.

Report which facts and command definitions were populated and their source files. A discovered
command is configured, not executed or passed; report execution separately if requested.

## Existing projects

On conflict, inspect only relevant conflicting files and merge requested operating guidance.
Preserve project facts, navigation, commands, model settings, architecture and history.
Do not replace working project data with uninitialized defaults. Resolve material ambiguity
with the user; unrelated files need no repository-wide scan.

## Scope

The core is AGENTS.md, PROJECT.md, models.yaml, routing.yaml and verification.yaml.
Models are role-mapped; configuration does not switch the current chat model.
Generic policy, role, preset and empty architecture documents are not bundled.
History, integrations, training, memory, capsules and evidence logs are
optional/inactive. Local SEV is the authorized single-model selection path; do not
introduce an API orchestrator, subagents or parallel execution for a scaffold request.
Do not install frameworks or connect APIs for a scaffold-only request.
Project copies are independent snapshots; skill changes do not update existing projects.

## Development after adoption

For development, follow the copied `AGENTS.md` and reuse unchanged instructions and settings already
read in the session. When `.ai/sev.json` is configured, invoke single-model-runner for
development requests using its configured paths; do not classify again in this chat.
The rest of this paragraph is the manual fallback for projects without SEV; an installation
or runtime error must be reported rather than silently activating it. Before implementation,
use copied routing.yaml to briefly assess task fit,
total time/tokens, uncertainty, failure impact, verifiability and rework risk; there is no fixed
default model or mandatory Luna-first attempt. Honor the user's model choice.
Assess only the currently available user request and project information. Do not perform broad
code exploration, run separate agents or add classification steps solely to choose a model.
Without a user override, recommend Sol when selection evidence is insufficient or failure impact is high. File count and
request length alone do not determine the model. Do not add classifier calls or scoring machinery.
One selected model explores, designs, implements, reviews and verifies; do not create subagents,
orchestrate Sol+Luna, or run agents in parallel. Model escalation is sequential and requires
actual runtime support or manual model selection. Escalate only after cause analysis of a confirmed
unresolved problem or related check failure beyond the current model; environment/tool errors or
uncertainty alone do not trigger escalation. Pass only goal, relevant files, attempts, check results
and remaining problems. Without switching support, retain the current model and disclose the actual
model, recommendation and reason; do not claim a switch. Decisions API is not required or invoked;
an optional integration needs demonstrated benefit and user authorization, accounting for cost and
latency. Its estimates are not measured coding success rates.
