from sunmcp.box import Hardware, box_config, choose_tier, detect_hardware, pull_commands
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
    assert cfg.backend.model == t.chat
    assert cfg.vision.model == t.vision and cfg.vision.max_side == 768
    assert pull_commands(t) == [f"ollama pull {t.chat}", f"ollama pull {t.vision}"]


def test_detect_hardware_sane():
    hw = detect_hardware()
    assert hw.cores >= 1 and hw.ram_gb > 0.5
