import tkinter as tk
from tkinter import ttk
from typing import NamedTuple

from ui.better_treeview import ScrollableTreeviewFrame

from .actions import UiContext
from .state import ActorCounts, FilterOperator, TagCounts


class FilterFrame(ttk.Frame):
    class __Widgets(NamedTuple):
        actions: ttk.Frame
        scan: ttk.Button
        filter_and: ttk.Button
        filter_or: ttk.Button
        filter_clear: ttk.Button
        actors: ScrollableTreeviewFrame
        tags: ScrollableTreeviewFrame

    _ctx: UiContext
    _widgets: __Widgets

    def __init__(self, parent, ctx: UiContext, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._ctx = ctx

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
        self._widgets.scan.config(command=ctx.actions.scan_metadata)
        self._widgets.scan.grid(column=0, row=0, sticky="W", padx=2, pady=2)
        self._widgets.filter_and.config(
            command=lambda: ctx.actions.apply_filters(*self._selection(), operator=FilterOperator.AND)
        )
        self._widgets.filter_and.grid(column=1, row=0, sticky="E", padx=2, pady=2)
        self._widgets.filter_or.config(
            command=lambda: ctx.actions.apply_filters(*self._selection(), operator=FilterOperator.OR)
        )
        self._widgets.filter_or.grid(column=2, row=0, sticky="E", padx=2, pady=2)
        self._widgets.filter_clear.config(command=ctx.actions.clear_filters)
        self._widgets.filter_clear.grid(column=3, row=0, sticky="E", padx=2, pady=2)

        self._widgets.actors.child.heading("#0", text="Actors")
        self._widgets.actors.child.heading("count", text="#")
        self._widgets.actors.child.column("count", minwidth=10, width=50, stretch=False)
        self._widgets.actors.child.bind(sequence="<<TreeviewSelect>>", func=self._handle_actors_select)
        self._widgets.actors.grid(column=0, row=1, sticky="NSEW", padx=2, pady=2)
        self._widgets.tags.child.heading("#0", text="Tags")
        self._widgets.tags.child.heading("count", text="#")
        self._widgets.tags.child.column("count", minwidth=10, width=50, stretch=False)
        self._widgets.tags.child.bind("<<TreeviewSelect>>", self._handle_tags_select)
        self._widgets.tags.grid(column=1, row=1, sticky="NSEW", padx=2, pady=2)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ctx.state.actor_counts_changed.connect(self._set_actors)
        ctx.state.tag_counts_changed.connect(self._set_tags)

    def _selection(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            tuple(self._widgets.actors.child.selection()),
            tuple(self._widgets.tags.child.selection()),
        )

    def _set_actors(self, value: ActorCounts) -> None:
        tv = self._widgets.actors.treeview
        tv.clear()
        for i in sorted(value.counts.keys()):
            tv.insert("", tk.END, i, text=str(i), values=(value.counts[i],))

    def _set_tags(self, value: TagCounts) -> None:
        tv = self._widgets.tags.treeview
        tv.clear()
        for i in sorted(value.counts.keys()):
            tv.insert("", tk.END, i, text=str(i), values=(value.counts[i],))

    def _handle_actors_select(self, ev: tk.Event) -> None:
        actors, tags = self._selection()
        self._ctx.actions.set_highlights(actors, tags)

    def _handle_tags_select(self, ev: tk.Event) -> None:
        actors, tags = self._selection()
        self._ctx.actions.set_highlights(actors, tags)
