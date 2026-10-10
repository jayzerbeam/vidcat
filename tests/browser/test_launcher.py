import os
from pathlib import Path
from typing import Any

import pytest

from browser import launcher as launcher_module
from browser.launcher import Launcher


def _write_file(path: Path) -> Path:
    path.write_text("x")
    return path


def test_reveal_missing_path_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Path] = []
    popen_calls: list[Any] = []
    monkeypatch.setattr(launcher_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(launcher_module.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(launcher_module.subprocess, "Popen", lambda *args: popen_calls.append(args))

    Launcher(None, ()).reveal(tmp_path / "missing.mp4")

    assert (opened, popen_calls) == ([], [])


def test_reveal_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _write_file(tmp_path / "video.mp4")
    opened: list[Path] = []
    monkeypatch.setattr(launcher_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(launcher_module.os, "startfile", opened.append, raising=False)

    Launcher(None, ()).reveal(f)

    assert opened == [f.resolve()]


@pytest.mark.parametrize(("system", "command"), [("Darwin", "open"), ("Linux", "xdg-open")])
def test_reveal_non_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, command: str
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    popen_calls: list[list[str | Path]] = []
    monkeypatch.setattr(launcher_module.platform, "system", lambda: system)
    monkeypatch.setattr(launcher_module.subprocess, "Popen", popen_calls.append)

    Launcher(None, ()).reveal(f)

    assert popen_calls == [[command, f.resolve()]]


def test_reveal_linux_missing_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    resolved = f.resolve()

    def _raise(_args: object) -> None:
        raise FileNotFoundError("xdg-open not found")

    monkeypatch.setattr(launcher_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(launcher_module.subprocess, "Popen", _raise)

    Launcher(None, ()).reveal(f)

    assert f"error: failed to open {resolved}: xdg-open not found" in capsys.readouterr().out


def test_play_missing_path_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Path] = []
    spawned: list[Any] = []
    monkeypatch.setattr(launcher_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(launcher_module.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(launcher_module.os, "spawnv", lambda *args: spawned.append(args))

    Launcher(_write_file(tmp_path / "player.exe"), ()).play(tmp_path / "missing.mp4")

    assert (opened, spawned) == ([], [])


@pytest.mark.parametrize("player_name", [None, "missing-player.exe"])
def test_play_windows_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, player_name: str | None
) -> None:
    """Without a player, or with one that does not exist, the OS default opens the file."""
    f = _write_file(tmp_path / "video.mp4")
    player = tmp_path / player_name if player_name is not None else None
    opened: list[Path] = []
    monkeypatch.setattr(launcher_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(launcher_module.os, "startfile", opened.append, raising=False)

    Launcher(player, ()).play(f)

    assert opened == [f.resolve()]


@pytest.mark.parametrize(
    ("args", "expected_tail"),
    [
        ((), []),
        (("--start=%t_ms", "--sec=%t_sec", "--fs"), ["--start=1500", "--sec=1.5", "--fs"]),
    ],
)
def test_play_with_configured_player(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: tuple[str, ...], expected_tail: list[str]
) -> None:
    player = _write_file(tmp_path / "mpv.exe")
    f = _write_file(tmp_path / "video.mp4")
    spawn_calls: list[tuple[int, Path, list[str]]] = []
    opened: list[Path] = []

    def _fake_spawnv(mode: int, path: Path, argv: list[str]) -> None:
        spawn_calls.append((mode, path, argv))

    monkeypatch.setattr(launcher_module.os, "spawnv", _fake_spawnv)
    monkeypatch.setattr(launcher_module.os, "startfile", opened.append, raising=False)

    Launcher(player, args).play(f, start_ms=1500)

    assert spawn_calls == [(os.P_NOWAIT, player, [player.name, f'"{f.resolve()}"', *expected_tail])]
    assert opened == []


@pytest.mark.parametrize(("system", "command"), [("Darwin", "open"), ("Linux", "xdg-open")])
def test_play_non_windows_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, command: str
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    call_calls: list[tuple[str | Path, ...]] = []
    monkeypatch.setattr(launcher_module.platform, "system", lambda: system)
    monkeypatch.setattr(launcher_module.subprocess, "call", lambda args: call_calls.append(args))

    Launcher(None, ()).play(f)

    assert call_calls == [(command, f.resolve())]
