import os
import re
import tkinter as tk
from collections.abc import Callable
from tkinter import StringVar, ttk


class LabeledEntry(ttk.Frame):
    def __init__(
        self,
        parent,
        label: str = "",
        textvariable: StringVar | None = None,
        *args,
        **kw,
    ):
        self.ui = {}
        super().__init__(parent, *args, **kw)
        self.ui["label"] = ttk.Label(self, text=label)
        self.ui["label"].grid(row=0, sticky="W")
        self.ui["entry"] = ttk.Entry(self)
        if textvariable is not None:
            self.ui["entry"].configure(textvariable=textvariable)
        self.ui["entry"].grid(row=1, sticky="EW", padx=4)
        self.columnconfigure(0, weight=1)

    def get_text(self):
        return self.ui["entry"].get()


class EditableList(tk.Frame):
    def __init__(
        self,
        parent,
        label: str = "",
        items: list | None = None,
        sorted: bool = True,
        *args,
        **kw,
    ):
        super().__init__(parent, *args, **kw)
        if items is None:
            items = []

        self.ui = {}
        self.items: list = []
        self.sorted: bool = sorted
        self.on_add_func: Callable | None = None
        self.ui["label"] = ttk.Label(self, text=label)
        self.ui["label"].grid(column=0, row=0, columnspan=2, sticky="W")
        self.ui["entry"] = ttk.Entry(self)
        self.ui["entry"].grid(column=0, row=1, sticky="EW", padx=3)
        self.ui["list"] = tk.Listbox(self, selectmode=tk.EXTENDED, height=0, width=0)
        self.ui["list"].grid(
            column=0, row=2, columnspan=2, sticky="NSEW", padx=2, pady=2
        )
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.add_items(items)

        def _add_entry(*args) -> None:
            entry = self.ui["entry"].get()
            if self.on_add_func and callable(self.on_add_func):
                entry = self.on_add_func(entry)
            if entry:
                self.add_items((entry,))
                self.ui["entry"].delete(0, tk.END)

        self.ui["entry"].bind("<Return>", _add_entry)

        def _remove_entry(*args) -> None:
            for idx in reversed(self.ui["list"].curselection()):
                self.ui["list"].delete(idx)
                del self.items[idx]

        self.ui["list"].bind("<Delete>", _remove_entry)

    def list_height(self, height: int) -> None:
        self.ui["list"].config(height=height)

    def add_items(self, items: list | tuple) -> None:
        for i in items:
            if self.sorted:
                idx = 0
                for val in self.items:
                    if i < val:
                        break
                    idx = idx + 1
                self.items.insert(idx, i)
                self.ui["list"].insert(idx, i)
            else:
                self.items.append(i)
                self.ui["list"].insert(tk.END, i)

    def sort_items(self) -> None:
        self.items.sort()
        self.ui["list"].delete(0, tk.END)
        self.ui["list"].insert(0, self.items)

    def clear_items(self) -> None:
        self.items.clear()
        self.ui["list"].delete(0, tk.END)

    def on_add_handler(self, func: Callable) -> None:
        self.on_add_func = func


# class ScrolledList(tk.Listbox):
#    def __init__(self, parent, *args, **kw):
#        container = ttk.Frame(parent)
#        super().__init__(container, *args, **kw)
#        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=listbox.yview)
#        listbox.config(yscrollcommand=scrollbar.set)
#        # listbox.pack(expand = True, fill = tk.BOTH, side = tk.LEFT)
#        # scrollbar.pack(expand = True, fill = tk.Y, side = tk.RIGHT)
#        self.grid(column=0, row=0, sticky="NSEW")
#        scrollbar.grid(column=1, row=0, sticky="NS")
#        container.columnconfigure(0, weight=1)
#        container.rowconfigure(0, weight=1)
#
#        self.ui = {"container": container, "scrollbar": scrollbar}
#
#    @property
#    def container(self):
#        return self.ui["container"]
#
#    @property
#    def scrollbar(self):
#        return self.ui["scrollbar"]


class ScrolledTreeview(ttk.Treeview):
    ASC = ASCENDING = "ascending"
    DESC = DESCENDING = "descending"

    def __init__(self, parent, sortable: bool = False, step: int = 3, *args, **kw):
        container = ttk.Frame(parent)
        super().__init__(container, *args, **kw)
        self.sortable = sortable
        self.step = step
        self.sort_direction = __class__.DESC
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.yview)
        self.config(yscrollcommand=scrollbar.set)
        self.grid(column=0, row=0, sticky="NSEW")
        scrollbar.grid(column=1, row=0, sticky="NS")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self.ui = {"container": container, "scrollbar": scrollbar}

        def _click(event) -> None:
            if self.sortable:
                region = self.identify("region", event.x, event.y)
                column = self.identify_column(event.x)
                if region == "heading":
                    self.sort_on_column(column)

        self.bind("<Button-1>", _click)

        def _mwheel(event) -> None:
            self.yview_scroll(
                int(-1 * (event.delta / 120) * (self.step - 1)), "units"
            )  # step - 1 accounts default scroll binding

        self.bind("<MouseWheel>", _mwheel)

    def config(self, *args, **kw) -> None:
        if "step" in kw:
            self.step = kw["step"]
            del kw["step"]
        if "sortable" in kw:
            self.sortable = kw["sortable"]
            del kw["sortable"]
        return super().config(*args, **kw)

    @property
    def container(self):
        return self.ui["container"]

    @property
    def scrollbar(self):
        return self.ui["scrollbar"]

    def clear(self) -> None:
        for item in self.get_children(""):
            self.delete(item)

    # TODO check out of bounds
    def sort_on_column(self, column: str) -> None:
        items = []
        column = column.strip("#")
        self.sort_direction = (
            __class__.DESC if self.sort_direction == __class__.ASC else __class__.ASC
        )
        for item in self.get_children(""):
            itemconfig = self.item(item)
            items.append((item, itemconfig["text"], *itemconfig["values"]))
            self.detach(item)
        items.sort(
            key=lambda item: item[int(column) + 1],
            reverse=self.sort_direction == __class__.DESC,
        )
        for item in items:
            self.move(item[0], "", tk.END)


class FileTreeview(ScrolledTreeview):
    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, selectmode=tk.BROWSE, **kw)
        self._p = {}
        self._p["path"] = ""
        self._p["filters"] = []
        self._p["extensions"] = []
        self.hidden_items = {}

        def _click(evtype) -> None:
            if os.path.isfile(self.selection()[0]):
                if evtype == "exec":
                    self.event_generate("<<FileExec>>")
                else:
                    self.event_generate("<<FileSelect>>")

        self.bind("<Double-Button-1>", lambda event: _click("exec"))
        self.bind("<<TreeviewSelect>>", lambda event: _click("select"))

    @property
    def root_path(self) -> str:
        return self._p["path"]

    @root_path.setter
    def root_path(self, path: str) -> None:  # TODO use pathlib.Path
        if not os.path.isdir(path):
            raise ValueError(f"{path} is not a directory")
        self._p["path"] = os.path.abspath(path)

    @property
    def filters(self):
        return self._p["filters"]

    def add_filter(self, regex: re.Pattern) -> None:
        if isinstance(regex, type(re.compile("null"))):
            self._p["filters"].append(regex)

    @property
    def extensions(self):
        return self._p["extensions"]

    def add_extensions(self, exts: list[str] | tuple[str, ...]) -> None:
        self._p["extensions"].extend(exts)
        self._p["extensions"].sort()

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

    def count_files(self):
        return self._count_child_tags("", "file")

    def count_dirs(self):
        return self._count_child_tags("", "dir")

    def update(self) -> None:
        def _filtered(filename: str) -> bool:
            if len(self.filters) == 0:
                return True
            for f in self.filters:
                if f.match(filename):
                    return True
            return False

        def _scandir(path: str, parent_iid: str) -> None:
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
                    _scandir(os.path.join(path, entry.name), iid)
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

        self.heading("#0", text=self._p["path"])
        _scandir(self._p["path"], "")

    def hide(self, item) -> None:
        self.hidden_items[item] = self.parent(item)  # key => item, value => parent
        self.detach(item)

    # always inserts at end
    def unhide(self, item) -> None:
        parent = self.hidden_items[item]
        for sibling in self.get_children(parent):
            if item.lower() > sibling.lower():
                self.move(item, parent, self.index(sibling) + 1)
                break
        del self.hidden_items[item]

    # this doesn't guarantee items will go back in their original order
    def unhide_all(self) -> None:
        for item in self.hidden_items:
            self.move(item, self.hidden_items[item], tk.END)
        self.hidden_items.clear()

    def process_items(self, func: Callable) -> None:
        if not isinstance(func, Callable):
            raise TypeError("func is not callable")

        def _recurse(item):
            func(self, item)
            for child in self.get_children(item):
                _recurse(item)

        _recurse("")


# somewhat inefficient: rebuilds the whole button widgets with any path change
class FilePathSelector(ttk.Frame):
    def __init__(self, parent, path=None):
        super().__init__(parent)
        self.path = path
        self.ui = {"path_widgets": []}
        # self.ui['base_path'] = ttk.Label(self, text = base_path)
        # self.ui['base_path'].grid(column = 0, row = 0, columnspan = 2, padx = 4, pady = 4, sticky = "W")
        if path:
            self.set_path(path)

    def set_path(self, path) -> None:
        def _dir_clicked(path):
            self.set_path(path)

        self.path = path
        splitpath = path.split("\\")
        for widget in self.ui["path_widgets"]:
            widget.destroy()
            widget = None
        for idx, d in enumerate(splitpath):
            button = ttk.Button(
                self,
                text=d,
                width=0,
                command=lambda d=d: _dir_clicked("\\".join(splitpath[0:idx])),
            )
            button.pack(side=tk.LEFT)
            self.ui["path_widgets"].append(button)
            if idx < len(splitpath) - 1:
                label = ttk.Label(self, text="\\", width=0)
                label.pack(side=tk.LEFT)
                self.ui["path_widgets"].append(label)
