"""Classification-only SEV candidate; supervised embeddings, not a reasoning LLM."""
import json
import time
import numpy as np
from selector import Encoder, HERE


class Candidate:
    def __init__(self, encoder=None):
        self.encoder = encoder or Encoder()
        self.weights = None
        self.threshold = None

    def embeddings(self, task, facts=''):
        text = task.strip() + ('\n' + facts.strip() if facts.strip() else '')
        if not text:
            return None, []
        # Preserve every token; avoid sending long but simple specifications to Sol
        # solely because a single embedding window is too short.
        tokenizer = self.encoder.tokenizer
        encoded = tokenizer.encode(text)
        windows = [encoded, *encoded.overflowing]
        if len(windows) == 1:
            return self.encoder.encode([text])[0], []
        chunks = [tokenizer.decode(w.ids, skip_special_tokens=True) for w in windows]
        vectors = np.concatenate([self.encoder.encode([chunk]) for chunk in chunks])
        lengths = np.array([sum(w.attention_mask) for w in windows])
        pooled = np.average(vectors, axis=0, weights=lengths)
        return pooled / max(np.linalg.norm(pooled), 1e-12), vectors

    def vector(self, task, facts=''):
        return self.embeddings(task, facts)[0]

    def fit(self, vectors, labels, regularization):
        self.center = vectors.mean(axis=0)
        centered = vectors - self.center
        targets = np.array([1.0 if label == 'main' else -1.0 for label in labels])
        self.bias = targets.mean()
        # Dual ridge regression: all training examples contribute to the boundary.
        self.weights = centered.T @ np.linalg.solve(
            centered @ centered.T + regularization * np.eye(len(vectors)),
            targets - self.bias)

    def score(self, vector):
        return float((vector - self.center) @ self.weights + self.bias)

    def select(self, task, facts='', override=None, allow_long=False):
        started = time.perf_counter()
        if override is not None and override not in ('worker', 'main'):
            raise ValueError('invalid user model override')
        if not override and not task.strip():
            return {'role':'main','score':None,'window_scores':[],
                    'elapsed_seconds':time.perf_counter()-started,'backend':'local',
                    'api_calls':0,'usage':None,'insufficient_request':True,
                    'scores_are_success_probabilities':False}
        text = task.strip() + ('\n' + facts.strip() if facts.strip() else '')
        if not override and text and self.encoder.exceeds_limit(text) and not allow_long:
            return {'role': 'main', 'score': None, 'window_scores': [],
                    'elapsed_seconds': time.perf_counter()-started, 'backend':'local',
                    'api_calls':0, 'usage':None, 'capacity_fallback':True,
                    'scores_are_success_probabilities':False}
        vector, windows = (None, []) if override else self.embeddings(task, facts)
        score = None if vector is None else self.score(vector)
        # Averages can wash out architecture/risk in detailed contracts. For
        # multi-window inputs, a main signal in any window vetoes worker.
        # This is a conservative learned signal, not a risk-keyword rule.
        window_scores = [self.score(window) for window in windows]
        if window_scores:
            score = max(score, *window_scores)
        role = override or ('worker' if score is not None and score < self.threshold else 'main')
        return {'role': role, 'score': score, 'window_scores': window_scores, 'elapsed_seconds': time.perf_counter()-started,
                'backend': 'local', 'api_calls': 0, 'usage': None,
                'scores_are_success_probabilities': False}

    def save(self, path):
        np.savez(path, weights=self.weights, center=self.center,
                 bias=self.bias, threshold=self.threshold)

    def load(self, path):
        saved = np.load(path)
        self.weights = saved['weights']; self.center = saved['center']
        self.bias = float(saved['bias']); self.threshold = float(saved['threshold'])


def main():
    import argparse
    p = argparse.ArgumentParser(description='SEV classification only; never executes a task')
    p.add_argument('--task-file', required=True)
    p.add_argument('--context-file')
    p.add_argument('--model', choices=['worker', 'main'])
    args = p.parse_args()
    candidate = Candidate(); candidate.load(HERE/'sev-candidate.npz')
    result = candidate.select(open(args.task_file, encoding='utf-8-sig').read(),
        open(args.context_file, encoding='utf-8-sig').read() if args.context_file else '', args.model)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
