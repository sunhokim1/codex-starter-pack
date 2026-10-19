# 0.3.3 maintenance and distribution

The maintained source is `distribution/releases/0.3.3/universal-ai-starter/`.
`distribution/manifest.json` explicitly maps every public source file, including
the Windows preflight tests. Root packaging never enumerates project directories.
The bundle package builder also uses an explicit source list; its integrity check
rejects unlisted files. Keep both lists in agreement when adding public source.

```text
python scripts/package_starter.py
python scripts/package_starter.py --check
python distribution/releases/0.3.3/universal-ai-starter/scripts/package_starter.py --check
```

The first command reproducibly writes `universal-ai-starter.zip`, with release version
from `.ai/config.yaml` and SHA256 for every source entry. To regenerate the canonical
bundle's `release.json`, run its package script with `--output <outside-bundle.zip>`,
then build the root reproducible ZIP. Outputs must remain outside canonical source.
Old 0.3.1 and 0.3.2 source remains immutable.

`distribution/skill/scripts/` and experiment runner/service entry points forward
to the maintained source. Root `tests/` tests packaging and installer integration;
the bundle's `tests/` covers runtime behavior. Local execution configuration and
reports are excluded from the distribution mapping.

`install_from_github.ps1` accepts `-Target <folder>` or prompts for a folder. It
validates paths, release 0.3.3, the complete ZIP and hashes before running staged
bootstrap. Personal skill promotion follows successful bootstrap. Existing projects
and previous skills are preserved. Windows preflight failure prevents later setup;
the installer never grants permissions automatically. The immutable URL must point
to the commit containing the verified release ZIP before publication.

Installer tests parse/load functions and use offline ZIPs and mocked bootstrap.
They do not install Python, change ACLs, authenticate, run models or edit startup.
