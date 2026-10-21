"""Read-only diagnostics. No torch import, downloads, installations or GPU allocation."""
if not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "rev"

import ctypes
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

from .errors import RevError, fail

GIB = 1024 ** 3


def registry_adapters():
    """Read-only Windows fallback when CIM is unavailable; memory is not CUDA VRAM."""
    adapters = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Video') as video:
            for index in range(min(winreg.QueryInfoKey(video)[0], 64)):
                name = winreg.EnumKey(video, index)
                try:
                    with winreg.OpenKey(video, name + r'\0000') as adapter:
                        label = winreg.QueryValueEx(adapter, 'HardwareInformation.AdapterString')[0]
                        if isinstance(label, bytes):
                            label = label.decode('utf-16-le', errors='replace').rstrip('\0')
                        memory = None
                        try:
                            memory = winreg.QueryValueEx(adapter, 'HardwareInformation.qwMemorySize')[0]
                        except OSError:
                            pass
                        if isinstance(label, str) and label and not any(a['Name'] == label for a in adapters):
                            adapters.append(dict(Name=label, AdapterRAM=memory if isinstance(memory, int) else None,
                                                 source='read_only_registry_not_dedicated_vram'))
                except OSError:
                    pass
    except (ImportError, OSError):
        pass
    return adapters


def command(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=8, check=True,
                              **({'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {})).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def diagnose():
    result = dict(os=platform.system(), release=platform.release(), machine=platform.machine(),
                  total_ram_bytes=None, available_ram_bytes=None, display_adapters=[],
                  nvidia=[], cuda_driver_observed=False, limitations=[])
    if result['os'] == 'Windows':
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]
        memory = Memory(); memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            result.update(total_ram_bytes=memory.total, available_ram_bytes=memory.available)
        raw = command(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                       '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress'])
        if raw:
            try:
                adapters = json.loads(raw)
                result['display_adapters'] = adapters if isinstance(adapters, list) else [adapters]
            except ValueError:
                result['limitations'].append('display adapter probe could not be parsed')
        else:
            result['limitations'].append('Windows CIM display adapter probe unavailable; attempting read-only registry fallback')
        if not result['display_adapters']:
            result['display_adapters'] = registry_adapters()
    elif result['os'] == 'Linux':
        try:
            values = {line.split(':')[0]: int(line.split()[1]) * 1024
                      for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:', 'MemAvailable:'))}
            result.update(total_ram_bytes=values.get('MemTotal'), available_ram_bytes=values.get('MemAvailable'))
        except (OSError, ValueError):
            result['limitations'].append('RAM probe unavailable')
    binary = shutil.which('nvidia-smi')
    if binary:
        raw = command([binary, '--query-gpu=index,name,memory.total,memory.free,driver_version', '--format=csv,noheader,nounits'])
        try:
            for line in (raw or '').splitlines():
                index, name, total, free, driver = [x.strip() for x in line.split(',')]
                result['nvidia'].append(dict(index=int(index), name=name, total_bytes=int(total) * 1024 ** 2,
                                             free_bytes=int(free) * 1024 ** 2, driver=driver))
            result['cuda_driver_observed'] = bool(result['nvidia'])
        except (ValueError, TypeError):
            result['nvidia'] = []
    result['limitations'].append('nvidia-smi is driver evidence only; CUDA/bf16 compatibility is checked again by the loader')
    return result


DTYPES = {'bf16': 'bfloat16', 'fp16': 'float16', 'fp32': 'float32'}


def normalize_mode(device=0, dtype='bf16'):
    """Legacy integer/digit CUDA indices remain accepted; never silently fall back."""
    if type(device) is int and device >= 0:
        device = 'cuda:%d' % device
    elif isinstance(device, str) and re.fullmatch(r'[0-9]+', device, flags=re.ASCII):
        device = 'cuda:%d' % int(device)
    elif device == 'cuda':
        device = 'cuda:0'
    if not isinstance(device, str) or not re.fullmatch(r'cpu|cuda:(0|[1-9][0-9]*)', device, flags=re.ASCII):
        fail('configuration', 'Select cpu or cuda:N (legacy nonnegative CUDA indices are accepted); Intel Iris Xe is not CUDA/XPU support')
    if not isinstance(dtype, str) or dtype not in DTYPES:
        fail('configuration', 'Select bf16, fp16 or fp32 explicitly; no implicit quantization or dtype fallback')
    return device, dtype


def resource_estimate(device=0, dtype='bf16'):
    device, dtype = normalize_mode(device, dtype)
    # Upper planning bound for the pinned 4B full image-text model, not a measured
    # minimum or upstream requirement. Keep checkpoint/merge and working reserves.
    weights = 4_500_000_000 * (4 if dtype == 'fp32' else 2)
    checkpoint = 2 * GIB
    working = 4 * GIB  # heads, activations, allocator; long rows can still OOM
    return dict(weights_bytes=weights, checkpoint_reserve_bytes=checkpoint,
                working_reserve_bytes=working,
                host_bytes=(2 * weights + checkpoint + working if device == 'cpu' else weights + checkpoint + GIB),
                device_bytes=0 if device == 'cpu' else weights + working,
                mode='full-resident', measured=False,
                assumptions='Legacy full-resident planning estimate only, not a universal minimum. Bounded CPU mapping requires a separate tensor-derived execution_plan. Long rows may need more.')


def memory_status():
    """Cheap fresh RAM probe, without CIM/driver subprocesses in forward hooks."""
    if platform.system() == 'Windows':
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]
        value = Memory(); value.length = ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            return dict(total_ram_bytes=value.total, available_ram_bytes=value.available)
    elif platform.system() == 'Linux':
        try:
            values = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in
                      Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:', 'MemAvailable:'))}
            return dict(total_ram_bytes=values['MemTotal'], available_ram_bytes=values['MemAvailable'])
        except (OSError, ValueError, KeyError):
            pass
    return dict(total_ram_bytes=None, available_ram_bytes=None)


def process_memory():
    """Current process only. Unknown counters stay unknown, never zero."""
    if platform.system() == 'Windows':
        class Counters(ctypes.Structure):
            _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage',
                 'PeakPagefileUsage', 'PrivateUsage')]
        value = Counters(); value.cb = ctypes.sizeof(value)
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        function = ctypes.windll.psapi.GetProcessMemoryInfo
        function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if function(kernel.GetCurrentProcess(), ctypes.byref(value), value.cb):
            return dict(rss_bytes=value.WorkingSetSize, peak_rss_bytes=value.PeakWorkingSetSize,
                        private_bytes=value.PrivateUsage)
    elif platform.system() == 'Linux':
        try:
            status = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in
                      Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:', 'VmHWM:'))}
            private = sum(int(line.split()[1]) * 1024 for line in Path('/proc/self/smaps_rollup').read_text().splitlines()
                          if line.startswith(('Private_Clean:', 'Private_Dirty:')))
            return dict(rss_bytes=status['VmRSS'], peak_rss_bytes=status['VmHWM'], private_bytes=private)
        except (OSError, ValueError, KeyError):
            pass
    return dict(rss_bytes=None, peak_rss_bytes=None, private_bytes=None)


def cpu_options(threads=None, priority='normal'):
    if threads is not None and (type(threads) is not int or not 1 <= threads <= 64):
        fail('configuration', 'CPU threads must be an integer within 1..64')
    if priority not in ('normal', 'above-normal'):
        fail('configuration', 'CPU priority must be normal or above-normal; High/Realtime forbidden')
    return threads, priority


def cpu_environment(threads=None, priority='normal'):
    threads, _ = cpu_options(threads, priority)
    return {} if threads is None else dict(OMP_NUM_THREADS=str(threads), MKL_NUM_THREADS=str(threads))


def preparation_threads(threads=None):
    """Explicit CPU policies preserve the original two-thread derivation/warmup.

    Unspecified service policy retains the inherited environment for compatibility.
    No ML imports are permitted here.
    """
    cpu_options(threads)
    return None if threads is None else 2


def configure_worker_cpu(threads=None, priority='normal', owned_job=False):
    """Only this worker changes priority; gateway/watchdog remain untouched."""
    import os
    import ctypes as C
    threads, priority = cpu_options(threads, priority)
    os.environ.update(cpu_environment(threads, priority))  # before any ML import
    observed = None
    if priority == 'above-normal' and (os.name != 'nt' or not owned_job):
        fail('configuration', 'AboveNormal requires an explicitly gated private Windows job')
    if os.name == 'nt':
        from ctypes import wintypes as W
        kernel = C.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = W.HANDLE
        kernel.GetPriorityClass.argtypes = [W.HANDLE]; kernel.GetPriorityClass.restype = W.DWORD
        kernel.SetPriorityClass.argtypes = [W.HANDLE, W.DWORD]; kernel.SetPriorityClass.restype = W.BOOL
        kernel.IsProcessInJob.argtypes = [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)]
        kernel.IsProcessInJob.restype = W.BOOL
        handle = kernel.GetCurrentProcess()
        member = W.BOOL()
        if priority == 'above-normal' and (not kernel.IsProcessInJob(handle, None, C.byref(member)) or not member.value):
            fail('identity', 'Worker is not in the owned launch job; priority unchanged')
        expected = 0x8000 if priority == 'above-normal' else 0x20
        if not kernel.SetPriorityClass(handle, expected):
            fail('resource', 'Cannot set requested ML worker priority; no model load')
        observed = kernel.GetPriorityClass(handle)
        if observed != expected:
            fail('resource', 'ML worker priority readback differs; no model load')
    return dict(worker_pid=os.getpid(), requested_threads=threads, requested_priority=priority,
                worker_priority_class=observed, omp_num_threads=os.environ.get('OMP_NUM_THREADS'),
                mkl_num_threads=os.environ.get('MKL_NUM_THREADS'))


def activation_estimate(tokens):
    # Explicit conservative selected-row planning reserve, NOT a measured minimum.
    # FP32 attention matrix (16 heads), hybrid FP32 intermediates and allocator slack.
    return 256 * 1024 ** 2 + 16 * 4 * tokens ** 2 + tokens * 2560 * 4 * 32


def execution_plan(report, catalog, dtype='bf16', mode='bounded-cpu', row_token_budget=256,
                   process_budget_bytes=None, safety_margin_bytes=None, budget_is_ceiling=False,
                   embedding_batch_budget=1):
    """Tensor-derived CPU plan, distinct from legacy full-resident candidates.

    SSD space is checked by the derivation caller, never counted as available RAM.
    Estimates require actual watchdog measurements in an owned worker before use.
    """
    normalize_mode('cpu', dtype)
    if mode not in ('bounded-cpu', 'full-resident') or type(row_token_budget) is not int or not 1 <= row_token_budget <= 16384:
        fail('configuration', 'Select a supported memory mode and explicit row token budget within 1..16384')
    total, available = report.get('total_ram_bytes'), report.get('available_ram_bytes')
    if any(type(value) is not int or value <= 0 for value in (total, available)) or available > total:
        fail('hardware', 'RAM resources unknown or inconsistent; do not import/load the model')
    margin = max(GIB, total // 12) if safety_margin_bytes is None else safety_margin_bytes
    if type(margin) is not int or margin < GIB:
        fail('configuration', 'System safety margin must be at least 1 GiB')
    budget = available - margin if process_budget_bytes is None else process_budget_bytes
    requested_budget = budget
    if budget_is_ceiling and type(budget) is int:
        # An external watchdog's upper limit is never permission to consume RAM
        # which disappeared during integrity verification. Only reduce it.
        budget = min(budget, available - margin)
    if type(budget) is not int or not 0 < budget <= available - margin:
        fail('hardware', 'Selected process budget exceeds fresh available RAM minus system safety margin')
    width = 4 if dtype == 'fp32' else 2
    from .offload import embedding_contract, INTEGRITY_BUFFER_BYTES
    if 'embed_tokens.weight' not in catalog:
        fail('identity', 'Exact embedding metadata is required for a memory plan')
    compact = embedding_contract(catalog['embed_tokens.weight']['shape'], DTYPES[dtype],
                                 row_token_budget, embedding_batch_budget)
    groups = {}
    weights = 0
    largest_tensor = 0
    for name, item in catalog.items():
        if (not isinstance(item.get('shape'), (list, tuple)) or not item['shape']
                or any(type(n) is not int or n <= 0 for n in item['shape'])):
            fail('identity', 'Invalid tensor shape in memory catalog')
        size = __import__('math').prod(item['shape']) * width
        weights += size
        largest_tensor = max(largest_tensor, size)
        if name == 'embed_tokens.weight' and mode == 'bounded-cpu':
            continue
        group = '.'.join(name.split('.')[:2]) if name.startswith('layers.') else name.split('.')[0]
        groups[group] = groups.get(group, 0) + size
    dense = max(groups.values(), default=0)
    largest = max(dense, compact['working_set_bytes']) if mode == 'bounded-cpu' else dense
    working = activation_estimate(((row_token_budget + 15) // 16) * 16) * embedding_batch_budget
    runtime = GIB  # fixture private commit ~0.85 GiB; full runtime still unmeasured
    merge = 128 * 1024 ** 2  # pinned mmap checkpoint (~60 MiB) + bounded chunks/A/rank
    heads = 2 * 2560 * 256 * 4
    materialization = max(dense + INTEGRITY_BUFFER_BYTES, compact['working_set_bytes']) if mode == 'bounded-cpu' else weights
    needed = runtime + heads + max(working + materialization, merge)
    plan = dict(schema=2, mode=mode, device='cpu', dtype=dtype, row_token_budget=row_token_budget,
                weights_bytes=weights, largest_materialized_block_bytes=largest, merge_reserve_bytes=merge,
                largest_dense_block_bytes=dense, largest_source_tensor_bytes=largest_tensor,
                embedding=compact, materialization_reserve_bytes=materialization,
                runtime_reserve_bytes=runtime, pointer_head_bytes=heads, activation_reserve_bytes=working,
                estimated_process_bytes=needed, process_budget_bytes=budget, safety_margin_bytes=margin,
                available_at_plan_bytes=available, measured_peak_bytes=None, verified_inference=False,
                requested_process_budget_bytes=requested_budget,
                assumptions='Exact dense block sizes; compact embedding output plus one row buffer and bounded indices/hash buffer, no full embedding mapping; private CPU decoder/norm mappings; 4 MiB merge chunks; FP32 LoRA delta. Runtime/activation/kernel reserves are conservative estimates, not measured minima. Explicit row/batch cap rejects, never truncates. External owned-worker watchdog required.')
    if needed > budget:
        fail('hardware', 'Selected %s row=%d estimate %.2f GiB exceeds safe process budget %.2f GiB; no model allocation. This is a planning bound, not a measured minimum' %
             (mode, row_token_budget, needed / GIB, budget / GIB))
    return plan


def check_plan(plan, report=None, process=None):
    """Recheck before materialization and each block; worker watchdog covers kernels."""
    report = memory_status() if report is None else report
    process = process_memory() if process is None else process
    available = report.get('available_ram_bytes')
    if type(available) is not int or available < plan['safety_margin_bytes']:
        fail('resource', 'Available RAM unknown or system safety margin disappeared; stop owned worker')
    values = [process.get(key) for key in ('rss_bytes', 'private_bytes')]
    if any(type(value) is not int or value <= 0 for value in values):
        fail('resource', 'Process RSS/private memory unknown; stop owned worker before allocation')
    if max(values) > plan['process_budget_bytes']:
        fail('resource', 'Owned process exceeded selected memory budget; stop worker and retain measurements')
    peak = process.get('peak_rss_bytes')
    if type(peak) is int and peak > plan['process_budget_bytes']:
        fail('resource', 'Owned process peak RSS exceeded selected budget; stop worker and retain measurements')
    plan['observed_peak_rss_bytes'] = max(plan.get('observed_peak_rss_bytes', 0), values[0], peak or 0)
    plan['observed_peak_private_bytes'] = max(plan.get('observed_peak_private_bytes', 0), values[1])
    plan['observed_available_low_water_bytes'] = min(plan.get('observed_available_low_water_bytes', available), available)


def admission(report, device=0, dtype='bf16'):
    device, dtype = normalize_mode(device, dtype)
    estimate = resource_estimate(device, dtype)
    reasons = []
    def memory(value, needed, label):
        if type(value) is not int or value <= 0:
            reasons.append(label + ' unknown; establish resources before loading')
        elif value < needed:
            reasons.append('%s insufficient for %s/%s estimate: %.2f GiB needed, %.2f GiB observed' %
                           (label, device, dtype, needed / GIB, value / GIB))
    for key in ('total_ram_bytes', 'available_ram_bytes'):
        memory(report.get(key), estimate['host_bytes'], key)
    if device != 'cpu':
        gpu = next((g for g in report.get('nvidia', []) if g.get('index') == int(device[5:])), None)
        if gpu is None:
            reasons.append('Requested NVIDIA CUDA device not observed; driver probe may be unavailable. Intel Iris Xe is not CUDA')
        else:
            for key in ('total_bytes', 'free_bytes'):
                memory(gpu.get(key), estimate['device_bytes'], 'CUDA ' + key)
    return dict(device=device, dtype=dtype, estimate=estimate, blocked_reasons=reasons,
                candidate=not reasons, verified_inference=False)


def installation_modes(report):
    candidates = [admission(report, device, dtype) for device in
                  ['cpu', *['cuda:%d' % g['index'] for g in report.get('nvidia', [])]] for dtype in DTYPES]
    eligible = [item for item in candidates if item['candidate']]
    return dict(modes=[item['device'] + '-' + item['dtype'] + '-local' for item in eligible],
                candidate_devices=sorted(set(item['device'] for item in eligible)), candidates=candidates,
                blocked_reasons=list(dict.fromkeys(reason for item in candidates for reason in item['blocked_reasons'])),
                verified_inference=False, policy='Resource candidates only; locked dependencies, actual kernels, warmup and score remain unverified')


def require_hardware(report, device=0, dtype='bf16'):
    result = admission(report, device, dtype)
    if not result['candidate']:
        fail('hardware', '; '.join(result['blocked_reasons']))
    return result


def require_runtime(torch, report, device=0, dtype='bf16', plan=None):
    """After environment verification, before checkpoint deserialization/model load."""
    device, dtype = normalize_mode(device, dtype)
    if device != 'cpu':
        index = int(device[5:])
        if not torch.cuda.is_available() or index >= torch.cuda.device_count():
            fail('hardware', 'Locked torch has no requested CUDA device; inspect its build/driver')
        try:
            with torch.cuda.device(index):
                if dtype == 'bf16' and not torch.cuda.is_bf16_supported():
                    fail('hardware', 'Requested CUDA device cannot provide bf16; explicitly select a supported dtype')
                free, total = torch.cuda.mem_get_info(index)
            report = dict(report, nvidia=[dict(index=index, free_bytes=free, total_bytes=total)])
        except RevError:
            raise
        except (RuntimeError, AssertionError):
            fail('hardware', 'CUDA capability/memory probe failed; capability is unknown')
    if plan is None:
        require_hardware(report, device, dtype)
    else:
        if device != 'cpu' or plan.get('device') != device or plan.get('dtype') != dtype:
            fail('configuration', 'Memory plan differs from selected runtime')
        check_plan(plan, report)
    try:
        # Exercise selected dtype/device kernels on tiny tensors, never model weights.
        # This is candidate capability, not proof that all model kernels will work.
        a = torch.ones((1, 1, 2, 2), device=device, dtype=getattr(torch, DTYPES[dtype]))
        torch.nn.functional.scaled_dot_product_attention(a, a, a)
        torch.nn.functional.linear(a, a[0, 0])
        if device != 'cpu':
            torch.cuda.synchronize(int(device[5:]))
    except (RuntimeError, TypeError, AttributeError, NotImplementedError, AssertionError):
        fail('hardware', 'Locked torch cannot execute selected device/dtype SDPA/linear kernels; inspect dependencies or explicitly select another mode')


if __name__ == '__main__':
    report = diagnose()
    print(json.dumps(dict(hardware=report, installation=installation_modes(report)), ensure_ascii=False, indent=2))
