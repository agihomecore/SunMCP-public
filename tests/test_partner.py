"""SunMCP partner CLI against a fake SunAPI (no network)."""
import json

import httpx
import pytest

from sunmcp import partner


class FakeAPI:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, json=None, timeout=None, headers=None):
        self.calls.append((method, url, json, headers))
        assert headers["Authorization"] == "Bearer sun_t_test"
        path = url.split("/t/v1", 1)[1]
        body = {
            ("GET", "/me"): {"id": "demo", "name": "Demo", "commission_pct": 30, "points": 1, "referral_link": "https://api.sun-agi.com/r/demo-1",
                             "referral_clicks": 3, "tokens_today": 10, "tokens_daily_limit": 200000, "usage_by_client": [], "proposals": {"answered": 1}},
            ("POST", "/proposals"): {"id": 7, "status": "new"},
            ("GET", "/proposals"): {"proposals": [{"id": 7, "status": "answered", "product": "sunmcp", "kind": "idea", "text": "t", "summary": "s",
                                                   "answer_text": "берём", "reward": 1, "first_reply": None}]},
            ("POST", "/keys"): {"key": "sun_c_abc", "prefix": "sun_c_abc", "label": json and json.get("label")},
        }[(method, path)]
        return httpx.Response(201 if method == "POST" else 200, json=body)


@pytest.fixture
def api(monkeypatch):
    fake = FakeAPI()
    monkeypatch.setenv("SUNAPI_KEY", "sun_t_test")
    monkeypatch.setattr(partner.httpx, "request", fake)
    return fake


def test_me_and_proposals(api, capsys):
    assert partner.run("me", []) == 0
    assert "referral link: https://api.sun-agi.com/r/demo-1" in capsys.readouterr().out
    assert partner.run("propose", ["one", "command", "install"], kind="idea") == 0
    assert api.calls[-1][2] == {"product": "sunmcp", "kind": "idea", "text": "one command install"}
    partner.run("proposals", [])
    assert "answer: берём  (+1 point)" in capsys.readouterr().out


def test_key_add(api, capsys):
    partner.run("key-add", ["Client", "A"])
    assert "sun_c_abc" in capsys.readouterr().out


def test_config_never_stores_key(api, tmp_path):
    cfg = tmp_path / "sunmcp.json"
    assert partner.run("config", [], config=str(cfg)) == 0
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["backend"] == {"type": "openai", "model": "sun-moe", "base_url": partner.DEFAULT_URL, "api_key_env": "SUNAPI_KEY"}
    assert "sun_t_test" not in cfg.read_text(encoding="utf-8")


def test_missing_key(monkeypatch):
    monkeypatch.delenv("SUNAPI_KEY", raising=False)
    with pytest.raises(SystemExit):
        partner.run("me", [])
