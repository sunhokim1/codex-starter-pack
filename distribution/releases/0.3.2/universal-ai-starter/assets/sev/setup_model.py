"""Download public ONNX weights only; no task text is sent to a service."""
from pathlib import Path
import hashlib
import json
from huggingface_hub import hf_hub_download

HERE = Path(__file__).resolve().parent
REPO = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
FILES = ['onnx/model_quint8_avx2.onnx','tokenizer.json','tokenizer_config.json','config.json']
REVISION = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
HASHES = {
 'onnx/model_quint8_avx2.onnx':'98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f',
 'tokenizer.json':'2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8',
 'tokenizer_config.json':'5036ea374ffedd706e3bef33e2e0d6953cb868ef8a490e76e32ba0faa37a6b9b',
 'config.json':'6300193cb75e01cf80c96decef7187dfb33094d97cc1490b7ead6ff134476e4e'}


def main():
    revision=REVISION
    target=HERE/'model'
    for name in FILES:
        if (target/name).exists() and hashlib.sha256((target/name).read_bytes()).hexdigest()==HASHES[name]:
            continue
        print('Downloading '+name,flush=True)
        hf_hub_download(REPO,name,revision=revision,local_dir=target)
        if hashlib.sha256((target/name).read_bytes()).hexdigest()!=HASHES[name]:
            raise ValueError('download integrity failed: '+name)
    manifest={'repository':REPO,'revision':revision,'license':'apache-2.0',
              'files':{name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in FILES}}
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest))


if __name__=='__main__':main()
