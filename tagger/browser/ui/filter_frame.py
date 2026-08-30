from tkinter import ttk
from typing import NamedTuple

from util.ui.better_treeview import ScrollableTreeview
from util.ui.constants import VirtualEventSequence as VEvent

from .constants import VirtualEventSequence as BVEvent


class FilterFrame(ttk.Frame):
    class _Widgets(NamedTuple):
        actions: ttk.Frame
        scan: ttk.Button
        filter_and: ttk.Button
        filter_or: ttk.Button
        filter_clear: ttk.Button
        actors: ScrollableTreeview
        tags: ScrollableTreeview

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)

        actions = ttk.Frame(self)
        self._widgets: __class__._Widgets = __class__._Widgets(
            actions=actions,
            scan=ttk.Button(actions, text="Scan"),
            filter_and=ttk.Button(actions, text="Filter AND"),
            filter_or=ttk.Button(actions, text="Filter OR"),
            filter_clear=ttk.Button(actions, text="Clear Filters"),
            actors=ScrollableTreeview(self, columns=("count"), sortable=True),
            tags=ScrollableTreeview(self, columns=("count"), sortable=True),
        )

        self._widgets.actions.grid(column=0, row=0, columnspan=2)
        self._widgets.scan.grid(column=0, row=0, sticky="W", padx=2, pady=2)
        self._widgets.filter_and.grid(column=1, row=0, sticky="E", padx=2, pady=2)
        self._widgets.filter_or.grid(column=2, row=0, sticky="E", padx=2, pady=2)
        self._widgets.filter_clear.grid(column=3, row=0, sticky="E", padx=2, pady=2)
        self._widgets.actors.heading("#0", text="Actors")
        self._widgets.actors.heading("#1", text="#")
        self._widgets.actors.column("#1", minwidth=10, width=50, stretch=False)
        self._widgets.actors.container.grid(column=0, row=1, sticky="NSEW", padx=2, pady=2)
        self._widgets.tags.heading("#0", text="Tags")
        self._widgets.tags.heading("#1", text="#")
        self._widgets.tags.column("#1", minwidth=10, width=50, stretch=False)
        self._widgets.tags.container.grid(column=1, row=1, sticky="NSEW", padx=2, pady=2)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self._widgets.scan.config(command=lambda: self.event_generate(BVEvent.SCAN_METADATA))
        self._widgets.filter_and.config(command=lambda: self.event_generate(BVEvent.FILTERS_AND))
        self._widgets.filter_or.config(command=lambda: self.event_generate(BVEvent.FILTERS_OR))
        self._widgets.filter_clear.config(command=lambda: self.event_generate(BVEvent.FILTERS_CLEAR))
        self._widgets.actors.bind(VEvent.TREEVIEW_SELECT, lambda ev: self.event_generate(BVEvent.APPLY_HIGHHIGHT))
        self._widgets.tags.bind(VEvent.TREEVIEW_SELECT, lambda ev: self.event_generate(BVEvent.APPLY_HIGHHIGHT))
