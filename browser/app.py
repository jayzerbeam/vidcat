import gc
import os
import pickle
import platform
import subprocess
import threading
import time
import tkinter as tk
import traceback
from collections.abc import Callable, Iterator, Sequence
from copy import deepcopy
from functools import partial
from pathlib import Path
from queue import Queue
from typing import Any, Final, NamedTuple

from util.file.sidecar import MagicSidecar
from util.file.tree import PathTree, path_extension_filter
from util.format import nice_bytesize, nice_duration
from util.video import ProgressFunc, VideoThumbnailer

from .config import Config
from .ui import InputWindow, MainFrame, StatusWindow
from .ui.actions import AppActions, BulkAction, UiContext
from .ui.state import FileTreeUpdate, UiState

_EMPTY_METADATA: Final[dict[str, Any]] = {
    "title": "",
    "video_properties": {"dimensions": (0, 0), "duration": 0},
    "actors": [],
    "tags": [],
    "thumbnails": [],
}


class App:
    _config: Config
    _pathtree: PathTree
    _trash_path: Path
    _metadata: dict[str, Any]
    _selected_path: Path  # for vid info tab
    _state: UiState

    class __Widgets(NamedTuple):
        root: tk.Tk
        mainframe: MainFrame
        status: StatusWindow
        input: InputWindow

    def __init__(self, root: tk.Tk, basepath: Path, config: Config):
        self._config = config
        self._pathtree = PathTree(basepath)
        self._metadata = deepcopy(_EMPTY_METADATA)
        self._selected_path = Path()

        self._state = UiState(root, thumb_interval=config.thumb_interval, thumb_height=config.thumb_height)

        actions: AppActions = self  # App structurally implements AppActions without inheriting from it
        self._widgets = __class__.__Widgets(
            root=root,
            mainframe=MainFrame(root, UiContext(state=self._state, actions=actions)),
            status=StatusWindow(root),
            input=InputWindow(root),
        )
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)

        # Worker threads post callables here; the main thread drains them in FIFO order.
        self._ui_queue: Queue[Callable[[], None]] = Queue()
        self._widgets.root.after(30, self._drain_ui_queue)

        # bind on root so the accelerators fire regardless of which widget has focus
        root.bind("<Control-s>", lambda _ev: self.save_metadata())
        root.bind("<Control-g>", lambda _ev: self.generate_thumbnails())

        self._widgets.status.transient(self._widgets.mainframe)  # type: ignore
        self.status_window(False)

        self._init_trash(config.trash_dir)
        self.update_filetree()

    def _post_ui(self, callback: Callable[[], None]) -> None:
        self._ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        while not self._ui_queue.empty():
            callback = self._ui_queue.get()
            try:
                callback()
            except Exception as ex:
                print(f"error: UI callback failed: {ex}")
                traceback.print_exc()
        self._widgets.root.after(30, self._drain_ui_queue)

    def _emit_file_metadata(self, path: Path, metadata: dict[str, Any]) -> None:
        self._state.file_metadata_changed.emit((path, metadata))

    def _emit_progress(self, info: str, progress: float) -> None:
        self._widgets.status.info = info
        self._widgets.status.progress = progress

    def _set_progress(self, progress: float) -> None:
        self._widgets.status.progress = progress

    def _emit_actor_counts(self, actors: dict[str, int]) -> None:
        self._state.actor_counts_changed.emit(actors)

    def _emit_tag_counts(self, tags: dict[str, int]) -> None:
        self._state.tag_counts_changed.emit(tags)

    def _emit_busy(self, busy: bool) -> None:
        self._state.busy_changed.emit(busy)

    def _close_status(self) -> None:
        self.status_window(False)

    def _apply_generated_metadata(self, metadata: dict[str, Any] | None) -> None:
        if metadata is not None:
            self._metadata |= metadata
        self.update_widgets_from_metadata()

    def _init_trash(self, path: Path) -> None:
        if not path.exists():
            path.mkdir()

        if path.is_dir():
            self._trash_path = path
        else:
            # shouldn't happen, config does a trash path check
            print("error:trash directory is not a directory, could not initialize")

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
            self.play_file(path)

    def show_in_explorer(self, path: Path) -> None:
        self.goto_path(path)

    def play_from_ms(self, ms: int) -> None:
        if self._selected_path.is_file():
            self.play_file(self._selected_path, start_ms=ms)

    def delete_paths(self, paths: Sequence[Path]) -> None:
        """Move paths to the trash and remove them from the file tree."""
        if self._trash_path is None:
            return

        if len(paths) == 0:
            return

        if self._selected_path in paths:
            self.clear_vidinfo()
            self._state.selection_changed.emit(())

        removed = self._send_to_trash(paths)
        if removed:
            self._state.paths_removed.emit(tuple(removed))

    def _send_to_trash(self, paths: Sequence[Path]) -> list[Path]:
        removed: list[Path] = []
        for p in paths:
            # container folder may have been moved
            if not p.exists():
                continue

            try:
                p.move(self._trash_path / p.name)
            except OSError as ex:
                print(f"error: failed to move {p} to trash: {ex}")
                continue
            self._pathtree.dig_and_remove(p)
            removed.append(p)
        return removed

    def rescan_path(self, path: Path) -> None:
        if not path.is_dir():
            return

        pt = self._pathtree.dig(path)
        if pt is not None:
            pt.clear()
            pt.scan(filters=[path_extension_filter(self._config.vid_exts)])
            self._state.file_tree_changed.emit(FileTreeUpdate(pt, str(path)))

    def scan_path_metadata(self, path: Path) -> None:
        if not path.is_dir():
            return

        pt = self._pathtree.dig(path)
        if pt is None:
            return

        fq = Queue()

        def _thread(pt: PathTree) -> None:
            _recurse(pt)

            total = fq.qsize()
            c = 0
            while not fq.empty():
                f = fq.get()
                c += 1
                self._post_ui(partial(self._emit_progress, f"[{c} / {total}] {f.name}", c / total))
                try:
                    metadata = pickle.loads(MagicSidecar(f, namespace=self._config.metadata_key).read())
                except FileNotFoundError:
                    pass
                except Exception as ex:
                    print(f"error: failed to load metadata for {f}: {ex}")
                    traceback.print_exc()
                else:
                    self._post_ui(partial(self._emit_file_metadata, f, metadata))
            self._post_ui(self._close_status)

        def _recurse(pt: PathTree) -> None:
            for d, child in pt.dirs():
                _recurse(child)

            for f in pt.files():
                fq.put(f)

        self.status_window(True)
        threading.Thread(target=lambda: _thread(pt), daemon=True).start()

    def delete_metadata(self, paths: Sequence[Path]) -> None:
        files = tuple(p for p in paths if p.is_file())

        for f in files:
            try:
                MagicSidecar(f, namespace=self._config.metadata_key).delete()
            except Exception as ex:
                print(f"error: failed to delete metadata for {f}: {ex}")
                traceback.print_exc()
            else:
                self._state.file_metadata_changed.emit((f, _EMPTY_METADATA))

    def generate_thumbnails_bulk(self, paths: Sequence[Path]) -> None:
        files = tuple(p for p in paths if p.is_file())

        self.gen_thumbs_bulk(files)

    def edit_metadata(self, action: BulkAction, paths: Sequence[Path]) -> None:
        files = tuple(p for p in paths if p.is_file())

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

        for f in files:
            sidecar = MagicSidecar(f, namespace=self._config.metadata_key)
            metadata = deepcopy(_EMPTY_METADATA)
            try:
                metadata = pickle.loads(sidecar.read())
            except FileNotFoundError:
                pass
            except Exception as ex:
                print(f"error: failed to load metadata for {f}: {ex}")
                traceback.print_exc()
                continue

            # sometimes the value is a tuple, coerce back to list
            actors = list(metadata.get("actors", []))
            tags = list(metadata.get("tags", []))
            match action:
                case BulkAction.ADD_ACTOR:
                    if val not in actors:
                        actors.append(val)
                        metadata["actors"] = sorted(actors)
                case BulkAction.DEL_ACTOR:
                    if val in actors:
                        actors.remove(val)
                        metadata["actors"] = actors
                case BulkAction.ADD_TAG:
                    tag = val.lower()
                    if tag not in tags:
                        tags.append(tag)
                        metadata["tags"] = sorted(tags)
                case BulkAction.DEL_TAG:
                    if val.lower() in tags:
                        tags.remove(val.lower())
                        metadata["tags"] = tags

            try:
                print(f"updating metdata for {f}")
                sidecar.write(pickle.dumps(metadata))
            except Exception as ex:
                print(f"error: failed to write metadata for {f}: {ex}")
                traceback.print_exc()
                continue
            else:
                self._state.file_metadata_changed.emit((f, metadata))

    def generate_thumbnails(self) -> None:
        if self._selected_path is None or not self._selected_path.is_file():
            return

        path = self._selected_path
        # Tk variables must be read on the main thread before the worker starts
        interval = self._state.thumb_interval.get()
        height = self._state.thumb_height.get()

        # probably not thread-safe
        def _thread_entry() -> None:
            def _progress(p: float, prefix: str) -> None:
                self._post_ui(partial(self._emit_progress, f"{prefix} {p * 100:.1f}%", p))

            generated: dict[str, Any] | None = None
            try:
                generated = self._generate_video_metadata(
                    path,
                    interval,
                    height,
                    extract_progress_func=partial(_progress, prefix="Extracting frames..."),
                    resize_progress_func=partial(_progress, prefix="Resizing frames..."),
                )
            except Exception as ex:
                print(f"error: failed to generate metadata for {path}: {ex}")
                traceback.print_exc()

            self._post_ui(partial(self._apply_generated_metadata, generated))
            self._post_ui(self._close_status)
            self._post_ui(partial(self._emit_busy, False))

            """ a lot of buffers, objects, etc. are created here so invoking a garbage collection afterward seems
                to keep memory usage from ballooning"""
            gc.collect()

        self.status_window(True)
        self._emit_busy(True)
        threading.Thread(target=_thread_entry, daemon=True).start()

    def save_metadata(self) -> None:
        print(f"saving metadata for {self._selected_path}")

        # thumbnails are updated on generation
        self._metadata["title"] = self._state.meta_title.get()
        self._metadata["actors"] = self._widgets.root.tk.splitlist(self._state.meta_actors.get())
        self._metadata["tags"] = self._widgets.root.tk.splitlist(self._state.meta_tags.get())
        self.update_widgets_from_metadata()
        try:
            buf = pickle.dumps(self._metadata)
            sidecar = MagicSidecar(self._selected_path, namespace=self._config.metadata_key)
            sidecar.write(buf)
            self._state.meta_size.set(f"metadata size: {round(len(buf) / 1000)}KB")
        except pickle.PickleError:
            print(f"failed to pickle metadata for {self._selected_path}")
        except Exception as ex:
            print(f"failed to save metadata for {self._selected_path}: {ex}")

    def scan_metadata(self) -> None:
        self.status_window(True)
        self._emit_busy(True)
        self._state.filters_changed.emit(((), (), "OR"))

        def _thread_entry() -> None:
            def _incr(totals: dict[str, int], keys: list[str]) -> None:
                for k in keys:
                    k = k.lower()
                    if k not in totals:
                        totals[k] = 1
                    else:
                        totals[k] += 1

            actors: dict[str, int] = {}
            tags: dict[str, int] = {}
            items: list[Path] = list(self._iter_files())

            item_count: int = len(items)
            update_interval: float = 0.05
            last_time: float = time.time()
            for c, path in enumerate(items):
                if time.time() > last_time + update_interval:
                    self._post_ui(partial(self._emit_progress, f"[{c}/{item_count}] {path}", (c + 1) / item_count))
                    last_time = time.time()

                if path.is_file():
                    sidecar = MagicSidecar(path, namespace=self._config.metadata_key)
                    if not sidecar.exists:
                        continue

                    try:
                        metadata = pickle.loads(sidecar.read())
                    except pickle.UnpicklingError:
                        print(f"failed to unpickle metadata for {path}")
                    except Exception:
                        print(f"failed to read metadata for {path}")
                    else:
                        self._post_ui(partial(self._emit_file_metadata, path, metadata))
                        _incr(actors, metadata["actors"])
                        _incr(tags, metadata["tags"])

            self._post_ui(partial(self._emit_progress, "populating widgets", 1.0))
            self._post_ui(partial(self._emit_actor_counts, actors))
            self._post_ui(partial(self._emit_tag_counts, tags))
            self._post_ui(partial(self._emit_busy, False))
            self._post_ui(self._close_status)

        threading.Thread(target=_thread_entry, daemon=True).start()

    def apply_filters(self, actors: Sequence[str], tags: Sequence[str], operator: str = "OR") -> None:
        self._state.filters_changed.emit((tuple(actors), tuple(tags), operator))

    def clear_filters(self) -> None:
        self._state.filters_changed.emit(((), (), "OR"))

    def _generate_video_metadata(
        self,
        path: Path,
        thumb_interval: str,
        thumb_height: str,
        extract_progress_func: ProgressFunc = lambda f: None,
        resize_progress_func: ProgressFunc = lambda f: None,
    ) -> dict[str, Any]:
        m = {}
        vt = VideoThumbnailer(path)
        m["video_properties"] = {}
        m["video_properties"]["dimensions"] = vt.dimensions
        m["video_properties"]["duration"] = round(vt.duration, 2) if vt.duration is not None else 0
        vt.extract_frames(interval=float(thumb_interval), progress_func=extract_progress_func)
        vt.resize_frames(resize_height=int(thumb_height), progress_func=resize_progress_func)
        jpgs = vt.gen_jpgs()
        if jpgs is not None:
            m["thumbnails"] = jpgs

        return m

    def gen_thumbs_bulk(self, files: Sequence[Path]) -> None:
        """generate thumbnails for a list of files with the blocking status window"""
        fq = Queue()
        for f in files:
            if f.is_file():
                fq.put(f)

        self.status_window(True)
        self._emit_busy(True)

        # Tk variables must be read on the main thread before the worker starts
        interval = self._state.thumb_interval.get()
        height = self._state.thumb_height.get()

        def _thread() -> None:
            def _xprog(fraction: float) -> None:
                self._post_ui(partial(self._set_progress, c / total + (1 / total * (0.5 * fraction))))

            def _rprog(fraction: float) -> None:
                self._post_ui(partial(self._set_progress, c / total + (1 / total * (0.5 * fraction + 0.5))))

            total = fq.qsize()
            c = 0

            while not fq.empty():
                f = fq.get()
                sidecar = MagicSidecar(f, namespace=self._config.metadata_key)
                metadata = deepcopy(_EMPTY_METADATA)
                try:
                    metadata = pickle.loads(sidecar.read())
                except FileNotFoundError:
                    print(f"no sidecar metadata for {f}")
                except Exception as ex:
                    print(f"error: loading sidecar metadata for {f}: {ex}")
                    traceback.print_exc()

                self._post_ui(partial(self._emit_progress, f"[{c + 1} / {total}] {f}", c / total))
                try:
                    metadata |= self._generate_video_metadata(
                        f, interval, height, extract_progress_func=_xprog, resize_progress_func=_rprog
                    )
                    sidecar.write(pickle.dumps(metadata))
                except Exception as ex:
                    print(f"error: failed to generate metadata for {f}: {ex}")
                    traceback.print_exc()
                    continue
                finally:
                    self._post_ui(partial(self._emit_file_metadata, f, metadata))
                    c = total - fq.qsize()
                    self._post_ui(partial(self._set_progress, c / total))

            self._post_ui(partial(self._emit_busy, False))
            self._post_ui(self._close_status)
            """ a lot of buffers, objects, etc. are created here so invoking a garbage collection afterward seems
                to keep memory usage from ballooning"""
            gc.collect()

        threading.Thread(target=_thread, daemon=True).start()

    def goto_path(self, path: Path) -> None:
        """open path in system file explorer"""
        if not path.exists():
            return
        path = path.resolve()

        match platform.system():
            case "Windows":
                os.startfile(path)
            case "Darwin":
                subprocess.Popen(["open", path])
            case _:  # linux
                try:
                    subprocess.Popen(["xdg-open", path])
                except FileNotFoundError as ex:
                    print(f"error: failed to open {path}: {ex}")

    def play_file(self, path: Path, start_ms: int = 0) -> None:
        """play video file"""
        if not path.is_file():
            return
        path = path.resolve()

        if self._config.vid_player is not None and self._config.vid_player.exists():
            argv = [self._config.vid_player.name, f'"{path}"']
            if len(self._config.vid_player_args) > 0:
                argv.extend(
                    s.replace("%t_ms", str(start_ms)).replace("%t_sec", str(start_ms / 1000))
                    for s in self._config.vid_player_args
                )
            os.spawnv(os.P_NOWAIT, self._config.vid_player, argv)
        else:
            match platform.system():
                case "Windows":
                    os.startfile(path)
                case "Darwin":
                    subprocess.call(("open", path))
                case _:  # linux
                    subprocess.call(("xdg-open", path))

    def load_metadata(self, p: Path) -> None:
        if p.is_file():
            self._selected_path = p
            sidecar = MagicSidecar(p, namespace=self._config.metadata_key)
            print(f"loading metadata for {p}")
            self._state.file_path.set(str(p))
            self._state.file_size.set(f"size: {nice_bytesize(p.stat().st_size, largest_unit='M')}")
            self._state.meta_size.set("metadata size: none")
            self._metadata = deepcopy(_EMPTY_METADATA)

            try:
                buf = sidecar.read()
                self._metadata = pickle.loads(buf)
                self._state.meta_size.set(f"metadata size: {nice_bytesize(len(buf))}")
            except FileNotFoundError:
                self._metadata = deepcopy(_EMPTY_METADATA)
                print(f"{p} does not have a magic sidecar")
            except pickle.UnpicklingError:
                print(f"{p} does not have valid pickle data, using default")
            except Exception as ex:
                print(f"{p} failed to load metadata: {ex}")
            finally:
                self.update_widgets_from_metadata()

            self._state.selection_changed.emit((p,))

    def clear_vidinfo(self) -> None:
        self._state.file_path.set("")
        self._state.file_size.set("size: none")
        self._state.meta_size.set("metadata size: none")
        self._metadata = deepcopy(_EMPTY_METADATA)
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

    def _iter_files(self, pt: PathTree | None = None) -> Iterator[Path]:
        pt = pt if pt is not None else self._pathtree
        for _, child in pt.dirs():
            yield from self._iter_files(child)
        yield from pt.files()

    def update_filetree(self) -> None:
        self._pathtree.scan(filters=[path_extension_filter(self._config.vid_exts)])
        self._state.file_tree_changed.emit(FileTreeUpdate(self._pathtree, ""))

    def status_window(self, active: bool) -> None:
        STATUS_SPACING: Final[int] = 80
        if active:
            width: int = round(self._widgets.root.winfo_width() - 80)
            xoffset: int = round(self._widgets.root.winfo_x() + STATUS_SPACING / 2)
            yoffset: int = round(
                self._widgets.root.winfo_y()
                + self._widgets.root.winfo_height() / 2
                - self._widgets.status.winfo_height() / 2
            )
            self._widgets.status.update_idletasks()
            height = self._widgets.status.winfo_reqheight()
            self._widgets.status.geometry(f"{width}x{height}+{xoffset}+{yoffset}")
            self._widgets.status.deiconify()
            self._widgets.status.lift(self._widgets.mainframe)
        else:
            self._widgets.status.withdraw()
