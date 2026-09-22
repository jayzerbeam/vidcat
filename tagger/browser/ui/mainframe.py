from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from tkinter import ttk
from typing import Any, NamedTuple

from ui.tk_event_data import DataEvents

from .constants import VirtualEventSequence
from .file_meta_treeview import FileMetaTreeviewFrame
from .filter_frame import FilterFrame
from .scrub_frame import ScrubFrame
from .video_info_frame import VideoInfoFrame


class MainFrame(DataEvents, ttk.Frame):
    class __Widgets(NamedTuple):
        pane: ttk.PanedWindow
        filetree: FileMetaTreeviewFrame
        tabs: ttk.Notebook
        vidinfo: VideoInfoFrame
        filters: FilterFrame
        scrubber: ScrubFrame

    _basepath: Path | None
    _widgets: __Widgets

    def __init__(
        self,
        parent: tk.Frame | tk.Tk,
        basepath: Path | None = None,
        *args: Any,
        **kw: Any,
    ):
        super().__init__(parent, *args, **kw)
        self._basepath = basepath

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        tabs = ttk.Notebook(pane)
        self._widgets = __class__.__Widgets(
            pane=pane,
            filetree=FileMetaTreeviewFrame(pane),
            tabs=tabs,
            filters=FilterFrame(tabs),
            vidinfo=VideoInfoFrame(tabs),
            scrubber=ScrubFrame(tabs),
        )
        self._widgets.pane.add(self._widgets.filetree)
        self._widgets.pane.add(self._widgets.tabs)
        self._widgets.pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._widgets.tabs.add(self._widgets.filters, text="Filters")
        self._widgets.tabs.add(self._widgets.vidinfo, text="Video Info")
        self._widgets.tabs.add(self._widgets.scrubber, text="Scrub")
        self._widgets.tabs.select(1)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        def _ctrlkey(event: tk.Event) -> None:
            if event.keysym == "s":
                self.event_generate(VirtualEventSequence.SAVE_METADATA)
            if event.keysym == "g":
                self.event_generate(VirtualEventSequence.GEN_THUMBS)

        self.bind_all("<Control-KeyPress>", _ctrlkey)

        self._widgets.filters.bind(VirtualEventSequence.FILTERS_AND, lambda event: self.apply_filters(operator="AND"))
        self._widgets.filters.bind(VirtualEventSequence.FILTERS_OR, lambda event: self.apply_filters(operator="OR"))
        self._widgets.filters.bind(VirtualEventSequence.FILTERS_CLEAR, self._handle_clear_filters)

    def update_thumbs(self, thumbs: Sequence[tuple[bytes, int, int]]) -> None:
        self._widgets.vidinfo.update_thumbs(thumbs)

    def update_scrubber(self, path: Path) -> None:
        self._widgets.scrubber.load(path)

    def clear_scrubber(self) -> None:
        self._widgets.scrubber.clear()

    def set_actors(self, items: dict):
        # TODO I don't like this, should find a better way
        tv = self._widgets.filters._widgets.actors.treeview
        tv.clear()
        for i in sorted(items.keys()):
            tv.insert("", tk.END, i, text=str(i), values=(items[i],))

    def set_tags(self, items: dict) -> None:
        tv = self._widgets.filters._widgets.tags.treeview
        tv.clear()
        for i in sorted(items.keys()):
            tv.insert("", tk.END, i, text=str(i), values=(items[i],))

    def apply_filters(self, operator: str = "OR") -> None:
        self._widgets.filetree.apply_filters(
            self._widgets.filters._widgets.actors.treeview.selection(),
            self._widgets.filters._widgets.tags.treeview.selection(),
            operator=operator,
        )

    def _handle_clear_filters(self, event: tk.Event) -> None:
        self._widgets.filetree.unhide_all()
