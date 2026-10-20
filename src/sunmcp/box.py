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
    cores: int  # physical cores (what tiers are based on)
    ram_gb: float
    threads: int = 0  # logical processors
    gpu: str = ""  # NVIDIA GPU name if nvidia-smi sees one


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


def _physical_cores(logical: int) -> int:
    """Physical core count; falls back to the logical count if unknown."""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum"],
                text=True, timeout=20,
            )
            return max(1, int(out.strip()))
        if sys.platform == "darwin":
            return max(1, int(subprocess.check_output(["sysctl", "-n", "hw.physicalcpu"]).strip()))
        pairs: set[tuple[str, str]] = set()
        phys = core = ""
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("physical id"):
                    phys = line.split(":")[1].strip()
                elif line.startswith("core id"):
                    core = line.split(":")[1].strip()
                elif not line.strip() and core != "":
                    pairs.add((phys, core))
                    phys = core = ""
        if pairs:
            return len(pairs)
    except Exception:
        pass
    return logical


def detect_nvidia(run: Any = None) -> str:
    """Name of the first NVIDIA GPU, or "" when there is none (or no driver)."""
    run = run or subprocess.run
    try:
        r = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return (r.stdout or "").strip().splitlines()[0].strip() if (r.stdout or "").strip() else ""
    except Exception:
        pass
    return ""


def detect_hardware() -> Hardware:
    logical = os.cpu_count() or 1
    return Hardware(cores=_physical_cores(logical), ram_gb=_ram_bytes() / 1024**3,
                    threads=logical, gpu=detect_nvidia())


REQUIREMENT = "Needs a CPU above average (8+ cores, 32 GB RAM) or an NVIDIA RTX GPU."


def choose_tier(hw: Hardware) -> Tier:
    """Tiers from docs/HARDWARE.md. Thresholds allow ~1 GB of OS-reported slack."""
    if hw.gpu and hw.ram_gb >= 15:
        return Tier("GPU", "qwen2.5:7b", "qwen2.5vl:7b", f"NVIDIA GPU ({hw.gpu}): models run on the GPU.")
    if hw.cores < 4 or hw.ram_gb < 15:
        return Tier(
            "Community", "qwen2.5:3b", "qwen2.5vl:3b",
            "Below the supported minimum. " + REQUIREMENT + " It may run, slowly; no support.",
        )
    if hw.cores >= 8 and hw.ram_gb >= 31:
        return Tier("Plus", "qwen2.5:7b", "qwen2.5vl:3b", "7B chat measured with tool calling; vision on command.")
    return Tier("Standard", "qwen2.5:3b", "qwen2.5vl:3b",
                "3B chat, slow on an average CPU. " + REQUIREMENT)


CHAT_ALIAS = "sunbox-chat"
VISION_ALIAS = "sunbox-vision"


def modelfiles(tier: Tier) -> dict[str, str]:
    """Ollama Modelfiles for CPU-only machines.

    Measured on a 4C/8T laptop: Ollama's default offloaded 24% of the layers to a
    weak integrated GPU with an 8192 context and ran qwen2.5:3b at ~3 tok/s;
    num_gpu 0 with a smaller context ran the same model at ~10.5 tok/s.
    """
    return {
        CHAT_ALIAS: f"FROM {tier.chat}\nPARAMETER num_gpu 0\nPARAMETER num_ctx 4096\n",
        VISION_ALIAS: f"FROM {tier.vision}\nPARAMETER num_gpu 0\nPARAMETER num_ctx 4096\n",
    }


def box_config(tier: Tier, cpu_only: bool = True) -> dict[str, Any]:
    chat = CHAT_ALIAS if cpu_only else tier.chat
    vision = VISION_ALIAS if cpu_only else tier.vision
    return {
        "backend": {"type": "ollama", "model": chat, "base_url": "http://localhost:11434/v1"},
        "vision": {
            "enabled": True, "model": vision, "base_url": "http://localhost:11434/v1",
            "tool": True, "max_side": 768, "timeout": 900,
        },
        "system": "You are a helpful assistant. Use the available tools when they help.",
        "servers": {},
    }


def pull_commands(tier: Tier, cpu_only: bool = True) -> list[str]:
    cmds = [f"ollama pull {tier.chat}", f"ollama pull {tier.vision}"]
    if cpu_only:
        cmds += [f"ollama create {n} -f Modelfile.{n}" for n in (CHAT_ALIAS, VISION_ALIAS)]
    return cmds


OLLAMA_DOWNLOAD = "https://ollama.com/download"


def install_models(
    tier: Tier,
    cpu_only: bool = True,
    cwd: str | None = None,
    run: Any = None,
    which: Any = None,
    echo: Any = print,
) -> int:
    """Run the pull/create commands so a buyer needs one command, not five.

    Returns 0 on success, 2 when Ollama is missing, otherwise the failing command's exit code.
    """
    import shlex
    import shutil
    import subprocess

    run = run or subprocess.run
    which = which or shutil.which
    if not which("ollama"):
        echo(f"Ollama is not installed. Install it from {OLLAMA_DOWNLOAD}, start it, then run this again.")
        return 2
    for cmd in pull_commands(tier, cpu_only):
        echo(f"$ {cmd}")
        code = run(shlex.split(cmd), cwd=cwd).returncode
        if code != 0:
            echo(f"failed ({code}): {cmd}")
            return code
    echo("models ready")
    return 0


def report(hw: Hardware, tier: Tier, cpu_only: bool = True) -> str:
    lines = [
        f"machine: {hw.cores} physical cores ({hw.threads or hw.cores} threads), {hw.ram_gb:.1f} GB RAM",
        f"gpu:     {hw.gpu or 'no NVIDIA GPU found'}",
        f"tier:    {tier.name}",
        f"chat:    {tier.chat}",
        f"vision:  {tier.vision} (on command only)",
        f"note:    {tier.note}",
        "mode:    " + ("CPU only (GPU offload off)" if cpu_only else "GPU allowed"),
        "install: " + "; ".join(pull_commands(tier, cpu_only)),
    ]
    return "\n".join(lines)
