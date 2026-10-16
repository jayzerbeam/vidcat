import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk
from typing import Any, NamedTuple

from browser.metadata import Bookmark
from ui.scrollable import ScrollableWidgetFrame
from util.format import clock_format


class BookmarkFrame(ttk.Frame):
    """Dumb bookmark list: renders the bookmarks it is given and forwards user actions to handlers.

    Holds no metadata/session knowledge and no selection state beyond what is rendered.
    """

    class __Widgets(NamedTuple):
        bookmarks: ScrollableWidgetFrame[ttk.Treeview]
        name: ttk.Entry
        add: ttk.Button

    _widgets: __Widgets
    _rows: dict[str, Bookmark]
    _enabled: bool
    _add_handler: Callable[[str], bool] | None
    _seek_handler: Callable[[Bookmark], None] | None
    _remove_handler: Callable[[Bookmark], None] | None

    def __init__(self, parent: tk.Misc, *, width: int = 200, **kwargs: Any) -> None:
        super().__init__(parent, width=width, **kwargs)
        self._rows = {}
        self._enabled = True
        self._add_handler = None
        self._seek_handler = None
        self._remove_handler = None

        self._widgets = __class__.__Widgets(
            bookmarks=ScrollableWidgetFrame(
                self,
                child_type=ttk.Treeview,
                child_params={"columns": ("time", "name"), "show": "headings", "selectmode": tk.BROWSE},
                xscrollable=False,
            ),
            name=ttk.Entry(self),
            add=ttk.Button(self, text="Bookmark", command=self._handle_add),
        )

        treeview = self._widgets.bookmarks.child
        treeview.heading("time", text="Time")
        treeview.heading("name", text="Name")
        treeview.column("time", width=80, minwidth=40, stretch=False)
        treeview.column("name", width=90, minwidth=40, stretch=True)
        treeview.bind("<Button-1>", self._handle_click, add=True)
        treeview.bind("<<TreeviewSelect>>", self._handle_select, add=True)
        treeview.bind("<Delete>", self._handle_delete, add=True)

        # gridded children otherwise win the width negotiation and override the requested frame width
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._widgets.bookmarks.grid(row=0, column=0, sticky="NSEW")
        self._widgets.name.grid(row=1, column=0, sticky="EW")
        self._widgets.add.grid(row=2, column=0, sticky="EW")
        self._widgets.name.bind("<Return>", self._handle_add)

    def set_bookmarks(self, bookmarks: Sequence[Bookmark]) -> None:
        """Render bookmarks (expected sorted by time_ms) as rows keyed by str(time_ms)."""
        treeview = self._widgets.bookmarks.child
        treeview.delete(*treeview.get_children())
        self._rows.clear()
        for bookmark in bookmarks:
            iid = str(bookmark.time_ms)
            if iid in self._rows:
                # a hand-edited sidecar can repeat a time_ms; re-inserting an iid raises in Tk
                continue
            time_text = clock_format(bookmark.time_ms / 1000, decimals=3) or ""
            treeview.insert("", tk.END, iid=iid, values=(time_text, bookmark.name))
            self._rows[iid] = bookmark

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._widgets.bookmarks.child.configure(selectmode=tk.BROWSE if enabled else tk.NONE)
        state = ["!disabled"] if enabled else ["disabled"]
        self._widgets.name.state(state)
        self._widgets.add.state(state)

    def set_add_handler(self, handler: Callable[[str], bool]) -> None:
        self._add_handler = handler

    def set_seek_handler(self, handler: Callable[[Bookmark], None]) -> None:
        self._seek_handler = handler

    def set_remove_handler(self, handler: Callable[[Bookmark], None]) -> None:
        self._remove_handler = handler

    def _handle_click(self, ev: tk.Event) -> None:
        if not self._enabled:
            return
        treeview = self._widgets.bookmarks.child
        if treeview.identify("region", ev.x, ev.y) in ("heading", "separator"):
            return
        bookmark = self._rows.get(treeview.identify_row(ev.y))
        if bookmark is not None and self._seek_handler is not None:
            self._seek_handler(bookmark)

    def _handle_select(self, ev: tk.Event) -> None:
        if not self._enabled:
            return
        # deleting all rows fires this with an empty selection
        selection = self._widgets.bookmarks.child.selection()
        if not selection:
            return
        bookmark = self._rows.get(selection[0])
        if bookmark is not None and self._seek_handler is not None:
            self._seek_handler(bookmark)

    def _handle_delete(self, ev: tk.Event) -> None:
        if not self._enabled:
            return
        selection = self._widgets.bookmarks.child.selection()
        if not selection:
            return
        bookmark = self._rows.get(selection[0])
        if bookmark is not None and self._remove_handler is not None:
            self._remove_handler(bookmark)

    def _handle_add(self, *_args: Any) -> None:
        if not self._enabled or self._add_handler is None:
            return
        if self._add_handler(self._widgets.name.get().strip()):
            self._widgets.name.delete(0, tk.END)
