"""Desktop eyes and hands for Windows (UI Automation). Since 0.4.0.

Two tools for the chat model:
  * desktop_look  ("Смотрю"): the active window's title and its controls (type, name, id).
                  Read-only. Field VALUES are never read, only names, so typed text stays private.
  * desktop_type  ("Делаю"):  type text into one control of the active window.
                  Off by default (desktop.act=false). Every action asks the human first.

Protocol 007 guard (always on):
  * windows whose title or process looks like a bank, Kaspi, a password manager, a wallet,
    or mentions passwords/secrets are neither looked at nor touched;
  * password fields (UIA IsPassword) are never typed into;
  * before typing, the foreground window must be the same one that was looked at.

Needs the optional extra:  pip install "sunmcp[desktop]"  (uiautomation, Windows only).
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

LOOK_TOOL = "desktop_look"
TYPE_TOOL = "desktop_type"

# Lower-case fragments. Title or process name containing any of these -> hands off.
GUARD_WORDS: tuple[str, ...] = (
    # banks and payments (KZ + general)
    "kaspi", "каспи", "halyk", "халык", "homebank", "jusan", "жусан", "forte", "форте",
    "freedom bank", "bcc", "centercredit", "bereke", "otbasy", "отбасы", "eubank",
    "bank", "банк", "paypal", "stripe", "payoneer", "visa", "mastercard",
    # passwords, keys, secrets
    "password", "пароль", "парол", "passcode", "pin-код", "keepass", "bitwarden",
    "1password", "lastpass", "dashlane", "authenticator", "authy", "secret", "секрет",
    "private key", "seed phrase", "recovery phrase", ".env", "credential",
    # wallets
    "wallet", "кошел", "metamask", "ledger", "trezor", "binance", "bybit", "okx",
    # system security
    "credential manager", "диспетчер учетных данных", "windows security", "безопасность windows",
    "bitlocker", "regedit", "редактор реестра",
)


@dataclass
class DesktopConfig:
    enabled: bool = False      # expose desktop_look to the model
    act: bool = False          # also expose desktop_type (still asks the human every time)
    max_nodes: int = 120       # how many controls desktop_look lists at most
    max_depth: int = 12
    max_text: int = 2000       # longest text desktop_type will type
    guard_words: list[str] = field(default_factory=list)  # extra words added to GUARD_WORDS


@dataclass
class Node:
    id: str
    type: str
    name: str
    is_password: bool = False
    enabled: bool = True
    editable: bool = False


@dataclass
class Window:
    handle: int
    title: str
    process: str


class UIBackend(Protocol):
    def foreground(self) -> Window: ...
    def nodes(self, max_nodes: int, max_depth: int) -> list[Node]: ...
    def type_into(self, node_id: str, text: str) -> str: ...


def guarded(win: Window, extra: list[str] | None = None) -> str | None:
    """Return the matched guard word if this window must not be seen or touched."""
    hay = f"{win.title} {win.process}".lower()
    for w in (*GUARD_WORDS, *(x.lower() for x in (extra or []))):
        if w and w in hay:
            return w
    return None


def escape_sendkeys(text: str) -> str:
    """Make arbitrary text literal for uiautomation.SendKeys."""
    out = []
    for ch in text:
        if ch == "{":
            out.append("{{}")
        elif ch == "}":
            out.append("{}}")
        elif ch in "()":
            out.append("{" + ch + "}")
        elif ch == "\n":
            out.append("{Enter}")
        elif ch == "\r":
            continue
        else:
            out.append(ch)
    return "".join(out)


EDIT_TYPES = {"EditControl", "DocumentControl", "ComboBoxControl"}


class UIABackend:
    """Real Windows backend on top of the `uiautomation` package."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("desktop tools work on Windows only (UI Automation)")
        try:
            import uiautomation as auto
        except ImportError as e:
            raise RuntimeError('desktop tools need the extra: pip install "sunmcp[desktop]"') from e
        self.auto = auto
        self._controls: dict[str, Any] = {}
        self._handle = 0

    def _top(self) -> Any:
        c = self.auto.GetForegroundControl()
        top = c.GetTopLevelControl() if c else None
        return top or c

    @staticmethod
    def _process_name(pid: int) -> str:
        try:
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    return buf.value.rsplit("\\", 1)[-1]
            finally:
                k32.CloseHandle(h)
        except Exception:
            pass
        return ""

    def foreground(self) -> Window:
        top = self._top()
        if top is None:
            return Window(0, "", "")
        return Window(int(top.NativeWindowHandle or 0), top.Name or "", self._process_name(top.ProcessId))

    def nodes(self, max_nodes: int, max_depth: int) -> list[Node]:
        top = self._top()
        self._controls = {}
        self._handle = int(top.NativeWindowHandle or 0) if top else 0
        out: list[Node] = []
        if top is None:
            return out
        for ctrl, _depth in self.auto.WalkControl(top, includeTop=False, maxDepth=max_depth):
            if len(out) >= max_nodes:
                break
            try:
                if ctrl.IsOffscreen:
                    continue
                t = ctrl.ControlTypeName
                name = (ctrl.Name or "").strip()
                if not name and t not in EDIT_TYPES:
                    continue
                nid = f"n{len(out) + 1}"
                self._controls[nid] = ctrl
                out.append(
                    Node(
                        id=nid,
                        type=t.replace("Control", ""),
                        name=name[:80],
                        is_password=bool(ctrl.IsPassword),
                        enabled=bool(ctrl.IsEnabled),
                        editable=t in EDIT_TYPES,
                    )
                )
            except Exception:
                continue
        return out

    def type_into(self, node_id: str, text: str) -> str:
        ctrl = self._controls.get(node_id)
        if ctrl is None:
            raise RuntimeError(f"unknown control {node_id}; call {LOOK_TOOL} first")
        if bool(ctrl.IsPassword):
            raise RuntimeError("password field: never typed into (Protocol 007)")
        ctrl.SetFocus()
        try:
            vp = ctrl.GetValuePattern()
            if vp and not vp.IsReadOnly:
                vp.SetValue(text)
                return "set via ValuePattern"
        except Exception:
            pass
        ctrl.SendKeys(escape_sendkeys(text), interval=0.01)
        return "typed via keyboard"


Confirm = Callable[[str], Awaitable[bool]]


async def deny_all(_: str) -> bool:
    return False


async def ask_console(prompt: str) -> bool:
    """Default human check for the CLI: y/N on the terminal."""
    import asyncio

    try:
        ans = await asyncio.to_thread(input, f"\n[SunMCP · Делаю] {prompt}\nРазрешить? y/N > ")
    except EOFError:  # no human at the terminal (bot, pipe) -> deny
        return False
    return ans.strip().lower() in ("y", "yes", "д", "да")


class Desktop:
    def __init__(self, cfg: DesktopConfig, backend: UIBackend | None = None, confirm: Confirm = deny_all):
        self.cfg = cfg
        self._backend = backend
        self.confirm = confirm
        self._looked: Window | None = None
        self._nodes: dict[str, Node] = {}

    @property
    def backend(self) -> UIBackend:
        if self._backend is None:
            self._backend = UIABackend()
        return self._backend

    def look(self) -> str:
        win = self.backend.foreground()
        g = guarded(win, self.cfg.guard_words)
        if g:
            self._looked, self._nodes = None, {}
            return f"Окно закрыто защитой П007 (совпало: «{g}»). Я его не смотрю и не трогаю."
        nodes = self.backend.nodes(self.cfg.max_nodes, self.cfg.max_depth)
        self._looked, self._nodes = win, {n.id: n for n in nodes}
        lines = [f"Окно: {win.title or '(без названия)'} · {win.process or '?'}", f"Элементов: {len(nodes)}"]
        for n in nodes:
            flags = []
            if n.editable:
                flags.append("поле")
            if n.is_password:
                flags.append("ПАРОЛЬ-не трогаю")
            if not n.enabled:
                flags.append("неактивно")
            f = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"{n.id}: {n.type} «{n.name}»{f}")
        return "\n".join(lines)

    def _resolve(self, target: str) -> Node:
        t = (target or "").strip()
        if t in self._nodes:
            return self._nodes[t]
        low = t.lower()
        hits = [n for n in self._nodes.values() if n.editable and low and low in n.name.lower()]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise RuntimeError(f"поле «{target}» не найдено; вызови {LOOK_TOOL} и укажи id")
        raise RuntimeError(f"поле «{target}» неоднозначно: {', '.join(n.id for n in hits)}")

    async def type_text(self, target: str, text: str) -> str:
        if not self.cfg.act:
            return "Действия выключены (desktop.act=false). Могу только смотреть."
        if not text:
            raise RuntimeError("пустой текст")
        if len(text) > self.cfg.max_text:
            raise RuntimeError(f"текст длиннее {self.cfg.max_text} символов")
        if self._looked is None:
            raise RuntimeError(f"сначала {LOOK_TOOL}")
        win = self.backend.foreground()
        g = guarded(win, self.cfg.guard_words)
        if g:
            return f"Окно закрыто защитой П007 (совпало: «{g}»). Ничего не ввожу."
        if win.handle != self._looked.handle:
            raise RuntimeError(f"активное окно сменилось; снова вызови {LOOK_TOOL}")
        node = self._resolve(target)
        if node.is_password:
            return "Это поле пароля. По Протоколу 007 я в него не ввожу никогда."
        if not node.editable:
            raise RuntimeError(f"{node.id} «{node.name}» — не поле ввода")
        preview = text if len(text) <= 200 else text[:200] + "…"
        ok = await self.confirm(f"Ввести в «{node.name}» ({node.id}) окна «{win.title}»:\n«{preview}»")
        if not ok:
            return "Человек не разрешил. Ничего не ввела."
        how = self.backend.type_into(node.id, text)
        return f"Готово: ввела {len(text)} символов в «{node.name}» ({how})."


def attach_desktop(hub: Any, desktop: Desktop) -> None:
    """Register desktop_look (and desktop_type when act=true) as built-in tools."""
    if not desktop.cfg.enabled:
        return

    async def look_handler(_args: dict[str, Any]) -> tuple[str, bool]:
        try:
            return desktop.look(), False
        except RuntimeError as e:
            return str(e), True

    hub.register_builtin(
        {
            "name": LOOK_TOOL,
            "description": (
                "Look at the user's active window: its title and its controls (buttons, fields) with ids. "
                "Reads names only, never field values. Call before desktop_type."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        look_handler,
    )
    if not desktop.cfg.act:
        return

    async def type_handler(args: dict[str, Any]) -> tuple[str, bool]:
        try:
            return await desktop.type_text(str(args.get("target", "")), str(args.get("text", ""))), False
        except RuntimeError as e:
            return str(e), True

    hub.register_builtin(
        {
            "name": TYPE_TOOL,
            "description": (
                "Type text into one input field of the active window. target = control id from "
                "desktop_look (e.g. n3) or part of the field name. The human confirms every action. "
                "Never use for passwords, banks or payments."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Control id (n3) or field name."},
                    "text": {"type": "string", "description": "Text to type."},
                },
                "required": ["target", "text"],
            },
        },
        type_handler,
    )
