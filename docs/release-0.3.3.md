# 0.3.3: automatic Windows permission preflight

This separate release carries forward 0.3.2 and adds a native managed Windows
sandbox check of the newly created venv's Python before dependencies/model setup,
service startup, project connections, personal skill promotion and optional startup.
It checks standard library access, a child Python process and temporary workspace
reads/writes, with a 45-second timeout. Missing CLI, unsupported flags, access denial,
timeout or failed probe stops installation with bounded diagnostics.

No ACL grants, authentication changes, unmanaged sandbox fallback or policy bypass
are performed. Device and managed policy remain authoritative. Non-Windows reports
`not_applicable`. An administrator may need to repair narrowly scoped runtime access
on an affected PC; approval on one PC does not authorize repairs on another.

The maintained bundle, root forwarding wrappers, template version, root manifest,
installer release requirement and version fixtures target 0.3.3. Released 0.3.1 and
0.3.2 sources remain unchanged. Existing model mappings and NPZ weights are retained.
Both package paths cover the exact source set, including all feature regression
tests. Extra files fail installed bundle verification; build outputs and local
configuration/reports are excluded from public packages.

Offline regression tests exercise mocked failure, rollback and ordering contracts.
A parent native integration probe returned
`{"status":"passed","profile":":workspace","managed_config":true}`.
That evidence concerns the probe, not an actual installation or future access on
other PCs. Full installation, inference, service lifecycle and startup registration
remain separate acceptance work. No actual installation was performed for this release.

Publication uses a release commit containing the verified ZIP, followed by an
installer commit pinning its download URL to that immutable release commit. Verify
the installer again after pinning; do not publish a version requirement that points
to an older ZIP. See the preserved [0.3.2 repair notes](repair-0.3.2.md) for earlier
workflow changes and their historical evidence.
