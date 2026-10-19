"""Screenshots + a vision model (default Qwen2.5-VL via Ollama).

Two ways to use it:
  * by command:  `sunmcp screen "what error is on my screen?"`  or  `/screen ...` in chat
  * on demand:   the chat model gets a `screenshot` tool and calls it when it needs to look

Screen capture needs the optional extra:  pip install "sunmcp[screen]"  (uses mss).
Nothing is captured unless you run the command or the model calls the tool, and with the
default config the image never leaves your machine (local Ollama).
"""

from __future__ import annotations

import base64
import io
import os
from typing import Any

import httpx

from .config import VisionConfig
from .hub import MCPHub

TOOL_NAME = "screenshot"
DEFAULT_QUESTION = "Describe what is on the screen. Read out any visible error messages or key text."


def capture_screen_png(monitor: int = 1) -> bytes:
    """Return a PNG of the given monitor (1 = primary). Raises RuntimeError with a fix hint."""
    try:
        import mss
        import mss.tools
    except ImportError as e:
        raise RuntimeError('screen capture needs the extra: pip install "sunmcp[screen]"') from e
    with mss.mss() as sct:
        mons = sct.monitors
        if not 0 <= monitor < len(mons):
            raise RuntimeError(f"monitor {monitor} not found (have 0..{len(mons) - 1})")
        shot = sct.grab(mons[monitor])
        return mss.tools.to_png(shot.rgb, shot.size)


def _shrink(png: bytes, max_side: int = 1568) -> bytes:
    """Downscale big screens so small local VL models stay fast. No-op without Pillow."""
    try:
        from PIL import Image
    except ImportError:
        return png
    try:
        img = Image.open(io.BytesIO(png))
        if max(img.size) <= max_side:
            return png
        img.thumbnail((max_side, max_side))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png


class Vision:
    def __init__(
        self,
        cfg: VisionConfig,
        capture=capture_screen_png,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cfg = cfg
        self._capture = capture
        self._client = client or httpx.AsyncClient(timeout=cfg.timeout)

    async def describe(self, png: bytes, question: str | None = None) -> str:
        key = os.environ.get(self.cfg.api_key_env) if self.cfg.api_key_env else None
        uri = "data:image/png;base64," + base64.b64encode(png).decode()
        payload = {
            "model": self.cfg.model,
            "max_tokens": self.cfg.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question or DEFAULT_QUESTION},
                        {"type": "image_url", "image_url": {"url": uri}},
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            r = await self._client.post(
                f"{self.cfg.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers
            )
            r.raise_for_status()
        except httpx.TimeoutException as e:
            raise RuntimeError(
                f"vision model '{self.cfg.model}' did not answer within {self.cfg.timeout:.0f}s. "
                f"It is probably running on CPU: lower vision.max_side (now {self.cfg.max_side}), "
                f"raise vision.timeout, or use a smaller / GPU-backed model."
            ) from e
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"vision model '{self.cfg.model}' unavailable at {self.cfg.base_url}: {e!r}. "
                f"With Ollama run: ollama pull {self.cfg.model}"
            ) from e
        return r.json()["choices"][0]["message"].get("content") or ""

    async def look(self, question: str | None = None, monitor: int = 1) -> str:
        return await self.describe(_shrink(self._capture(monitor), self.cfg.max_side), question)


def attach_vision(hub: MCPHub, vision: Vision) -> None:
    """Give the chat model a `screenshot(question)` tool. Skipped when config says tool=false."""
    if not (vision.cfg.enabled and vision.cfg.tool):
        return

    async def handler(args: dict[str, Any]) -> tuple[str, bool]:
        try:
            q = args.get("question")
            return await vision.look(q, int(args.get("monitor") or 1)), False
        except RuntimeError as e:
            return str(e), True

    hub.register_builtin(
        {
            "name": TOOL_NAME,
            "description": (
                "Take a screenshot of the user's screen and have the vision model answer a question "
                "about it. Use only when you need to see the screen to help."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "What to look for on the screen."},
                    "monitor": {"type": "integer", "description": "1 = primary monitor (default)."},
                },
            },
        },
        handler,
    )
