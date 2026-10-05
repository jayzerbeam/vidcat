import io
import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import NamedTuple

from PIL import Image, ImageTk

from ui.better_frames import ImagesFrame
from ui.better_widgets import EditableList, LabeledEntry, LabeledEntryLayout

from .actions import UiContext


class VideoInfoFrame(ttk.Frame):
    class __Widgets(NamedTuple):
        props: VideoProperties
        title: LabeledEntry
        lists: ActorTagPane
        pane: ttk.PanedWindow
        thumbnails: ImagesFrame
        generate: ThumbGen
        save: ttk.Button

    _thumbs: tuple  # tuple[ImageTk.PhotoImage, int, int] | tuple[()]
    _widgets: __Widgets

    def __init__(self, parent, ctx: UiContext, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._ctx = ctx
        self._thumbs = ()
        self._play_from_ms = 0

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._widgets = __class__.__Widgets(
            props=VideoProperties(self, ctx),
            title=LabeledEntry(
                self,
                layout=LabeledEntryLayout.TWO_LINE,
                labelconf={"text": "Title"},
                entryconf={"textvariable": ctx.state.meta_title},
            ),
            lists=ActorTagPane(pane, ctx, orient=tk.VERTICAL, width=200),
            pane=pane,
            thumbnails=ImagesFrame(self, per_row=0),
            generate=ThumbGen(self, ctx),
            save=ttk.Button(
                self,
                text="Save",
                command=ctx.actions.save_metadata,
            ),
        )

        self._widgets.props.grid(row=0, sticky="EW")
        self._widgets.title.grid(row=1, sticky="EW")
        self._widgets.pane.add(self._widgets.lists)
        self._widgets.pane.add(self._widgets.thumbnails)
        self._widgets.pane.grid(row=2, column=0, sticky="NSEW")
        self._widgets.generate.grid(row=3, column=0, sticky="EW")
        self._widgets.save.grid(row=3, column=0, sticky="E")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        def _play_from_image(image: ImageTk.PhotoImage) -> None:
            # thumbnail contains frameno and ms timecode
            for t in self._thumbs:
                if t[0] == image:
                    self._ctx.actions.play_from_ms(t[2])
                    break

        self._widgets.thumbnails.set_image_click_handler(_play_from_image)
        ctx.state.thumbnails_changed.connect(self.update_thumbs)

    def update_thumbs(self, thumbs: Sequence[tuple[bytes, int, int]]) -> None:
        for t in thumbs:
            del t
        self._thumbs = tuple((ImageTk.PhotoImage(Image.open(io.BytesIO(t[0]))), *t[1:]) for t in thumbs)
        self.redraw_thumbs()

    def redraw_thumbs(self):
        self._widgets.thumbnails.clear_images()
        self._widgets.thumbnails.add_images(tuple(t[0] for t in self._thumbs))


class VideoProperties(ttk.Frame):
    class __Widgets(NamedTuple):
        row1: ttk.Frame
        row2: ttk.Frame
        file_path: ttk.Label
        file_size: ttk.Label
        dimensions: ttk.Label
        duration: ttk.Label
        metadata_size: ttk.Label

    def __init__(self, parent, ctx: UiContext, *args, **kw):
        super().__init__(parent, *args, **kw)
        row1 = ttk.Frame(self)
        row2 = ttk.Frame(self)
        self._widgets = __class__.__Widgets(
            row1=row1,
            row2=row2,
            file_path=ttk.Label(row1, textvariable=ctx.state.file_path),
            file_size=ttk.Label(row2, textvariable=ctx.state.file_size),
            dimensions=ttk.Label(row2, textvariable=ctx.state.video_res),
            duration=ttk.Label(row2, textvariable=ctx.state.video_len),
            metadata_size=ttk.Label(row2, textvariable=ctx.state.meta_size),
        )
        self._widgets.row1.pack(fill=tk.X, side=tk.TOP)
        self._widgets.row2.pack(fill=tk.X, side=tk.TOP)
        # row 1
        self._widgets.file_path.pack(ipadx=4, side=tk.LEFT)
        # row 2
        self._widgets.dimensions.pack(ipadx=4, side=tk.LEFT)
        self._widgets.duration.pack(ipadx=4, side=tk.LEFT)
        self._widgets.file_size.pack(ipadx=4, side=tk.LEFT)
        self._widgets.metadata_size.pack(ipadx=4, side=tk.LEFT)


class ActorTagPane(ttk.PanedWindow):
    class __Widgets(NamedTuple):
        actors: EditableList
        tags: EditableList

    def __init__(self, parent, ctx: UiContext, *args, **kw):
        super().__init__(parent, *args, **kw)

        def _remove_commas(entry: str) -> str:
            if isinstance(entry, str):
                return entry.replace(",", "").strip()
            else:
                return entry

        self._widgets = __class__.__Widgets(
            actors=EditableList(
                self,
                "Actors",
                listboxconf={"selectmode": tk.EXTENDED, "listvariable": ctx.state.meta_actors},
                width=1,
            ),
            tags=EditableList(
                self,
                "Tags",
                listboxconf={"selectmode": tk.EXTENDED, "listvariable": ctx.state.meta_tags},
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


class ThumbGen(ttk.Frame):
    class __Widgets(NamedTuple):
        interval: LabeledEntry
        height: LabeledEntry
        button: ttk.Button

    def __init__(self, parent, ctx: UiContext, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._widgets = __class__.__Widgets(
            interval=LabeledEntry(
                self,
                layout=LabeledEntryLayout.ONE_LINE,
                labelconf={"text": "Interval"},
                entryconf={"textvariable": ctx.state.thumb_interval, "width": 8},
            ),
            height=LabeledEntry(
                self,
                layout=LabeledEntryLayout.ONE_LINE,
                labelconf={"text": "Height"},
                entryconf={"textvariable": ctx.state.thumb_height, "width": 8},
            ),
            button=ttk.Button(self, text="Generate", command=ctx.actions.generate_thumbnails),
        )
        self._widgets.interval.grid(column=1, row=0, padx=(0, 4))
        self._widgets.height.grid(column=2, row=0, padx=(0, 4))
        self._widgets.button.grid(column=3, row=0)
