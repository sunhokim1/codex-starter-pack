import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'distribution/skill/scripts/install_sev.py'
spec=importlib.util.spec_from_file_location('install_sev',SCRIPT)
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallSevTests(unittest.TestCase):
    def test_merge_preserves_project_map_and_custom_rules(self):
        original='# Project\ncustom verification and navigation\n'
        merged=installer.merge_guidance(original)
        self.assertTrue(merged.startswith(original.rstrip()))
        self.assertEqual(installer.merge_guidance(merged),merged)
        self.assertEqual(merged.count(installer.BEGIN),1)

    def test_ambiguous_marker_does_not_overwrite(self):
        with self.assertRaises(ValueError):
            installer.merge_guidance('custom '+installer.BEGIN)

    def test_bundle_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'release.json').write_text(json.dumps({'version':'0.3.0','sha256':{'universal-ai-starter/a.txt':'0'*64}}))
            (root/'a.txt').write_text('tampered')
            with self.assertRaises(ValueError):installer.verify_bundle(root)

    def test_release_paths_cannot_escape_or_use_wrong_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.txt').write_bytes(b'content')
            digest=hashlib.sha256(b'content').hexdigest()
            for name in ('wrong-root/a.txt', 'universal-ai-starter/../a.txt',
                         'universal-ai-starter/C:/a.txt', 'universal-ai-starter/a\\b'):
                (root/'release.json').write_text(json.dumps({'version':'0.3.0','sha256':{name:digest}}))
                with self.subTest(name=name), self.assertRaises(ValueError):installer.verify_bundle(root)

    def test_missing_core_never_installs_or_runs(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(installer,'verify_bundle',return_value='test'), patch.object(installer,'checked') as checked:
            root=Path(temp)
            with self.assertRaises(ValueError):installer.install(root,root/'runtime',root/'skills',root)
            checked.assert_not_called()


if __name__=='__main__':unittest.main()
