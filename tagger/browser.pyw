import gc
import os
import pickle
import sys
import threading
import time
import tkinter as tk
from copy import deepcopy
from functools import partial
from pathlib import Path
from tkinter import StringVar, ttk
from typing import Any, Final, NamedTuple, cast

# from meta_editor import ThumbGen, VideoProperties
from browser.ui import MainFrame
from browser.ui.constants import TkVarNames
from browser.ui.constants import VirtualEventSequence as BVEvent
from util.file.sidecar import MagicSidecar
from util.file.tree import PathTree, path_extension_filter
from util.format import nice_bytesize, nice_duration
from util.ui.constants import TkCursor
from util.ui.constants import VirtualEventSequence as VEvent
from util.ui.message_system import MessageWindow
from util.video_thumbnailer import VideoThumbnailer

VID_EXTS: Final[tuple[str, ...]] = (
    ".avi",
    ".mp4",
    ".m4v",
    ".mkv",
    ".mpg",
    ".mpeg",
    ".wmv",
    ".flv",
    ".f4v",
    ".mov",
)


class StatusWindow(tk.Toplevel):
    class _Widgets(NamedTuple):
        frame: ttk.Frame
        progress: ttk.Progressbar
        status: ttk.Label

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self.overrideredirect(True)  # no titlebar, borders
        self.resizable(False, False)
        self.title("Status")
        self.group(parent)

        self.status_text = StringVar()
        frame = ttk.Frame(self)
        self._widgets = __class__._Widgets(
            frame=frame,
            progress=ttk.Progressbar(frame, maximum=1.0),
            status=ttk.Label(frame, textvariable=self.status_text),
        )
        self._widgets.progress.grid(column=0, row=0, padx=2, pady=2, sticky="ew")
        self._widgets.status.grid(column=0, row=1, padx=2, pady=2)
        self._widgets.frame.columnconfigure(0, weight=1)
        self._widgets.frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    @property
    def info(self) -> str:
        return self.status_text.get()

    @info.setter
    def info(self, val: str):
        return self.status_text.set(val)

    @property
    def progress(self) -> float:
        """Returns progress value [0,1]"""
        return self._widgets.progress["value"]

    @progress.setter
    def progress(self, val: float):
        """Set progress value [0,1]"""
        self._widgets.progress.config(value=val)


class App:
    VIDEO_PLAYER: Final[str] = "C:\\Program Files\\MPC-BE\\mpc-be64.exe"
    METADATA_STREAM: Final[str] = "video_metadata"
    TRASH_NAME: Final[str] = ".trash"
    _EMPTY_METADATA: Final[dict[str, Any]] = {
        "title": "",
        "video_properties": {"dimensions": (0, 0), "duration": 0},
        "actors": [],
        "tags": [],
        "thumbnails": [],
    }

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

    def __init__(self, root: tk.Tk, basepath: Path):
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
            thumb_interval=tk.StringVar(root, name=TkVarNames.THUMB_INTERVAL, value="-30"),
            thumb_height=tk.StringVar(root, name=TkVarNames.THUMB_HEIGHT, value="200"),
            video_len=tk.StringVar(root, name=TkVarNames.VIDEO_LEN),
            video_res=tk.StringVar(root, name=TkVarNames.VIDEO_RES),
        )

        self._widgets = __class__._Widgets(root=root, mainframe=MainFrame(root), status=StatusWindow(root))
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)
        # self._widgets.mainframe.basepath = basepath

        self._widgets.root.bind_all(VEvent.FILE_SELECT, func=self._handle_file_selected, add=True)
        self._widgets.root.bind_all(VEvent.FILE_EXEC, func=self._handle_file_exec, add=True)
        self._widgets.root.bind_all(BVEvent.GENERATE_THUMBS, func=self._handle_generate_thumbnails, add=True)
        self._widgets.root.bind_all(BVEvent.SAVE_METADATA, func=self._handle_save_metadata, add=True)
        self._widgets.root.bind_all(BVEvent.SCAN_METADATA, func=self._handle_scan_metadata, add=True)
        # bind_all_with_data is a Monkey patch but only on widgets, not root
        self._widgets.mainframe.bind_all_with_data(BVEvent.PLAY_FROM_MS, func=self._handle_play_from_ms, add=True)
        self._widgets.mainframe.bind_all_with_data(BVEvent.FILE_DELETE, func=self._handle_file_delete, add=True)

        self._widgets.status.transient(self._widgets.mainframe)  # type: ignore
        self._init_trash(basepath / __class__.TRASH_NAME)
        self.update_filetree()
        self._widgets.mainframe._widgets.filetree.fill_from_pathtree(self._pathtree)
        self.status_window(False)

    def _init_trash(self, path: Path) -> None:
        if not path.exists():
            path.mkdir()

        if path.is_dir():
            self._trash_path = path
        else:
            print("trash directory is a file, could not initialize")

    def _handle_file_selected(self, ev: tk.Event) -> None:
        tv = cast(ttk.Treeview, ev.widget)
        """ sometimes there's no selection ie. if the selection is deleted by click menu"""
        if hasattr(ev.widget, "selection") and len(tv.selection()):
            p = Path(tv.selection()[0])
            if p.is_file():
                self._selected_path = p
                sidecar = MagicSidecar(p, __class__.METADATA_STREAM)
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

    def _handle_file_delete(self, ev: tk.Event, data: str) -> None:
        """data is the treeview iid which is the file path"""
        if self._trash_path is None:
            return

        path = Path(data)
        self._pathtree.dig_and_remove(path)
        path.move(self._trash_path / path.name)

    def _handle_play_from_ms(self, ev: tk.Event, data: str) -> None:
        self.play_file(self._selected_path, startms=int(data))

    def _handle_generate_thumbnails(self, ev: tk.Event) -> None:
        if self._selected_path is None or not self._selected_path.is_file():
            self._widgets.mainframe.event_generate(BVEvent.GENERATE_THUMBS_COMPLETE)
            return

        # probably not thread-safe
        def _thread_entry():
            def _progress(prefix: str, p: float) -> None:
                self._widgets.status.progress = p
                self._widgets.status.info = f"{prefix} {p * 100:.1f}%"

            vt = VideoThumbnailer(self._selected_path)
            self._metadata["video_properties"] = {}
            self._metadata["video_properties"]["dimensions"] = vt.dimensions
            self._metadata["video_properties"]["duration"] = round(vt.duration, 2) if vt.duration is not None else 0
            vt.extract_frames(
                interval=float(self._vars.thumb_interval.get()), progress_func=partial(_progress, "Extracting frames ")
            )
            vt.resize_frames(
                resize_height=int(self._vars.thumb_height.get()), progress_func=partial(_progress, "Resizing frames")
            )
            jpgs = vt.gen_jpgs()
            if jpgs is not None:
                self._metadata["thumbnails"] = jpgs
                self._widgets.mainframe.update_thumbs(jpgs)

            self._widgets.mainframe.event_generate(BVEvent.GENERATE_THUMBS_COMPLETE)
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
            sidecar = MagicSidecar(self._selected_path, __class__.METADATA_STREAM)
            sidecar.write(buf)
            self._vars.meta_size.set(f"metadata size: {round(len(buf) / 1000)}KB")
        except pickle.PickleError:
            print(f"failed to pickle metadata for {self._selected_path}")
        except Exception:
            print(f"failed to save metadata for {self._selected_path}")

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
                    sidecar = MagicSidecar(path, namespace=__class__.METADATA_STREAM)
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

    def play_file(self, path: Path, startms: int = 0):
        if not path.is_file():
            return

        os.spawnv(
            os.P_NOWAIT,
            __class__.VIDEO_PLAYER,
            [
                os.path.basename(__class__.VIDEO_PLAYER),
                f'"{path}"',
                f"/start {startms}",
            ],
        )

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
        self._widgets.mainframe.update_thumbs(self._metadata["thumbnails"])
        self._vars.video_res.set(f"resolution: {vres[0]}x{vres[1]}")

    def update_filetree(self) -> None:
        self._pathtree.scan(filters=[path_extension_filter(VID_EXTS)])

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


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print("filename argument required")
        raise SystemExit
    path = Path(sys.argv[1])
    if not path.is_dir():
        print(f"{path} is not a directory")
        raise SystemExit

    window = MessageWindow()
    window.title(f"Video Browser ({path.resolve()})")
    window.geometry("1200x1000")
    app = App(window, path)
    window.mainloop()
