from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple

from browser.metadata import Bookmark
from util.file.tree import PathTree


class Signal[T]:
    """Minimal typed observer. Callbacks run synchronously on the emitting thread.

    Handlers must not synchronously emit a signal that one of their own handlers consumes.
    """

    def __init__(self) -> None:
        self._callbacks: list[Callable[[T], None]] = []

    def connect(self, callback: Callable[[T], None]) -> None:
        self._callbacks.append(callback)

    def disconnect(self, callback: Callable[[T], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, value: T) -> None:
        for callback in tuple(self._callbacks):
            callback(value)


class FileTreeUpdate(NamedTuple):
    """tree is the library's live PathTree: rescan()/remove() mutate it in
    place after emission, so read it synchronously and never retain it.
    """

    tree: PathTree
    from_iid: str  # empty string means full refresh


class SelectionChanged(NamedTuple):
    paths: tuple[Path, ...]


class FileMetadataChanged(NamedTuple):
    """path is Path() when no video is selected.

    The metadata liveness contract depends on the producing signal: a live staged
    dict for selected_metadata_changed, a fresh snapshot for file_metadata_changed.
    See the contract comments on those UiState attributes.
    """

    path: Path
    metadata: Mapping[str, Any]


class PathsRemoved(NamedTuple):
    paths: tuple[Path, ...]


class Thumbnail(NamedTuple):
    jpeg: bytes
    frame_no: int
    time_ms: int


class ThumbnailsChanged(NamedTuple):
    thumbnails: tuple[Thumbnail, ...]


class BookmarksChanged(NamedTuple):
    """path is Path() when no video is selected.

    The payload is an immutable snapshot: consumers may retain it and cache it as
    (path, bookmarks). A selection change emits this before selection_changed, and a
    staged add/remove emits it without refreshing the rest of the view, so consumers
    must match path against their own selection rather than assume it is current.
    """

    path: Path
    bookmarks: tuple[Bookmark, ...]


class ActorCounts(NamedTuple):
    counts: Mapping[str, int]


class TagCounts(NamedTuple):
    counts: Mapping[str, int]


class HighlightsChanged(NamedTuple):
    actors: tuple[str, ...]
    tags: tuple[str, ...]


class FilterOperator(StrEnum):
    AND = "AND"
    OR = "OR"


class FiltersChanged(NamedTuple):
    actors: tuple[str, ...]
    tags: tuple[str, ...]
    operator: FilterOperator


class ColumnsChanged(NamedTuple):
    """hidden is the complete set of hidden filetree column ids: imply all other columns are shown."""

    hidden: tuple[str, ...]


class UiState:
    """Display state owned by App.

    Scalar values are Tk variables so widgets can bind them directly.
    Structured updates use signals. All mutations/emissions must happen on the
    Tk main thread.
    """

    def __init__(self, root: tk.Misc, *, thumb_interval: int, thumb_height: int) -> None:
        self.file_path = tk.StringVar(root)
        self.file_size = tk.StringVar(root)
        self.meta_title = tk.StringVar(root)
        self.meta_actors = tk.Variable(root)
        self.meta_tags = tk.Variable(root)
        self.meta_size = tk.StringVar(root)
        self.video_len = tk.StringVar(root)
        self.video_res = tk.StringVar(root)
        self.thumb_interval = tk.StringVar(root, value=str(thumb_interval))
        self.thumb_height = tk.StringVar(root, value=str(thumb_height))

        self.selection_changed = Signal[SelectionChanged]()
        # emitted only by store-side flows (metadata edit/clean/scan and thumbnail generation in App);
        # metadata is a snapshot: every current emitter passes a fresh dict it never retains or mutates
        # afterwards, so consumers may read it synchronously
        self.file_metadata_changed = Signal[FileMetadataChanged]()
        # emitted only by VideoSession._show() for the selected file's staged view; metadata is the live
        # _metadata dict, mutated in place by save()/apply_for() after emission, so consume synchronously
        # and never retain it
        self.selected_metadata_changed = Signal[FileMetadataChanged]()
        self.file_tree_changed = Signal[FileTreeUpdate]()
        self.paths_removed = Signal[PathsRemoved]()
        self.thumbnails_changed = Signal[ThumbnailsChanged]()
        self.bookmarks_changed = Signal[BookmarksChanged]()
        self.actor_counts_changed = Signal[ActorCounts]()
        self.tag_counts_changed = Signal[TagCounts]()
        self.highlights_changed = Signal[HighlightsChanged]()
        self.filters_changed = Signal[FiltersChanged]()
        self.columns_changed = Signal[ColumnsChanged]()
        self.busy_changed = Signal[bool]()
