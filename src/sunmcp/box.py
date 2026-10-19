"""`sunmcp box`: detect the machine, pick a tier and models, write a config.

The user never types a model name. Tiers follow docs/HARDWARE.md.
Model names marked "unmeasured" have not been timed by us yet.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class Hardware:
    cores: int
    ram_gb: float


@dataclass
class Tier:
    name: str
    chat: str
    vision: str
    note: str


def _ram_bytes() -> int:
    if sys.platform == "win32":
        class MEM(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        m = MEM()
        m.dwLength = ctypes.sizeof(MEM)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
        return int(m.ullTotalPhys)
    if sys.platform == "darwin":
        return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("cannot detect RAM")


def detect_hardware() -> Hardware:
    return Hardware(cores=os.cpu_count() or 1, ram_gb=_ram_bytes() / 1024**3)


def choose_tier(hw: Hardware) -> Tier:
    """Tiers from docs/HARDWARE.md. Thresholds allow ~1 GB of OS-reported slack."""
    if hw.cores < 4 or hw.ram_gb < 15:
        return Tier(
            "Community", "qwen2.5:3b", "qwen2.5vl:3b",
            "Below the supported minimum (4 cores, 16 GB). It may run, slowly; no support.",
        )
    if hw.cores >= 8 and hw.ram_gb >= 31:
        return Tier("Plus", "qwen2.5:7b", "qwen2.5vl:3b", "7B chat measured with tool calling; vision on command.")
    return Tier("Standard", "qwen2.5:3b", "qwen2.5vl:3b", "3B chat (unmeasured speed); vision on command only.")


def box_config(tier: Tier) -> dict[str, Any]:
    return {
        "backend": {"type": "ollama", "model": tier.chat, "base_url": "http://localhost:11434/v1"},
        "vision": {
            "enabled": True, "model": tier.vision, "base_url": "http://localhost:11434/v1",
            "tool": True, "max_side": 768, "timeout": 900,
        },
        "system": "You are a helpful assistant. Use the available tools when they help.",
        "servers": {},
    }


def pull_commands(tier: Tier) -> list[str]:
    return [f"ollama pull {tier.chat}", f"ollama pull {tier.vision}"]


def report(hw: Hardware, tier: Tier) -> str:
    lines = [
        f"machine: {hw.cores} cores, {hw.ram_gb:.1f} GB RAM",
        f"tier:    {tier.name}",
        f"chat:    {tier.chat}",
        f"vision:  {tier.vision} (on command only)",
        f"note:    {tier.note}",
        "install: " + "; ".join(pull_commands(tier)),
    ]
    return "\n".join(lines)
