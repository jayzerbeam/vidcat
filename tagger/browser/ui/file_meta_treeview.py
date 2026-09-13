import tkinter as tk
from pathlib import Path
from typing import Any, NamedTuple, cast

from browser.ui.constants import TkVarNames, VirtualEventSequence
from ui.better_treeview import FileTreeviewFrame
from ui.constants import VirtualEventSequence as TKVES
from util.format import clock_format
from util.typing import StringListy


def any_in_list(s1: set, s2: set, case_sensitive: bool = False) -> bool:
    if not case_sensitive:
        s1 = set(map(str.lower, s1))
        s2 = set(map(str.lower, s2))

    return len(s1 & s2) > 0


class FileMetaTreeviewFrame(FileTreeviewFrame):
    """A FileTreeviewFrame that adds columns and functionality for actors and tags"""

    class _Menus(NamedTuple):
        dir: tk.Menu
        dir_scan: tk.Menu
        dir_thumb: tk.Menu
        file: tk.Menu
        file_meta: tk.Menu

    class __Vars(NamedTuple):
        actors: tk.Variable
        tags: tk.Variable
        selected_paths: tk.Variable

    _menu_iid: str | None
    _menus: _Menus
    _vars: __Vars

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, columns=("time", "res", "actors", "tags"), sortable=False, width=300, **kw)

        self._vars = __class__.__Vars(
            actors=tk.Variable(name=TkVarNames.HIGHLIGHTED_ACTORS),
            tags=tk.Variable(name=TkVarNames.HIGHLIGHTED_TAGS),
            selected_paths=tk.Variable(name=TkVarNames.SELECTED_PATHS),
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
        self.treeview.bind("<Button-2>" if is_mac else "<Button-3>", self._handle_right_click)
        self.treeview.bind(
            TKVES.TREEVIEW_SELECT,
            func=lambda ev: self._vars.selected_paths.set(self.treeview.selection()),
            add=True,
        )

        self._menu_iid = None
        self._menus = __class__._Menus(
            dir=tk.Menu(self, tearoff=0),
            dir_scan=tk.Menu(self, tearoff=0),
            dir_thumb=tk.Menu(self, tearoff=0),
            file=tk.Menu(self, tearoff=0),
            file_meta=tk.Menu(self, tearoff=0),
        )
        self._menus.dir_scan.add_command(
            label="Files",
            command=lambda: self.event_generate(VirtualEventSequence.SCAN_PATH_FILES, data=self._menu_iid),
        )
        self._menus.dir_scan.add_command(
            label="Video Metadata",
            command=lambda: self.event_generate(VirtualEventSequence.SCAN_PATH_METADATA, data=self._menu_iid),
        )
        self._menus.dir_thumb.add_command(
            label="missing",
            command=lambda: self.event_generate(VirtualEventSequence.GEN_MISSING_THUMBS, data=self._menu_iid),
        )
        self._menus.dir_thumb.add_command(
            label="missing (recursive)",
            command=lambda: self.event_generate(VirtualEventSequence.GEN_MISSING_THUMBS_RECURSIVE, data=self._menu_iid),
        )
        self._menus.dir_thumb.add_command(
            label="all",
            command=lambda: self.event_generate(VirtualEventSequence.GEN_ALL_THUMBS, data=self._menu_iid),
        )
        self._menus.dir_thumb.add_command(
            label="all (recursive)",
            command=lambda: self.event_generate(VirtualEventSequence.GEN_ALL_THUMBS_RECURSIVE, data=self._menu_iid),
        )

        self._menus.dir.add_cascade(label="Reload ...", menu=self._menus.dir_scan)
        self._menus.dir.add_cascade(label="Generate thumbnails ...", menu=self._menus.dir_thumb)
        self._menus.dir.add_separator()
        self._menus.dir.add_command(label="Trash", command=self._handle_remove)

        self._menus.file_meta.add_command(
            label="Add actor", command=lambda: self.event_generate(VirtualEventSequence.BULK_ADD_ACTOR)
        )
        self._menus.file_meta.add_command(
            label="Del actor", command=lambda: self.event_generate(VirtualEventSequence.BULK_DEL_ACTOR)
        )
        self._menus.file_meta.add_command(
            label="Add tag", command=lambda: self.event_generate(VirtualEventSequence.BULK_ADD_TAG)
        )
        self._menus.file_meta.add_command(
            label="Del tag", command=lambda: self.event_generate(VirtualEventSequence.BULK_DEL_TAG)
        )
        self._menus.file.add_cascade(label="Metadata ...", menu=self._menus.file_meta)
        self._menus.file.add_separator()
        self._menus.file.add_command(label="Trash", command=self._handle_remove)

    def _handle_right_click(self, ev: tk.Event) -> None:
        iid = self.treeview.identify_row(ev.y)
        if iid is None:
            return
        if not iid in self.treeview.selection():
            self.treeview.selection_set(iid)

        self._menu_iid = iid
        menu = None
        if self.treeview.tag_has("file", iid):
            self._menus.file.entryconfigure(2, label=f"Trash {Path(iid).name}")
            menu = self._menus.file
        elif self.treeview.tag_has("dir", iid):
            self._menus.dir.entryconfigure(3, label=f"Trash {Path(iid).name}")
            menu = self._menus.dir

        if menu is not None:
            try:
                menu.tk_popup(ev.x_root, ev.y_root)
            finally:
                menu.grab_release()

    def _handle_remove(self):
        if self._menu_iid is not None:
            self.event_generate(VirtualEventSequence.PATH_DELETE, data=self._menu_iid)
            self.treeview.delete(self._menu_iid)
            self._menu_iid = None

    def set_meta_column_vals(
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
