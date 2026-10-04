from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from util.file.tree import PathTree


class Signal[T]:
    """Minimal typed observer. Callbacks run synchronously on the emitting thread."""

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
    tree: PathTree
    from_iid: str  # empty string means full refresh


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

        self.selection_changed = Signal[Sequence[Path]]()
        self.file_metadata_changed = Signal[tuple[Path, Mapping[str, Any]]]()
        self.file_tree_changed = Signal[FileTreeUpdate]()
        self.paths_removed = Signal[Sequence[Path]]()
        self.thumbnails_changed = Signal[Sequence[tuple[bytes, int, int]]]()
        self.actor_counts_changed = Signal[Mapping[str, int]]()
        self.tag_counts_changed = Signal[Mapping[str, int]]()
        self.highlights_changed = Signal[tuple[Sequence[str], Sequence[str]]]()
        self.filters_changed = Signal[tuple[Sequence[str], Sequence[str], str]]()
        self.busy_changed = Signal[bool]()
