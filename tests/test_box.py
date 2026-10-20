from sunmcp.box import Hardware, box_config, choose_tier, detect_hardware, modelfiles, pull_commands
from sunmcp.config import parse_config


def test_tiers():
    assert choose_tier(Hardware(2, 8)).name == "Community"
    assert choose_tier(Hardware(4, 16)).name == "Standard"
    assert choose_tier(Hardware(4, 15.9)).name == "Standard"
    assert choose_tier(Hardware(8, 32)).name == "Plus"
    assert choose_tier(Hardware(8, 16)).name == "Standard"
    assert choose_tier(Hardware(16, 14)).name == "Community"


def test_generated_config_parses():
    t = choose_tier(Hardware(4, 16))
    cfg = parse_config(box_config(t))
    assert cfg.backend.model == "sunbox-chat"
    assert cfg.vision.model == "sunbox-vision" and cfg.vision.max_side == 768
    cmds = pull_commands(t)
    assert cmds[:2] == [f"ollama pull {t.chat}", f"ollama pull {t.vision}"]
    assert any("ollama create sunbox-chat" in c for c in cmds)
    gpu = parse_config(box_config(t, cpu_only=False))
    assert gpu.backend.model == t.chat and gpu.vision.model == t.vision
    assert pull_commands(t, cpu_only=False) == cmds[:2]
    mf = modelfiles(t)
    assert mf["sunbox-chat"].startswith(f"FROM {t.chat}") and "num_gpu 0" in mf["sunbox-chat"]


def test_detect_hardware_sane():
    hw = detect_hardware()
    assert hw.cores >= 1 and hw.ram_gb > 0.5


def test_physical_cores_never_exceed_logical():
    from sunmcp.box import _physical_cores
    import os
    n = os.cpu_count() or 1
    assert 1 <= _physical_cores(n) <= n
    assert _physical_cores(0) >= 1


def test_install_models_runs_commands_in_order(tmp_path):
    from types import SimpleNamespace

    from sunmcp.box import Tier, install_models

    tier = Tier("Standard", "qwen2.5:3b", "qwen2.5vl:3b", "")
    ran, out = [], []
    rc = install_models(
        tier, True, cwd=str(tmp_path), run=lambda c, cwd: ran.append((c, cwd)) or SimpleNamespace(returncode=0),
        which=lambda n: "/usr/bin/ollama", echo=out.append,
    )
    assert rc == 0 and ran[0][0][:2] == ["ollama", "pull"] and ran[-1][0][:2] == ["ollama", "create"]
    assert all(c[1] == str(tmp_path) for c in ran)


def test_install_models_without_ollama_points_to_download():
    from sunmcp.box import Tier, install_models

    tier = Tier("Standard", "qwen2.5:3b", "qwen2.5vl:3b", "")
    out = []
    assert install_models(tier, True, which=lambda n: None, echo=out.append) == 2
    assert "ollama.com/download" in out[0]


def test_install_models_stops_on_failure():
    from types import SimpleNamespace

    from sunmcp.box import Tier, install_models

    tier = Tier("Standard", "qwen2.5:3b", "qwen2.5vl:3b", "")
    calls = []
    rc = install_models(tier, True, run=lambda c, cwd: calls.append(c) or SimpleNamespace(returncode=1),
                        which=lambda n: "x", echo=lambda m: None)
    assert rc == 1 and len(calls) == 1
