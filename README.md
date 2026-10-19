# Universal AI Development Starter 0.3.3

0.3.3 adds automatic Windows permission preflight during installation. After creating
the new venv, the installer checks that exact Python under the native managed Codex
`:workspace` sandbox before preparing dependencies/models, starting the service,
connecting the project, promoting skills or registering optional startup.
Failures stop with diagnostics. The probe never grants ACLs or bypasses device policy.

The maintained source is [the 0.3.3 bundle](distribution/releases/0.3.3/universal-ai-starter/README.md).
The root `universal-ai-starter.zip` is built from `distribution/manifest.json` and
contains the complete source and regression tests. Released 0.3.1 and 0.3.2 sources
remain unchanged. Existing projects, model mappings and weights are preserved.

```text
python scripts/package_starter.py
python scripts/package_starter.py --check
python distribution/releases/0.3.3/universal-ai-starter/scripts/package_starter.py --check
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s distribution/releases/0.3.3/universal-ai-starter/tests -p "test_*.py" -v
```

Use a ZIP from a trusted source and verify its integrity before applying it.
The public installer requires release 0.3.3 and validates the full ZIP before staging
bootstrap; publishing requires an immutable download pin to the verified ZIP commit.
See [release details](docs/release-0.3.3.md) and the bundle's repair notes for limits.
Actual installation, model inference and startup behavior require separate validation.
Offline regression results do not establish access on every Windows PC.

Compatibility runner/service/install/scaffold entry points forward to 0.3.3.
[Continuous improvement](CONTINUOUS_IMPROVEMENT.md) retains the remaining work.
