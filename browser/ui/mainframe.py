from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, NamedTuple

from ui.constants import TkCursor

from .actions import UiContext
from .file_meta_treeview import FileMetaTreeviewFrame
from .filter_frame import FilterFrame
from .scrub_frame import ScrubFrame
from .video_info_frame import VideoInfoFrame


class MainFrame(ttk.Frame):
    class __Widgets(NamedTuple):
        pane: ttk.PanedWindow
        filetree: FileMetaTreeviewFrame
        tabs: ttk.Notebook
        vidinfo: VideoInfoFrame
        filters: FilterFrame
        scrubber: ScrubFrame

    _ctx: UiContext
    _widgets: __Widgets

    def __init__(
        self,
        parent: tk.Frame | tk.Tk,
        ctx: UiContext,
        *args: Any,
        **kw: Any,
    ):
        super().__init__(parent, *args, **kw)
        self._ctx = ctx
        ctx.state.busy_changed.connect(self._handle_busy)

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        tabs = ttk.Notebook(pane)
        self._widgets = __class__.__Widgets(
            pane=pane,
            filetree=FileMetaTreeviewFrame(pane, ctx),
            tabs=tabs,
            filters=FilterFrame(tabs, ctx),
            vidinfo=VideoInfoFrame(tabs, ctx),
            scrubber=ScrubFrame(tabs, ctx),
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

    def _handle_busy(self, busy: bool) -> None:
        if busy:
            self.busy_hold(cursor=TkCursor.WATCH)
        else:
            self.busy_forget()
