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
If Python is unavailable, preflight destination conflicts and copy with native tools.

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
History, integrations, custom routing, training, memory, capsules and evidence logs are
optional/inactive. Do not enable them or introduce a separate API orchestrator for a scaffold request.
Do not install frameworks or connect APIs for a scaffold-only request.
Project copies are independent snapshots; skill changes do not update existing projects.

## Development after adoption

For development, follow the copied `AGENTS.md` and reuse unchanged instructions and settings already
read in the session. One selected model implements and verifies; do not create subagents,
orchestrate Sol+Luna, or run agents in parallel. Model escalation is sequential and requires
actual runtime support or manual model selection. The current chat model does not switch automatically.
