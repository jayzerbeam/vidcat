import tkinter as tk
from collections.abc import Mapping
from tkinter import ttk
from typing import NamedTuple

from .tk_event_data import DataEvents

ScrollableWidget = tk.Canvas | ttk.Treeview | tk.Entry | tk.Listbox


class ScrollableWidgetFrame[T: ScrollableWidget](DataEvents, ttk.Frame):
    _scroll_step: int

    class _Widgets(NamedTuple):
        child: T
        xscrollbar: ttk.Scrollbar | None
        yscrollbar: ttk.Scrollbar | None

    def __init__(
        self,
        parent,
        child_type: type[T],
        child_params: Mapping = {},
        xscrollable: bool = True,
        yscrollable: bool = True,
        scroll_step: int = 3,
        *args,
        **kw,
    ):
        super().__init__(parent, *args, **kw)
        self._scroll_step = scroll_step

        child = child_type(self, **child_params)
        child.grid(column=0, row=0, sticky="NSEW")
        xscroll = yscroll = None
        if xscrollable:
            xscroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=child.xview)
            xscroll.grid(column=0, row=1, sticky="EW")
            child.config(xscrollcommand=xscroll.set)
        if yscrollable and hasattr(child, "yview"):
            yscroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=child.yview)
            yscroll.grid(column=1, row=0, sticky="NS")
            child.config(yscrollcommand=yscroll.set)

        self._widgets = __class__._Widgets(child=child, xscrollbar=xscroll, yscrollbar=yscroll)

        def _mwheel(event) -> None:
            if yscrollable and hasattr(child, "yview"):
                self._widgets.child.yview_scroll(int(-1 * (event.delta / 120) * (self._scroll_step - 1)), "units")
            elif xscrollable and hasattr(child, "xview"):
                self._widgets.child.xview_scroll(int(-1 * (event.delta / 120) * (self._scroll_step - 1)), "units")

        self.bind("<MouseWheel>", _mwheel)

        # self.grid(column=0, row=0, sticky="NSEW")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def config(self, *args, **kw):
        if "scroll_step" in kw:
            self._scroll_step = kw["scroll_step"]
            del kw["scroll_step"]
        return super().config(*args, **kw)

    @property
    def child(self) -> T:
        return self._widgets.child

    @property
    def xscrollbar(self) -> ttk.Scrollbar | None:
        return self._widgets.xscrollbar

    @property
    def yscrollbar(self) -> ttk.Scrollbar | None:
        return self._widgets.yscrollbar
