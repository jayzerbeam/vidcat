import tkinter as tk
from tkinter import ttk
from typing import NamedTuple

from ui.better_treeview import ScrollableTreeviewFrame
from ui.constants import VirtualEventSequence as VEvent

from .constants import TkVarNames
from .constants import VirtualEventSequence as BVEvent


class FilterFrame(ttk.Frame):
    class __Widgets(NamedTuple):
        actions: ttk.Frame
        scan: ttk.Button
        filter_and: ttk.Button
        filter_or: ttk.Button
        filter_clear: ttk.Button
        actors: ScrollableTreeviewFrame
        tags: ScrollableTreeviewFrame

    class __Vars(NamedTuple):
        actors: tk.Variable
        tags: tk.Variable

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)

        self._vars = __class__.__Vars(
            actors=tk.Variable(name=TkVarNames.HIGHLIGHTED_ACTORS),
            tags=tk.Variable(name=TkVarNames.HIGHLIGHTED_TAGS),
        )
        actions = ttk.Frame(self)
        self._widgets: __class__.__Widgets = __class__.__Widgets(
            actions=actions,
            scan=ttk.Button(actions, text="Scan"),
            filter_and=ttk.Button(actions, text="Filter AND"),
            filter_or=ttk.Button(actions, text="Filter OR"),
            filter_clear=ttk.Button(actions, text="Clear Filters"),
            actors=ScrollableTreeviewFrame(self, xscrollable=False, columns=("count",), sortable=True),
            tags=ScrollableTreeviewFrame(self, xscrollable=False, columns=("count",), sortable=True),
        )

        self._widgets.actions.grid(column=0, row=0, columnspan=2)
        # configured inside actions actions frame
        self._widgets.scan.config(command=lambda: self.event_generate(BVEvent.SCAN_METADATA))
        self._widgets.scan.grid(column=0, row=0, sticky="W", padx=2, pady=2)
        self._widgets.filter_and.config(command=lambda: self.event_generate(BVEvent.FILTERS_AND))
        self._widgets.filter_and.grid(column=1, row=0, sticky="E", padx=2, pady=2)
        self._widgets.filter_or.config(command=lambda: self.event_generate(BVEvent.FILTERS_OR))
        self._widgets.filter_or.grid(column=2, row=0, sticky="E", padx=2, pady=2)
        self._widgets.filter_clear.config(command=lambda: self.event_generate(BVEvent.FILTERS_CLEAR))
        self._widgets.filter_clear.grid(column=3, row=0, sticky="E", padx=2, pady=2)

        self._widgets.actors.grid(column=0, row=1, sticky="NSEW", padx=2, pady=2)
        self._widgets.actors.child.heading("#0", text="Actors")
        self._widgets.actors.child.heading("count", text="#")
        self._widgets.actors.child.column("count", minwidth=10, width=50, stretch=False)
        self._widgets.actors.child.bind(sequence=VEvent.TREEVIEW_SELECT, func=self._handle_actors_select)
        self._widgets.tags.child.heading("#0", text="Tags")
        self._widgets.tags.child.heading("count", text="#")
        self._widgets.tags.child.column("count", minwidth=10, width=50, stretch=False)
        self._widgets.tags.child.bind(VEvent.TREEVIEW_SELECT, self._handle_tags_select)
        self._widgets.tags.grid(column=1, row=1, sticky="NSEW", padx=2, pady=2)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

    def _handle_actors_select(self, ev: tk.Event) -> None:
        self._vars.actors.set(self._widgets.actors.child.selection())

    def _handle_tags_select(self, ev: tk.Event) -> None:
        self._vars.tags.set(self._widgets.tags.child.selection())
