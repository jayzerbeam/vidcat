import tkinter as tk
from pathlib import Path
from typing import Any, NamedTuple, cast

from browser.ui.constants import TkVarNames, VirtualEventSequence
from ui.better_treeview import FileTreeviewFrame
from ui.constants import VirtualEventSequence as TKVES
from util.format import clock_format, ellipsize
from util.typing import StringListy


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

    class __Vars(NamedTuple):
        actors: tk.Variable
        tags: tk.Variable
        triggered_iid: tk.StringVar
        context_iid: tk.StringVar
        selected_iids: tk.Variable

    _menus: _Menus
    _vars: __Vars

    def __init__(self, parent, *args, **kw):
        aiid = tk.StringVar(name=TkVarNames.TRIGGERED_IID)
        super().__init__(
            parent,
            *args,
            triggered_iid_var=aiid,
            columns=("time", "res", "actors", "tags"),
            sortable=False,
            width=300,
            **kw,
        )

        self._vars = __class__.__Vars(
            actors=tk.Variable(name=TkVarNames.HIGHLIGHTED_ACTORS),
            tags=tk.Variable(name=TkVarNames.HIGHLIGHTED_TAGS),
            triggered_iid=aiid,
            context_iid=tk.StringVar(name=TkVarNames.CONTEXT_IID),
            selected_iids=tk.Variable(name=TkVarNames.SELECTED_IIDS),
        )
        self._vars.actors.trace_add(mode="write", callback=self.highlight_by_metadata)
        self._vars.tags.trace_add(mode="write", callback=self.highlight_by_metadata)

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
        self.treeview.bind(
            TKVES.TREEVIEW_SELECT, func=lambda ev: self._vars.selected_iids.set(self.treeview.selection()), add=True
        )

        ctxmenu = tk.Menu(self, tearoff=0)
        self._menus = __class__._Menus(
            context=ctxmenu,
            context_meta=tk.Menu(ctxmenu, tearoff=0),
        )
        self._menus.context.add_command(label="[info]")
        self._menus.context.add_separator()
        self._menus.context.add_command(
            label="Refresh files", command=lambda: self.event_generate(VirtualEventSequence.SCAN_PATH_FILES)
        )
        self._menus.context.add_command(
            label="Refresh metadata", command=lambda: self.event_generate(VirtualEventSequence.SCAN_PATH_METADATA)
        )
        self._menus.context.add_separator()
        self._menus.context.add_cascade(label="Metadata...", menu=self._menus.context_meta)
        self._menus.context.add_separator()
        self._menus.context.add_command(label="Send to trash", command=self._handle_remove)

        self._menus.context_meta.add_command(
            label="Add actor", command=lambda: self.event_generate(VirtualEventSequence.BULK_ADD_ACTOR)
        )
        self._menus.context_meta.add_command(
            label="Del actor", command=lambda: self.event_generate(VirtualEventSequence.BULK_DEL_ACTOR)
        )
        self._menus.context_meta.add_command(
            label="Add tag", command=lambda: self.event_generate(VirtualEventSequence.BULK_ADD_TAG)
        )
        self._menus.context_meta.add_command(
            label="Del tag", command=lambda: self.event_generate(VirtualEventSequence.BULK_DEL_TAG)
        )
        self._menus.context_meta.add_command(
            label="Generate Thumbnails", command=lambda: self.event_generate(VirtualEventSequence.BULK_GEN_THUMBS)
        )
        self._menus.context_meta.add_separator()
        self._menus.context_meta.add_command(
            label="Clean", command=lambda: self.event_generate(VirtualEventSequence.BULK_DEL_METADATA)
        )

    def _handle_right_click(self, ev: tk.Event) -> None:
        iid = self.treeview.identify_row(ev.y)
        if iid == "":
            return
        if not iid in self.treeview.selection():
            self.treeview.selection_set(iid)
            self._vars.selected_iids.set(self.treeview.selection())

        self._vars.context_iid.set(iid)
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

    def _handle_remove(self):
        if len(self.treeview.selection()) == 0:
            return

        self._vars.selected_iids.set(self.treeview.selection())
        self.event_generate(VirtualEventSequence.PATH_DELETE)
        while len(self.treeview.selection()) > 0:
            iid = self.treeview.selection()[0]
            self.treeview.delete(iid)

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

    def apply_filters(self, actors: StringListy, tags: StringListy, operator: str = "AND") -> None:
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
                if operator == "AND":
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

    # def apply_highlight(self, actors: StringListy, tags: StringListy):
    def highlight_by_metadata(self, *args: Any) -> None:
        actors = self.winfo_toplevel().tk.splitlist(self._vars.actors.get())
        tags = self.winfo_toplevel().tk.splitlist(self._vars.tags.get())

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
