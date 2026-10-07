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

Read the resulting AGENTS.md and PROJECT.md. Preserve scaffold-only uninitialized status.
If project requirements were supplied, record them in PROJECT.md. Check template completeness
and report results. Add project-specific documents only when actual architecture needs them.

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
