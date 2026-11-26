import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from browser.metadata import BulkAction
from browser.ui.actions import UiContext
from browser.ui.filter_frame import FilterFrame
from browser.ui.state import ActorCounts, FilterOperator, TagCounts, UiState


class StubActions:
    """Structural AppActions stub: records scan/filter/highlight requests, everything else is a no-op."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def select_paths(self, paths: Sequence[Path], triggered: Path | None = None) -> None: ...
    def activate_path(self, path: Path) -> None: ...
    def open_path(self, path: Path) -> None: ...
    def play_from_ms(self, ms: int) -> None: ...
    def save_metadata(self) -> None: ...
    def add_bookmark(self, time_ms: int, frame_no: int | None, name: str) -> bool:
        return False

    def remove_bookmark(self, time_ms: int) -> None: ...
    def scan_metadata(self) -> None:
        self.calls.append(("scan_metadata",))

    def scan_path_metadata(self, path: Path) -> None: ...
    def rescan_path(self, path: Path) -> None: ...
    def delete_paths(self, paths: Sequence[Path]) -> None: ...
    def delete_metadata(self, paths: Sequence[Path]) -> None: ...
    def edit_metadata(self, action: BulkAction, paths: Sequence[Path]) -> None: ...
    def generate_thumbnails(self) -> None: ...
    def generate_thumbnails_bulk(self, paths: Sequence[Path]) -> None: ...
    def apply_filters(self, actors: Sequence[str], tags: Sequence[str], operator: FilterOperator) -> None:
        self.calls.append(("apply_filters", tuple(actors), tuple(tags), operator))

    def clear_filters(self) -> None:
        self.calls.append(("clear_filters",))

    def set_highlights(self, actors: Sequence[str], tags: Sequence[str]) -> None:
        self.calls.append(("set_highlights", tuple(actors), tuple(tags)))

    def set_columns_hidden(self, names: Sequence[str]) -> None: ...


@pytest.fixture
def root():
    window = tk.Tk()
    yield window
    window.destroy()


def make_frame(root: tk.Tk) -> tuple[FilterFrame, StubActions]:
    actions = StubActions()
    ctx = UiContext(state=UiState(root, thumb_interval=0, thumb_height=0), actions=actions)
    frame = FilterFrame(root, ctx)
    frame._set_actors(ActorCounts({"Alice": 2, "Bob": 1}))
    frame._set_tags(TagCounts({"fun": 3}))
    return frame, actions


def test_selecting_an_actor_emits_highlights(root: tk.Tk) -> None:
    frame, actions = make_frame(root)

    frame._widgets.actors.child.selection_set("Alice")
    root.update()

    assert ("set_highlights", ("Alice",), ()) in actions.calls


def test_filter_buttons_apply_the_current_selection(root: tk.Tk) -> None:
    frame, actions = make_frame(root)

    frame._widgets.actors.child.selection_set("Alice")
    frame._widgets.tags.child.selection_set("fun")
    root.update()

    frame._widgets.filter_and.invoke()
    frame._widgets.filter_or.invoke()

    assert ("apply_filters", ("Alice",), ("fun",), FilterOperator.AND) in actions.calls
    assert ("apply_filters", ("Alice",), ("fun",), FilterOperator.OR) in actions.calls


def test_clear_drops_selections_and_highlights_together(root: tk.Tk) -> None:
    frame, actions = make_frame(root)

    frame._widgets.actors.child.selection_set("Alice")
    frame._widgets.tags.child.selection_set("fun")
    root.update()

    frame._widgets.filter_clear.invoke()
    root.update()

    # the pane selections are gone, so the next Filter click starts from nothing
    assert frame._widgets.actors.child.selection() == ()
    assert frame._widgets.tags.child.selection() == ()
    assert ("clear_filters",) in actions.calls
    # an empty HighlightsChanged was emitted, so the filetree drops its highlight tags
    assert ("set_highlights", (), ()) in actions.calls


def test_clear_with_no_selection_still_clears_filters(root: tk.Tk) -> None:
    frame, actions = make_frame(root)

    frame._widgets.filter_clear.invoke()

    assert ("clear_filters",) in actions.calls
