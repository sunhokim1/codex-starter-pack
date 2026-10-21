"""Offline-only verified loading of the pinned official LoRA/pointer-head implementation.

No Hub download call exists here. Provision snapshots and a reviewed environment lock
in a separate isolated runtime. Importing this module does not import ML packages.
"""
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
from pathlib import Path
import sys
import time
import types

from . import contracts as c
from .errors import RevError, fail
from .hardware import DTYPES, diagnose, normalize_mode, require_hardware, require_runtime, execution_plan, memory_status, check_plan

BUNDLE = Path(__file__).resolve().parents[2]
PROVENANCE = BUNDLE / 'contracts/provenance'


def regular(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            fail('integrity', 'Linked/reparse runtime paths are not allowed')
    if not path.is_file():
        fail('integrity', 'Required local artifact is missing; provision the pinned snapshot explicitly')
    return path


def checked_bytes(path, expected):
    raw = regular(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        fail('integrity', 'Artifact hash mismatch; discard the corrupt isolated snapshot and provision the pinned revision again')
    return raw


def checked_file(path, expected):
    with regular(path).open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        fail('integrity', 'Local wheel/installed file hash mismatch; rebuild the isolated environment from reviewed wheels')


def locked_provenance():
    lock = json.loads((BUNDLE / 'contracts/upstream.lock.json').read_text(encoding='utf-8'))
    c.validate_lock(lock)
    index = json.loads((PROVENANCE / 'index.json').read_text(encoding='utf-8'))
    # index and lock are shipped inside the release manifest; release/package integrity
    # must be verified by installer before Python executes this trusted runtime.
    base = json.loads(checked_bytes(PROVENANCE / 'base-api.json', index['base-api.json']['sha256']))
    if base['sha'] != lock['base']['revision']:
        fail('integrity', 'Base metadata revision mismatch')
    source = checked_bytes(PROVENANCE / 'serve_local.py.txt', lock['source']['artifacts']['serve_local.py'])
    return lock, base, source


def verify_base(directory, lock, metadata):
    regular(Path(directory) / 'config.json')  # Reject linked parent before resolve erases it.
    root = Path(directory).resolve(strict=True)
    known = {entry['rfilename']: entry for entry in metadata['siblings']}
    required = {'config.json', 'tokenizer_config.json', 'tokenizer.json', 'vocab.json', 'merges.txt',
                'model.safetensors.index.json', *lock['base']['artifacts']}
    found = {str(p.relative_to(root)).replace('\\', '/') for p in root.rglob('*') if p.is_file()}
    if not required <= found or not found <= set(known):
        fail('integrity', 'Incomplete base snapshot or unlisted files; provision only files from the pinned base revision (no custom code)')
    for name in sorted(found):
        item = known[name]; path = regular(root / name)
        # Non-LFS content is anchored by immutable Hub Git blob identity. SHA256 LFS
        # identities cover tensors/tokenizer; do not confuse Git SHA1 with SHA256.
        expected = lock['base']['artifacts'].get(name) or item.get('lfs', {}).get('sha256')
        hasher = hashlib.sha256() if expected else hashlib.sha1()
        size = path.stat().st_size
        if size != item['size']:
            fail('integrity', 'Base artifact size mismatch')
        if not expected:
            hasher.update(('blob %d\0' % size).encode('ascii'))
            expected = item['blobId']
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
        if hasher.hexdigest() != expected:
            fail('integrity', 'Base artifact identity mismatch; do not load')
    index = json.loads((root / 'model.safetensors.index.json').read_text())
    if not set(index['weight_map'].values()) <= found:
        fail('integrity', 'Weight index references an unverified shard')
    return root


def isolated_prefix(receipt):
    """Locate a venv without site initialization (also on Python before 3.14)."""
    root = Path(receipt.get('venv') or '').resolve()
    executable = Path(os.path.abspath(sys.executable))
    expected_bin = root / ('Scripts' if os.name == 'nt' else 'bin')
    # Do not resolve the executable on POSIX: a normal venv uses a symlink to
    # the trusted interpreter, while artifacts and site-packages reject links.
    if executable.parent != expected_bin or not executable.is_file() or not (root / 'pyvenv.cfg').is_file():
        fail('environment', 'Use the explicitly locked isolated venv interpreter, never shared SEV/global Python')
    regular(root / 'pyvenv.cfg')
    if expected_bin.is_symlink():
        fail('environment', 'The venv executable directory must not be linked')
    # Before 3.14, -S leaves prefix at base_prefix; it must not redirect us to
    # global site-packages. The explicit venv/executable identity is authoritative.
    if Path(sys.prefix).resolve() not in (root, Path(sys.base_prefix).resolve()):
        fail('environment', 'Interpreter prefix differs from the explicitly locked venv')
    return root


def verify_environment(environment, lock):
    """Reviewable installer output, not a resolver or an implicit install command.

    Pin each exact version, original wheel SHA256 AND installed RECORD SHA256.
    Verify the RECORD's installed files before importing any model dependency.
    No generated receipt can supply its own trusted expected hashes.
    """
    receipt = json.loads(regular(environment).read_text(encoding='utf-8'))
    if receipt.get('schema') != 1 or receipt.get('resolved') is not True:
        fail('environment', 'Resolve/review exact dependency wheels in an isolated runtime and supply its environment lock; shipped template is intentionally unresolved')
    if not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:
        fail('environment', 'Start the isolated interpreter with -I -S -B so site/.pth code and unverified bytecode cannot execute before integrity checks')
    prefix = isolated_prefix(receipt)
    dependencies = receipt.get('distributions', {})
    if not set(lock['dependencies']) <= set(dependencies):
        fail('environment', 'Environment lock omits a required direct dependency')
    site = prefix / ('Lib/site-packages' if os.name == 'nt' else 'lib/python%d.%d/site-packages' % sys.version_info[:2])
    # Do not call site.addsitedir: it would execute .pth files before verification.
    distributions = {dist.metadata['Name'].lower().replace('-', '_'): dist
                     for dist in importlib.metadata.distributions(path=[str(site)])}
    installed_names = set(distributions)
    if not installed_names <= set(dependencies):
        fail('environment', 'Every installed distribution (including transitives/tools) must be locked; remove unreviewed optional CUDA extensions')
    verified_files = set()
    for name, item in dependencies.items():
        version = item.get('version')
        if not isinstance(version, str) or not version:
            fail('environment', 'Exact distribution versions are required')
        declared = lock['dependencies'].get(name, {})
        if declared.get('status') == 'upstream_pinned' and declared['version'] != version:
            fail('environment', 'Environment differs from an upstream version pin')
        checked_file(item['wheel'], item['wheel_sha256'])
        if name not in distributions:
            fail('environment', 'Locked distribution is not installed in the isolated site-packages')
        distribution = distributions[name]
        if distribution.version != version:
            fail('environment', 'Installed distribution version mismatch')
        files = distribution.files or []
        # A wheel can include vendored distributions (e.g. setuptools). Their
        # RECORD files are payload covered by the outer RECORD, not alternative
        # installation manifests. Keep verifying every payload entry below.
        records = [p for p in files if len(Path(p).parts) == 2
                   and Path(p).parts[0].endswith('.dist-info') and Path(p).name == 'RECORD']
        if len(records) != 1:
            fail('integrity', 'Distribution must have exactly one wheel RECORD')
        raw = checked_bytes(distribution.locate_file(records[0]), item['record_sha256'])
        for relative, digest, size in csv.reader(io.StringIO(raw.decode('utf-8'))):
            located = distribution.locate_file(relative)
            # pip may list generated bytecode. Absent bytecode is safe; present
            # bytecode must be explicitly hashed because Python can execute it.
            if relative.endswith('.pyc') and not Path(located).exists():
                continue
            path = regular(located)
            verified_files.add(path.resolve())
            if not path.resolve().is_relative_to(prefix):
                fail('integrity', 'Installed file escapes isolated venv')
            if not digest:
                if relative != str(records[0]):
                    fail('integrity', 'Unhashed executable distribution file')
                continue
            algorithm, encoded = digest.split('=', 1)
            if algorithm != 'sha256':
                fail('integrity', 'Only SHA256 wheel RECORD entries are supported')
            expected = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).hex()
            checked_file(path, expected)
            if size and path.stat().st_size != int(size):
                fail('integrity', 'Installed distribution file size mismatch')
    for path in site.rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.py', '.pyc', '.pyd', '.so', '.dll') and path.resolve() not in verified_files:
            fail('integrity', 'Unlisted executable file/bytecode in isolated site-packages; rebuild from reviewed wheels')
    sys.path.insert(0, str(site))  # Verified code becomes importable only now; .pth is never evaluated.
    return receipt


def load_verified(base_directory, adapter_directory, environment, device=0, dtype='bf16',
                  memory_mode='full-resident', offload_directory=None, row_token_budget=16384,
                  process_budget_bytes=None, safety_margin_bytes=None, preflight_request=None):
    device_name, dtype = normalize_mode(device, dtype)
    if memory_mode not in ('full-resident', 'bounded-cpu'):
        fail('configuration', 'Unsupported memory mode; no implicit fallback')
    bounded = memory_mode == 'bounded-cpu'
    if bounded and (device_name != 'cpu' or not offload_directory):
        fail('configuration', 'Bounded mapping requires explicit cpu and a task-owned offload directory')
    if not bounded:
        require_hardware(diagnose(), device_name, dtype)  # Resident estimate only.
    elif any(type(value) is not int or value <= 0 for value in memory_status().values()):
        fail('hardware', 'Fresh RAM probe unknown; do not import ML libraries')
    lock, base_metadata, source = locked_provenance()
    receipt = verify_environment(environment, lock)
    base = verify_base(base_directory, lock, base_metadata)
    checkpoint_path = regular(Path(adapter_directory) / 'checkpoint.pt')
    try:
        c.verify_artifacts(adapter_directory, lock['adapter']['artifacts'])
    except (c.ContractError, OSError):
        fail('integrity', 'Adapter checkpoint does not match its independently pinned adapter revision')
    plan = None
    if bounded:
        from . import offload
        offload.disjoint_destination(offload_directory,
             [base, adapter_directory, receipt['venv'], BUNDLE, environment])
        catalog = offload.text_catalog(offload.tensor_catalog(base))
        plan = execution_plan(memory_status(), catalog, dtype, memory_mode, row_token_budget,
                              process_budget_bytes, safety_margin_bytes, budget_is_ceiling=True)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', FLA_USE_COMPILE='0', HF_HUB_DISABLE_IMPLICIT_TOKEN='1')
    # Execute exactly the previously hashed bytes. Do NOT invoke upstream resolve_checkpoint/load/build_app.
    official = types.ModuleType('_verified_rev_official'); official.__file__ = str(PROVENANCE / 'serve_local.py.txt')
    import torch
    from transformers import AutoTokenizer, AutoModelForImageTextToText
    require_runtime(torch, memory_status() if bounded else diagnose(), device_name, dtype, plan=plan)
    exec(compile(source, official.__file__, 'exec'), official.__dict__)
    start = time.monotonic()
    # Hold and hash the same open checkpoint handle passed to torch.load, before pickle deserialization.
    with checkpoint_path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        if sha != lock['adapter']['artifacts']['checkpoint.pt']:
            fail('integrity', 'Checkpoint changed before deserialization')
        stream.seek(0)
        if bounded:
            # mmap requires a pathname, not an open file. Recheck the opened file's
            # identity before/after loading the independently hashed pinned pickle.
            before = checkpoint_path.stat()
            checkpoint = torch.load(str(checkpoint_path), map_location='cpu', weights_only=False, mmap=True)
            after = checkpoint_path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                fail('integrity', 'Checkpoint changed during mapped deserialization')
        else:
            checkpoint = torch.load(stream, map_location='cpu', weights_only=False)
    metadata = checkpoint['metadata']
    if (metadata.get('model') != lock['base']['repo'] or metadata.get('revision') != lock['base']['revision']
            or metadata.get('temperature') != 1.96 or metadata.get('state_format') != 'raw'):
        fail('identity', 'Checkpoint metadata differs from pinned model card/source')
    torch.manual_seed(814)
    if device_name != 'cpu':
        torch.backends.cuda.enable_cudnn_sdp(False)
    tokenizer = AutoTokenizer.from_pretrained(str(base), local_files_only=True, trust_remote_code=False)
    warmup_tokens = None
    preflight_tokens = None
    if bounded:
        # Use the official encoder before any expensive derivation, not a token
        # approximation or a shortened replacement warmup.
        probe = types.SimpleNamespace(tok=tokenizer, state_format='raw')
        warmup_ids, _, _ = official.Scorer.encode(probe, official.SELFTEST_REQUEST['state'],
                                                official.SELFTEST_REQUEST['questions'][0])
        warmup_tokens = len(warmup_ids)
        if warmup_tokens > plan['row_token_budget']:
            fail('resource', 'Official mandatory warmup exceeds selected row budget; select a safely admitted larger plan, never truncate warmup')
        if preflight_request is not None:
            preflight_tokens = preflight_rows(official, probe, preflight_request, plan['row_token_budget'])
    if bounded:
        from accelerate import init_empty_weights
        from transformers import AutoConfig
        guard = lambda: check_plan(plan)
        guard()
        # include_buffers=False preserves the tiny real CPU RoPE buffers; no
        # full model is ever materialized and no from_pretrained copy is made.
        with init_empty_weights(include_buffers=False):
            config = AutoConfig.from_pretrained(str(base), local_files_only=True, trust_remote_code=False)
            full = AutoModelForImageTextToText.from_config(config, trust_remote_code=False,
                       dtype=getattr(torch, DTYPES[dtype]), attn_implementation='sdpa').eval()
    else:
        full = AutoModelForImageTextToText.from_pretrained(str(base), local_files_only=True, trust_remote_code=False,
                    dtype=getattr(torch, DTYPES[dtype]), device_map=device_name, attn_implementation='sdpa').eval()
    backbone = full.model.language_model; del full
    modules = dict(backbone.named_modules())
    if not checkpoint['adapters']:
        fail('identity', 'Checkpoint has no LoRA adapters')
    for name, weights in checkpoint['adapters'].items():
        module = modules[name]
        if not isinstance(module, torch.nn.Linear) or name.split('.')[-1] not in official.LORA_TARGETS:
            fail('identity', 'Unexpected LoRA target')
        if not bounded:
            with torch.no_grad():
                module.weight.add_((2 * (weights['b'].float() @ weights['a'].float())).to(module.weight.dtype).to(module.weight.device))
        elif (weights['a'].numel() * 4 > 8 * 1024 ** 2 or weights['a'].shape[0] > 256):
            fail('resource', 'LoRA rank/A matrix exceeds the bounded merge contract')
    if bounded:
        identity = dict(source_revision=lock['source']['revision'], base_revision=lock['base']['revision'],
                        adapter_revision=lock['adapter']['revision'], checkpoint_sha256=sha,
                        environment_sha256=hashlib.sha256(regular(environment).read_bytes()).hexdigest(),
                        dtype=dtype, algorithm=offload.ALGORITHM,
                        algorithm_sha256=hashlib.sha256(regular(Path(offload.__file__)).read_bytes()).hexdigest())
        destination = Path(offload_directory)
        ancestor = destination
        while not ancestor.exists():
            ancestor = ancestor.parent
        # Resumable completed artifacts may already consume this space. Require
        # one full derived checkpoint plus a largest-tensor staging file.
        needed = plan['weights_bytes'] + plan['largest_source_tensor_bytes']
        if shutil.disk_usage(ancestor).free < needed:
            fail('resource', 'Insufficient SSD space for verified derived tensors and atomic staging; disk is not RAM')
        derived_hash = offload.derive(base, destination, catalog, checkpoint['adapters'], identity, DTYPES[dtype], guard)
        manifest = offload.verify_derived(destination, identity, derived_hash)
        offload.attach_mapped_blocks(backbone, destination, manifest, guard, embedding_plan=plan['embedding'])
    heads = [torch.nn.Linear(backbone.config.hidden_size, 256, bias=False, device=device_name, dtype=torch.float32) for _ in range(2)]
    heads[0].load_state_dict(checkpoint['headq']); heads[1].load_state_dict(checkpoint['headk'])
    del checkpoint, modules, weights, module
    info = dict(model=lock['base']['repo'], revision=lock['base']['revision'], adapter_revision=lock['adapter']['revision'],
                checkpoint_sha256=sha, temperature=1.96, state_format='raw', device=device_name, dtype=dtype,
                max_row_tokens=official.MAX_ROW_TOKENS, warmed=False, ready=False)
    scorer = official.Scorer(tokenizer, backbone, *heads, info)
    if bounded:
        # Official Scorer infers device from the first parameter, which is meta
        # between block calls. Execution itself and FP32 heads stay on CPU.
        scorer.device = torch.device('cpu')
        info.update(memory_plan=plan, derived_manifest_sha256=derived_hash, offload_mode='block-private-mmap',
                    embedding_mode='authenticated-bounded-row-read',
                    warmup_tokens=warmup_tokens, preflight_encoded_tokens=preflight_tokens,
                    inference_evidence='not-yet-run')
        official_run_rows = scorer.run_rows
        def guarded_run_rows(rows):
            if max(len(ids) for ids, _ in rows) > plan['row_token_budget'] or len(rows) != 1:
                fail('resource', 'Input exceeds the explicitly planned single-row memory budget; reduce input explicitly, never truncate')
            guard()
            return official_run_rows(rows)
        scorer.run_rows = guarded_run_rows
    scorer.warm()
    if bounded:
        info['inference_evidence'] = 'official-warmup-completed; authenticated-score-evidence-required'
    info.update(warmed=True, ready=True, load_seconds=time.monotonic() - start)
    return scorer


def preflight_rows(official, probe, body, budget):
    c.validate_request(body)
    if len(body['questions']) != 1 or set(body['questions'][0]['criteria']) != {'worker', 'main'}:
        fail('input', 'Preflight requires one worker/main question')
    tokens = [len(official.Scorer.encode(probe, body['state'], q)[0]) for q in body['questions']]
    if any(not value or value > min(budget, c.MAX_ROW_TOKENS) for value in tokens):
        fail('oversize', 'Official preflight encoded row tokens=%s exceed selected budget=%d; no model derivation/forward and no truncation' % (tokens, budget))
    return tokens


def check_rows(scorer, body):
    """Use official tokenizer/prompt encoder, never a character/token approximation."""
    c.validate_request(body)
    if len(body['questions']) != 1 or set(body['questions'][0]['criteria']) != {'worker', 'main'}:
        fail('input', 'Local routing endpoint accepts one worker/main question per request')
    rows = [scorer.encode(body['state'], question) for question in body['questions']]
    if any(not ids or len(ids) > c.MAX_ROW_TOKENS for ids, _, _ in rows):
        fail('oversize', 'Official encoded row exceeds 16384 tokens; explicitly reduce dependencies, never truncate mandatory context')
    return rows
