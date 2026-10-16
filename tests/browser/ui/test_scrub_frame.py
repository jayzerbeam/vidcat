import tkinter as tk
from collections.abc import Sequence
from pathlib import Path

import pytest

from browser.metadata import BulkAction
from browser.ui.actions import UiContext
from browser.ui.scrub_frame import ScrubFrame
from browser.ui.state import FilterOperator, UiState


class StubActions:
    """Structural AppActions stub: every action is a no-op."""

    def select_paths(self, paths: Sequence[Path], triggered: Path | None = None) -> None: ...
    def activate_path(self, path: Path) -> None: ...
    def show_in_explorer(self, path: Path) -> None: ...
    def play_from_ms(self, ms: int) -> None: ...
    def save_metadata(self) -> None: ...
    def add_bookmark(self, time_ms: int, frame_no: int | None, name: str) -> bool: ...
    def remove_bookmark(self, time_ms: int) -> None: ...
    def scan_metadata(self) -> None: ...
    def scan_path_metadata(self, path: Path) -> None: ...
    def rescan_path(self, path: Path) -> None: ...
    def delete_paths(self, paths: Sequence[Path]) -> None: ...
    def delete_metadata(self, paths: Sequence[Path]) -> None: ...
    def edit_metadata(self, action: BulkAction, paths: Sequence[Path]) -> None: ...
    def generate_thumbnails(self) -> None: ...
    def generate_thumbnails_bulk(self, paths: Sequence[Path]) -> None: ...
    def apply_filters(self, actors: Sequence[str], tags: Sequence[str], operator: FilterOperator) -> None: ...
    def clear_filters(self) -> None: ...
    def set_columns_hidden(self, names: Sequence[str]) -> None: ...


@pytest.fixture
def root():
    window = tk.Tk()
    yield window
    window.destroy()


@pytest.fixture
def frame(root: tk.Tk):
    ctx = UiContext(state=UiState(root, thumb_interval=0, thumb_height=0), actions=StubActions())
    frame = ScrubFrame(root, ctx)
    yield frame
    frame.destroy()


def simulate_scrubbed(frame: ScrubFrame, path: Path) -> None:
    """Leave the widget as a loaded and scrubbed video does: enabled bar, stale fraction."""
    frame._path = path
    frame._duration_ms = 60_000.0
    frame._widgets.seek.state(["!disabled"])
    frame._widgets.seek.set(0.6)
    assert frame._widgets.seek.get() == 0.6


def test_load_resets_seek_while_scale_is_disabled(frame: ScrubFrame, tmp_path: Path) -> None:
    simulate_scrubbed(frame, tmp_path / "a.mp4")

    frame.load(tmp_path / "b.mp4")

    # the scale is disabled at this moment, where set() is a no-op
    assert "disabled" in frame._widgets.seek.state()
    assert frame._widgets.seek.get() == 0.0


def test_clear_resets_seek_while_scale_is_disabled(frame: ScrubFrame, tmp_path: Path) -> None:
    simulate_scrubbed(frame, tmp_path / "a.mp4")

    frame.clear()

    assert "disabled" in frame._widgets.seek.state()
    assert frame._widgets.seek.get() == 0.0


def test_loaded_video_reports_zero_ms_at_reset_seek(frame: ScrubFrame, tmp_path: Path) -> None:
    simulate_scrubbed(frame, tmp_path / "a.mp4")
    frame.load(tmp_path / "b.mp4")

    frame._apply_loaded(frame._load_seq, 60.0, 30.0, None)

    # a stale 0.6 fraction would report 36000 ms into the newly loaded 60 s video
    assert frame._current_ms() == 0
