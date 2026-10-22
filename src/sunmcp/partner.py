"""SunMCP partner programme: testers who resell SunMCP / SunAPI.

Everything goes to SunAPI (https://api.sun-agi.com/t/v1) with the tester's key in $SUNAPI_KEY.
The key never touches the config file or the screen.

  sunmcp partner me                        your referral link, points, usage by client
  sunmcp partner propose "text" [--product sunmcp --kind idea]
  sunmcp partner proposals                 status and answers to your proposals
  sunmcp partner keys                      client keys you resell
  sunmcp partner key-add "Client name"     new client key (shown once)
  sunmcp partner config [--model sun-moe]  write sunmcp.json that runs on SunAPI models
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

from .config import SAMPLE_CONFIG

DEFAULT_URL = "https://api.sun-agi.com/t/v1"


def _base() -> str:
    return os.environ.get("SUNAPI_URL", DEFAULT_URL).rstrip("/")


def _key() -> str:
    key = os.environ.get("SUNAPI_KEY", "").strip()
    if not key:
        raise SystemExit("set SUNAPI_KEY to your tester key (sun_t_...) first")
    return key


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    r = httpx.request(method, _base() + path, json=body, timeout=60,
                      headers={"Authorization": f"Bearer {_key()}"})
    try:
        data = r.json()
    except ValueError:
        data = {"error": r.text[:200]}
    if r.status_code >= 400:
        raise SystemExit(f"SunAPI {r.status_code}: {data.get('error', data)}")
    return data


def run(action: str, text: list[str], product: str = "sunmcp", kind: str = "idea",
        model: str = "sun-moe", config: str = "sunmcp.json", force: bool = False) -> int:
    if action == "me":
        me = _call("GET", "/me")
        print(f"{me['name']} ({me['id']})  commission {me['commission_pct']}%  points {me['points']}")
        print(f"referral link: {me['referral_link']}  (clicks: {me['referral_clicks']})")
        print(f"tokens today: {me['tokens_today']} / {me['tokens_daily_limit']}")
        for row in me.get("usage_by_client", []):
            print(f"  {row['client']:<24} calls={row['calls']} in={row['prompt_tokens']} out={row['completion_tokens']}")
        if me.get("proposals"):
            print("proposals:", ", ".join(f"{k}={v}" for k, v in me["proposals"].items()))
        return 0
    if action == "propose":
        msg = " ".join(text).strip()
        if not msg:
            raise SystemExit('usage: sunmcp partner propose "what to change and why"')
        res = _call("POST", "/proposals", {"product": product, "kind": kind, "text": msg})
        print(f"proposal #{res['id']} received; check `sunmcp partner proposals` in a few minutes")
        return 0
    if action == "proposals":
        for p in _call("GET", "/proposals")["proposals"]:
            head = f"#{p['id']} [{p['status']}] {p['product']}/{p['kind']}: {p.get('summary') or p['text'][:80]}"
            print(head)
            if p.get("answer_text"):
                print(f"    answer: {p['answer_text']}" + ("  (+1 point)" if p.get("reward") else ""))
            elif p.get("first_reply"):
                print(f"    {p['first_reply']}")
        return 0
    if action == "keys":
        for k in _call("GET", "/keys")["keys"]:
            print(f"{k['prefix']}…  {k['label']:<24} {'active' if k['active'] else 'off'}  {k['created_at']}")
        return 0
    if action == "key-add":
        label = " ".join(text).strip()
        if not label:
            raise SystemExit('usage: sunmcp partner key-add "Client name"')
        res = _call("POST", "/keys", {"label": label})
        # shown once, on purpose: the tester hands it to the client
        print(f"client key for {res['label']} (shown once, store it safely):\n{res['key']}")
        return 0
    if action == "config":
        path = Path(config)
        if path.exists() and not force:
            print(f"{path} already exists (use --force)", file=sys.stderr)
            return 1
        cfg = json.loads(json.dumps(SAMPLE_CONFIG))
        cfg["backend"] = {"type": "openai", "model": model, "base_url": _base(), "api_key_env": "SUNAPI_KEY"}
        cfg["vision"]["enabled"] = False  # SunAPI v0.1 has no vision endpoint yet
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path}: backend = SunAPI {model} (key from $SUNAPI_KEY)")
        return 0
    raise SystemExit(__doc__)
