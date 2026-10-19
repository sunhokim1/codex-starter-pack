"""Offline semantic example router. Scores are similarities, not success probabilities."""
from pathlib import Path
import json
import time
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

HERE=Path(__file__).resolve().parent


class Encoder:
    def __init__(self,model_dir=HERE/'model'):
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(model_dir/'onnx/model_quint8_avx2.onnx'),options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(model_dir/'tokenizer.json'))
        self.tokenizer.enable_padding()
        config=json.loads((model_dir/'config.json').read_text(encoding='utf-8'))
        self.tokenizer.enable_truncation(max_length=config['max_position_embeddings'])
        self.names={i.name for i in self.session.get_inputs()}

    def encode(self,texts):
        encoded=self.tokenizer.encode_batch(texts)
        ids=np.array([e.ids for e in encoded],dtype=np.int64)
        mask=np.array([e.attention_mask for e in encoded],dtype=np.int64)
        types=np.array([e.type_ids for e in encoded],dtype=np.int64)
        feeds={k:v for k,v in [('input_ids',ids),('attention_mask',mask),('token_type_ids',types)] if k in self.names}
        output=self.session.run(None,feeds)[0]
        weights=mask[...,None]
        pooled=(output*weights).sum(axis=1)/np.clip(weights.sum(axis=1),1,None)
        return pooled/np.clip(np.linalg.norm(pooled,axis=1,keepdims=True),1e-12,None)

    def exceeds_limit(self,text):
        # Do not silently classify a truncated request as safe for Luna.
        return bool(self.tokenizer.encode(text).overflowing)


class Selector:
    def __init__(self):
        started=time.perf_counter()
        self.encoder=Encoder()
        self.index=np.load(HERE/'index.npz')
        self.policy=json.loads((HERE/'calibrated.json').read_text(encoding='utf-8'))
        self.load_seconds=time.perf_counter()-started

    def scores(self,text):
        vector=self.encoder.encode([text])[0]
        scores=self.index['vectors']@vector
        labels=self.index['labels']
        return float(scores[labels=='worker'].max()),float(scores[labels=='main'].max())

    def select(self,task,facts='',override=None):
        started=time.perf_counter()
        if override:
            if override not in ('worker','main'):raise ValueError('invalid user model override')
            return {'role':override,'reason':'user specified model','elapsed_seconds':0,'backend':'local','usage':None,'api_calls':0}
        text=task.strip()+('\n'+facts.strip() if facts.strip() else '')
        if not text or self.encoder.exceeds_limit(text):
            return {'role':'main','reason':'insufficient evidence or input exceeds calibrated encoder capacity','elapsed_seconds':time.perf_counter()-started,'backend':'local','usage':None,'api_calls':0}
        worker,main=self.scores(text)
        margin=worker-main
        role='worker' if worker>=self.policy['min_similarity'] and margin>=self.policy['min_margin'] else 'main'
        return {'role':role,'reason':'local semantic match passed calibrated Luna gate' if role=='worker' else 'local evidence did not pass calibrated Luna gate',
                'elapsed_seconds':round(time.perf_counter()-started,6),'backend':'local','usage':None,'api_calls':0,
                'similarity_worker':worker,'similarity_main':main,'margin':margin,'scores_are_success_probabilities':False}


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--task-file',required=True);p.add_argument('--context-file');p.add_argument('--model',choices=['worker','main'])
    args=p.parse_args();s=Selector()
    result=s.select(Path(args.task_file).read_text(encoding='utf-8-sig'),Path(args.context_file).read_text(encoding='utf-8-sig') if args.context_file else '',args.model)
    result['load_seconds']=s.load_seconds
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
