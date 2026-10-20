import tkinter as tk
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NamedTuple

from .config import Config
from .launcher import Launcher
from .library import Trash, VideoLibrary
from .metadata import (
    MetadataStore,
    aggregate_files,
    empty_metadata,
    generate_files,
    generate_video_metadata,
    refresh_files,
)
from .session import VideoSession
from .ui import InputWindow, MainFrame, StatusWindow
from .ui.actions import AppActions, BulkAction, UiContext
from .ui.state import (
    ActorCounts,
    ColumnsChanged,
    FileMetadataChanged,
    FileTreeUpdate,
    FilterOperator,
    FiltersChanged,
    PathsRemoved,
    TagCounts,
    UiState,
)
from .ui.tasks import BackgroundJobs, JobContext, UiDispatcher


class App:
    _config: Config
    _library: VideoLibrary
    _trash: Trash
    _store: MetadataStore
    _session: VideoSession
    _state: UiState
    _launcher: Launcher
    _dispatcher: UiDispatcher
    _jobs: BackgroundJobs

    class __Widgets(NamedTuple):
        root: tk.Tk
        mainframe: MainFrame
        status: StatusWindow
        input: InputWindow

    def __init__(self, root: tk.Tk, basepath: Path, config: Config):
        self._config = config
        self._library = VideoLibrary(basepath, config.vid_exts)

        self._state = UiState(root, thumb_interval=config.thumb_interval, thumb_height=config.thumb_height)

        self._launcher = Launcher(config.vid_player, config.vid_player_args)
        self._trash = Trash(config.trash_dir)
        self._store = MetadataStore(config.metadata_key)
        self._session = VideoSession(self._state, self._store, split_list=root.tk.splitlist)

        actions: AppActions = self  # App structurally implements AppActions without inheriting from it
        self._widgets = __class__.__Widgets(
            root=root,
            mainframe=MainFrame(root, UiContext(state=self._state, actions=actions)),
            status=StatusWindow(root),
            input=InputWindow(root),
        )
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)

        # push the persisted column visibility to the filetree before connecting persistence, so the
        # initial state is not round-tripped to the config file
        self._state.hidden_columns_changed.emit(ColumnsChanged(tuple(self._config.hidden_columns)))
        self._state.hidden_columns_changed.connect(self._persist_columns)

        # worker threads post callbacks through the dispatcher; the Tk thread drains them in FIFO order
        self._dispatcher = UiDispatcher(root)
        self._jobs = BackgroundJobs(self._dispatcher, self._widgets.status, self._state.busy_changed.emit)

        # bind on root so the accelerators fire regardless of which widget has focus
        root.bind("<Control-s>", lambda _ev: self.save_metadata())
        root.bind("<Control-g>", lambda _ev: self.generate_thumbnails())

        self._library.scan()
        self._state.file_tree_changed.emit(FileTreeUpdate(self._library.tree, ""))

    def select_paths(self, paths: Sequence[Path], triggered: Path | None = None) -> None:
        self._session.select(paths, triggered)

    def activate_path(self, path: Path) -> None:
        if path.is_file():
            self._launcher.play(path)

    def show_in_explorer(self, path: Path) -> None:
        self._launcher.reveal(path)

    def play_from_ms(self, ms: int) -> None:
        p = self._session.selected_path
        if p is not None and p.is_file():
            self._launcher.play(p, start_ms=ms)

    def delete_paths(self, paths: Sequence[Path]) -> None:
        """Move paths to the trash and remove them from the file tree."""
        if len(paths) == 0:
            return

        if not self._trash.available:
            return

        if self._session.selected_path in paths:
            self._session.clear()

        removed = self._trash.send(paths)
        for p in removed:
            self._library.remove(p)
        if removed:
            self._state.paths_removed.emit(PathsRemoved(tuple(removed)))

    def rescan_path(self, path: Path) -> None:
        pt = self._library.rescan(path)
        if pt is not None:
            self._state.file_tree_changed.emit(FileTreeUpdate(pt, str(path)))

    def scan_path_metadata(self, path: Path) -> None:
        if not path.is_dir():
            return

        # snapshot the file list on the main thread so the worker does not race tree mutations
        files = tuple(self._library.iter_files(path))
        # a directory absent from the library tree yields no files: the status window then only shows and
        # closes (unreachable from the UI, which passes tree iids; acceptable per spec delta 1)

        def work(ui: JobContext) -> None:
            refresh_files(
                files,
                self._store,
                on_file=lambda f, m: ui.post(self._state.stored_metadata_changed.emit, FileMetadataChanged(f, m)),
                on_progress=ui.progress,
            )

        self._jobs.run(work)  # status only, no busy, like today

    def delete_metadata(self, paths: Sequence[Path]) -> None:
        for f in self._store.delete_files(paths):
            self._state.stored_metadata_changed.emit(FileMetadataChanged(f, empty_metadata()))

    def generate_thumbnails_bulk(self, paths: Sequence[Path]) -> None:
        """generate thumbnails for a list of files with the blocking status window"""
        files = tuple(p for p in paths if p.is_file())

        # Tk variables must be read on the main thread before the worker starts
        interval = self._state.thumb_interval.get()
        height = self._state.thumb_height.get()

        def work(ui: JobContext) -> None:
            generate_files(
                files,
                self._store,
                interval=interval,
                height=height,
                on_file=lambda f, m: ui.post(self._state.stored_metadata_changed.emit, FileMetadataChanged(f, m)),
                on_progress=ui.progress,
                on_fraction=ui.fraction,
            )

        self._jobs.run(work, busy=True, collect_garbage=True)

    def edit_metadata(self, action: BulkAction, paths: Sequence[Path]) -> None:
        match action:
            case BulkAction.ADD_ACTOR:
                self._widgets.input.title_text = "Add Actor"
                self._widgets.input.label_text = "Enter actor to add"
            case BulkAction.DEL_ACTOR:
                self._widgets.input.title_text = "Remove Actor"
                self._widgets.input.label_text = "Enter actor to remove"
            case BulkAction.ADD_TAG:
                self._widgets.input.title_text = "Add Tag"
                self._widgets.input.label_text = "Enter tag to add"
            case BulkAction.DEL_TAG:
                self._widgets.input.title_text = "Remove Tag"
                self._widgets.input.label_text = "Enter tag to remove"

        val = self._widgets.input.block_for_input()
        if val is None or not val.strip():
            return

        for f, file_metadata in self._store.edit_files(paths, action, val):
            self._state.stored_metadata_changed.emit(FileMetadataChanged(f, file_metadata))

    def generate_thumbnails(self) -> None:
        selected = self._session.selected_path
        if selected is None or not selected.is_file():
            return

        path = selected
        # Tk variables must be read on the main thread before the worker starts
        interval = self._state.thumb_interval.get()
        height = self._state.thumb_height.get()

        def work(ui: JobContext) -> None:
            generated: dict[str, Any] | None = None
            try:
                generated = generate_video_metadata(
                    path,
                    interval,
                    height,
                    extract_progress_func=ui.progress_func("Extracting frames..."),
                    resize_progress_func=ui.progress_func("Resizing frames..."),
                )
            except Exception as ex:
                print(f"error: failed to generate metadata for {path}: {ex}")
                traceback.print_exc()

            # apply_for drops the merge when the user has selected a different file or none by then
            ui.post(self._session.apply_for, path, generated)

        self._jobs.run(work, busy=True, collect_garbage=True)

    def save_metadata(self) -> None:
        self._session.save()

    def add_bookmark(self, time_ms: int, frame_no: int | None, name: str) -> bool:
        return self._session.add_bookmark(time_ms, frame_no, name)

    def remove_bookmark(self, time_ms: int) -> None:
        self._session.remove_bookmark(time_ms)

    def scan_metadata(self) -> None:
        self._state.filters_changed.emit(FiltersChanged((), (), FilterOperator.OR))

        # snapshot the file list on the main thread so the worker does not race tree mutations
        items = tuple(self._library.iter_files())

        def work(ui: JobContext) -> None:
            actors, tags = aggregate_files(
                items,
                self._store,
                on_file=lambda f, m: ui.post(self._state.stored_metadata_changed.emit, FileMetadataChanged(f, m)),
                on_progress=ui.progress,
            )
            ui.progress("populating widgets", 1.0)
            ui.post(self._state.actor_counts_changed.emit, ActorCounts(actors))
            ui.post(self._state.tag_counts_changed.emit, TagCounts(tags))

        self._jobs.run(work, busy=True)

    def apply_filters(
        self, actors: Sequence[str], tags: Sequence[str], operator: FilterOperator = FilterOperator.OR
    ) -> None:
        self._state.filters_changed.emit(FiltersChanged(tuple(actors), tuple(tags), operator))

    def clear_filters(self) -> None:
        self._state.filters_changed.emit(FiltersChanged((), (), FilterOperator.OR))

    def set_columns_hidden(self, names: Sequence[str]) -> None:
        self._state.hidden_columns_changed.emit(ColumnsChanged(tuple(names)))

    def _persist_columns(self, change: ColumnsChanged) -> None:
        self._config.set_hidden_columns(change.hidden)
        self._config.save()
