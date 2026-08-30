from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, NamedTuple

from util.ui.tk_event_data import DataEvents

from .constants import VirtualEventSequence
from .file_meta_treeview import FileMetaTreeview
from .filter_frame import FilterFrame
from .video_info_frame import VideoInfoFrame


class MainFrame(DataEvents, ttk.Frame):
    class _Widgets(NamedTuple):
        pane: ttk.PanedWindow
        filetree: FileMetaTreeview
        tabs: ttk.Notebook
        vidinfo: VideoInfoFrame
        filters: FilterFrame

    _basepath: Path | None

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
        self._widgets = __class__._Widgets(
            pane=pane,
            filetree=FileMetaTreeview(pane),
            tabs=tabs,
            vidinfo=VideoInfoFrame(tabs),
            filters=FilterFrame(tabs),
        )
        self._widgets.pane.add(self._widgets.filetree.container)
        self._widgets.pane.add(self._widgets.tabs)
        self._widgets.pane.pack(fill=tk.BOTH, expand=True)

        self._widgets.tabs.add(self._widgets.filters, text="Filters")
        self._widgets.tabs.add(self._widgets.vidinfo, text="Video Info")
        self._widgets.tabs.select(1)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        def _ctrlkey(event: tk.Event) -> None:
            if event.keysym == "s":
                self.event_generate(VirtualEventSequence.SAVE_METADATA)
            if event.keysym == "g":
                self.event_generate(VirtualEventSequence.GENERATE_THUMBS)

        self.bind_all("<Control-KeyPress>", _ctrlkey)

        self._widgets.filters.bind(VirtualEventSequence.FILTERS_AND, lambda event: self.apply_filters(operator="AND"))
        self._widgets.filters.bind(VirtualEventSequence.FILTERS_OR, lambda event: self.apply_filters(operator="OR"))
        self._widgets.filters.bind(VirtualEventSequence.FILTERS_CLEAR, self._handle_clear_filters)
        self._widgets.filters.bind(VirtualEventSequence.APPLY_HIGHHIGHT, self._handle_apply_highlight)

    @property
    def basepath(self) -> Path:
        return self.basepath

    @basepath.setter
    def basepath(self, path: Path) -> None:
        if path.is_dir():
            self._basepath = path
            self._widgets.filetree.root_path = path
            self._widgets.filetree.update()

    def extensions(self, *extensions: str) -> None:
        self._widgets.filetree.add_extensions(*extensions)

    @property
    def metadata(self):
        return self._widgets.vidinfo.metadata

    @metadata.setter
    def metadata(self, value: dict) -> None:
        self._widgets.vidinfo.metadata = value

    @property
    def selected_file(self) -> Path | None:
        if len(self._widgets.filetree.selection()) > 0:
            return Path(self._widgets.filetree.selection()[0])

    def set_actors(self, items: dict):
        self._widgets.filetree.with_meta_columns(True)
        self._widgets.filters._widgets.actors.clear()
        for i in sorted(items.keys()):
            self._widgets.filters._widgets.actors.insert("", tk.END, i, text=str(i), values=(items[i]))

    def set_tags(self, items: dict) -> None:
        self._widgets.filetree.with_meta_columns(True)
        self._widgets.filters._widgets.tags.clear()
        for i in sorted(items.keys()):
            self._widgets.filters._widgets.tags.insert("", tk.END, i, text=str(i), values=(items[i]))

    def apply_filters(self, operator: str = "OR") -> None:
        self._widgets.filetree.apply_filters(
            self._widgets.filters._widgets.actors.selection(),
            self._widgets.filters._widgets.tags.selection(),
            operator=operator,
        )

    def _handle_clear_filters(self, event: tk.Event) -> None:
        self._widgets.filetree.unhide_all()

    def _handle_apply_highlight(self, event: tk.Event) -> None:
        self._widgets.filetree.apply_highlight(
            self._widgets.filters._widgets.actors.selection(),
            self._widgets.filters._widgets.tags.selection(),
        )
