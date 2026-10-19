"""SEV sentence-aware long request experiment; local classifier only."""
import re
import time
import numpy as np
from tokenizers import Tokenizer
from sev_candidate import Candidate
from selector import HERE


class LongCandidate(Candidate):
    def __init__(self, encoder=None):
        super().__init__(encoder)
        self.segment_tokenizer=Tokenizer.from_str(self.encoder.tokenizer.to_str())
        self.segment_tokenizer.enable_truncation(max_length=128)
        self.segment_tokenizer.no_padding()
        self.short_classifier=Candidate(self.encoder)
        self.short_classifier.load(HERE/'sev-candidate.npz')

    def segments(self, text):
        # Sentence/paragraph boundaries keep a short qualification from sharing
        # its embedding with hundreds of unrelated implementation instructions.
        # Keep adjacent sentences together so negation/context remains attached.
        # A numbered-list prefix has no model-selection meaning of its own.
        units=[re.sub(r'^\s*(?:\d+[.)]|[-*])\s+','',line) for line in text.splitlines()]
        units=[unit for unit in units if unit.strip()]
        # The opening scope/title needs its first specification paragraph. A
        # bare title such as "build a formatter" has too little context to
        # independently veto a completely specified low-risk request. Preserve
        # both paragraphs, including any risk stated at the very beginning.
        if len(units)>1:
            units=[units[0]+' '+units[1],*units[1:]]
        chunks=[]
        for unit in units:
            if not unit.strip():continue
            encoded=self.segment_tokenizer.encode(unit)
            for window in [encoded,*encoded.overflowing]:
                chunks.append(self.segment_tokenizer.decode(window.ids,skip_special_tokens=True))
        return list(dict.fromkeys(chunks))  # identical clauses need one inference

    def decision_score(self, task, facts=''):
        text=task.strip()+('\n'+facts.strip() if facts.strip() else '')
        vector=self.vector(task,facts)
        scores=[self.score(vector)]
        if self.encoder.exceeds_limit(text):
            for segment in self.segments(text):
                scores.append(self.score(self.encoder.encode([segment])[0]))
        return max(scores),len(scores)-1

    def select(self,task,facts='',override=None,**kwargs):
        if override or not task.strip():
            return super().select(task,facts,override)
        text=task.strip()+('\n'+facts.strip() if facts.strip() else '')
        if not self.encoder.exceeds_limit(text):
            return self.short_classifier.select(task,facts,override)
        started=time.perf_counter()
        score,count=self.decision_score(task,facts)
        return {'role':'worker' if score<self.threshold else 'main','score':score,
                'segment_count':count,'elapsed_seconds':time.perf_counter()-started,
                'backend':'local','api_calls':0,'usage':None,'scores_are_success_probabilities':False}


def main():
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser(description='SEV long-input classification only')
    p.add_argument('--task-file',required=True);p.add_argument('--context-file')
    p.add_argument('--model',choices=['worker','main'])
    args=p.parse_args();candidate=LongCandidate();candidate.load(HERE/'sev-long-candidate.npz')
    print(json.dumps(candidate.select(Path(args.task_file).read_text(encoding='utf-8-sig'),
        Path(args.context_file).read_text(encoding='utf-8-sig') if args.context_file else '',args.model)))


if __name__=='__main__':main()
