import os
import re
import tkinter as tk
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from tkinter import ttk
from typing import Any, NamedTuple

from .constants import VirtualEventSequence
from .tk_event_data import DataEvents


class SortDir(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class ScrollableTreeview(DataEvents, ttk.Treeview):
    _sortable: bool
    _step: int
    _sort_dir: SortDir

    class _Widgets(NamedTuple):
        container: ttk.Frame
        scrollbar: ttk.Scrollbar

    def __init__(self, parent, sortable: bool = False, step: int = 3, *args, **kw):
        container = ttk.Frame(parent)
        self._widgets = __class__._Widgets(
            container=container,
            scrollbar=ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.yview),
        )
        super().__init__(container, *args, **kw)

        self._sortable = sortable
        self._step = step
        self._sort_dir = SortDir.DESC

        self.config(yscrollcommand=self._widgets.scrollbar.set)
        self.grid(column=0, row=0, sticky="NSEW")
        self._widgets.scrollbar.grid(column=1, row=0, sticky="NS")
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)

        def _click(event) -> None:
            if self._sortable:
                region = self.identify("region", event.x, event.y)
                column = self.identify_column(event.x)
                if region == "heading":
                    self.sort_on_column(column)

        self.bind("<Button-1>", _click)

        def _mwheel(event) -> None:
            self.yview_scroll(
                int(-1 * (event.delta / 120) * (self._step - 1)), "units"
            )  # step - 1 accounts default scroll binding

        self.bind("<MouseWheel>", _mwheel)

    def config(self, *args, **kw):
        if "step" in kw:
            self._step = kw["step"]
            del kw["step"]
        if "sortable" in kw:
            self._sortable = kw["sortable"]
            del kw["sortable"]
        return super().config(*args, **kw)

    @property
    def container(self) -> ttk.Frame:
        return self._widgets.container

    @property
    def scrollbar(self) -> ttk.Scrollbar:
        return self._widgets.scrollbar

    def clear(self) -> None:
        for item in self.get_children(""):
            self.delete(item)

    # TODO check out of bounds
    def sort_on_column(self, column: str) -> None:
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


class FileTreeview(ScrollableTreeview):
    asdf: str
    _root_path: Path | None
    _extensions: list[str]
    _filters: list[re.Pattern]
    _hidden_items: dict[str, Any]

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, selectmode=tk.BROWSE, **kw)
        self._root_path = None
        self._extensions = []
        self._filters = []
        self._hidden_items = {}

        def _click(evtype) -> None:
            match evtype:
                case "exec":
                    self.event_generate(VirtualEventSequence.FILE_EXEC)
                case "select" | _:
                    self.event_generate(VirtualEventSequence.FILE_SELECT)

        self.bind("<Double-Button-1>", lambda event: _click("exec"))
        self.bind(VirtualEventSequence.TREEVIEW_SELECT, lambda event: _click("select"))

    @property
    def root_path(self) -> Path | None:
        return self._root_path

    @root_path.setter
    def root_path(self, path: Path) -> None:
        if not path.is_dir():
            raise ValueError(f"{path} is not a directory")
        self._root_path = path

    @property
    def filters(self) -> list[re.Pattern]:
        return self._filters

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
                itemcfg = self.item(item)
                if len(set(itemcfg["tags"]) & set(with_tags)) > 0:
                    items.append(item)

            for child in self.get_children(item):
                _recurse(child)

        _recurse("")
        return items

    def _count_child_tags(self, item, item_tag) -> int:
        def _recurse(item):
            c = 0
            if self.tag_has(item_tag, item):
                c += 1
            for child in self.get_children(item):
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
            if len(self.filters) == 0:
                return True
            for f in self.filters:
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
                    self.insert(
                        parent_iid,
                        tk.END,
                        iid=iid,
                        text=f"[{entry.name}]",
                        tags=["dir"],
                    )
                    _scandir(path / entry.name, iid)
                    # remove directories with nothing in them
                    if not self.get_children(iid):
                        self.delete(iid)
                else:
                    _, ext = os.path.splitext(entry.name)
                    if ext in self.extensions:
                        files.append(entry)

            for file in files:
                self.insert(
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
        self._hidden_items[item] = self.parent(item)  # key => item, value => parent
        self.detach(item)

    # always inserts at end
    def unhide(self, item) -> None:
        parent = self._hidden_items[item]
        for sibling in self.get_children(parent):
            if item.lower() > sibling.lower():
                self.move(item, parent, self.index(sibling) + 1)
                break
        del self._hidden_items[item]

    # this doesn't guarantee items will go back in their original order
    def unhide_all(self) -> None:
        for item in self._hidden_items:
            self.move(item, self._hidden_items[item], tk.END)
        self._hidden_items.clear()

    def process_items(self, func: Callable) -> None:
        if not isinstance(func, Callable):
            raise TypeError("func is not callable")

        def _recurse(item):
            func(self, item)
            for child in self.get_children(item):
                _recurse(item)

        _recurse("")
