"""Bounded, unquantized CPU checkpoint derivation and block-scoped read mappings.

ML imports are deliberately delayed until the strict environment has been verified.
Original safetensors/checkpoint files are never written. No model-sized state_dict,
save_file, disk-offload copy, or additive merge in a forward hook is used.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import types

from .errors import fail

ALGORITHM = 'rev-row-merge-fp32-delta-v1'
CHUNK_BYTES = 4 * 1024 ** 2
PREFIX = 'model.language_model.'
SIZES = {'BF16': 2, 'F16': 2, 'F32': 4}
INTEGRITY_BUFFER_BYTES = 256 * 1024


def embedding_contract(shape, dtype, row_token_budget, batch_budget=1):
    """Shared allocation/read contract. No unique/sort/index-select temporary tensors.

    One output, one row bytearray and zero copied index tensors. The caller-owned
    indices are charged at int64 width. Python/Tensor metadata and allocator slack
    additionally live in the plan's unchanged runtime/activation reserves.
    """
    if (not isinstance(shape, (tuple, list)) or len(shape) != 2
            or any(type(n) is not int or n <= 0 for n in shape)
            or dtype not in ('bfloat16', 'float16', 'float32')
            or type(row_token_budget) is not int or not 1 <= row_token_budget <= 16384
            or type(batch_budget) is not int or not 1 <= batch_budget <= 16):
        fail('configuration', 'Unsupported bounded embedding shape/dtype/row/batch contract')
    tokens = (row_token_budget + 15) // 16 * 16
    ids = tokens * batch_budget
    if ids > 16384:
        fail('resource', 'Bounded embedding total ID budget exceeds 16384')
    row = shape[1] * (4 if dtype == 'float32' else 2)
    if row > CHUNK_BYTES:
        fail('resource', 'Embedding row exceeds bounded row buffer')
    result = dict(schema=1, shape=list(shape), dtype=dtype, max_batch=batch_budget,
                  max_row_tokens=tokens, max_ids=ids, row_buffer_bytes=row,
                  output_bytes=ids * row, indices_bytes=ids * 8,
                  integrity_buffer_bytes=INTEGRITY_BUFFER_BYTES,
                  copy_workspace_bytes=0, index_workspace_bytes=0)
    result['working_set_bytes'] = sum(result[key] for key in
        ('row_buffer_bytes', 'output_bytes', 'indices_bytes', 'integrity_buffer_bytes',
         'copy_workspace_bytes', 'index_workspace_bytes'))
    return result


def embedding_options(module):
    import torch
    if (type(module) is not torch.nn.Embedding or module.max_norm is not None
            or module.norm_type != 2.0 or module.scale_grad_by_freq or module.sparse
            or module.training or module.weight.device.type != 'meta'
            or module.padding_idx is not None and not 0 <= module.padding_idx < module.num_embeddings):
        fail('configuration', 'Bounded embedding requires eval meta nn.Embedding with default immutable options; padding_idx is supported')


def embedding_lookup(module, input, directory, item, contract, guard):
    """Bit-preserving row reads, including a nonzero stored padding row.

    Authenticate the same open file with a fixed buffer before row reads. This
    sequential integrity scan is not tensor materialization. No full weight mmap,
    tensor, index list, deduplication map or gather workspace exists here.
    """
    import torch
    from .loader import regular
    embedding_options(module)
    if (type(input) is not torch.Tensor or input.layout != torch.strided
            or input.device.type != 'cpu' or input.dtype not in (torch.int32, torch.int64)
            or input.ndim != 2 or not 1 <= input.shape[0] <= contract['max_batch']
            or not 1 <= input.shape[1] <= contract['max_row_tokens']
            or input.numel() > contract['max_ids']
            or input.untyped_storage().nbytes() > contract['indices_bytes']):
        fail('resource', 'Bounded embedding requires bounded CPU int32/int64 [batch,tokens] IDs/storage')
    # Complete validation precedes file opening, hashing, output or row allocation.
    for batch in range(input.shape[0]):
        for token in range(input.shape[1]):
            if not 0 <= input[batch, token].item() < contract['shape'][0]:
                fail('identity', 'Embedding ID outside verified vocabulary')
    guard()
    path = regular(Path(directory) / item['file'])
    expected_bytes = math.prod(contract['shape']) * module.weight.element_size()
    def fingerprint(stat):
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    with path.open('rb', buffering=0) as stream:
        before = os.fstat(stream.fileno())
        if before.st_nlink != 1 or before.st_size != expected_bytes or item['bytes'] != expected_bytes:
            fail('integrity', 'Embedding file size/link differs from verified row layout')
        buffer = bytearray(INTEGRITY_BUFFER_BYTES)
        view = memoryview(buffer)
        digest = hashlib.sha256()
        while count := stream.readinto(buffer):
            guard()
            digest.update(view[:count])
        del view, buffer
        if digest.hexdigest() != item['sha256']:
            fail('integrity', 'Embedding weight hash mismatch')
        guard()
        output = torch.empty((*input.shape, contract['shape'][1]), dtype=module.weight.dtype, device='cpu')
        raw = bytearray(contract['row_buffer_bytes'])
        row = torch.frombuffer(raw, dtype=module.weight.dtype)
        for batch in range(input.shape[0]):
            for token in range(input.shape[1]):
                guard()
                index = input[batch, token].item()
                # Recheck against concurrent caller mutation before every seek.
                offset = index * len(raw)
                if index < 0 or offset + len(raw) > expected_bytes:
                    fail('identity', 'Embedding ID changed outside verified vocabulary')
                stream.seek(offset)
                if stream.readinto(raw) != len(raw):
                    fail('integrity', 'Truncated embedding row')
                output[batch, token].copy_(row)
        if (fingerprint(before) != fingerprint(os.fstat(stream.fileno()))
                or fingerprint(before) != fingerprint(path.stat())):
            fail('integrity', 'Embedding file changed during authenticated lookup')
    guard()
    return output


class _EmbeddingForwardHandle:
    def __init__(self, module):
        self.module = module

    def remove(self):
        if self.module is not None:
            del self.module.forward
            self.module = None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def disjoint_destination(directory, protected):
    destination = Path(directory).resolve()
    for path in protected:
        path = Path(path).resolve()
        if destination.is_relative_to(path) or path.is_relative_to(destination):
            fail('configuration', 'Derived output must be separate from original snapshots, source and runtime')


def staging_path(path):
    from .loader import regular
    if os.path.lexists(path):
        regular(path)
        if path.stat().st_nlink != 1:
            fail('integrity', 'Hardlinked staging files are forbidden')


def tensor_catalog(base):
    """Read only bounded safetensors headers; callers first verify the originals."""
    base = Path(base)
    index = json.loads((base / 'model.safetensors.index.json').read_text())['weight_map']
    result = {}
    for shard in sorted(set(index.values())):
        if Path(shard).name != shard:
            fail('integrity', 'Unsafe shard name')
        path = base / shard
        with path.open('rb') as stream:
            size = struct.unpack('<Q', stream.read(8))[0]
            if not 2 <= size <= 16 * 1024 ** 2:
                fail('integrity', 'Invalid or oversized safetensors header')
            header = json.loads(stream.read(size))
        for name, entry in header.items():
            if name == '__metadata__':
                continue
            shape, offsets, dtype = entry['shape'], entry['data_offsets'], entry['dtype']
            if (dtype not in SIZES or not shape or any(type(x) is not int or x <= 0 for x in shape)
                    or len(offsets) != 2 or any(type(x) is not int for x in offsets)
                    or offsets[0] < 0 or offsets[1] - offsets[0] != math.prod(shape) * SIZES[dtype]
                    or 8 + size + offsets[1] > path.stat().st_size or index.get(name) != shard
                    or name in result):
                fail('integrity', 'Invalid tensor metadata or index')
            result[name] = dict(shape=shape, source_dtype=dtype, source_file=shard,
                                offset=8 + size + offsets[0], source_bytes=offsets[1] - offsets[0])
    if set(result) != set(index):
        fail('integrity', 'Shard/index tensor sets differ')
    return result


def text_catalog(catalog):
    result = {name[len(PREFIX):]: value for name, value in catalog.items() if name.startswith(PREFIX)}
    if not result:
        fail('identity', 'Pinned Qwen3.5 language backbone tensors are missing')
    return result


def merge_chunks(base, entry, pair, dtype, guard=lambda: None):
    """Official semantics: cast base to selected dtype, then add cast(2*B@A).

    Only the output-row dimension is split: each dot product retains its complete
    reduction dimension. The final cast/add has exactly the eager merge ordering.
    """
    import torch
    source_dtype = {'BF16': torch.bfloat16, 'F16': torch.float16, 'F32': torch.float32}[entry['source_dtype']]
    target_dtype = getattr(torch, dtype)
    shape = entry['shape']
    columns = math.prod(shape[1:])
    if columns * 4 > CHUNK_BYTES:
        fail('resource', 'A source tensor row exceeds the bounded merge buffer contract')
    rows = max(1, CHUNK_BYTES // (max(columns, 1) * 4))
    a = b = None
    if pair is not None:
        if len(shape) != 2 or set(pair) != {'a', 'b'}:
            fail('identity', 'Invalid LoRA pair')
        a, b = pair['a'], pair['b']
        if a.ndim != 2 or b.ndim != 2 or a.shape[1] != columns or b.shape != (shape[0], a.shape[0]):
            fail('identity', 'LoRA tensor shape mismatch')
        if a.numel() * 4 > 8 * 1024 ** 2 or a.shape[0] > 256:
            fail('resource', 'LoRA A/rank exceeds the bounded merge contract')
        rows = min(rows, max(1, CHUNK_BYTES // (a.shape[0] * 4)))
        # Adapter remains file-mapped. Convert only the small A matrix once and B rows.
        a = a.float()
    with (Path(base) / entry['source_file']).open('rb') as stream, torch.no_grad():
        stream.seek(entry['offset'])
        for first in range(0, shape[0], rows):
            guard()
            count = min(rows, shape[0] - first)
            raw = bytearray(stream.read(count * columns * SIZES[entry['source_dtype']]))
            if len(raw) != count * columns * SIZES[entry['source_dtype']]:
                fail('integrity', 'Truncated source tensor')
            weight = torch.frombuffer(raw, dtype=source_dtype).reshape(count, *shape[1:]).to(target_dtype)
            if pair is not None:
                delta = 2 * (b[first:first + count].float() @ a)
                weight.add_(delta.to(target_dtype))
                del delta
            # uint8/numpy is a view; only this bounded row chunk becomes bytes.
            yield weight.contiguous().view(torch.uint8).numpy().tobytes()
            del weight, raw


def derive(base, directory, catalog, adapters, identity, dtype, guard=lambda: None):
    """Build/verify each output from originals, including on reuse.

    A mutable local manifest never supplies its own trust anchor. Existing tensor
    files are reused only when their hash equals freshly derived expected bytes.
    Interrupted files have .partial suffix; a successful tensor is atomically replaced.
    """
    from .loader import regular, checked_file
    directory = Path(directory)
    # Reject linked directories before creating or replacing any artifacts.
    for parent in (directory, *directory.parents):
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
            fail('integrity', 'Linked derived artifact directories are forbidden')
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'manifest.json').exists():
        previous = json.loads(regular(directory / 'manifest.json').read_text(encoding='utf-8'))
        if previous.get('identity') != identity:
            fail('integrity', 'Derived code/artifact identity changed; use a new owned derived directory and retain previous evidence')
    if not adapters or not set(adapters) <= {name[:-7] for name in catalog if name.endswith('.weight')}:
        fail('identity', 'LoRA targets do not match the language backbone')
    tensors = {}
    for name, entry in sorted(catalog.items()):
        guard()
        filename = hashlib.sha256(name.encode()).hexdigest() + '.bin'
        path = directory / filename
        partial = directory / (filename + '.partial')
        staging_path(partial)
        if path.exists():
            regular(path)
        digest = hashlib.sha256()
        with partial.open('wb') as stream:
            for raw in merge_chunks(base, entry, adapters.get(name[:-7]) if name.endswith('.weight') else None, dtype, guard):
                stream.write(raw); digest.update(raw)
        expected = digest.hexdigest()
        reuse = False
        if path.exists():
            try:
                checked_file(path, expected)
                reuse = True
            except Exception:
                partial.unlink(missing_ok=True)
                fail('integrity', 'Existing derived tensor differs from independently regenerated originals; inspect task-owned artifacts')
        if reuse:
            partial.unlink()
        else:
            os.replace(partial, path)
        tensors[name] = dict(file=filename, sha256=expected, shape=entry['shape'], dtype=dtype,
                             bytes=path.stat().st_size, lora_merged=name[:-7] in adapters if name.endswith('.weight') else False)
    manifest = dict(schema=1, algorithm=ALGORITHM, identity=identity, dtype=dtype, tensors=tensors)
    raw = canonical(manifest)
    partial = directory / 'manifest.partial'
    staging_path(partial)
    if (directory / 'manifest.json').exists():
        regular(directory / 'manifest.json')
    partial.write_bytes(raw)
    os.replace(partial, directory / 'manifest.json')
    return hashlib.sha256(raw).hexdigest()


def verify_derived(directory, identity, expected_hash):
    from .loader import checked_bytes, checked_file
    directory = Path(directory)
    manifest = json.loads(checked_bytes(directory / 'manifest.json', expected_hash))
    if (manifest.get('schema') != 1 or manifest.get('algorithm') != ALGORITHM
            or manifest.get('identity') != identity):
        fail('integrity', 'Derived checkpoint provenance mismatch')
    for name, item in manifest['tensors'].items():
        if item['file'] != hashlib.sha256(name.encode()).hexdigest() + '.bin':
            fail('integrity', 'Invalid derived tensor filename')
        checked_file(directory / item['file'], item['sha256'])
    return manifest


def attach_mapped_blocks(backbone, directory, manifest, guard=lambda: None, *, embedding_plan=None):
    """Compact embedding reads and current decoder/norm private mappings.

    Parameters are read-only by contract (inference_mode, no merge hooks); private
    mappings cannot write derived files. Tied aliases map identical verified bytes.
    Hooks capture neither the wrapper nor the adapter nor a resident state_dict.
    """
    import torch
    from .loader import checked_file
    directory = Path(directory)
    tensors = manifest['tensors']
    parameters = dict(backbone.named_parameters(remove_duplicate=False))
    if set(parameters) != set(tensors):
        fail('identity', 'Derived tensors and exact backbone parameters differ')
    aliases = {}
    embedding = backbone.embed_tokens
    embedding_options(embedding)
    item = tensors['embed_tokens.weight']
    if (not isinstance(embedding_plan, dict) or embedding_plan != embedding_contract(
            item['shape'], item['dtype'], embedding_plan.get('max_row_tokens', 0),
            embedding_plan.get('max_batch', 0))
            or [embedding.num_embeddings, embedding.embedding_dim] != item['shape']
            or 'forward' in embedding.__dict__ or embedding._forward_pre_hooks or embedding._forward_hooks
            or sum(module is embedding for _, module in backbone.named_modules(remove_duplicate=False)) != 1
            or [name for name, parameter in parameters.items() if parameter is embedding.weight] != ['embed_tokens.weight']):
        fail('configuration', 'Missing/inconsistent bounded embedding plan or unsupported embedding override/hooks/alias')
    for name, parameter in parameters.items():
        item = tensors[name]
        if list(parameter.shape) != item['shape'] or str(parameter.dtype).split('.')[-1] != item['dtype']:
            fail('identity', 'Derived tensor shape/dtype differs from meta architecture')
        if id(parameter) in aliases and aliases[id(parameter)] != item['sha256']:
            fail('integrity', 'Tied parameter aliases have different derived values')
        aliases[id(parameter)] = item['sha256']
    groups = [('layers.%d' % i, layer) for i, layer in enumerate(backbone.layers)] + [('norm', backbone.norm)]
    covered = {'embed_tokens.weight'}
    handles = []
    # Validate all coverage before installing any hook or forward replacement.
    if covered | {prefix + '.' + local for prefix, block in groups
                  for local, _ in block.named_parameters(remove_duplicate=False)} != set(parameters):
        fail('identity', 'Backbone parameters exist outside supported execution blocks')
    # Capture only the embedding meta parameter, not a full parameter dictionary.
    original_embedding = parameters['embed_tokens.weight']
    embedding_item = dict(tensors['embed_tokens.weight'])
    embedding_plan = dict(embedding_plan)
    def compact_forward(module, input):
        if module.weight is not original_embedding:
            fail('identity', 'Bounded embedding meta parameter changed')
        return embedding_lookup(module, input, directory, embedding_item, embedding_plan, guard)
    embedding.forward = types.MethodType(compact_forward, embedding)
    handles.append(_EmbeddingForwardHandle(embedding))
    for prefix, block in groups:
        entries = []
        for local, parameter in block.named_parameters(remove_duplicate=False):
            name = prefix + '.' + local
            parent_name, _, leaf = local.rpartition('.')
            parent = block.get_submodule(parent_name) if parent_name else block
            entries.append((parent, leaf, parameter, tensors[name]))
            covered.add(name)
        def before(module, args, entries=entries):
            guard()
            for parent, leaf, original, item in entries:
                path = directory / item['file']
                checked_file(path, item['sha256'])
                mapped = torch.from_file(str(path), shared=False, size=math.prod(item['shape']),
                                         dtype=getattr(torch, item['dtype'])).reshape(item['shape'])
                parent._parameters[leaf] = torch.nn.Parameter(mapped, requires_grad=False)
        def after(module, args, output, entries=entries):
            for parent, leaf, original, item in entries:
                parent._parameters[leaf] = original
            guard()
        handles.extend([block.register_forward_pre_hook(before),
                        block.register_forward_hook(after, always_call=True)])
    if covered != set(parameters):
        for handle in handles:
            handle.remove()
        fail('identity', 'Backbone parameters exist outside supported execution blocks')
    return handles
