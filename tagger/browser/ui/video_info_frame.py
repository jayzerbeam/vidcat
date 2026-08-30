import io
import tkinter as tk
from tkinter import StringVar, ttk
from typing import Any, NamedTuple

from PIL import Image, ImageTk

from browser.ui.constants import VirtualEventSequence
from util.ui.better_frames import ImagesFrame
from util.ui.better_widgets import EditableList, LabeledEntry, LabeledEntryLayout
from util.ui.tk_event_data import DataEvents


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


class VideoInfoFrame(DataEvents, ttk.Frame):
    class _Widgets(NamedTuple):
        props: VideoProperties
        title: LabeledEntry
        lists: ActorTagPane
        pane: ttk.PanedWindow
        thumbnails: ImagesFrame
        generate: ThumbGen
        save: ttk.Button

    class _Vars(NamedTuple):
        title: StringVar

    _play_from_ms: int
    _thumbs: tuple  # tuple[ImageTk.PhotoImage, int, int] | tuple[()]
    _metadata: dict[str, Any]

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._thumbs = ()
        self._play_from_ms = 0
        self._metadata = {}

        self._vars = __class__._Vars(
            title=StringVar(self),
        )
        self._vars.title.trace_add("write", lambda *args: _set_metadata("title", self._vars.title.get()))

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._widgets = __class__._Widgets(
            props=VideoProperties(self),
            title=LabeledEntry(
                self,
                layout=LabeledEntryLayout.TWO_LINE,
                labelconf={"text": "Title"},
                entryconf={"textvariable": self._vars.title},
            ),
            lists=ActorTagPane(pane, orient=tk.VERTICAL, width=200),
            pane=pane,
            thumbnails=ImagesFrame(self, per_row=0),
            generate=ThumbGen(self),
            save=ttk.Button(
                self,
                text="Save",
                command=lambda self=self: self.event_generate(VirtualEventSequence.SAVE_METADATA),
            ),
        )
        self.bind_all(VirtualEventSequence.GENERATE_THUMBS, func=self._handle_generate_thumbs, add=True)
        self.bind_all(
            VirtualEventSequence.GENERATE_THUMBS_COMPLETE, func=self._handle_generate_thumbs_complete, add=True
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

        def _set_metadata(key: str, value: Any) -> None:
            self._metadata[key] = value

        def _play_from_image(image: ImageTk.PhotoImage) -> None:
            # thumbnail contains frameno and ms timecode
            for t in self._thumbs:
                if t[0] == image:
                    self._play_from_ms = t[1][2]
                    self.event_generate(VirtualEventSequence.PLAY_FROM_MS, data=self._play_from_ms)
                    break

        self._widgets.thumbnails.set_image_click_handler(_play_from_image)

    def _handle_generate_thumbs(self, ev: tk.Event) -> None:
        self._widgets.thumbnails.busy_hold(cursor="wait")

    def _handle_generate_thumbs_complete(self, ev: tk.Event) -> None:
        if self._widgets.thumbnails.busy_status():
            self._widgets.thumbnails.busy_forget()

    @property
    def metadata(self):
        self._metadata["actors"] = self._widgets.lists.actors
        self._metadata["tags"] = self._widgets.lists.tags
        return self._metadata

    @metadata.setter
    def metadata(self, metadata: dict[str, Any]):
        self._metadata = metadata
        vp = metadata["video_properties"]
        (vidw, vidh) = (vp["dimensions"][0], vp["dimensions"][1]) if len(vp["dimensions"]) else (0, 0)
        viddur = vp.get("duration", 0)
        self._vars.title.set(metadata["title"])
        self._widgets.lists.actor_listbox.clear_items()
        self._widgets.lists.actor_listbox.add_items(metadata["actors"])
        self._widgets.lists.tag_listbox.clear_items()
        self._widgets.lists.tag_listbox.add_items(metadata["tags"])
        self._widgets.props.set_properties(vidw, vidh, viddur)
        for t in self._thumbs:
            del t
        self._thumbs = tuple((ImageTk.PhotoImage(Image.open(io.BytesIO(t[0]))), t) for t in metadata["thumbnails"])
        self._widgets.thumbnails.clear_images()
        self._widgets.thumbnails.add_images(tuple(i[0] for i in self._thumbs))

    def reload_thumbs(self):
        self._widgets.thumbnails.clear_images()
        self._widgets.thumbnails.add_images(
            tuple(ImageTk.PhotoImage(Image.open(io.BytesIO(t[0]))) for t in self._metadata["thumbnails"])
        )
        self._widgets.generate.busy_forget()


class VideoProperties(DataEvents, ttk.Frame):
    class _Widgets(NamedTuple):
        dimensions: ttk.Label
        duration: ttk.Label

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._widgets = __class__._Widgets(dimensions=ttk.Label(self), duration=ttk.Label(self))
        self._widgets.dimensions.pack(ipadx=4, side=tk.LEFT)
        self._widgets.duration.pack(ipadx=4, side=tk.LEFT)

    def set_properties(self, width, height, duration):
        self._widgets.dimensions.config(text=f"dimensions: {width}x{height}")
        self._widgets.duration.config(text=f"duration: {nice_duration(duration)}")


class ActorTagPane(DataEvents, ttk.PanedWindow):
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


class ThumbGen(DataEvents, ttk.Frame):
    class _Widgets(NamedTuple):
        interval: LabeledEntry
        button: ttk.Button

    class _Vars(NamedTuple):
        interval: StringVar

    def __init__(self, parent, *args, **kw):
        def _gen_thumbs():
            self.busy_hold(cursor="wait")
            self.event_generate(VirtualEventSequence.GENERATE_THUMBS)

        super().__init__(parent, *args, **kw)
        self._vars = __class__._Vars(interval=StringVar(self))
        self._vars.interval.trace_add(
            "write",
            lambda *args: self.event_generate(VirtualEventSequence.INTERVAL_CHANGED, data=self._vars.interval.get()),
        )
        self._widgets = __class__._Widgets(
            interval=LabeledEntry(
                self,
                layout=LabeledEntryLayout.ONE_LINE,
                labelconf={"text": "Interval"},
                entryconf={"textvariable": self._vars.interval, "width": 8},
            ),
            button=ttk.Button(self, text="Generate", command=_gen_thumbs),
        )
        self._widgets.interval.entry_set("-30")
        self._widgets.interval.grid(column=1, row=0, padx=(0, 4))
        self._widgets.button.grid(column=2, row=0)
        self.bind_all(
            VirtualEventSequence.GENERATE_THUMBS_COMPLETE, func=self._handle_generate_thumbs_complete, add=True
        )

    def _handle_generate_thumbs_complete(self, ev: tk.Event) -> None:
        if self.busy_status():
            self.busy_forget()

    @property
    def interval(self):
        return self._vars.interval.get()
