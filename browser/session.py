import pickle
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from util.format import nice_bytesize, nice_duration

from .metadata import MetadataStore, empty_metadata
from .ui.state import FileMetadataChanged, SelectionChanged, Thumbnail, ThumbnailsChanged, UiState


class VideoSession:
    """Selected-video view model: owns the current path/metadata and updates UiState."""

    _state: UiState
    _store: MetadataStore
    _split_list: Callable[[Any], Sequence[str]]
    _selected_path: Path | None
    _metadata: dict[str, Any]

    def __init__(self, state: UiState, store: MetadataStore, split_list: Callable[[Any], Sequence[str]]) -> None:
        self._state = state
        self._store = store
        self._split_list = split_list
        self._selected_path = None
        self._metadata = empty_metadata()

    @property
    def selected_path(self) -> Path | None:
        return self._selected_path

    def select(self, paths: Sequence[Path], triggered: Path | None = None) -> None:
        """Load the triggered file, else the first file in paths; otherwise clear the selection."""
        if triggered is not None and triggered in paths:
            if triggered.is_file():
                self._load(triggered)
            else:
                self.clear()
            return

        for p in paths:
            if p.is_file():
                self._load(p)
                return
        self.clear()

    def clear(self) -> None:
        """Reset the selection and the info pane."""
        self._state.file_path.set("")
        self._state.file_size.set("size: none")
        self._state.meta_size.set("metadata size: none")
        self._metadata = empty_metadata()
        self._selected_path = None
        self._show()
        self._state.selection_changed.emit(SelectionChanged(()))

    def save(self) -> None:
        """Write the edited title/actors/tags into the selected file's sidecar."""
        # cast: selected_path is None only before any selection; the write below then fails as before
        path = cast(Path, self._selected_path)
        print(f"saving metadata for {path}")

        # thumbnails are updated on generation
        self._metadata["title"] = self._state.meta_title.get()
        self._metadata["actors"] = self._split_list(self._state.meta_actors.get())
        self._metadata["tags"] = self._split_list(self._state.meta_tags.get())
        self._show()
        try:
            size = self._store.write(path, self._metadata)
            self._state.meta_size.set(f"metadata size: {round(size / 1000)}KB")
        except pickle.PickleError:
            print(f"failed to pickle metadata for {path}")
        except Exception as ex:
            print(f"failed to save metadata for {path}: {ex}")

    def apply_for(self, path: Path, metadata: dict[str, Any] | None) -> None:
        """Merge generated metadata (when present) into the loaded metadata and refresh the view.

        Scope the merge to the file it was generated for: with no selection loaded, or with the
        selection moved on to another file, the generated data is stale and must not be applied.
        """
        if self._selected_path is None or path != self._selected_path:
            return
        if metadata is not None:
            self._metadata |= metadata
        self._show()

    def _load(self, path: Path) -> None:
        self._selected_path = path
        print(f"loading metadata for {path}")
        self._state.file_path.set(str(path))
        self._state.file_size.set(f"size: {nice_bytesize(path.stat().st_size, largest_unit='M')}")
        self._state.meta_size.set("metadata size: none")

        stored = self._store.read_or_empty(path)
        self._metadata = stored.metadata
        if stored.byte_size > 0:
            self._state.meta_size.set(f"metadata size: {nice_bytesize(stored.byte_size)}")

        self._show()
        self._state.selection_changed.emit(SelectionChanged((path,)))

    def _show(self) -> None:
        self._state.file_metadata_changed.emit(FileMetadataChanged(self._selected_path or Path(), self._metadata))

        vres = self._metadata["video_properties"]["dimensions"]
        vlen = nice_duration(self._metadata["video_properties"]["duration"])
        self._state.meta_title.set(self._metadata["title"])
        self._state.meta_actors.set(self._metadata["actors"])
        self._state.meta_tags.set(self._metadata["tags"])
        self._state.video_len.set(f"length: {vlen}")
        self._state.video_res.set(f"resolution: {vres[0]}x{vres[1]}")
        # the stored thumbnails are raw (jpeg, frame_no, time_ms) tuples; convert to the UI payload type
        self._state.thumbnails_changed.emit(
            ThumbnailsChanged(tuple(Thumbnail(*t) for t in self._metadata["thumbnails"]))
        )
