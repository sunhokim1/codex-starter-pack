import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_starter.py"


class PackageStarterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "starter"
        (self.root / "distribution").mkdir(parents=True)
        (self.root / ".ai").mkdir()
        (self.root / "distribution/manifest.json").write_text(json.dumps({
            "skill_name": "universal-ai-starter",
            "template_files": ["docs/example.txt"],
            "skill_files": {"SKILL.md": "distribution/skill/SKILL.md"},
        }))
        (self.root / ".ai/config.yaml").write_text('starter:\n  version: "2.4.7"\n')
        (self.root / "docs").mkdir()
        (self.root / "docs/example.txt").write_text("template bytes")
        (self.root / "distribution/skill").mkdir(parents=True)
        (self.root / "distribution/skill/SKILL.md").write_text("skill bytes")

    def run_package(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args], capture_output=True, text=True)

    def test_check_validates_without_writing(self):
        out = self.root / "custom.zip"
        result = self.run_package("--output", str(out), "--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(out.exists())

    def test_success_extract_hash_and_version(self):
        out = self.root / "release.zip"
        result = self.run_package("--output", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(archive.read("universal-ai-starter/SKILL.md"), b"skill bytes")
            self.assertEqual(archive.read("universal-ai-starter/assets/starter/docs/example.txt"), b"template bytes")
            release = json.loads(archive.read("universal-ai-starter/release.json"))
            for name, digest in release["sha256"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
        self.assertEqual(release["version"], "2.4.7")

    def test_missing_source_preserves_previous_output(self):
        out = self.root / "release.zip"
        out.write_bytes(b"previous archive")
        (self.root / "docs/example.txt").unlink()
        result = self.run_package("--output", str(out))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(out.read_bytes(), b"previous archive")

    def test_invalid_traversal_rejected(self):
        manifest_path = self.root / "distribution/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["template_files"] = ["../outside.txt"]
        manifest_path.write_text(json.dumps(manifest))
        result = self.run_package("--check")
        self.assertNotEqual(result.returncode, 0)

    def test_source_change_reflected_on_rebuild(self):
        out = self.root / "release.zip"
        self.assertEqual(self.run_package("--output", str(out)).returncode, 0)
        (self.root / "docs/example.txt").write_text("updated")
        self.assertEqual(self.run_package("--output", str(out)).returncode, 0)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(archive.read("universal-ai-starter/assets/starter/docs/example.txt"), b"updated")

    def test_output_source_collision_rejected(self):
        source = self.root / "docs/example.txt"
        result = self.run_package("--output", str(source))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(source.read_text(), "template bytes")

    def test_output_metadata_collision_rejected_by_check(self):
        manifest = self.root / "distribution/manifest.json"
        original = manifest.read_bytes()
        result = self.run_package("--output", str(manifest), "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(manifest.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
