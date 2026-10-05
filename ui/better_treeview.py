import tkinter as tk
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from tkinter import ttk
from typing import Any

from util.file.tree import PathTree

from .scrollable import ScrollableWidgetFrame


class SortDir(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class SortableTreeview(ttk.Treeview):
    _sort_dir = SortDir
    _sortable: bool

    def __init__(self, parent, sortable: bool = True, *args, **kwargs):
        self._sortable = sortable
        super().__init__(parent, *args, **kwargs)

        def _click(ev: tk.Event) -> None:
            region = self.identify("region", ev.x, ev.y)
            column = self.identify_column(ev.x)
            if region == "heading":
                self.sort_on_column(column)

        self.bind("<Button-1>", _click, add=True)

    def clear(self, from_iid: str = ""):
        self.delete(*self.get_children(from_iid))

    # TODO check out of bounds
    def sort_on_column(self, column: str) -> None:
        if not self._sortable:
            return

        items = []
        column = column.strip("#")
        self._sort_dir = SortDir.DESC if self._sort_dir == SortDir.ASC else SortDir.ASC
        for item in self.get_children(""):
            itemconfig = self.item(item)
            items.append((item, itemconfig["text"], *itemconfig["values"]))
            self.detach(item)
        items.sort(
            key=lambda item: item[int(column) + 1],
            reverse=self._sort_dir == SortDir.DESC,
        )
        for item in items:
            self.move(item[0], "", tk.END)


class ScrollableTreeviewFrame(ScrollableWidgetFrame):
    def __init__(
        self,
        parent,
        xscrollable: bool = True,
        yscrollable: bool = True,
        scroll_step: int = 3,
        sortable: bool = True,
        columns: tuple[str, ...] = (),
        *args,
        **kw,
    ):
        super().__init__(
            parent,
            *args,
            child_type=SortableTreeview,
            child_params={"columns": columns, "sortable": sortable},
            xscrollable=xscrollable,
            yscrollable=yscrollable,
            scroll_step=scroll_step,
            **kw,
        )

        self._scroll_step = scroll_step

    @property
    def treeview(self) -> SortableTreeview:
        return super().child


class FileTreeviewFrame(ScrollableTreeviewFrame):
    _hidden_items: dict[str, Any]

    def __init__(
        self,
        parent,
        on_activate: Callable[[Path], None],
        on_select: Callable[[Sequence[Path]], None],
        *args,
        **kw,
    ):
        super().__init__(parent, *args, **kw)
        self.treeview.configure(selectmode=tk.BROWSE)
        self._on_activate = on_activate
        self._on_select = on_select
        self._hidden_items = {}

        self.treeview.bind("<Double-Button-1>", self._handle_dclick, add=True)
        self.treeview.bind("<<TreeviewSelect>>", self._handle_select, add=True)

    def _handle_dclick(self, ev: tk.Event) -> None:
        if self.treeview.identify("region", ev.x, ev.y) == "heading":
            return
        iid = self.treeview.identify_row(ev.y)
        if iid:
            self._on_activate(Path(iid))

    def _handle_select(self, ev: tk.Event) -> None:
        self._on_select(tuple(Path(iid) for iid in self.treeview.selection()))

    def fill_from_pathtree(self, root_pt: PathTree, from_iid: str = "") -> None:
        # Hidden items are detached, so treeview.clear() leaves them behind and re-inserting the
        # refreshed subtree would fail with "item already exists". Drop hidden descendants first.
        for iid in tuple(self._hidden_items):
            if from_iid and iid != from_iid:
                parent = self._hidden_items[iid]
                while parent and parent != from_iid:
                    parent = self.treeview.parent(parent)
                if parent != from_iid:
                    continue
            if self.treeview.exists(iid):
                self.treeview.delete(iid)
            del self._hidden_items[iid]

        def _recurse(pt: PathTree, parent_iid: str) -> None:
            for d, child in pt.dirs():
                if child.is_empty:
                    continue

                iid = str(child.root)
                self.treeview.insert(
                    parent=parent_iid,
                    index=tk.END,
                    iid=iid,
                    text=f"[{d}]",
                    tags=["dir"],
                )
                _recurse(child, iid)

            for f in pt.files():
                self.treeview.insert(
                    parent=parent_iid,
                    index=tk.END,
                    iid=str(f),
                    text=f.name,
                    tags=["file"],
                )

        self.treeview.clear(from_iid)
        _recurse(root_pt, from_iid)

    def hide(self, item) -> None:
        self._hidden_items[item] = self.treeview.parent(item)  # key => item, value => parent
        self.treeview.detach(item)

    # always inserts at end
    def unhide(self, item) -> None:
        parent = self._hidden_items[item]
        for sibling in self.treeview.get_children(parent):
            if item.lower() > sibling.lower():
                self.treeview.move(item, parent, self.treeview.index(sibling) + 1)
                break
        del self._hidden_items[item]

    # this doesn't guarantee items will go back in their original order
    def unhide_all(self) -> None:
        for item in self._hidden_items:
            self.treeview.move(item, self._hidden_items[item], tk.END)
        self._hidden_items.clear()
