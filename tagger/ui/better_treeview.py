import re
import tkinter as tk
from enum import StrEnum
from pathlib import Path
from tkinter import ttk
from typing import Any

from util.file.tree import PathTree

from .constants import VirtualEventSequence
from .scrollable import ScrollableWidgetFrame
from .tk_event_data import DataEvents


class SortDir(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class SortableTreeview(DataEvents, ttk.Treeview):
    _sort_dir = SortDir
    _sortable: bool

    def __init__(self, parent, sortable: bool = True, *args, **kwargs):
        self._sortable = sortable
        super().__init__(parent, *args, **kwargs)

        def _click(event) -> None:
            region = self.identify("region", event.x, event.y)
            column = self.identify_column(event.x)
            if region == "heading":
                self.sort_on_column(column)

        self.bind("<Button-1>", _click)

    def config(self, *args, **kw):
        if "sortable" in kw:
            self._sortable = kw["sortable"]
            del kw["sortable"]
        return super().config(*args, **kw)

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
    _root_path: Path | None
    _extensions: list[str]
    _filters: list[re.Pattern]
    _hidden_items: dict[str, Any]

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self.treeview.configure(selectmode=tk.BROWSE)
        self._root_path = None
        self._extensions = []
        self._filters = []
        self._hidden_items = {}

        def _click(ev: tk.Event, type: str) -> None:
            if len(self.treeview.selection()) == 0:
                return

            tags = self.treeview.item(self.treeview.selection()[0]).get("tags", [])
            if "file" in tags:
                match type:
                    case "exec":
                        self.treeview.event_generate(VirtualEventSequence.FILE_EXEC)
                    case "select" | _:
                        self.treeview.event_generate(VirtualEventSequence.FILE_SELECT)

            if "dir" in tags:
                self.treeview.event_generate(VirtualEventSequence.DIR_SELECT)

        self.treeview.bind("<Double-Button-1>", lambda ev: _click(ev, "exec"), add=True)
        self.treeview.bind(VirtualEventSequence.TREEVIEW_SELECT, lambda ev: _click(ev, "select"), add=True)

    def add_filter(self, regex: re.Pattern) -> None:
        if isinstance(regex, type(re.compile("null"))):
            self._filters.append(regex)

    def get_items(self, with_tags: list | None) -> list:
        if with_tags is None:
            with_tags = []

        items: list = []

        def _recurse(item):
            if len(with_tags) <= 0:
                items.append(item)
            else:
                itemcfg = self.treeview.item(item)
                if len(set(itemcfg["tags"]) & set(with_tags)) > 0:
                    items.append(item)

            for child in self.treeview.get_children(item):
                _recurse(child)

        _recurse("")
        return items

    def fill_from_pathtree(self, root_pt: PathTree, from_iid: str = "") -> None:
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
