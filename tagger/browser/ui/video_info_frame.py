import io
import tkinter as tk
from tkinter import StringVar, ttk
from typing import NamedTuple

from PIL import Image, ImageTk

from util.ui.better_frames import ImagesFrame
from util.ui.better_widgets import (
    EditableList,
    LabeledEntry,
)


# t is seconds
def nice_duration(t: int):
    units = ["h", "m", "s"]
    formatted = ""
    try:
        t = int(t)
        while t >= 1:
            formatted = f" {t % 60}{units.pop()}" + formatted
            t = int(t / 60)
        return formatted.strip()
    except ValueError:
        return "???"


class VideoInfoFrame(ttk.Frame):
    class _Widgets(NamedTuple):
        props: VideoProperties
        title: LabeledEntry
        lists: ActorTagPane
        pane: ttk.PanedWindow
        panes: dict[str, ttk.PanedWindow]
        thumbnails: ImagesFrame
        generate: ThumbGen
        save: ttk.Button

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self.thumbs = []
        self.play_ms = 0
        self._p = {}
        self._p["metadata"] = {}
        self._p["video_path"] = ""

        self.vars = {}
        self.vars["title"] = StringVar(self)
        self.vars["title"].trace_add(
            "write", lambda *args: _set_metadata("title", self.vars["title"].get())
        )

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._widgets = __class__._Widgets(
            props=VideoProperties(self),
            title=LabeledEntry(self, "Title", self.vars["title"]),
            lists=ActorTagPane(pane, orient=tk.VERTICAL, width=200),
            pane=pane,
            panes={},
            thumbnails=ImagesFrame(self, per_row=0),
            generate=ThumbGen(self),
            save=ttk.Button(
                self,
                text="Save",
                command=lambda self=self: self.event_generate("<<SaveMetadata>>"),
            ),
        )

        self._widgets.props.grid(row=0, sticky="EW")
        self._widgets.title.grid(row=1, sticky="EW")
        self._widgets.pane.add(self._widgets.lists)
        self._widgets.pane.add(self._widgets.thumbnails)
        self._widgets.pane.grid(row=2, column=0, sticky="NSEW", pady=4, padx=4)
        self._widgets.generate.grid(row=3, column=0, sticky="EW", pady=4, padx=4)
        self._widgets.save.grid(row=3, column=0, sticky="E", pady=4, padx=4, ipadx=4)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        def _set_metadata(key, value):
            self._p["metadata"][key] = value

        def _play_from_image(image):
            # thumbnail contains frameno and ms timecode
            for img in self.thumbs:
                if img[0] == image:
                    self.play_ms = img[1][2]
                    self.event_generate("<<PlayFileAt>>")
                    break

        self._widgets.thumbnails.set_image_click_handler(_play_from_image)

    @property
    def metadata(self):
        self._p["metadata"]["actors"] = self._widgets.lists.actors
        self._p["metadata"]["tags"] = self._widgets.lists.tags
        return self._p["metadata"]

    @metadata.setter
    def metadata(self, metadata: dict):
        self._p["metadata"] = metadata
        vp = metadata["video_properties"]
        (vidw, vidh) = (
            (vp["dimensions"][0], vp["dimensions"][1])
            if len(vp["dimensions"])
            else (0, 0)
        )
        viddur = vp.get("duration", 0)
        self.vars["title"].set(metadata["title"])
        self._widgets.lists.actor_listbox.clear_items()
        self._widgets.lists.actor_listbox.add_items(metadata["actors"])
        self._widgets.lists.tag_listbox.clear_items()
        self._widgets.lists.tag_listbox.add_items(metadata["tags"])
        self._widgets.props.set_properties(vidw, vidh, viddur)
        for t in self.thumbs:
            del t
        self.thumbs = [
            (ImageTk.PhotoImage(Image.open(io.BytesIO(t[0]))), t)
            for t in metadata["thumbnails"]
        ]
        self._widgets.thumbnails.clear_images()
        self._widgets.thumbnails.add_images([i[0] for i in self.thumbs])

    @property
    def video_path(self):
        return self._p["video_path"]

    @video_path.setter
    def video_path(self, video_path):
        self._p["video_path"] = video_path

    @property
    def thumb_interval(self):
        return self.vars["interval"].get()

    def reload_thumbs(self):
        self._widgets.thumbnails.clear_images()
        self._widgets.thumbnails.add_images(
            [
                ImageTk.PhotoImage(Image.open(io.BytesIO(t[0])))
                for t in self._p["metadata"]["thumbnails"]
            ]
        )
        self._widgets.generate.busy = False


class VideoProperties(ttk.Frame):
    class _Widgets(NamedTuple):
        dimensions: ttk.Label
        duration: ttk.Label

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._widgets = __class__._Widgets(
            dimensions=ttk.Label(self), duration=ttk.Label(self)
        )
        self._widgets.dimensions.pack(ipadx=4, side=tk.LEFT)
        self._widgets.duration.pack(ipadx=4, side=tk.LEFT)

    def set_properties(self, width, height, duration):
        self._widgets.dimensions.config(text=f"dimensions: {width}x{height}")
        self._widgets.duration.config(text=f"duration: {nice_duration(duration)}")


class ActorTagPane(ttk.PanedWindow):
    class _Widgets(NamedTuple):
        actors: EditableList
        tags: EditableList

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)

        def _on_add(entry):
            if isinstance(entry, str):
                return entry.replace(",", "").strip()
            else:
                return entry

        self._widgets = __class__._Widgets(
            actors=EditableList(self, "Actors", width=1),
            tags=EditableList(self, "Tags", width=1),
        )
        self._widgets.actors.list_height(10)
        self._widgets.actors.on_add_handler(_on_add)
        self.add(self._widgets.actors)
        self._widgets.tags.on_add_handler(_on_add)
        self.add(self._widgets.tags)

    @property
    def actors(self):
        return self._widgets.actors.items

    @property
    def actor_listbox(self):
        return self._widgets.actors

    @property
    def tags(self):
        return self._widgets.tags.items

    @property
    def tag_listbox(self):
        return self._widgets.tags


class ThumbGen(ttk.Frame):
    class _Widgets(NamedTuple):
        label: ttk.Label
        interval: ttk.Entry
        button: ttk.Button

    def __init__(self, parent, *args, **kw):
        def _gen_thumbs():
            self.event_generate("<<GenerateThumbs>>")
            self._widgets.button.config(state=tk.DISABLED)

        super().__init__(parent, *args, **kw)
        self._widgets = __class__._Widgets(
            label=ttk.Label(self, text="interval"),
            interval=ttk.Entry(self, width=5),
            button=ttk.Button(self, text="Generate", command=_gen_thumbs),
        )
        self._widgets.label.grid(column=0, row=0)
        self._widgets.interval.insert(0, "-30")
        self._widgets.interval.grid(column=1, row=0, padx=4)
        self._widgets.button.grid(column=2, row=0)
        self.bind_all(
            "<<GenerateThumbsComplete>>",
            lambda event: self._widgets.button.config(state=tk.ACTIVE),
        )

        self.is_busy: bool = False

    @property
    def interval(self) -> int:
        return int(self._widgets.interval.get())

    @property
    def busy(self) -> bool:
        return self.is_busy

    @busy.setter
    def busy(self, state: bool) -> None:
        self.is_busy = state
        if state:
            self._widgets.button.config(state=tk.DISABLED)
        else:
            self._widgets.button.config(state=tk.NORMAL)
