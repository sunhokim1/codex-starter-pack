#!/usr/bin/env python3
"""Build a reproducible ZIP distribution of the Universal AI Starter."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ARCHIVE_NAME = "universal-ai-starter"
MANIFEST_PATH = Path("distribution/manifest.json")
CONFIG_PATH = Path(".ai/config.yaml")


class PackageError(ValueError):
    """Invalid package inputs or failed package verification."""


def _safe_relative(value: object, label: str) -> PurePosixPath:
    if (not isinstance(value, str) or not value or "\\" in value
            or re.match(r"^[A-Za-z]:", value)):
        raise PackageError(f"{label} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise PackageError(f"unsafe {label}: {value!r}")
    return path


def _source(root: Path, rel: PurePosixPath) -> Path:
    candidate = root.joinpath(*rel.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise PackageError(f"missing source or source escapes root: {rel}") from exc
    if not resolved.is_file():
        raise PackageError(f"source is not a file: {rel}")
    return resolved


def _version(root: Path) -> str:
    manifest = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    if 'version' in manifest:
        version = manifest['version']
        if not isinstance(version, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', version):
            raise PackageError('invalid distribution version')
        return version
    text = _source(root, PurePosixPath(CONFIG_PATH.as_posix())).read_text(encoding="utf-8")
    in_starter = False
    for line in text.splitlines():
        if re.match(r"^starter:\s*(?:#.*)?$", line):
            in_starter = True
            continue
        if in_starter:
            match = re.match(r"^  version:\s*['\"]([0-9]+(?:\.[0-9]+)+)['\"]\s*(?:#.*)?$", line)
            if match:
                return match.group(1)
            if line and not line[0].isspace():
                break
    raise PackageError(".ai/config.yaml must contain starter.version as a quoted dotted version")


def _load(root: Path):
    try:
        manifest = json.loads(_source(root, PurePosixPath(MANIFEST_PATH.as_posix())).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read {MANIFEST_PATH}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PackageError("manifest must be a JSON object")
    templates = manifest.get("template_files")
    skills = manifest.get("skill_files")
    if (not isinstance(manifest.get("skill_name"), str) or not manifest["skill_name"]
            or not isinstance(templates, list) or not isinstance(skills, dict)):
        raise PackageError("manifest needs skill_name, template_files list, and skill_files mapping")
    if manifest["skill_name"] != ARCHIVE_NAME:
        raise PackageError(f"skill_name must be {ARCHIVE_NAME!r}")

    sources: dict[str, Path] = {}
    for raw in templates:
        source_rel = _safe_relative(raw, "template source")
        archive_rel = PurePosixPath("assets/starter", *source_rel.parts)
        name = f"{ARCHIVE_NAME}/{archive_rel.as_posix()}"
        if name in sources:
            raise PackageError(f"duplicate archive entry: {name}")
        sources[name] = _source(root, source_rel)
    for raw_dest, raw_source in skills.items():
        dest = _safe_relative(raw_dest, "skill archive path")
        source_rel = _safe_relative(raw_source, "skill source")
        name = f"{ARCHIVE_NAME}/{dest.as_posix()}"
        if name in sources or name == f"{ARCHIVE_NAME}/release.json":
            raise PackageError(f"duplicate or reserved archive entry: {name}")
        sources[name] = _source(root, source_rel)
    entry_paths = [PurePosixPath(name) for name in sources]
    entry_paths.append(PurePosixPath(ARCHIVE_NAME, "release.json"))
    for index, entry in enumerate(entry_paths):
        if any(entry in other.parents or other in entry.parents for other in entry_paths[index + 1:]):
            raise PackageError(f"conflicting archive entry paths: {entry}")
    return manifest, sources


def _validate_output(output: Path, root: Path, sources: dict[str, Path]) -> Path:
    protected = list(sources.values()) + [
        _source(root, PurePosixPath(MANIFEST_PATH.as_posix())),
        _source(root, PurePosixPath(CONFIG_PATH.as_posix())),
    ]
    output_abs = output.resolve()
    if output_abs == (root / 'universal-ai-starter.zip').resolve() and _version(root) == '0.4.0':
        raise PackageError('archived root ZIP is immutable; use versioned 0.4.0 output')
    if output_abs.is_relative_to((root / 'distribution/releases').resolve()) and not output_abs.is_relative_to((root / 'distribution/releases/0.4.0').resolve()):
        raise PackageError('archived releases are immutable')
    if output_abs.is_relative_to((root / 'distribution/releases/0.4.0/universal-ai-starter').resolve()):
        raise PackageError('output must not be inside canonical bundle sources')
    if any(output_abs == source.resolve() for source in protected):
        raise PackageError("output path would overwrite a package source or configuration file")
    return output_abs


def _build(root: Path, output: Path) -> None:
    manifest, sources = _load(root)
    version = _version(root)
    output_abs = _validate_output(output, root, sources)
    release_name = f"{ARCHIVE_NAME}/release.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, stage_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(fd)
    try:
        hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sorted(sources.items())}
        release = json.dumps({"version": version, "sha256": hashes}, indent=2, sort_keys=True) + "\n"
        with zipfile.ZipFile(stage_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, source in sorted(sources.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes())
            release_info = zipfile.ZipInfo(release_name, date_time=(1980, 1, 1, 0, 0, 0))
            release_info.compress_type = zipfile.ZIP_DEFLATED
            release_info.external_attr = 0o100644 << 16
            archive.writestr(release_info, release.encode("utf-8"))
        with zipfile.ZipFile(stage_name, "r") as archive:
            expected = set(sources) | {release_name}
            if set(archive.namelist()) != expected:
                raise PackageError("staged archive entries do not match manifest")
            release_data = json.loads(archive.read(release_name))
            if release_data != {"version": version, "sha256": hashes}:
                raise PackageError("staged release metadata failed verification")
            for name, source in sources.items():
                data = archive.read(name)
                if data != source.read_bytes() or hashlib.sha256(data).hexdigest() != hashes[name]:
                    raise PackageError(f"staged entry failed source/hash verification: {name}")
        os.replace(stage_name, output_abs)
    finally:
        try:
            os.unlink(stage_name)
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="starter repository root (defaults to script parent)")
    parser.add_argument("--output", type=Path, help="output ZIP (defaults to ROOT/universal-ai-starter.zip)")
    parser.add_argument("--check", action="store_true", help="validate package inputs without writing")
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parent.parent).resolve()
    output = args.output or root / "distribution/releases/0.4.0" / f"{ARCHIVE_NAME}.zip"
    try:
        manifest, sources = _load(root)
        _version(root)
        _validate_output(output, root, sources)
        if args.check:
            print(f"Package inputs valid: {len(sources)} files for {manifest['skill_name']}")
        else:
            _build(root, output)
            print(f"Wrote {output}")
    except (PackageError, OSError) as exc:
        print(f"package_starter: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

