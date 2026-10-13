import json
from pathlib import Path

import pytest

from browser.config import DEFAULT_HIDDEN_COLUMNS, Config


def _write_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_reads_settings(tmp_path: Path) -> None:
    player = tmp_path / "player.exe"
    player.touch()
    config = tmp_path / "config.json"
    _write_config(
        config,
        {
            "metadata_key": "meta",
            "thumb_height": 100,
            "thumb_interval": 5,
            "trash_dir": "..",
            "vid_player": str(player),
            "vid_player_args": ["a", "b"],
            "vid_exts": [".mp4"],
            "hidden_columns": ["res", "tags"],
            "unknown_key": "ignored",
        },
    )

    cfg = Config()
    cfg.load(config)

    assert cfg.metadata_key == "meta"
    assert cfg.thumb_height == 100
    assert cfg.thumb_interval == 5
    assert cfg.trash_dir == Path("..")
    assert cfg.vid_player == player
    assert cfg.vid_player_args == ("a", "b")
    assert cfg.vid_exts == (".mp4",)
    assert cfg.hidden_columns == ("res", "tags")


def test_load_defaults_when_file_missing(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    cfg = Config()
    cfg.load(tmp_path / "missing.json")

    assert cfg.metadata_key == "video_metadata"
    assert cfg.vid_player is None
    assert cfg.vid_player_args == ()
    assert cfg.hidden_columns == DEFAULT_HIDDEN_COLUMNS
    assert "error: failed to load config file" in capsys.readouterr().out


def test_hidden_columns_missing_from_file_uses_default(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    _write_config(config, {"metadata_key": "video_metadata"})

    cfg = Config()
    cfg.load(config)

    assert cfg.hidden_columns == DEFAULT_HIDDEN_COLUMNS


def test_hidden_columns_cannot_be_persisted_without_load(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    config = tmp_path / "config.json"
    _write_config(config, {"hidden_columns": ["res"]})

    cfg = Config()
    cfg.set_hidden_columns(("res",))
    cfg.save()

    assert json.loads(config.read_text()) == {"hidden_columns": ["res"]}
    assert "error: failed to save config file" not in capsys.readouterr().out


def test_save_round_trip(tmp_path: Path) -> None:
    player = tmp_path / "player.exe"
    player.touch()
    config = tmp_path / "config.json"
    _write_config(
        config,
        {
            "metadata_key": "meta",
            "thumb_height": 100,
            "thumb_interval": 5,
            "trash_dir": "..",
            "vid_player": str(player),
            "vid_player_args": ["a", "b"],
            "vid_exts": [".mp4"],
            "hidden_columns": [],
        },
    )

    cfg = Config()
    cfg.load(config)
    cfg.set_hidden_columns(("time", "res"))
    cfg.save()

    raw = json.loads(config.read_text())
    assert raw["hidden_columns"] == ["time", "res"]
    assert raw["metadata_key"] == "meta"
    assert raw["thumb_height"] == 100
    assert raw["trash_dir"] == ".."
    assert raw["vid_player"] == str(player)
    assert raw["vid_player_args"] == ["a", "b"]
    assert raw["vid_exts"] == [".mp4"]

    reloaded = Config()
    reloaded.load(config)
    assert reloaded.hidden_columns == ("time", "res")
