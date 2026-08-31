import os
import pickle
import sys
import threading
import time
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import StringVar, ttk
from typing import Any, Final, NamedTuple, cast

# from meta_editor import ThumbGen, VideoProperties
import util.file.alternate_data_streams as ADS
from browser.ui import MainFrame
from browser.ui.constants import TkVarNames
from browser.ui.constants import VirtualEventSequence as BVEvent
from util.file.alternate_data_streams import ADSFile
from util.ui.constants import TkCursor
from util.ui.constants import VirtualEventSequence as VEvent
from util.ui.message_system import MessageWindow
from util.video_thumbnailer import VideoThumbnailer


class StatusWindow(tk.Toplevel):
    class _Widgets(NamedTuple):
        frame: ttk.Frame
        progress: ttk.Progressbar
        status: ttk.Label

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self.resizable(False, False)
        self.title("Status")
        self.group(parent)

        self.status_text = StringVar()
        frame = ttk.Frame(self)
        self._widgets = __class__._Widgets(
            frame=frame,
            progress=ttk.Progressbar(frame),
            status=ttk.Label(frame, textvariable=self.status_text),
        )
        self._widgets.progress.grid(column=0, row=0, padx=2, pady=2, sticky="ew")
        self._widgets.status.grid(column=0, row=1, padx=2, pady=2)
        self._widgets.frame.columnconfigure(0, weight=1)
        self._widgets.frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    @property
    def info(self):
        return self.status_text.get()

    @info.setter
    def info(self, val):
        return self.status_text.set(val)

    @property
    def progress(self):
        return self._widgets.progress["value"]

    @progress.setter
    def progress(self, val):
        self._widgets.progress.config(value=val)


class App:
    VIDEO_PLAYER: Final[str] = "C:\\Program Files\\MPC-BE\\mpc-be64.exe"
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
    METADATA_STREAM: Final[str] = "video_metadata"
    _EMPTY_METADATA: Final[dict[str, Any]] = {
        "title": "",
        "video_properties": {"dimensions": (0, 0), "duration": 0},
        "actors": [],
        "tags": [],
        "thumbnails": [],
    }

    _basepath: Path
    _root: tk.Tk
    _metadata: dict[str, Any]
    _file_meta_filters: dict
    _all_tags: list[str]
    _all_actors: list[str]
    _selected_path: Path

    class _Widgets(NamedTuple):
        mainframe: MainFrame
        status: StatusWindow

    class _Vars(NamedTuple):
        thumb_interval: StringVar
        thumb_height: StringVar

    def __init__(self, root: tk.Tk, basepath: Path):
        self._root = root
        self._basepath = basepath
        self._metadata = deepcopy(__class__._EMPTY_METADATA)
        self._file_meta_filters = {}
        self._all_tags = []
        self._all_actors = []
        self._selected_path = Path()

        self._vars = __class__._Vars(
            thumb_interval=tk.StringVar(self._root, name=TkVarNames.THUMB_INTERVAL, value="-30"),
            thumb_height=tk.StringVar(self._root, name=TkVarNames.THUMB_HEIGHT, value="240"),
        )

        self._widgets = __class__._Widgets(mainframe=MainFrame(root), status=StatusWindow(root))
        self._widgets.mainframe.extensions(*App.VID_EXTS)
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)
        self._widgets.mainframe.basepath = basepath

        self._widgets.mainframe.bind_all(VEvent.FILE_SELECT, func=self._handle_file_selected, add=True)
        self._widgets.mainframe.bind_all(VEvent.FILE_EXEC, func=self._handle_file_exec, add=True)
        self._widgets.mainframe.bind_all(BVEvent.GENERATE_THUMBS, func=self._handle_generate_thumbnails, add=True)
        self._widgets.mainframe.bind_all(BVEvent.SAVE_METADATA, func=self._handle_save_metadata, add=True)
        self._widgets.mainframe.bind_all(BVEvent.SCAN_METADATA, func=self._handle_scan_metadata, add=True)
        self._widgets.mainframe.bind_all_with_data(BVEvent.PLAY_FROM_MS, func=self._handle_play_from_ms, add=True)

        self._widgets.status.transient(self._widgets.mainframe)  # type: ignore
        self._widgets.status.overrideredirect(True)
        self._widgets.status.withdraw()

    def _handle_file_selected(self, ev: tk.Event) -> None:
        if hasattr(ev.widget, "selection"):
            p = Path(cast(ttk.Treeview, ev.widget).selection()[0])
            if p.is_file():
                self._selected_path = p
                print(f"loading metadata for {p.name}")
                try:
                    adsfile = ADSFile(p)
                    if not adsfile.has_stream(__class__.METADATA_STREAM):
                        adsfile.write_stream(
                            __class__.METADATA_STREAM,
                            pickle.dumps(__class__._EMPTY_METADATA),
                        )
                    self._metadata = pickle.loads(adsfile.read_stream(__class__.METADATA_STREAM))
                except FileNotFoundError:
                    self._metadata = deepcopy(__class__._EMPTY_METADATA)
                self._widgets.mainframe.metadata = self._metadata

    def _handle_file_exec(self, ev: tk.Event) -> None:
        self.play_file(self._selected_path)

    def _handle_play_from_ms(self, ev: tk.Event, data: str) -> None:
        self.play_file(self._selected_path, startms=int(data))

    def _handle_generate_thumbnails(self, ev: tk.Event) -> None:
        if self._selected_path is None or not self._selected_path.is_file():
            self._widgets.mainframe.event_generate(BVEvent.GENERATE_THUMBS_COMPLETE)
            return

        # probably not thread-safe
        def _thread_entry():
            vt = VideoThumbnailer(self._selected_path)
            self._metadata["video_properties"] = {}
            self._metadata["video_properties"]["dimensions"] = vt.get_dimensions()
            self._metadata["video_properties"]["duration"] = round(vt.get_frame_count() / (vt.get_fps() or 30.0), 2)
            vt.extract_frames(interval=int(self._vars.thumb_interval.get()))
            vt.resize_frames(resize_height=int(self._vars.thumb_height.get()))
            jpgs = vt.gen_jpgs(jpgq=70)
            self._metadata["thumbnails"] = jpgs
            self._widgets.mainframe.metadata = self._metadata  # TODO
            self._widgets.mainframe.event_generate(BVEvent.GENERATE_THUMBS_COMPLETE)

        threading.Thread(target=_thread_entry, daemon=True).start()

    def _handle_save_metadata(self, ev: tk.Event) -> None:
        print(f"saving metadata for {self._widgets.mainframe.selected_file}")
        if not self._widgets.mainframe.selected_file:
            return
        self._metadata = self._widgets.mainframe.metadata
        adsfile = ADSFile(self._selected_path)
        adsfile.write_stream(__class__.METADATA_STREAM, pickle.dumps(self._metadata))

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
                    self._widgets.status.progress = (c + 1) / item_count * 100.0
                    self._widgets.status.info = f"[{c}/{item_count}] {item}"
                    last_time = time.time()

                path = self._basepath / item
                if path.is_file() and ADS.has_stream(path, __class__.METADATA_STREAM):
                    try:
                        metadata = pickle.loads(ADS.read_stream(path, __class__.METADATA_STREAM))
                    except pickle.UnpicklingError:
                        print(f"failed to unpickle metadata for {path}")
                    else:
                        self._widgets.mainframe._widgets.filetree.set_meta_column_vals(
                            item, metadata["actors"], metadata["tags"]
                        )
                        _incr(actors, metadata["actors"])
                        _incr(tags, metadata["tags"])

            self._widgets.status.progress = 100.0
            self._widgets.status.info = "populating widgets"
            self._widgets.mainframe.set_actors(actors)
            self._widgets.mainframe.set_tags(tags)
            self._widgets.mainframe.busy_forget()
            self.status_window(False)

        threading.Thread(target=_thread_entry, daemon=True).start()

    def status_window(self, active: bool) -> None:
        STATUS_SPACING: Final[int] = 80
        if active:
            width: int = round(self._root.winfo_width() - 80)
            xoffset: int = round(self._root.winfo_x() + STATUS_SPACING / 2)
            yoffset: int = round(
                self._root.winfo_y() + self._root.winfo_height() / 2 - self._widgets.status.winfo_height() / 2
            )
            self._widgets.status.update_idletasks()
            height = self._widgets.status.winfo_reqheight()
            self._widgets.status.geometry(f"{width}x{height}+{xoffset}+{yoffset}")
            self._widgets.status.deiconify()
            self._widgets.status.lift(self._widgets.mainframe)
        else:
            self._widgets.status.withdraw()

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
