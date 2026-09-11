import tkinter as tk
from collections.abc import Callable, Sequence
from enum import Enum, auto
from pathlib import Path
from tkinter import ttk
from typing import Any, NamedTuple

from .tk_event_data import DataEvents


class LabeledEntryLayout(Enum):
    ONE_LINE = auto()
    TWO_LINE = auto()


class LabeledEntry(DataEvents, ttk.Frame):
    class _Widgets(NamedTuple):
        label: ttk.Label
        entry: ttk.Entry

    def __init__(
        self,
        parent,
        layout: LabeledEntryLayout,
        labelconf: dict[str, Any] | None = None,
        entryconf: dict[str, Any] | None = None,
        *args,
        **kw,
    ):
        super().__init__(parent, *args, **kw)
        self._widgets = __class__._Widgets(
            label=ttk.Label(self),
            entry=ttk.Entry(self),
        )
        if labelconf:
            self._widgets.label.configure(**labelconf)
        if entryconf:
            self._widgets.entry.configure(**entryconf)

        match layout:
            case LabeledEntryLayout.ONE_LINE:
                self._widgets.label.grid(column=1, row=0)
                self._widgets.entry.grid(column=2, row=0)

            case LabeledEntryLayout.TWO_LINE:
                self._widgets.label.grid(row=0, sticky="W")
                self._widgets.entry.grid(row=1, sticky="EW", padx=4)
        self.columnconfigure(0, weight=1)

    def entry_set(self, val: str) -> None:
        self._widgets.entry.delete(0, tk.END)
        self._widgets.entry.insert(0, val)

    def entry_get(self) -> str:
        return self._widgets.entry.get()


class EditableList(DataEvents, tk.Frame):
    class _Widgets(NamedTuple):
        label: ttk.Label
        entry: ttk.Entry
        list: tk.Listbox

    _sorted: bool
    _widgets: _Widgets
    _entry_filter: Callable[[str], str]

    def __init__(
        self,
        parent,
        label: str = "",
        init_items: Sequence[str] | None = None,
        sorted: bool = True,
        listboxconf: dict[str, Any] | None = None,
        *args,
        **kw,
    ):
        super().__init__(parent, *args, **kw)

        if listboxconf is None:
            listboxconf = {}

        self._widgets = __class__._Widgets(
            label=ttk.Label(self, text=label),
            entry=ttk.Entry(self),
            list=tk.Listbox(self, height=0, width=0, **listboxconf),
        )

        self._sorted = sorted
        self._on_add_func = lambda s: s
        self._widgets.label.grid(column=0, row=0, columnspan=2, sticky="W")
        self._widgets.entry.grid(column=0, row=1, sticky="EW", padx=3)
        self._widgets.list.grid(column=0, row=2, columnspan=2, sticky="NSEW", padx=2, pady=2)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        if init_items is not None:
            self.add_items(init_items)

        def _add_entry(*args) -> None:
            entry = self._widgets.entry.get()
            entry = self._entry_filter(entry)
            if entry:
                self.add_items((entry,))
                self._widgets.entry.delete(0, tk.END)

        self._widgets.entry.bind("<Return>", _add_entry)

        def _remove_entry(*args) -> None:
            for idx in reversed(self._widgets.list.curselection()):
                self._widgets.list.delete(idx)

        self._widgets.list.bind("<Delete>", _remove_entry)

    def list_height(self, height: int) -> None:
        self._widgets.list.config(height=height)

    @property
    def items(self) -> Sequence[str]:
        return self._widgets.list.curselection()

    def add_items(self, items: Sequence[str]) -> None:
        for item in items:
            if self._sorted:
                idx = 0
                for val in self._widgets.list.get(0, tk.END):
                    if item < val:
                        break
                    idx = idx + 1
                self._widgets.list.insert(idx, item)
            else:
                self._widgets.list.insert(tk.END, item)

    def clear_items(self) -> None:
        self._widgets.list.delete(0, tk.END)

    def set_entry_filter(self, func: Callable[[str], str]) -> None:
        self._entry_filter = func


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


# somewhat inefficient: rebuilds the whole button widgets with any path change
class FilePathSelector(DataEvents, ttk.Frame):
    class _Widgets(NamedTuple):
        path_widgets: list[ttk.Widget]

    def __init__(self, parent, path=None):
        super().__init__(parent)
        self.path = path
        self._widgets = __class__._Widgets(path_widgets=[])
        if path:
            self.set_path(path)

    def set_path(self, path: Path) -> None:
        def _dir_clicked(path: Path):
            self.set_path(path)

        self.path = path
        for widget in self._widgets.path_widgets:
            widget.destroy()
            widget = None

        for idx, p in enumerate(path.parts):
            button = ttk.Button(
                self,
                text=p,
                width=0,
                command=lambda i=idx: _dir_clicked(Path("\\".join(path.parts[0:i]))),
            )
            button.pack(side=tk.LEFT)
            self._widgets.path_widgets.append(button)
            label = ttk.Label(self, text="/", width=0)
            label.pack(side=tk.LEFT)
            self._widgets.path_widgets.append(label)
