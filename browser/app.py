import pickle
import tkinter as tk
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NamedTuple

from util.format import nice_bytesize, nice_duration

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
from .ui import InputWindow, MainFrame, StatusWindow
from .ui.actions import AppActions, BulkAction, UiContext
from .ui.state import FileTreeUpdate, UiState
from .ui.tasks import BackgroundJobs, JobContext, UiDispatcher


class App:
    _config: Config
    _library: VideoLibrary
    _trash: Trash
    _store: MetadataStore
    _metadata: dict[str, Any]
    _selected_path: Path  # for vid info tab
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
        self._metadata = empty_metadata()
        self._selected_path = Path()

        self._state = UiState(root, thumb_interval=config.thumb_interval, thumb_height=config.thumb_height)

        self._launcher = Launcher(config.vid_player, config.vid_player_args)
        self._trash = Trash(config.trash_dir)
        self._store = MetadataStore(config.metadata_key)

        actions: AppActions = self  # App structurally implements AppActions without inheriting from it
        self._widgets = __class__.__Widgets(
            root=root,
            mainframe=MainFrame(root, UiContext(state=self._state, actions=actions)),
            status=StatusWindow(root),
            input=InputWindow(root),
        )
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)

        # worker threads post callbacks through the dispatcher; the Tk thread drains them in FIFO order
        self._dispatcher = UiDispatcher(root)
        self._jobs = BackgroundJobs(self._dispatcher, self._widgets.status, self._state.busy_changed.emit)

        # bind on root so the accelerators fire regardless of which widget has focus
        root.bind("<Control-s>", lambda _ev: self.save_metadata())
        root.bind("<Control-g>", lambda _ev: self.generate_thumbnails())

        self._library.scan()
        self._state.file_tree_changed.emit(FileTreeUpdate(self._library.tree, ""))

    def _apply_generated_metadata(self, metadata: dict[str, Any] | None) -> None:
        if metadata is not None:
            self._metadata |= metadata
        self.update_widgets_from_metadata()

    def select_paths(self, paths: Sequence[Path], triggered: Path | None = None) -> None:
        if triggered is not None and triggered in paths:
            if triggered.is_file():
                self.load_metadata(triggered)
            else:
                self.clear_vidinfo()
            return

        for p in paths:
            if p.is_file():
                self.load_metadata(p)
                return
        self.clear_vidinfo()

    def activate_path(self, path: Path) -> None:
        if path.is_file():
            self._launcher.play(path)

    def show_in_explorer(self, path: Path) -> None:
        self._launcher.reveal(path)

    def play_from_ms(self, ms: int) -> None:
        if self._selected_path.is_file():
            self._launcher.play(self._selected_path, start_ms=ms)

    def delete_paths(self, paths: Sequence[Path]) -> None:
        """Move paths to the trash and remove them from the file tree."""
        if len(paths) == 0:
            return

        if not self._trash.available:
            return

        if self._selected_path in paths:
            self.clear_vidinfo()
            self._state.selection_changed.emit(())

        removed = self._trash.send(paths)
        for p in removed:
            self._library.remove(p)
        if removed:
            self._state.paths_removed.emit(tuple(removed))

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
                on_file=lambda f, m: ui.post(self._state.file_metadata_changed.emit, (f, m)),
                on_progress=ui.progress,
            )

        self._jobs.run(work)  # status only, no busy, like today

    def delete_metadata(self, paths: Sequence[Path]) -> None:
        for f in self._store.delete_files(paths):
            self._state.file_metadata_changed.emit((f, empty_metadata()))

    def generate_thumbnails_bulk(self, paths: Sequence[Path]) -> None:
        files = tuple(p for p in paths if p.is_file())

        self.gen_thumbs_bulk(files)

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
            self._state.file_metadata_changed.emit((f, file_metadata))

    def generate_thumbnails(self) -> None:
        if self._selected_path is None or not self._selected_path.is_file():
            return

        path = self._selected_path
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

            ui.post(self._apply_generated_metadata, generated)

        self._jobs.run(work, busy=True, collect_garbage=True)

    def save_metadata(self) -> None:
        print(f"saving metadata for {self._selected_path}")

        # thumbnails are updated on generation
        self._metadata["title"] = self._state.meta_title.get()
        self._metadata["actors"] = self._widgets.root.tk.splitlist(self._state.meta_actors.get())
        self._metadata["tags"] = self._widgets.root.tk.splitlist(self._state.meta_tags.get())
        self.update_widgets_from_metadata()
        try:
            size = self._store.write(self._selected_path, self._metadata)
            self._state.meta_size.set(f"metadata size: {round(size / 1000)}KB")
        except pickle.PickleError:
            print(f"failed to pickle metadata for {self._selected_path}")
        except Exception as ex:
            print(f"failed to save metadata for {self._selected_path}: {ex}")

    def scan_metadata(self) -> None:
        self._state.filters_changed.emit(((), (), "OR"))

        # snapshot the file list on the main thread so the worker does not race tree mutations
        items = tuple(self._library.iter_files())

        def work(ui: JobContext) -> None:
            actors, tags = aggregate_files(
                items,
                self._store,
                on_file=lambda f, m: ui.post(self._state.file_metadata_changed.emit, (f, m)),
                on_progress=ui.progress,
            )
            ui.progress("populating widgets", 1.0)
            ui.post(self._state.actor_counts_changed.emit, actors)
            ui.post(self._state.tag_counts_changed.emit, tags)

        self._jobs.run(work, busy=True)

    def apply_filters(self, actors: Sequence[str], tags: Sequence[str], operator: str = "OR") -> None:
        self._state.filters_changed.emit((tuple(actors), tuple(tags), operator))

    def clear_filters(self) -> None:
        self._state.filters_changed.emit(((), (), "OR"))

    def gen_thumbs_bulk(self, files: Sequence[Path]) -> None:
        """generate thumbnails for a list of files with the blocking status window"""
        files = tuple(f for f in files if f.is_file())

        # Tk variables must be read on the main thread before the worker starts
        interval = self._state.thumb_interval.get()
        height = self._state.thumb_height.get()

        def work(ui: JobContext) -> None:
            generate_files(
                files,
                self._store,
                interval=interval,
                height=height,
                on_file=lambda f, m: ui.post(self._state.file_metadata_changed.emit, (f, m)),
                on_progress=ui.progress,
                on_fraction=ui.fraction,
            )

        self._jobs.run(work, busy=True, collect_garbage=True)

    def load_metadata(self, p: Path) -> None:
        if p.is_file():
            self._selected_path = p
            print(f"loading metadata for {p}")
            self._state.file_path.set(str(p))
            self._state.file_size.set(f"size: {nice_bytesize(p.stat().st_size, largest_unit='M')}")
            self._state.meta_size.set("metadata size: none")

            stored = self._store.read_or_empty(p)
            self._metadata = stored.metadata
            if stored.byte_size > 0:
                self._state.meta_size.set(f"metadata size: {nice_bytesize(stored.byte_size)}")

            self.update_widgets_from_metadata()
            self._state.selection_changed.emit((p,))

    def clear_vidinfo(self) -> None:
        self._state.file_path.set("")
        self._state.file_size.set("size: none")
        self._state.meta_size.set("metadata size: none")
        self._metadata = empty_metadata()
        self._selected_path = Path("")
        self.update_widgets_from_metadata()
        self._state.selection_changed.emit(())

    def update_widgets_from_metadata(self) -> None:
        self._state.file_metadata_changed.emit((self._selected_path, self._metadata))

        vres = self._metadata["video_properties"]["dimensions"]
        vlen = nice_duration(self._metadata["video_properties"]["duration"])
        self._state.meta_title.set(self._metadata["title"])
        self._state.meta_actors.set(self._metadata["actors"])
        self._state.meta_tags.set(self._metadata["tags"])
        self._state.video_len.set(f"length: {vlen}")
        self._state.video_res.set(f"resolution: {vres[0]}x{vres[1]}")
        self._state.thumbnails_changed.emit(tuple(self._metadata["thumbnails"]))
