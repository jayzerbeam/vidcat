import io
import tkinter as tk
from collections.abc import Sequence
from tkinter import StringVar, ttk
from typing import NamedTuple

from PIL import Image, ImageTk

from browser.ui.constants import TkVarNames, VirtualEventSequence
from util.ui.better_frames import ImagesFrame
from util.ui.better_widgets import EditableList, LabeledEntry, LabeledEntryLayout
from util.ui.constants import TkCursor
from util.ui.tk_event_data import DataEvents


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

    _thumbs: tuple  # tuple[ImageTk.PhotoImage, int, int] | tuple[()]

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._thumbs = ()
        self._play_from_ms = 0

        self._vars = __class__._Vars(
            title=StringVar(name=TkVarNames.META_TITLE),
        )

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

        def _play_from_image(image: ImageTk.PhotoImage) -> None:
            # thumbnail contains frameno and ms timecode
            for t in self._thumbs:
                if t[0] == image:
                    self.event_generate(VirtualEventSequence.PLAY_FROM_MS, data=t[2])
                    break

        self._widgets.thumbnails.set_image_click_handler(_play_from_image)

    def _handle_generate_thumbs(self, ev: tk.Event) -> None:
        self._widgets.thumbnails.busy_hold(cursor=TkCursor.WAIT)

    def _handle_generate_thumbs_complete(self, ev: tk.Event) -> None:
        self.redraw_thumbs()
        if self._widgets.thumbnails.busy_status():
            self._widgets.thumbnails.busy_forget()

    def update_thumbs(self, thumbs: Sequence[tuple[bytes, int, int]]) -> None:
        for t in thumbs:
            del t
        self._thumbs = tuple((ImageTk.PhotoImage(Image.open(io.BytesIO(t[0]))), *t[1:]) for t in thumbs)
        self.redraw_thumbs()

    def redraw_thumbs(self):
        self._widgets.thumbnails.clear_images()
        self._widgets.thumbnails.add_images(tuple(t[0] for t in self._thumbs))


class VideoProperties(DataEvents, ttk.Frame):
    class _Widgets(NamedTuple):
        dimensions: ttk.Label
        duration: ttk.Label
        metadata_size: ttk.Label

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._widgets = __class__._Widgets(
            dimensions=ttk.Label(self, textvariable=tk.StringVar(name=TkVarNames.VIDEO_RES)),
            duration=ttk.Label(self, textvariable=tk.StringVar(name=TkVarNames.VIDEO_LEN)),
            metadata_size=ttk.Label(self, textvariable=tk.StringVar(name=TkVarNames.META_SIZE)),
        )
        self._widgets.dimensions.pack(ipadx=4, side=tk.LEFT)
        self._widgets.duration.pack(ipadx=4, side=tk.LEFT)
        self._widgets.metadata_size.pack(ipadx=4, side=tk.LEFT)


class ActorTagPane(DataEvents, ttk.PanedWindow):
    class _Widgets(NamedTuple):
        actors: EditableList
        tags: EditableList

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)

        def _remove_commas(entry: str) -> str:
            if isinstance(entry, str):
                return entry.replace(",", "").strip()
            else:
                return entry

        self._widgets = __class__._Widgets(
            actors=EditableList(
                self,
                "Actors",
                listboxconf={"selectmode": tk.EXTENDED, "listvariable": tk.Variable(name=TkVarNames.META_ACTORS)},
                width=1,
            ),
            tags=EditableList(
                self,
                "Tags",
                listboxconf={"selectmode": tk.EXTENDED, "listvariable": tk.Variable(name=TkVarNames.META_TAGS)},
                width=1,
            ),
        )
        self._widgets.actors.list_height(10)
        self._widgets.actors.set_entry_filter(_remove_commas)
        self.add(self._widgets.actors)
        self._widgets.tags.set_entry_filter(_remove_commas)
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
        height: LabeledEntry
        button: ttk.Button

    class _Vars(NamedTuple):
        interval: StringVar
        height: StringVar

    def __init__(self, parent, *args, **kw):
        def _gen_thumbs():
            self.busy_hold(cursor=TkCursor.WAIT)
            self.event_generate(VirtualEventSequence.GENERATE_THUMBS)

        super().__init__(parent, *args, **kw)
        self._vars = __class__._Vars(
            interval=StringVar(name="THUMB_INTERVAL"),
            height=StringVar(name="THUMB_HEIGHT"),
        )
        self._widgets = __class__._Widgets(
            interval=LabeledEntry(
                self,
                layout=LabeledEntryLayout.ONE_LINE,
                labelconf={"text": "Interval"},
                entryconf={"textvariable": self._vars.interval, "width": 8},
            ),
            height=LabeledEntry(
                self,
                layout=LabeledEntryLayout.ONE_LINE,
                labelconf={"text": "Height"},
                entryconf={"textvariable": self._vars.height, "width": 8},
            ),
            button=ttk.Button(self, text="Generate", command=_gen_thumbs),
        )
        self._widgets.interval.grid(column=1, row=0, padx=(0, 4))
        self._widgets.height.grid(column=2, row=0, padx=(0, 4))
        self._widgets.button.grid(column=3, row=0)
        self.bind_all(
            VirtualEventSequence.GENERATE_THUMBS_COMPLETE, func=self._handle_generate_thumbs_complete, add=True
        )

    def _handle_generate_thumbs_complete(self, ev: tk.Event) -> None:
        if self.busy_status():
            self.busy_forget()
