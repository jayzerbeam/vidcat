import os
import pickle
import sys
import threading
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import StringVar, ttk
from typing import Any, Final, NamedTuple, cast

# from meta_editor import ThumbGen, VideoProperties
import util.file.alternate_data_streams as ADS
from browser.ui import MainFrame
from util.file.alternate_data_streams import ADSFile
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
            progress=ttk.Progressbar(frame, length=500),
            status=ttk.Label(frame, textvariable=self.status_text),
        )
        self._widgets.progress.grid(column=0, row=0, padx=2, pady=2)
        self._widgets.status.grid(column=0, row=1, padx=2, pady=2)
        self._widgets.frame.pack(padx=10, pady=10)

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
    _interval: int
    _selected_path: Path

    class _Widgets(NamedTuple):
        mainframe: MainFrame
        status: StatusWindow

    def __init__(self, root: tk.Tk, basepath: Path):
        self._root = root
        self._basepath = basepath
        self._metadata = deepcopy(__class__._EMPTY_METADATA)
        self._file_meta_filters = {}
        self._all_tags = []
        self._all_actors = []
        self._selected_path = Path()

        self._widgets = __class__._Widgets(mainframe=MainFrame(root), status=StatusWindow(root))
        self._widgets.mainframe.extensions(*App.VID_EXTS)
        self._widgets.mainframe.pack(expand=True, fill=tk.BOTH)
        self._widgets.mainframe.basepath = basepath

        self._widgets.mainframe.bind_all("<<FileSelect>>", self.handle_file_selected)
        self._widgets.mainframe.bind_all("<<FileExec>>", self.handle_file_exec)
        self._widgets.mainframe.bind_all("<<PlayFromMs>>", self.handle_play_from_ms)
        self._widgets.mainframe.bind_all("<<IntervalChanged>>", self.handle_interval_changed)
        self._widgets.mainframe.bind_all("<<GenerateThumbs>>", self.handle_generate_thumbnails)
        self._widgets.mainframe.bind_all("<<SaveMetadata>>", self.handle_save_metadata)
        self._widgets.mainframe.bind_all("<<ScanMetadata>>", lambda ev: self.scan_files_metadata())

        self._widgets.status.transient(self._widgets.mainframe)  # type: ignore
        self._widgets.status.overrideredirect(True)
        self._widgets.status.withdraw()

    def handle_file_selected(self, ev: tk.Event) -> None:
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

    def handle_file_exec(self, ev: tk.Event) -> None:
        self.play_file(self._selected_path)

    def handle_play_from_ms(self, ev: tk.Event) -> None:
        if hasattr(ev.widget, "play_from_ms"):
            self.play_file(self._selected_path, startms=ev.widget.play_from_ms)  # type: ignore

    def handle_generate_thumbnails(self, ev: tk.Event) -> None:
        self.generate_thumbnails(self._widgets.mainframe.selected_file, self._interval)

    def handle_interval_changed(self, ev: tk.Event) -> None:
        if hasattr(ev.widget, "interval"):
            self._interval = ev.widget.interval  # type: ignore

    def handle_save_metadata(self, ev: tk.Event) -> None:
        print(f"saving metadata for {self._widgets.mainframe.selected_file}")
        if not self._widgets.mainframe.selected_file:
            return
        self._metadata = self._widgets.mainframe.metadata
        adsfile = ADSFile(self._selected_path)
        adsfile.write_stream(__class__.METADATA_STREAM, pickle.dumps(self._metadata))

    def scan_files_metadata(self):
        xoffset = round(self._root.winfo_x() + self._root.winfo_width() / 2 - self._widgets.status.winfo_reqwidth() / 2)
        yoffset = round(
            self._root.winfo_y() + self._root.winfo_height() / 2 - self._widgets.status.winfo_reqheight() / 2
        )
        self._widgets.status.geometry(f"+{xoffset}+{yoffset}")
        self._widgets.status.deiconify()
        self._widgets.status.lift(self._widgets.mainframe)

        self._widgets.mainframe._widgets.filetree.unhide_all()

        def _incr(totals: dict, keys):
            for k in keys:
                if k not in totals:
                    totals[k] = 1
                else:
                    totals[k] += 1

        actors = {}
        tags = {}
        items = self._widgets.mainframe._widgets.filetree.get_items(with_tags=["file"])

        item_count = len(items)
        steps = 200  # bar updates steps, so it's not updating with every file
        for c, item in enumerate(items):
            if item_count <= steps or c % int(item_count / steps) == 0 or c + 1 == item_count:
                self._widgets.status.progress = (c + 1) / item_count * 100.0
                self._widgets.status.info = item
                self._root.update()
            filename = os.path.join(self._basepath, item)
            if os.path.isfile(filename) and ADS.has_stream(filename, __class__.METADATA_STREAM):
                try:
                    metadata = pickle.loads(ADS.read_stream(filename, __class__.METADATA_STREAM))
                except pickle.UnpicklingError:
                    print(f"failed to unpickle metadata for {filename}")
                else:
                    self._widgets.mainframe._widgets.filetree.set_meta_columns(
                        item, metadata["actors"], metadata["tags"]
                    )
                    _incr(actors, metadata["actors"])
                    _incr(tags, metadata["tags"])
        self._widgets.mainframe.set_actors(actors)
        self._widgets.mainframe.set_tags(tags)
        self._widgets.status.withdraw()

    # so not thread-safe
    def generate_thumbnails(self, path: Path | None, interval: int):
        if path is None:
            return

        def thread_entry():
            vt = VideoThumbnailer(path)
            self._metadata["video_properties"] = {}
            self._metadata["video_properties"]["dimensions"] = vt.get_dimensions()
            self._metadata["video_properties"]["duration"] = round(vt.get_frame_count() / (vt.get_fps() or 30.0), 2)
            vt.extract_frames(interval=interval)
            vt.resize_frames(resize_height=200)
            jpgs = vt.gen_jpgs(jpgq=70)
            self._metadata["thumbnails"] = jpgs
            self._widgets.mainframe.metadata = self._metadata  # TODO
            self._widgets.mainframe.event_generate("<<GenerateThumbsComplete>>")

        threading.Thread(target=thread_entry).start()

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
    window.title("Video Metadata Browser")
    window.geometry("1200x1000")
    app = App(window, path)
    window.mainloop()
