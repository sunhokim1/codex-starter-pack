"""검증된 0.4.0 번들의 재현 가능한 로컬 ZIP 생성."""
import argparse
import json
from pathlib import Path
import os
import tempfile
import zipfile
from install_rev import verify_bundle

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1]
    verify_bundle(root)
    release=json.loads((root/'release.json').read_text(encoding='utf-8'))
    if args.check:
        print('0.4.0 package sources verified');return 0
    output=(args.output or root.parent/'universal-ai-starter.zip').absolute()
    from runner.runtime_safety import reject_links
    reject_links(output)
    if output.is_relative_to(root):raise ValueError('Package must not overwrite bundle sources')
    releases=root.parent.parent
    if output.is_relative_to(releases) and not output.is_relative_to(root.parent):raise ValueError('Archived releases are immutable')
    if output==releases.parent.parent/'universal-ai-starter.zip':raise ValueError('Archived root ZIP is immutable')
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,stage=tempfile.mkstemp(dir=output.parent,suffix='.zip.tmp');os.close(fd)
    try:
        with zipfile.ZipFile(stage,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name in [*sorted(release['sha256']),'universal-ai-starter/release.json']:
                info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                data=((json.dumps(release,indent=2,sort_keys=True)+'\n').encode('utf-8')
                      if name=='universal-ai-starter/release.json' else (root/name.split('/',1)[1]).read_bytes())
                archive.writestr(info,data)
        os.replace(stage,output)
    finally:
        Path(stage).unlink(missing_ok=True)
    print('0.4.0 package created');return 0

if __name__=='__main__':raise SystemExit(main())
