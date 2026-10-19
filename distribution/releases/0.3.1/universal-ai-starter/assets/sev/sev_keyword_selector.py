"""Personal intent-rule-first SEV experiment. Classification only; never executes code."""
import argparse
import json
from pathlib import Path
import re
import time
import unicodedata


# Match risk topic AND change/design/review intent, not a bare topic noun.
# Check the user's request, not background facts which may mention these routinely.
RULES = (
    ('security', r'보안|\bsecurity\b'),
    ('privacy', r'개인정보|\bprivacy\b|\bpersonal\s+(?:data|information)\b'),
    ('permissions', r'권한|\bauthorization\b|\bpermissions?\b|\baccess\s+control\b'),
    ('encryption', r'암호화|\bencrypt(?:ion|ed|ing)?\b'),
    ('data_deletion', r'데이터\s*삭제|\bdata[\s-]+deletion\b|\bdelete\s+data\b'),
    ('compatibility', r'호환성|\bcompatibility\b'),
    ('unknown_cause', r'원인\s*불명|원인(?:은|을)?\s*(?:모르|알\s*수\s*없)|\bunknown\s+(?:root\s+)?cause\b|\b(?:root\s+)?cause\s+is\s+unknown\b'),
)
PATTERNS = [(category,re.compile(pattern,re.IGNORECASE)) for category,pattern in RULES]
ACTION=re.compile(r'변경|수정|바꾸|바꿔|바꾼|바꿀|바뀌|설계|검토|분석|마이그레이션|삭제|노출|유출|제거|공개|교체|'
    r'\b(?:chang(?:e|es|ed|ing)|modif\w*|design\w*|review\w*|assess\w*|analy[sz]\w*|'
    r'migrat\w*|delet\w*|remov\w*|expos\w*|leak\w*|disclos\w*|rotat\w*|replac\w*|redact\w*)\b',re.I)
UNCHANGED=re.compile(r'(?:변경|수정|바꾸|바꿔|설계|삭제|제거|교체)(?:하지|하지는|되지|되지는|지|지는)?\s*(?:않|안|말)|'
    r'(?:변경|수정|삭제)(?:은|는|이|가|도|을|를)?\s*(?:하지\s*(?:않|말)|안|없)|'
    r'안\s*(?:바꾸|바꿔|바꾼|바꿀|변경|수정)|'
    r'\b(?:do\s+not|don.t|must\s+not|will\s+not|never|without)\s+(?:be\s+)?(?:change\w*|modif\w*|delete\w*|remove\w*|redesign\w*)\b|'
    r'\bno\b.*\b(?:changes?|modifications?|deletion)\b|'
    r'\b(?:remain|remains|stay|stays)\s+(?:unchanged|untouched|unmodified|unaffected)\b',re.I)
UNRESOLVED=re.compile(r'미정|정해지지|합의되지|확인되지|아직\s*(?:정하지|모르)|'
    r'\b(?:undefined|undecided|unresolved|unknown|not\s+(?:yet\s+)?(?:agreed|defined|decided|established))\b',re.I)
CLAUSE_BREAK=re.compile(r'\n+|[.!?;。]|,|하지만|그러나|다만|지만|(?<=않고)\s*|(?<=없고)\s*|'
    r'\b(?:but|however|whereas|and)\b',re.I)


def intent_matches(task):
    matches=[]
    for clause in CLAUSE_BREAK.split(unicodedata.normalize('NFC',task)):
        if not clause.strip():continue
        for category,pattern in PATTERNS:
            match=pattern.search(clause)
            if not match:continue
            if category=='unknown_cause':
                matches.append({'category':category,'text':match.group(0),'clause':clause.strip()})
            elif UNRESOLVED.search(clause) or (ACTION.search(clause) and not UNCHANGED.search(clause)):
                matches.append({'category':category,'text':match.group(0),'clause':clause.strip()})
    return matches


class KeywordSelector:
    def __init__(self, fallback_factory=None):
        self.fallback_factory=fallback_factory
        self.fallback=None

    def select(self, task, facts='', override=None):
        started=time.perf_counter()
        common={'backend':'local','api_calls':0,'usage':None,'scores_are_success_probabilities':False}
        if override is not None:
            if override not in ('worker','main'):raise ValueError('invalid user model override')
            return dict(common,role=override,route='user_override',elapsed_seconds=time.perf_counter()-started)
        if not task.strip():
            return dict(common,role='main',route='empty_request',elapsed_seconds=time.perf_counter()-started)
        matches=intent_matches(task)
        if matches:
            return dict(common,role='main',route='intent_rule',matches=matches,
                elapsed_seconds=time.perf_counter()-started)
        # Heavy dependencies and model files are loaded ONLY if no keyword hits.
        if self.fallback is None:
            if self.fallback_factory is None:
                from sev_long_candidate import LongCandidate
                from selector import HERE
                self.fallback=LongCandidate();self.fallback.load(HERE/'sev-long-candidate.npz')
            else:self.fallback=self.fallback_factory()
        record=self.fallback.select(task,facts)
        return dict(record,route='sev',sev_inference_seconds=record.get('elapsed_seconds'),
            elapsed_seconds=time.perf_counter()-started)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-file',required=True)
    parser.add_argument('--context-file')
    parser.add_argument('--model',choices=['worker','main'])
    args=parser.parse_args()
    record=KeywordSelector().select(Path(args.task_file).read_text(encoding='utf-8-sig'),
        Path(args.context_file).read_text(encoding='utf-8-sig') if args.context_file else '',args.model)
    print(json.dumps(record,ensure_ascii=True))


if __name__=='__main__':main()
