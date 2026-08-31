import os
import re
import tkinter as tk
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from tkinter import ttk
from typing import Any

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

    def clear(self) -> None:
        for item in self.get_children(""):
            self.delete(item)

    # TODO check out of bounds
    def sort_on_column(self, column: str) -> None:
        if not self._sortable:
            return

        items = []
        column = column.strip("#")
        self._sort_dir = SortDir.DESC if self._sort_dir == SortDir.ASC else SortDir.ASC
        for item in self.get_children(""):
            itemconfig = self.item(item)
            items.append((item, itemconfig["text"], itemconfig["values"]))
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

        def _click(evtype) -> None:
            match evtype:
                case "exec":
                    self.treeview.event_generate(VirtualEventSequence.FILE_EXEC)
                case "select" | _:
                    self.treeview.event_generate(VirtualEventSequence.FILE_SELECT)

        self.treeview.bind("<Double-Button-1>", lambda event: _click("exec"))
        self.treeview.bind(VirtualEventSequence.TREEVIEW_SELECT, lambda event: _click("select"))

    @property
    def root_path(self) -> Path | None:
        return self._root_path

    @root_path.setter
    def root_path(self, path: Path) -> None:
        if not path.is_dir():
            raise ValueError(f"{path} is not a directory")
        self._root_path = path

    def add_filter(self, regex: re.Pattern) -> None:
        if isinstance(regex, type(re.compile("null"))):
            self._filters.append(regex)

    @property
    def extensions(self) -> list[str]:
        return self._extensions

    def add_extensions(self, *exts: str) -> None:
        self._extensions.extend(exts)
        self._extensions.sort()

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

    def _count_child_tags(self, item, item_tag) -> int:
        def _recurse(item):
            c = 0
            if self.treeview.tag_has(item_tag, item):
                c += 1
            for child in self.treeview.get_children(item):
                c += _recurse(child)
            return c

        return _recurse(item)

    def count_files(self) -> int:
        return self._count_child_tags("", "file")

    def count_dirs(self) -> int:
        return self._count_child_tags("", "dir")

    # TODO: refactor out the file scanning to separate interface
    def update(self) -> None:
        def _filtered(filename: str) -> bool:
            if len(self._filters) == 0:
                return True
            for f in self._filters:
                if f.match(filename):
                    return True
            return False

        def _scandir(path: Path, parent_iid: str) -> None:
            files = []  # cache files so that they can be added after directories
            for entry in os.scandir(path):
                if not _filtered(entry.name):
                    continue

                iid = os.path.join(path, entry.name)
                if entry.is_dir():
                    self.treeview.insert(
                        parent_iid,
                        tk.END,
                        iid=iid,
                        text=f"[{entry.name}]",
                        tags=["dir"],
                    )
                    _scandir(path / entry.name, iid)
                    # remove directories with nothing in them
                    if not self.treeview.get_children(iid):
                        self.treeview.delete(iid)
                else:
                    _, ext = os.path.splitext(entry.name)
                    if ext in self.extensions:
                        files.append(entry)

            for file in files:
                self.treeview.insert(
                    parent_iid,
                    tk.END,
                    os.path.join(path, file.name),
                    text=file.name,
                    tags=["file"],
                )

        if self._root_path is not None:
            # self.heading("#0", text=str(self._root_path.resolve()))
            _scandir(self._root_path, "")

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

    def process_items(self, func: Callable) -> None:
        if not isinstance(func, Callable):
            raise TypeError("func is not callable")

        def _recurse(item):
            func(self, item)
            for child in self.treeview.get_children(item):
                _recurse(item)

        _recurse("")
