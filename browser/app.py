import gc
import os
import pickle
import platform
import subprocess
import threading
import time
import tkinter as tk
import traceback
from collections.abc import Sequence
from copy import deepcopy
from functools import partial
from pathlib import Path
from queue import Queue
from tkinter import ttk
from typing import Any, Final, NamedTuple, cast

from ui.constants import TkCursor
from ui.constants import VirtualEventSequence as VEvent
from util.file.sidecar import MagicSidecar
from util.file.tree import PathTree, path_extension_filter
from util.format import nice_bytesize, nice_duration
from util.video import ProgressFunc, VideoThumbnailer

from .config import Config
from .ui import InputWindow, MainFrame, StatusWindow
from .ui.actions import AppActions, BulkAction, UiContext
from .ui.constants import TkVarNames
from .ui.constants import VirtualEventSequence as BVEvent
from .ui.state import UiState

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
    _file_meta_filters: dict
    _all_tags: list[str]
    _all_actors: list[str]
    _selected_path: Path  # for vid info tab
    _state: UiState

    class __Widgets(NamedTuple):
        root: tk.Tk
        mainframe: MainFrame
        status: StatusWindow
        input: InputWindow

    class __Vars(NamedTuple):
        triggered_iid: tk.StringVar
        context_iid: tk.StringVar
        selected_iids: tk.Variable
        thumb_interval: tk.StringVar
        thumb_height: tk.StringVar

    def __init__(self, root: tk.Tk, basepath: Path, config: Config):
        self._config = config
        self._pathtree = PathTree(basepath)
        self._metadata = deepcopy(_EMPTY_METADATA)
        self._file_meta_filters = {}
        self._all_tags = []
        self._all_actors = []
        self._selected_path = Path()

        self._state = UiState(root, thumb_interval=config.thumb_interval, thumb_height=config.thumb_height)

        self._vars = __class__.__Vars(
            triggered_iid=tk.StringVar(root, name=TkVarNames.TRIGGERED_IID),
            context_iid=tk.StringVar(root, name=TkVarNames.CONTEXT_IID),
            selected_iids=tk.Variable(root, name=TkVarNames.SELECTED_IIDS),
            thumb_interval=tk.StringVar(root, name=TkVarNames.THUMB_INTERVAL, value=str(self._config.thumb_interval)),
            thumb_height=tk.StringVar(root, name=TkVarNames.THUMB_HEIGHT, value=str(self._config.thumb_height)),
        )

        actions: AppActions = self  # App structurally implements AppActions without inheriting from it
        self._widgets = __class__.__Widgets(
            root=root,
            mainframe=MainFrame(root, UiContext(state=self._state, actions=actions)),
            status=StatusWindow(root),
            input=InputWindow(root),
        )
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)

        self._widgets.root.bind_all(VEvent.DIR_SELECT, func=self._handle_dir_selected, add=True)
        self._widgets.root.bind_all(VEvent.FILE_SELECT, func=self._handle_file_selected, add=True)
        self._widgets.root.bind_all(VEvent.FILE_DESELECT, func=self._handle_file_deselected, add=True)
        self._widgets.root.bind_all(VEvent.FILE_EXEC, func=self._handle_file_exec, add=True)
        self._widgets.root.bind_all(BVEvent.GOTO_PATH, func=self._handle_goto_path, add=True)
        self._widgets.root.bind_all(BVEvent.GEN_THUMBS, func=self._handle_gen_thumbs, add=True)
        self._widgets.root.bind_all(BVEvent.SAVE_METADATA, func=self._handle_save_metadata, add=True)
        self._widgets.root.bind_all(BVEvent.SCAN_METADATA, func=self._handle_scan_metadata, add=True)
        self._widgets.root.bind_all(
            BVEvent.BULK_ADD_ACTOR, func=partial(self._handle_bulk_edit_meta, action=BulkAction.ADD_ACTOR), add=True
        )
        self._widgets.root.bind_all(
            BVEvent.BULK_DEL_ACTOR, func=partial(self._handle_bulk_edit_meta, action=BulkAction.DEL_ACTOR), add=True
        )
        self._widgets.root.bind_all(
            BVEvent.BULK_ADD_TAG, func=partial(self._handle_bulk_edit_meta, action=BulkAction.ADD_TAG), add=True
        )
        self._widgets.root.bind_all(
            BVEvent.BULK_DEL_TAG, func=partial(self._handle_bulk_edit_meta, action=BulkAction.DEL_TAG), add=True
        )
        self._widgets.root.bind_all(BVEvent.BULK_GEN_THUMBS, func=self._handle_bulk_thumbs, add=True)
        self._widgets.root.bind_all(BVEvent.BULK_DEL_METADATA, func=self._handle_bulk_del_meta, add=True)
        self._widgets.root.bind_all(BVEvent.PATH_DELETE, func=self._handle_path_delete, add=True)
        self._widgets.root.bind_all(BVEvent.SCAN_PATH_FILES, func=self._handle_scan_path_files, add=True)
        self._widgets.root.bind_all(BVEvent.SCAN_PATH_METADATA, func=self._handle_scan_path_metadata, add=True)

        self._widgets.status.transient(self._widgets.mainframe)  # type: ignore
        self._widgets.input.transient(self._widgets.mainframe)  # type: ignore
        self.input_window(False)
        self.status_window(False)

        self._init_trash(config.trash_dir)
        self.update_filetree()
        self._widgets.mainframe._widgets.filetree.fill_from_pathtree(self._pathtree)

    def _init_trash(self, path: Path) -> None:
        if not path.exists():
            path.mkdir()

        if path.is_dir():
            self._trash_path = path
        else:
            # shouldn't happen, config does a trash path check
            print("error:trash directory is not a directory, could not initialize")

    def select_paths(self, paths: Sequence[Path]) -> None:
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
            self._widgets.mainframe.remove_filetree_items(removed)

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
            self._widgets.mainframe._widgets.filetree.fill_from_pathtree(pt, str(path))

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
                self._widgets.status.info = f"[{c} / {total}] {f.name}"
                self._widgets.status.progress = c / total
                try:
                    metadata = pickle.loads(MagicSidecar(f, namespace=self._config.metadata_key).read())
                except FileNotFoundError:
                    pass
                except Exception as ex:
                    print(f"error: failed to load metadata for {f}: {ex}")
                    traceback.print_exc()
                else:
                    self._widgets.mainframe._widgets.filetree.update_item_cols(
                        str(f),
                        metadata["video_properties"]["duration"],
                        metadata["video_properties"]["dimensions"],
                        metadata["actors"],
                        metadata["tags"],
                    )
            self.status_window(False)

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
                self._widgets.mainframe._widgets.filetree.update_item_cols(str(f), 0, (0, 0), [], [])

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

        val = self._widgets.input.block_for_input(parent=self._widgets.mainframe)
        if val is None:
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
                self._widgets.mainframe._widgets.filetree.update_item_cols(
                    str(f),
                    metadata["video_properties"]["duration"],
                    metadata["video_properties"]["dimensions"],
                    metadata["actors"],
                    metadata["tags"],
                )

    def generate_thumbnails(self) -> None:
        if self._selected_path is None or not self._selected_path.is_file():
            self._widgets.mainframe.event_generate(BVEvent.GEN_THUMBS_COMPLETE)
            return

        # probably not thread-safe
        def _thread_entry():
            def _progress(p: float, prefix: str) -> None:
                self._widgets.status.progress = p
                self._widgets.status.info = f"{prefix} {p * 100:.1f}%"

            try:
                metadata = self._generate_video_metadata(
                    self._selected_path,
                    extract_progress_func=partial(_progress, prefix="Extracting frames..."),
                    resize_progress_func=partial(_progress, prefix="Resizing frames..."),
                )
            except Exception as ex:
                print(f"error: failed to generate metadata for {self._selected_path}: {ex}")
                traceback.print_exc()
            else:
                self._metadata |= metadata

            self._widgets.mainframe.event_generate(
                BVEvent.GEN_THUMBS_COMPLETE
            )  # widgets listen to this to remove their busy
            self.update_widgets_from_metadata()
            self.status_window(False)

            """ a lot of buffers, objects, etc. are created here so invoking a garbage collection afterward seems
                to keep memory usage from ballooning"""
            gc.collect()

        self.status_window(True)
        threading.Thread(target=_thread_entry, daemon=True).start()

    def _handle_gen_thumbs(self, ev: tk.Event) -> None:
        self.generate_thumbnails()

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

    def _handle_save_metadata(self, ev: tk.Event) -> None:
        self.save_metadata()

    def scan_metadata(self) -> None:
        self.status_window(True)
        self._widgets.mainframe.busy_hold(cursor=TkCursor.WATCH)
        self._widgets.mainframe._widgets.filetree.unhide_all()

        def _thread_entry():
            def _incr(totals: dict[str, int], keys: list[str]):
                for k in keys:
                    k = k.lower()
                    if k not in totals:
                        totals[k] = 1
                    else:
                        totals[k] += 1

            actors: dict[str, int] = {}
            tags: dict[str, int] = {}
            items: list = self._widgets.mainframe._widgets.filetree.get_items(with_tags=["file"])

            item_count: int = len(items)
            update_interval: float = 0.05
            last_time: float = time.time()
            for c, item in enumerate(items):
                if time.time() > last_time + update_interval:
                    self._widgets.status.progress = (c + 1) / item_count
                    self._widgets.status.info = f"[{c}/{item_count}] {item}"
                    last_time = time.time()

                path = self._pathtree.root / item
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
                        self._widgets.mainframe._widgets.filetree.update_item_cols(
                            item,
                            metadata["video_properties"]["duration"],
                            metadata["video_properties"]["dimensions"],
                            metadata["actors"],
                            metadata["tags"],
                        )
                        _incr(actors, metadata["actors"])
                        _incr(tags, metadata["tags"])

            self._widgets.status.progress = 1.0
            self._widgets.status.info = "populating widgets"
            self._widgets.mainframe.set_actors(actors)
            self._widgets.mainframe.set_tags(tags)
            self._widgets.mainframe.busy_forget()
            self.status_window(False)

        threading.Thread(target=_thread_entry, daemon=True).start()

    def _handle_scan_metadata(self, ev: tk.Event) -> None:
        self.scan_metadata()

    def apply_filters(self, actors: Sequence[str], tags: Sequence[str], operator: str = "OR") -> None:
        """Temporary deep access; removed in task 08 when FilterFrame owns filter state."""
        self._widgets.mainframe._widgets.filetree.apply_filters(list(actors), list(tags), operator=operator)

    def clear_filters(self) -> None:
        """Temporary deep access; removed in task 08 when FilterFrame owns filter state."""
        self._widgets.mainframe._widgets.filetree.unhide_all()

    def _handle_dir_selected(self, ev: tk.Event) -> None:
        self.clear_vidinfo()

    def _handle_file_selected(self, ev: tk.Event) -> None:
        tv = cast(ttk.Treeview, ev.widget)
        if not hasattr(ev.widget, "selection"):
            return

        iid = self._vars.triggered_iid.get()
        if iid not in tv.selection():  # sanity check: shouldn't happen
            iid = tv.selection()[0]

        self.select_paths((Path(iid),))

    def _handle_file_deselected(self, ev: tk.Event) -> None:
        tv = cast(ttk.Treeview, ev.widget)
        if not hasattr(ev.widget, "selection"):
            return

        self.select_paths(tuple(Path(p) for p in tv.selection()))

    def _handle_goto_path(self, ev: tk.Event) -> None:
        self.show_in_explorer(Path(self._vars.context_iid.get()))

    def _handle_file_exec(self, ev: tk.Event) -> None:
        tv = cast(ttk.Treeview, ev.widget)
        if not hasattr(ev.widget, "selection"):
            return

        iid = self._vars.triggered_iid.get()
        if iid not in tv.selection():
            iid = tv.selection()[0]

        self.activate_path(Path(iid))

    def _handle_path_delete(self, ev: tk.Event) -> None:
        """data is the treeview iid which is the file path"""
        paths = tuple(
            Path(p) for p in self._widgets.root.tk.splitlist(self._vars.selected_iids.get()) if Path(p).exists()
        )
        self.delete_paths(paths)

    def _handle_scan_path_files(self, ev: tk.Event) -> None:
        self.rescan_path(Path(self._vars.context_iid.get()))

    def _handle_scan_path_metadata(self, ev: tk.Event) -> None:
        self.scan_path_metadata(Path(self._vars.context_iid.get()))

    def _handle_bulk_del_meta(self, ev: tk.Event) -> None:
        paths = tuple(Path(p) for p in self._widgets.root.tk.splitlist(self._vars.selected_iids.get()))
        self.delete_metadata(paths)

    def _handle_bulk_thumbs(self, ev: tk.Event) -> None:
        paths = tuple(Path(p) for p in self._widgets.root.tk.splitlist(self._vars.selected_iids.get()))
        self.generate_thumbnails_bulk(paths)

    def _handle_bulk_edit_meta(self, ev: tk.Event, action: BulkAction) -> None:
        paths = tuple(Path(p) for p in self._widgets.root.tk.splitlist(self._vars.selected_iids.get()))
        self.edit_metadata(action, paths)

    def _generate_video_metadata(
        self,
        path: Path,
        extract_progress_func: ProgressFunc = lambda f: None,
        resize_progress_func: ProgressFunc = lambda f: None,
    ) -> dict[str, Any]:
        m = {}
        vt = VideoThumbnailer(path)
        m["video_properties"] = {}
        m["video_properties"]["dimensions"] = vt.dimensions
        m["video_properties"]["duration"] = round(vt.duration, 2) if vt.duration is not None else 0
        vt.extract_frames(interval=float(self._vars.thumb_interval.get()), progress_func=extract_progress_func)
        vt.resize_frames(resize_height=int(self._vars.thumb_height.get()), progress_func=resize_progress_func)
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
        self._widgets.mainframe.busy_hold(cursor=TkCursor.WATCH)

        def _thread() -> None:
            def _xprog(f: float) -> None:
                self._widgets.status.progress = c / total + (1 / total * (0.5 * f))

            def _rprog(f: float) -> None:
                self._widgets.status.progress = c / total + (1 / total * (0.5 * f + 0.5))

            total = fq.qsize()
            c = 0

            while not fq.empty():
                f = fq.get()
                sidecar = MagicSidecar(f, namespace=self._config.metadata_key)
                metadata = deepcopy(_EMPTY_METADATA)
                try:
                    metadata = pickle.loads(sidecar.read())
                except Exception as ex:
                    print(f"error: loading sidecar metadata for {f}: {ex}")
                    traceback.print_exc()

                self._widgets.status.info = f"[{c + 1} / {total}] {f}"
                try:
                    metadata |= self._generate_video_metadata(
                        f, extract_progress_func=_xprog, resize_progress_func=_rprog
                    )
                    sidecar.write(pickle.dumps(metadata))
                except Exception as ex:
                    print(f"error: failed to generate metadata for {f}: {ex}")
                    traceback.print_exc()
                    continue
                finally:
                    self._widgets.mainframe._widgets.filetree.update_item_cols(
                        str(f),
                        metadata["video_properties"]["duration"],
                        metadata["video_properties"]["dimensions"],
                        metadata["actors"],
                        metadata["tags"],
                    )
                    c = total - fq.qsize()
                    self._widgets.status.progress = c / total

            self._widgets.mainframe.busy_forget()
            self.status_window(False)
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
        # todo don't reach down through widgets
        self._widgets.mainframe._widgets.filetree.update_item_cols(
            str(self._selected_path),
            self._metadata["video_properties"]["duration"],
            self._metadata["video_properties"]["dimensions"],
            self._metadata["actors"],
            self._metadata["tags"],
        )

        vres = self._metadata["video_properties"]["dimensions"]
        vlen = nice_duration(self._metadata["video_properties"]["duration"])
        self._state.meta_title.set(self._metadata["title"])
        self._state.meta_actors.set(self._metadata["actors"])
        self._state.meta_tags.set(self._metadata["tags"])
        self._state.video_len.set(f"length: {vlen}")
        self._state.video_res.set(f"resolution: {vres[0]}x{vres[1]}")
        self._widgets.mainframe.update_thumbs(self._metadata["thumbnails"])

    def update_filetree(self) -> None:
        self._pathtree.scan(filters=[path_extension_filter(self._config.vid_exts)])

    def update_selected_files_metadata(self, action: str, value: str) -> None:
        pass

    def input_window(self, active: bool, title: str = "", label: str = "") -> None:
        if active:
            self._widgets.input.title_text = title
            self._widgets.input.label_text = label
            self._widgets.input.update_idletasks()
            self._widgets.input.block_for_input(parent=self._widgets.mainframe)
        else:
            self._widgets.input.withdraw()

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
