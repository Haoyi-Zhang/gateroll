"""Fresh private outputs and owned Windows campaign process cleanup."""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path


def plain_path(path: Path) -> Path:
    text = str(path)
    if os.name == "nt" and text.startswith("\\\\?\\"):
        text = ("\\\\" + text[8:]) if text.startswith("\\\\?\\UNC\\") else text[4:]
    return Path(text)


def filesystem_path(path: Path) -> Path:
    """Use absolute extended Windows paths without changing resolved ownership."""
    resolved = plain_path(path).resolve()
    if os.name != "nt":
        return resolved
    text = str(resolved)
    return Path("\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text)


def private_path(root: Path, path: Path) -> Path:
    root = plain_path(root).resolve(strict=True)
    anchor = root / "results" / "runtime_reproductions"
    if anchor.resolve() != anchor:
        raise ValueError("private output anchor must not redirect through a link/junction")
    resolved = plain_path(path).resolve()
    if resolved == anchor or not resolved.is_relative_to(anchor):
        raise ValueError(f"output must be strictly under {anchor}: {resolved}")
    return resolved


def fresh_directory(root: Path, path: Path) -> Path:
    resolved = private_path(root, path)
    # No replacement, pruning or recursive deletion, even for a prior own run.
    native = filesystem_path(resolved)
    native.mkdir(parents=True, exist_ok=False)
    return native


def wait_start_gate(root: Path) -> None:
    value = os.environ.get("GATEROLL_START_GATE")
    if not value:
        return
    gate = filesystem_path(private_path(root, Path(value)))
    deadline = time.monotonic() + 10
    while not gate.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("owned reproduction parent did not release start gate")
        time.sleep(0.01)


class WindowsJob:
    """Kill-on-close job containing only one gated campaign parent and children."""

    def __init__(self, process: subprocess.Popen):
        self.handle = None
        if os.name != "nt":
            return
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel = kernel
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
