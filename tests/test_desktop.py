import pytest

from sunmcp.desktop import (
    Desktop, DesktopConfig, Node, Window, attach_desktop, escape_sendkeys, guarded,
)


class FakeUI:
    def __init__(self, win, nodes):
        self.win, self._nodes, self.typed = win, nodes, []

    def foreground(self):
        return self.win

    def nodes(self, max_nodes, max_depth):
        return self._nodes[:max_nodes]

    def type_into(self, node_id, text):
        self.typed.append((node_id, text))
        return "fake"


def yes():
    async def f(_):
        return True
    return f


NOTEPAD = Window(1, "Без имени — Блокнот", "notepad.exe")
NODES = [
    Node("n1", "Edit", "Текстовый редактор", editable=True),
    Node("n2", "Button", "Закрыть"),
    Node("n3", "Edit", "Пароль", is_password=True, editable=True),
]


def test_guard_words():
    assert guarded(Window(1, "Kaspi Gold — вход", "chrome.exe")) == "kaspi"
    assert guarded(Window(1, "KeePassXC", "keepassxc.exe"))
    assert guarded(Window(1, "Блокнот", "notepad.exe")) is None
    assert guarded(Window(1, "Мой проект", "x.exe"), ["проект"]) == "проект"


def test_escape_sendkeys():
    assert escape_sendkeys("a{b}(c)\nd") == "a{{}b{}}{(}c{)}{Enter}d"


def test_look_lists_names_and_flags():
    d = Desktop(DesktopConfig(enabled=True), FakeUI(NOTEPAD, NODES))
    out = d.look()
    assert "Блокнот" in out and "n1: Edit «Текстовый редактор» [поле]" in out
    assert "ПАРОЛЬ" in out


def test_look_refuses_guarded_window():
    d = Desktop(DesktopConfig(enabled=True), FakeUI(Window(2, "Halyk Homebank", "chrome.exe"), NODES))
    assert "П007" in d.look()


async def test_type_off_by_default():
    ui = FakeUI(NOTEPAD, NODES)
    d = Desktop(DesktopConfig(enabled=True), ui, confirm=yes())
    d.look()
    assert "выключены" in await d.type_text("n1", "привет")
    assert ui.typed == []


async def test_type_with_confirm_and_by_name():
    ui = FakeUI(NOTEPAD, NODES)
    d = Desktop(DesktopConfig(enabled=True, act=True), ui, confirm=yes())
    d.look()
    assert "Готово" in await d.type_text("редактор", "привет {мир}")
    assert ui.typed == [("n1", "привет {мир}")]


async def test_type_denied_by_human():
    ui = FakeUI(NOTEPAD, NODES)
    d = Desktop(DesktopConfig(enabled=True, act=True), ui)  # default confirm = deny_all
    d.look()
    assert "не разрешил" in await d.type_text("n1", "x")
    assert ui.typed == []


async def test_never_types_into_password():
    ui = FakeUI(NOTEPAD, NODES)
    d = Desktop(DesktopConfig(enabled=True, act=True), ui, confirm=yes())
    d.look()
    assert "пароля" in await d.type_text("n3", "secret")
    assert ui.typed == []


async def test_window_changed():
    ui = FakeUI(NOTEPAD, NODES)
    d = Desktop(DesktopConfig(enabled=True, act=True), ui, confirm=yes())
    d.look()
    ui.win = Window(9, "Другое окно", "x.exe")
    with pytest.raises(RuntimeError, match="сменилось"):
        await d.type_text("n1", "x")


async def test_switch_to_bank_after_look():
    ui = FakeUI(NOTEPAD, NODES)
    d = Desktop(DesktopConfig(enabled=True, act=True), ui, confirm=yes())
    d.look()
    ui.win = Window(1, "Kaspi.kz", "chrome.exe")
    assert "П007" in await d.type_text("n1", "x")
    assert ui.typed == []


class Hub:
    def __init__(self):
        self.specs = {}

    def register_builtin(self, spec, handler):
        self.specs[spec["name"]] = handler


def test_attach_respects_flags():
    h = Hub()
    attach_desktop(h, Desktop(DesktopConfig(enabled=False)))
    assert h.specs == {}
    attach_desktop(h, Desktop(DesktopConfig(enabled=True)))
    assert set(h.specs) == {"desktop_look"}
    h2 = Hub()
    attach_desktop(h2, Desktop(DesktopConfig(enabled=True, act=True)))
    assert set(h2.specs) == {"desktop_look", "desktop_type"}
