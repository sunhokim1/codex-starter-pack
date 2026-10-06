---
name: universal-ai-starter
description: Apply the user's framework-neutral Universal AI Starter to a new project or adopt it into an existing project while preserving project facts. Use when asked to apply this reusable starter, not for ordinary development in an initialized project.
---

# Universal AI Starter

Strong models, thin harness. Use the bundled 27-file snapshot in `assets/starter/`.
User requirements and existing project instructions take precedence over template defaults.

## Apply

Use the requested target directory or current project. Read applicable AGENTS.md instructions.
Run `python <skill-dir>/scripts/scaffold.py --target <project-dir> --dry-run`, then run
without `--dry-run` if the preflight passes. The script never overwrites existing files.
If Python is unavailable, preflight destination conflicts and copy with native tools.

Read the resulting AGENTS.md and PROJECT.md. Preserve scaffold-only uninitialized status.
If project requirements were supplied, record them in PROJECT.md and use the relevant preset
only if helpful. Check template completeness and report results.

## Existing projects

On conflict, inspect only relevant conflicting files and merge requested operating guidance.
Preserve project facts, navigation, commands, model settings, architecture and history.
Do not replace working project data with uninitialized defaults. Resolve material ambiguity
with the user; unrelated files need no repository-wide scan.

## Scope

The core is AGENTS.md, PROJECT.md, models.yaml, routing.yaml and verification.yaml.
Models are role-mapped; configuration does not switch the current chat model.
Supporting policies, agent perspectives, presets and docs are read only when useful.
History, integrations, custom routing, training, memory, capsules and evidence logs are
optional/inactive. Do not enable them or introduce a separate API orchestrator for a scaffold request.
Do not install frameworks or connect APIs for a scaffold-only request.
Project copies are independent snapshots; skill changes do not update existing projects.

## Native worker execution after adoption

Follow the copied AGENTS.md and routing.yaml during development: small implementations use
one worker; independent small implementations may use at most two parallel workers, with
main coordinating, reviewing and verifying. Read the actual model_id from models.yaml and
explicitly specify it when spawning a native subagent; do not silently inherit the host model.
Use minimal task context and disjoint file ownership. Dependencies/shared interfaces run serially.
If native model selection is unavailable, disclose that and work sequentially with the current
model. This instruction does not switch the current chat model or install an API runtime.
