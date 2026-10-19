import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'distribution/skill/scripts/scaffold.py'


class ScaffoldAdoptTests(unittest.TestCase):
    def test_existing_readme_preserved_missing_core_added(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            bundle=root/'bundle'
            source=bundle/'assets/starter'
            source.mkdir(parents=True)
            files={'README.md':'template','AGENTS.md':'map','.ai/models.yaml':'models'}
            for name,text in files.items():
                p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            (bundle/'release.json').write_text(json.dumps({'sha256':{
                'universal-ai-starter/assets/starter/'+name:hashlib.sha256(text.encode()).hexdigest()
                for name,text in files.items()}}))
            target=root/'project';target.mkdir();(target/'README.md').write_text('user facts')
            spec=importlib.util.spec_from_file_location('scaffold_adopt',SCRIPT)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.__file__=str(bundle/'scripts/scaffold.py')
            with patch.object(module.sys,'argv',['scaffold','--target',str(target),'--adopt']), patch.object(module.subprocess,'call',return_value=0) as install, patch.object(module,'verify_bundle',return_value='0.3.2'):
                self.assertEqual(module.main(),0)
                self.assertEqual(install.call_count,1)
            self.assertEqual((target/'README.md').read_text(),'user facts')
            self.assertEqual((target/'AGENTS.md').read_text(),'map')
            with patch.object(module.sys,'argv',['scaffold','--target',str(target),'--adopt','--dry-run']), patch.object(module.subprocess,'call') as install, patch.object(module,'verify_bundle',return_value='0.3.2'):
                self.assertEqual(module.main(),0)
                install.assert_not_called()


if __name__=='__main__':unittest.main()
