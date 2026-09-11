import gc
import os
import pickle
import platform
import subprocess
import threading
import time
import tkinter as tk
import traceback
from copy import deepcopy
from functools import partial
from pathlib import Path
from queue import Queue
from tkinter import StringVar, ttk
from typing import Any, Final, NamedTuple, cast

from ui.constants import TkCursor
from ui.constants import VirtualEventSequence as VEvent
from util.file.sidecar import MagicSidecar
from util.file.tree import PathTree, path_extension_filter
from util.format import nice_bytesize, nice_duration
from util.video import ProgressFunc, VideoThumbnailer

from .config import Config
from .ui import MainFrame, StatusWindow
from .ui.constants import TkVarNames
from .ui.constants import VirtualEventSequence as BVEvent


class App:
    _EMPTY_METADATA: Final[dict[str, Any]] = {
        "title": "",
        "video_properties": {"dimensions": (0, 0), "duration": 0},
        "actors": [],
        "tags": [],
        "thumbnails": [],
    }

    _config: Config
    _pathtree: PathTree
    _trash_path: Path
    _metadata: dict[str, Any]
    _file_meta_filters: dict
    _all_tags: list[str]
    _all_actors: list[str]
    _selected_path: Path

    class _Widgets(NamedTuple):
        root: tk.Tk
        mainframe: MainFrame
        status: StatusWindow

    class _Vars(NamedTuple):
        file_path: tk.StringVar
        file_size: tk.StringVar
        meta_actors: tk.Variable
        meta_tags: tk.Variable
        meta_title: StringVar
        meta_size: StringVar
        thumb_interval: StringVar
        thumb_height: StringVar
        video_len: StringVar
        video_res: StringVar

    def __init__(self, root: tk.Tk, basepath: Path, config: Config):
        self._config = config
        self._pathtree = PathTree(basepath)
        self._metadata = deepcopy(__class__._EMPTY_METADATA)
        self._file_meta_filters = {}
        self._all_tags = []
        self._all_actors = []
        self._selected_path = Path()

        self._vars = __class__._Vars(
            file_path=tk.StringVar(root, name=TkVarNames.FILE_PATH),
            file_size=tk.StringVar(root, name=TkVarNames.FILE_SIZE),
            meta_actors=tk.Variable(root, name=TkVarNames.META_ACTORS),
            meta_tags=tk.Variable(root, name=TkVarNames.META_TAGS),
            meta_title=tk.StringVar(root, name=TkVarNames.META_TITLE),
            meta_size=tk.StringVar(root, name=TkVarNames.META_SIZE),
            thumb_interval=tk.StringVar(root, name=TkVarNames.THUMB_INTERVAL, value=str(self._config.thumb_interval)),
            thumb_height=tk.StringVar(root, name=TkVarNames.THUMB_HEIGHT, value=str(self._config.thumb_height)),
            video_len=tk.StringVar(root, name=TkVarNames.VIDEO_LEN),
            video_res=tk.StringVar(root, name=TkVarNames.VIDEO_RES),
        )

        self._widgets = __class__._Widgets(root=root, mainframe=MainFrame(root), status=StatusWindow(root))
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)

        self._widgets.root.bind_all(VEvent.DIR_SELECT, func=self._handle_dir_selected, add=True)
        self._widgets.root.bind_all(VEvent.FILE_SELECT, func=self._handle_file_selected, add=True)
        self._widgets.root.bind_all(VEvent.FILE_EXEC, func=self._handle_file_exec, add=True)
        self._widgets.root.bind_all(BVEvent.GEN_THUMBS, func=self._handle_gen_thumbs, add=True)
        self._widgets.root.bind_all(BVEvent.SAVE_METADATA, func=self._handle_save_metadata, add=True)
        self._widgets.root.bind_all(BVEvent.SCAN_METADATA, func=self._handle_scan_metadata, add=True)
        # bind_all_with_data is a Monkey patch but only on widgets, not root
        self._widgets.mainframe.bind_all_with_data(
            BVEvent.GEN_MISSING_THUMBS, func=partial(self._handle_gen_thumbs_bulk, force=False, depth=0)
        )
        self._widgets.mainframe.bind_all_with_data(
            BVEvent.GEN_MISSING_THUMBS_RECURSIVE, func=partial(self._handle_gen_thumbs_bulk, force=False, depth=16)
        )
        self._widgets.mainframe.bind_all_with_data(
            BVEvent.GEN_ALL_THUMBS, func=partial(self._handle_gen_thumbs_bulk, force=True, depth=0)
        )
        self._widgets.mainframe.bind_all_with_data(
            BVEvent.GEN_ALL_THUMBS_RECURSIVE, func=partial(self._handle_gen_thumbs_bulk, force=True, depth=16)
        )
        self._widgets.mainframe.bind_all_with_data(BVEvent.PLAY_FROM_MS, func=self._handle_play_from_ms, add=True)
        self._widgets.mainframe.bind_all_with_data(BVEvent.PATH_DELETE, func=self._handle_path_delete, add=True)
        self._widgets.mainframe.bind_all_with_data(BVEvent.SCAN_PATH_FILES, func=self._handle_scan_path_files, add=True)
        self._widgets.mainframe.bind_all_with_data(
            BVEvent.SCAN_PATH_METADATA, func=self._handle_scan_path_metadata, add=True
        )

        self._widgets.status.transient(self._widgets.mainframe)  # type: ignore
        self._init_trash(config.trash_dir)
        self.update_filetree()
        self._widgets.mainframe._widgets.filetree.fill_from_pathtree(self._pathtree)
        self.status_window(False)

    def _init_trash(self, path: Path) -> None:
        if not path.exists():
            path.mkdir()

        if path.is_dir():
            self._trash_path = path
        else:
            # shouldn't happen, config does a trash path check
            print("error:trash directory is not a directory, could not initialize")

    def _handle_dir_selected(self, ev: tk.Event) -> None:
        self._vars.file_path.set("")
        self._vars.file_size.set("size: none")
        self._vars.meta_size.set("metadata size: none")
        self._metadata = deepcopy(self._EMPTY_METADATA)
        self._selected_path = Path("")
        self.update_widgets_from_metadata()

    def _handle_file_selected(self, ev: tk.Event) -> None:
        tv = cast(ttk.Treeview, ev.widget)
        """ sometimes there's no selection ie. if the selection is deleted by click menu"""
        if hasattr(ev.widget, "selection") and len(tv.selection()):
            p = Path(tv.selection()[0])
            if p.is_file():
                self._selected_path = p
                sidecar = MagicSidecar(p, namespace=self._config.metadata_key)
                print(f"loading metadata for {p}")
                self._vars.file_path.set(str(p))
                self._vars.file_size.set(f"size: {nice_bytesize(p.stat().st_size, largest_unit='M')}")
                self._vars.meta_size.set("metadata size: none")
                self._metadata = deepcopy(__class__._EMPTY_METADATA)

                try:
                    buf = sidecar.read()
                    self._metadata = pickle.loads(buf)
                    self._vars.meta_size.set(f"metadata size: {nice_bytesize(len(buf))}")
                except FileNotFoundError:
                    self._metadata = deepcopy(self._EMPTY_METADATA)
                    print(f"{p} does not have a magic sidecar")
                except pickle.UnpicklingError:
                    print(f"{p} does not have valid pickle data, using default")
                except Exception as ex:
                    print(f"{p} failed to load metadata: {ex}")
                finally:
                    self.update_widgets_from_metadata()

    def _handle_file_exec(self, ev: tk.Event) -> None:
        self.play_file(self._selected_path)

    def _handle_path_delete(self, ev: tk.Event, data: str) -> None:
        """data is the treeview iid which is the file path"""
        if self._trash_path is None:
            return

        path = Path(data)
        self._pathtree.dig_and_remove(path)
        path.move(self._trash_path / path.name)

    def _handle_play_from_ms(self, ev: tk.Event, data: str) -> None:
        self.play_file(self._selected_path, start_ms=int(data))

    def _handle_scan_path_files(self, ev: tk.Event, data: str) -> None:
        pt = self._pathtree.dig(Path(data))
        if pt is not None:
            pt.clear()
            pt.scan(filters=[path_extension_filter(self._config.vid_exts)])
            self._widgets.mainframe._widgets.filetree.fill_from_pathtree(pt, data)

    def _handle_scan_path_metadata(self, ev: tk.Event, data: str) -> None:
        pt = self._pathtree.dig(Path(data))
        if pt is None:
            return

        def _recurse(pt: PathTree) -> None:
            for d, child in pt.dirs():
                _recurse(child)

            for f in pt.files():
                try:
                    metadata = pickle.loads(MagicSidecar(f, namespace=self._config.metadata_key).read())
                except FileNotFoundError:
                    pass
                except Exception as ex:
                    print(f"error: failed to load metadata for {f}: {ex}")
                else:
                    self._widgets.mainframe._widgets.filetree.set_meta_column_vals(
                        str(f),
                        metadata["video_properties"]["duration"],
                        metadata["video_properties"]["dimensions"],
                        metadata["actors"],
                        metadata["tags"],
                    )

        threading.Thread(target=lambda: _recurse(pt), daemon=True).start()

    def _handle_gen_thumbs_bulk(
        self, ev: tk.Event, data: str, force: bool = False, depth: int = 0, *args, **kwargs
    ) -> None:
        pt = self._pathtree.dig(Path(data))
        if pt is None:
            return

        fq = Queue()
        self.status_window(True)
        self._widgets.mainframe.busy_hold(cursor=TkCursor.WATCH)

        def _recurse(pt: PathTree, depth: int) -> None:
            if depth > 0:
                for d, child in pt.dirs():
                    _recurse(child, depth - 1)

            for f in pt.files():
                fq.put(f)

        def _thread() -> None:
            def _xprog(f: float) -> None:
                self._widgets.status.progress = c / total + (1 / total * (0.5 * f))

            def _rprog(f: float) -> None:
                self._widgets.status.progress = c / total + (1 / total * (0.5 * f + 0.5))

            total = fq.qsize()
            c = 0

            while not fq.empty():
                f = fq.get()
                try:
                    sidecar = MagicSidecar(f, namespace=self._config.metadata_key)
                    if sidecar.exists and force is False:
                        continue
                    self._widgets.status.info = f"[{c} / {total}] {f}"
                    metadata = self._generate_metadata(f, extract_progress_func=_xprog, resize_progress_func=_rprog)
                    sidecar.write(pickle.dumps(metadata))
                    self._widgets.mainframe._widgets.filetree.set_meta_column_vals(
                        str(f),
                        metadata["video_properties"]["duration"],
                        metadata["video_properties"]["dimensions"],
                        metadata["actors"],
                        metadata["tags"],
                    )
                    c = total - fq.qsize()
                    self._widgets.status.progress = c / total
                except Exception as ex:
                    print(f"error: failed to generate metadata for {f}: {ex}")
                    traceback.print_exc()
                    continue

            self._widgets.mainframe.busy_forget()
            self.status_window(False)

        _recurse(pt, depth=depth)
        threading.Thread(target=_thread, daemon=True).start()

    def _handle_gen_thumbs(self, ev: tk.Event) -> None:
        if self._selected_path is None or not self._selected_path.is_file():
            self._widgets.mainframe.event_generate(BVEvent.GEN_THUMBS_COMPLETE)
            return

        # probably not thread-safe
        def _thread_entry():
            def _progress(p: float, prefix: str) -> None:
                self._widgets.status.progress = p
                self._widgets.status.info = f"{prefix} {p * 100:.1f}%"

            try:
                metadata = self._generate_metadata(
                    self._selected_path,
                    extract_progress_func=partial(_progress, prefix="Extracting frames..."),
                    resize_progress_func=partial(_progress, prefix="Resizing frames..."),
                )
            except Exception as ex:
                print(f"error: failed to generate metadata for {self._selected_path}: {ex}")
                traceback.print_exc()
            else:
                self._metadata = metadata

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

    def _handle_save_metadata(self, ev: tk.Event) -> None:
        print(f"saving metadata for {self._selected_path}")

        # thumbnails are updated on generation
        self._metadata["title"] = self._vars.meta_title.get()
        self._metadata["actors"] = self._widgets.root.tk.splitlist(self._vars.meta_actors.get())
        self._metadata["tags"] = self._widgets.root.tk.splitlist(self._vars.meta_tags.get())
        self.update_widgets_from_metadata()
        try:
            buf = pickle.dumps(self._metadata)
            sidecar = MagicSidecar(self._selected_path, namespace=self._config.metadata_key)
            sidecar.write(buf)
            self._vars.meta_size.set(f"metadata size: {round(len(buf) / 1000)}KB")
        except pickle.PickleError:
            print(f"failed to pickle metadata for {self._selected_path}")
        except Exception as ex:
            print(f"failed to save metadata for {self._selected_path}: {ex}")

    def _handle_scan_metadata(self, ev: tk.Event) -> None:
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
                        self._widgets.mainframe._widgets.filetree.set_meta_column_vals(
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

    def _generate_metadata(
        self,
        path: Path,
        extract_progress_func: ProgressFunc = lambda f: None,
        resize_progress_func: ProgressFunc = lambda f: None,
    ) -> dict[str, Any]:
        metadata = deepcopy(__class__._EMPTY_METADATA)
        vt = VideoThumbnailer(path)
        metadata["video_properties"] = {}
        metadata["video_properties"]["dimensions"] = vt.dimensions
        metadata["video_properties"]["duration"] = round(vt.duration, 2) if vt.duration is not None else 0
        vt.extract_frames(interval=float(self._vars.thumb_interval.get()), progress_func=extract_progress_func)
        vt.resize_frames(resize_height=int(self._vars.thumb_height.get()), progress_func=resize_progress_func)
        jpgs = vt.gen_jpgs()
        if jpgs is not None:
            metadata["thumbnails"] = jpgs

        return metadata

    def play_file(self, path: Path, start_ms: int = 0):
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

    def update_widgets_from_metadata(self) -> None:
        # todo don't reach down through widgets
        self._widgets.mainframe._widgets.filetree.set_meta_column_vals(
            str(self._selected_path),
            self._metadata["video_properties"]["duration"],
            self._metadata["video_properties"]["dimensions"],
            self._metadata["actors"],
            self._metadata["tags"],
        )

        vres = self._metadata["video_properties"]["dimensions"]
        vlen = nice_duration(self._metadata["video_properties"]["duration"])
        self._vars.meta_title.set(self._metadata["title"])
        self._vars.meta_actors.set(self._metadata["actors"])
        self._vars.meta_tags.set(self._metadata["tags"])
        self._vars.video_len.set(f"length: {vlen}")
        self._vars.video_res.set(f"resolution: {vres[0]}x{vres[1]}")
        self._widgets.mainframe.update_thumbs(self._metadata["thumbnails"])

    def update_filetree(self) -> None:
        self._pathtree.scan(filters=[path_extension_filter(self._config.vid_exts)])

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
