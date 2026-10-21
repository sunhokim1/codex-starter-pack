"""Fail-closed Windows owned-job accounting; never opens a PID from saved state.

Job membership is assigned before releasing a child's stdin launch gate. All
descendants inherit membership. Handles, rather than a PID tree snapshot, own
cleanup; KILL_ON_JOB_CLOSE also covers supervisor failure.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import time

from .errors import fail
from .hardware import memory_status


class OwnedJob:
    def __init__(self, commit_budget=None):
        if os.name != 'nt':
            fail('monitor', 'This owned-job supervisor requires Windows; no unmonitored fallback')
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.p = C.WinDLL('psapi', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [C.c_void_p, W.LPCWSTR], W.HANDLE),
            ('SetInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            ('QueryInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            ('AssignProcessToJobObject', [W.HANDLE, W.HANDLE], W.BOOL),
            ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ('GetPriorityClass', [W.HANDLE], W.DWORD),
            ('CloseHandle', [W.HANDLE], W.BOOL),
            ('TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL)):
            function = getattr(self.k, name); function.argtypes = args; function.restype = result
        self.handle = self.k.CreateJobObjectW(None, None)
        if not self.handle:
            fail('monitor', 'Cannot create owned job; no model started')
        class Basic(C.Structure):
            _fields_ = [('per_process', C.c_longlong), ('per_job', C.c_longlong), ('flags', W.DWORD),
                        ('min_ws', C.c_size_t), ('max_ws', C.c_size_t), ('active', W.DWORD),
                        ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]
        class IO(C.Structure):
            _fields_ = [(name, C.c_ulonglong) for name in ('read_op', 'write_op', 'other_op', 'read', 'write', 'other')]
        class Limits(C.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process', C.c_size_t), ('job', C.c_size_t),
                        ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]
        self.Limits = Limits
        limits = Limits(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if commit_budget is not None:
            if type(commit_budget) is not int or commit_budget <= 0:
                self.close(); fail('configuration', 'Owned job requires a positive commit budget')
            # Enforced by Windows even between polls/in a native kernel. This
            # bounds committed private memory, not file-backed working set/RSS.
            limits.basic.flags |= 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY
            limits.job = commit_budget
        if not self.k.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)):
            self.close(); fail('monitor', 'Cannot enforce owned-job cleanup; no model started')

    def assign(self, process):
        if not self.k.AssignProcessToJobObject(self.handle, W.HANDLE(int(process._handle))):
            fail('monitor', 'Cannot assign gated child to owned job; model launch remains blocked')

    def sample(self):
        class Pids(C.Structure):
            _fields_ = [('assigned', W.DWORD), ('count', W.DWORD), ('ids', C.c_size_t * 128)]
        ids = Pids()
        if not self.k.QueryInformationJobObject(self.handle, 3, C.byref(ids), C.sizeof(ids), None) or ids.count > 128:
            fail('monitor', 'Owned-job membership query failed; stop all owned children')
        class Counters(C.Structure):
            _fields_ = [('cb', W.DWORD), ('faults', W.DWORD)] + [(name, C.c_size_t) for name in (
                'peak_rss', 'rss', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'commit', 'peak_commit', 'private')]
        function = self.p.GetProcessMemoryInfo
        function.argtypes = [W.HANDLE, C.c_void_p, W.DWORD]; function.restype = W.BOOL
        rows = []
        for pid in ids.ids[:ids.count]:
            handle = self.k.OpenProcess(0x1000 | 0x10, False, pid)
            if not handle:
                fail('monitor', 'Cannot sample owned job member; fail closed')
            try:
                value = Counters(); value.cb = C.sizeof(value)
                if not function(handle, C.byref(value), value.cb):
                    fail('monitor', 'Owned process memory query failed; fail closed')
                priority = self.k.GetPriorityClass(handle)
                if not priority:
                    fail('monitor', 'Owned process priority query failed; fail closed')
                rows.append(dict(pid=pid, rss_bytes=value.rss, private_bytes=value.private,
                                 peak_rss_bytes=value.peak_rss, peak_commit_bytes=value.peak_commit,
                                 priority_class=priority))
            finally:
                self.k.CloseHandle(handle)
        limits = self.Limits()
        if not self.k.QueryInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits), None):
            fail('monitor', 'Owned-job peak query failed; stop owned children')
        return dict(timestamp=time.time(), monotonic=time.monotonic(), processes=rows,
                    rss_bytes=sum(row['rss_bytes'] for row in rows),
                    private_bytes=sum(row['private_bytes'] for row in rows),
                    peak_job_commit_bytes=limits.peak_job,
                    enforced_job_commit_limit_bytes=(limits.job if limits.basic.flags & 0x200 else None),
                    **memory_status())

    def terminate(self):
        if self.handle and not self.k.TerminateJobObject(self.handle, 2):
            fail('monitor', 'Owned job termination failed; closing kill-on-close handle')

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle); self.handle = None


def check_sample(sample, budget, margin, deadline):
    if time.monotonic() >= deadline:
        fail('timeout', 'Owned smoke deadline expired; stop owned job')
    values = [sample.get(key) for key in ('rss_bytes', 'private_bytes', 'peak_job_commit_bytes', 'available_ram_bytes')]
    if any(type(value) is not int or value <= 0 for value in values) or not sample.get('processes'):
        fail('monitor', 'Required process/system counters unavailable; stop owned job')
    if sample['available_ram_bytes'] < margin:
        fail('resource', 'System safety margin disappeared; stop owned job, retain evidence, do not wait for RAM')
    peaks = [row[key] for row in sample['processes'] for key in ('peak_rss_bytes', 'peak_commit_bytes')]
    if max(values[:3] + peaks) > budget:
        fail('resource', 'Owned tree RSS/private/observed OS peak exceeds selected budget; stop owned job')
