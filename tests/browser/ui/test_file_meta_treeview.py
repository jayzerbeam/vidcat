import tkinter as tk
from collections.abc import Sequence
from pathlib import Path

import pytest

from browser.metadata import BulkAction
from browser.ui.actions import UiContext
from browser.ui.file_meta_treeview import _DATA_COLUMNS, FileMetaTreeviewFrame
from browser.ui.state import ColumnsChanged, FilterOperator, UiState


class StubActions:
    """Structural AppActions stub: records set_columns_hidden requests, everything else is a no-op."""

    def __init__(self) -> None:
        self.hidden_columns: tuple[str, ...] | None = None

    def select_paths(self, paths: Sequence[Path], triggered: Path | None = None) -> None: ...
    def activate_path(self, path: Path) -> None: ...
    def show_in_explorer(self, path: Path) -> None: ...
    def play_from_ms(self, ms: int) -> None: ...
    def save_metadata(self) -> None: ...
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
    def set_columns_hidden(self, names: Sequence[str]) -> None:
        self.hidden_columns = tuple(names)


@pytest.fixture
def root():
    window = tk.Tk()
    yield window
    window.destroy()


def make_frame(root: tk.Tk) -> tuple[FileMetaTreeviewFrame, StubActions]:
    actions = StubActions()
    ctx = UiContext(state=UiState(root, thumb_interval=0, thumb_height=0), actions=actions)
    return FileMetaTreeviewFrame(root, ctx), actions


def test_before_any_change_all_data_columns_counts_as_shown(root: tk.Tk) -> None:
    frame, _ = make_frame(root)

    assert frame._shown_columns() == {name for name, _ in _DATA_COLUMNS}


def test_columns_option_matches_data_columns(root: tk.Tk) -> None:
    frame, _ = make_frame(root)

    assert tuple(frame.treeview.cget("columns")) == tuple(name for name, _ in _DATA_COLUMNS)


def test_columns_changed_updates_displaycolumns_and_menu_vars(root: tk.Tk) -> None:
    frame, _ = make_frame(root)

    frame._on_columns_changed(ColumnsChanged(("res",)))

    displaycolumns = frame.treeview.cget("displaycolumns")
    assert displaycolumns == ("time", "actors", "tags")
    assert not frame._col_vars["res"].get()
    assert all(frame._col_vars[name].get() for name, _ in _DATA_COLUMNS if name != "res")


def test_toggle_on_hidden_column_re_shows_it(root: tk.Tk) -> None:
    frame, actions = make_frame(root)
    frame._on_columns_changed(ColumnsChanged(("res",)))

    frame._handle_toggle_column("res")

    assert actions.hidden_columns == ()


def test_toggle_on_shown_column_hides_it(root: tk.Tk) -> None:
    frame, actions = make_frame(root)
    frame._on_columns_changed(ColumnsChanged(()))

    frame._handle_toggle_column("time")

    assert actions.hidden_columns == ("time",)
