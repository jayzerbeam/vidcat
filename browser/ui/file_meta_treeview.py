import tkinter as tk
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import Final, NamedTuple, cast

from browser.ui.actions import BulkAction, UiContext
from browser.ui.state import (
    ColumnsChanged,
    FileMetadataChanged,
    FileTreeUpdate,
    FilterOperator,
    FiltersChanged,
    HighlightsChanged,
    PathsRemoved,
)
from ui.better_treeview import FileTreeviewFrame
from util.format import clock_format, ellipsize
from util.typing import StringListy

_DATA_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("time", "Time"),
    ("res", "Res"),
    ("actors", "Actors"),
    ("tags", "Tags"),
)


def any_in_list(s1: set, s2: set, case_sensitive: bool = False) -> bool:
    if not case_sensitive:
        s1 = set(map(str.lower, s1))
        s2 = set(map(str.lower, s2))

    return len(s1 & s2) > 0


class FileMetaTreeviewFrame(FileTreeviewFrame):
    """A FileTreeviewFrame that adds columns and functionality for actors and tags"""

    class _Menus(NamedTuple):
        context: tk.Menu
        context_meta: tk.Menu
        columns: tk.Menu

    _menus: _Menus
    _col_vars: dict[str, tk.BooleanVar]

    def __init__(self, parent, ctx: UiContext, *args, **kw):
        super().__init__(
            parent,
            on_activate=ctx.actions.activate_path,
            on_select=ctx.actions.select_paths,
            columns=tuple(name for name, _ in _DATA_COLUMNS),
            sortable=False,
            width=300,
            **kw,
        )

        self._ctx = ctx
        self._context_path: str = ""

        # disable propogation to set a treeview total width wider than the frame
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.treeview.configure(selectmode=tk.EXTENDED)
        self.treeview.heading("#0", text="Path")
        self.treeview.heading("#1", text="Time")
        self.treeview.heading("#2", text="Res")
        self.treeview.heading("#3", text="Actors")
        self.treeview.heading("#4", text="Tags")
        self.treeview.column("#0", minwidth=100, width=280, stretch=False)
        self.treeview.column("#1", minwidth=10, width=50, stretch=False)
        self.treeview.column("#2", minwidth=10, width=70, stretch=False)
        self.treeview.column("#3", minwidth=10, width=100, stretch=False)
        self.treeview.column("#4", minwidth=10, width=100, stretch=False)
        self.treeview.tag_configure("highlight", background="#DFD")
        is_mac = self.winfo_toplevel().tk.call("tk", "windowingsystem") == "aqua"
        self.treeview.bind("<Button-2>" if is_mac else "<Button-3>", self._handle_right_click, add=True)

        ctxmenu = tk.Menu(self, tearoff=0)
        self._col_vars = {name: tk.BooleanVar(self, value=True) for name, _ in _DATA_COLUMNS}
        colmenu = tk.Menu(self, tearoff=0)
        for name, label in _DATA_COLUMNS:
            colmenu.add_checkbutton(
                label=label, variable=self._col_vars[name], command=partial(self._handle_toggle_column, name)
            )
        self._menus = __class__._Menus(
            context=ctxmenu,
            context_meta=tk.Menu(ctxmenu, tearoff=0),
            columns=colmenu,
        )
        self._menus.context.add_command(
            label="[info]", command=lambda: ctx.actions.show_in_explorer(Path(self._context_path))
        )
        self._menus.context.add_separator()
        self._menus.context.add_command(
            label="Refresh files", command=lambda: ctx.actions.rescan_path(Path(self._context_path))
        )
        self._menus.context.add_command(
            label="Refresh metadata", command=lambda: ctx.actions.scan_path_metadata(Path(self._context_path))
        )
        self._menus.context.add_separator()
        self._menus.context.add_cascade(label="Metadata...", menu=self._menus.context_meta)
        self._menus.context.add_separator()
        self._menus.context.add_command(label="Send to trash", command=self._handle_remove)

        self._menus.context_meta.add_command(
            label="Add actor", command=lambda: ctx.actions.edit_metadata(BulkAction.ADD_ACTOR, self._selected_paths())
        )
        self._menus.context_meta.add_command(
            label="Del actor", command=lambda: ctx.actions.edit_metadata(BulkAction.DEL_ACTOR, self._selected_paths())
        )
        self._menus.context_meta.add_command(
            label="Add tag", command=lambda: ctx.actions.edit_metadata(BulkAction.ADD_TAG, self._selected_paths())
        )
        self._menus.context_meta.add_command(
            label="Del tag", command=lambda: ctx.actions.edit_metadata(BulkAction.DEL_TAG, self._selected_paths())
        )
        self._menus.context_meta.add_command(
            label="Generate Thumbnails", command=lambda: ctx.actions.generate_thumbnails_bulk(self._selected_paths())
        )
        self._menus.context_meta.add_separator()
        self._menus.context_meta.add_command(
            label="Clean", command=lambda: ctx.actions.delete_metadata(self._selected_paths())
        )

        # a store-side event for the selected path renders the row from the snapshot, then once
        # more from the session restage; the duplicate render is idempotent and intentional
        ctx.state.stored_metadata_changed.connect(self._on_file_metadata)
        ctx.state.staged_metadata_changed.connect(self._on_file_metadata)
        ctx.state.file_tree_changed.connect(self._on_file_tree)
        ctx.state.paths_removed.connect(self._on_paths_removed)
        ctx.state.highlights_changed.connect(self._on_highlights)
        ctx.state.filters_changed.connect(self._on_filters)
        ctx.state.hidden_columns_changed.connect(self._on_columns_changed)

    def _on_file_metadata(self, change: FileMetadataChanged) -> None:
        props = change.metadata.get("video_properties", {})
        self.update_item_cols(
            str(change.path),
            props.get("duration", 0),
            props.get("dimensions", (0, 0)),
            change.metadata.get("actors", []),
            change.metadata.get("tags", []),
        )

    def _on_file_tree(self, update: FileTreeUpdate) -> None:
        self.fill_from_pathtree(update.tree, update.from_iid)

    def _on_paths_removed(self, change: PathsRemoved) -> None:
        self.remove_items([str(p) for p in change.paths])

    def _on_highlights(self, change: HighlightsChanged) -> None:
        self.highlight_by_metadata(change.actors, change.tags)

    def _on_filters(self, change: FiltersChanged) -> None:
        if not change.actors and not change.tags:
            self.unhide_all()
        else:
            self.apply_filters(change.actors, change.tags, operator=change.operator)

    def _on_columns_changed(self, change: ColumnsChanged) -> None:
        hidden = frozenset(change.hidden)
        for name, _ in _DATA_COLUMNS:
            self._col_vars[name].set(name not in hidden)

        # displaycolumns holds the visible data column ids; a column re-shown this way keeps its
        # width and returns to its original position since the subset is derived in stored order
        self.treeview.configure(displaycolumns=tuple(name for name, _ in _DATA_COLUMNS if name not in hidden))

    def _handle_right_click(self, ev: tk.Event) -> None:
        if self.treeview.identify("region", ev.x, ev.y) == "heading":
            try:
                self._menus.columns.tk_popup(ev.x_root, ev.y_root)
            finally:
                self._menus.columns.grab_release()
            return

        iid = self.treeview.identify_row(ev.y)
        if iid == "":
            return
        if not iid in self.treeview.selection():
            self.treeview.selection_set(iid)

        self._context_path = iid
        if len(self.treeview.selection()) == 1:
            item_display_text = ellipsize(Path(iid).name, 32)
            if self.treeview.tag_has("dir", iid):
                item_display_text = "[" + item_display_text + "]"
        else:
            item_display_text = f"<{len(self.treeview.selection())} items>"
        self._menus.context.entryconfigure(0, label=f"{item_display_text}")

        if not self.treeview.tag_has("dir", iid) or len(self.treeview.selection()) > 1:
            self._menus.context.entryconfigure(2, state=tk.DISABLED)
            self._menus.context.entryconfigure(3, state=tk.DISABLED)
        else:
            self._menus.context.entryconfigure(2, state=tk.ACTIVE)
            self._menus.context.entryconfigure(3, state=tk.ACTIVE)

        try:
            self._menus.context.tk_popup(ev.x_root, ev.y_root)
        finally:
            self._menus.context.grab_release()

    def _selected_paths(self) -> tuple[Path, ...]:
        return tuple(Path(iid) for iid in self.treeview.selection())

    def _shown_columns(self) -> set[str]:
        """the currently visible data column ids. until _on_columns_changed runs, the treeview
        displays its default #all, so every data column counts as shown."""
        disp = self.treeview.cget("displaycolumns")
        all_names = {name for name, _ in _DATA_COLUMNS}
        if isinstance(disp, str) or "#all" in disp:
            return set(all_names)

        return set(disp) & all_names

    def _handle_toggle_column(self, name: str) -> None:
        # the menu checkbutton state is owned by the checked/hidden state, which App echoes back
        # through hidden_columns_changed, so the toggle itself only requests the change
        shown = self._shown_columns()
        shown ^= {name}
        self._ctx.actions.set_columns_hidden(tuple(n for n, _ in _DATA_COLUMNS if n not in shown))

    def _handle_remove(self) -> None:
        if not self.treeview.selection():
            return

        self._ctx.actions.delete_paths(self._selected_paths())

    def remove_items(self, iids: Sequence[str]) -> None:
        existing = [iid for iid in iids if self.treeview.exists(iid)]
        if existing:
            self.treeview.delete(*existing)

    def update_item_cols(
        self, iid: str, duration: float, res: tuple[int, int], actors: StringListy, tags: StringListy
    ) -> None:
        if not self.child.exists(iid):
            return

        self.child.item(iid, values=(clock_format(duration), f"{res[0]}x{res[1]}", ", ".join(actors), ", ".join(tags)))

    def collapse_all(self) -> None:
        def _recurse(item: str):
            child = None
            for child in self.treeview.get_children(item):
                _recurse(child)
            if child:
                self.treeview.item(item, open=False)

        _recurse("")

    def apply_filters(
        self, actors: Sequence[str], tags: Sequence[str], operator: FilterOperator = FilterOperator.AND
    ) -> None:
        def _recurse(item):
            if self.treeview.tag_has("file", item):
                itemconfig = self.treeview.item(item)
                (item_actors, item_tags) = (
                    (
                        itemconfig["values"][2].split(", "),
                        itemconfig["values"][3].split(", "),
                    )
                    if len(itemconfig["values"])
                    else ([], [])
                )
                if operator == FilterOperator.AND:
                    if (actors and len(set(actors) & set(item_actors)) != len(actors)) or (
                        tags and len(set(tags) & set(item_tags)) != len(tags)
                    ):
                        self.hide(item)
                else:
                    if (actors and len(set(actors) & set(item_actors)) == 0) or (
                        tags and len(set(tags) & set(item_tags)) == 0
                    ):
                        self.hide(item)
            for child in self.treeview.get_children(item):
                _recurse(child)

        _recurse("")

    def highlight_by_metadata(self, actors: Sequence[str], tags: Sequence[str]) -> None:
        def _highlight_item(item: str, highlighted: bool, see: bool = False):
            itemconfig = self.treeview.item(item)
            if "highlight" in itemconfig["tags"] and not highlighted:
                cast(list, itemconfig["tags"]).remove("highlight")

            if "highlight" not in itemconfig["tags"] and highlighted:
                if isinstance(itemconfig["tags"], list):
                    itemconfig["tags"].append("highlight")
                else:
                    itemconfig["tags"] = ["highlight"]

            self.treeview.item(item, tags=itemconfig["tags"])

            if highlighted and see:
                self.treeview.see(item)

        def _recurse(item: str):
            highlighted = False
            if self.treeview.tag_has("file", item):
                itemconfig = self.treeview.item(item)
                (item_actors, item_tags) = (
                    (
                        set(itemconfig["values"][2].split(", ")),
                        set(itemconfig["values"][3].split(", ")),
                    )
                    if len(itemconfig["values"])
                    else (set(), set())
                )
                highlighted = any_in_list(set(actors), item_actors) or any_in_list(set(tags), item_tags)
                _highlight_item(item, highlighted, see=True)
            for child in self.treeview.get_children(item):
                _recurse(child)

        self.collapse_all()
        _recurse("")
